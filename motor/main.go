// archiva-rede: motor de rede do Archiva (modo Nuvem, 2.0).
//
// Leva a biblioteca de um computador até outro pela internet, sem instalar VPN, serviço ou driver:
// o Tailscale vem embutido (tsnet, licença BSD-3) e roda dentro deste processo, sem administrador.
//
//	servir: publica o servidor local do Archiva (127.0.0.1:<porta>) na rede, na porta 80.
//	ligar:  abre 127.0.0.1:<porta> neste PC; tudo o que chega lá vai para a biblioteca de outro PC.
//
// Conversa com o Archiva:
//   - a 1ª linha da saída é um JSON com os endereços locais ({"controle": "...", "local": "..."});
//   - GET  http://<controle>/estado  -> estado da conexão (precisa entrar? link de login, nome na rede…);
//   - POST http://<controle>/sair    -> desconecta a conta deste PC;
//   - quando a entrada padrão fecha (o Archiva fechou ou caiu), o motor termina sozinho.
//
// A chave de autenticação de um convite chega pela variável ARCHIVA_AUTHKEY (não aparece na lista de processos).
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"

	"tailscale.com/tsnet"
)

type estado struct {
	Estado   string   `json:"estado"`            // Running, NeedsLogin, Starting, NoState, Stopped...
	URLLogin string   `json:"url_login"`         // link para entrar (quando Estado = NeedsLogin)
	Nome     string   `json:"nome"`              // nome deste PC na rede
	DNS      string   `json:"dns"`               // nome completo (MagicDNS)
	IPs      []string `json:"ips"`               //
	Rede     string   `json:"rede"`              // nome da rede (tailnet)
	AlvoOK   *bool    `json:"alvo_ok,omitempty"` // modo ligar: o PC da biblioteca está na rede?
	Erro     string   `json:"erro,omitempty"`    //
	Versao   string   `json:"versao"`            // versão do motor
	Pares    []par    `json:"pares,omitempty"`   // computadores que este PC enxerga na rede
	Avisos   []string `json:"avisos,omitempty"`  // avisos de saúde do Tailscale (ex.: sem acesso ao servidor)
	Segundos int      `json:"segundos"`          // há quanto tempo o motor está ligado
}

type par struct {
	Nome   string `json:"nome"`
	DNS    string `json:"dns"`
	Online bool   `json:"online"`
	Via    string `json:"via,omitempty"` // direto, retransmissão (DERP) ou vazio
}

const versaoMotor = "2"

var inicio = time.Now()

var (
	mu         sync.Mutex
	ultimaURL  string
	ultimoErro string
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "uso: archiva-rede servir|ligar [opções]")
		os.Exit(2)
	}
	modo := os.Args[1]
	fs := flag.NewFlagSet(modo, flag.ExitOnError)
	dir := fs.String("dir", "", "pasta do estado (identidade deste PC na rede)")
	nome := fs.String("nome", "archiva", "nome deste PC na rede")
	destino := fs.String("destino", "", "servir: endereço do servidor do Archiva (127.0.0.1:porta)")
	alvo := fs.String("alvo", "", "ligar: nome do PC da biblioteca na rede")
	local := fs.String("local", "127.0.0.1:0", "ligar: endereço local")
	controle := fs.String("controle", "127.0.0.1:0", "endereço do controle")
	fs.Parse(os.Args[2:])
	if *dir == "" {
		log.Fatal("--dir é obrigatório")
	}
	if err := os.MkdirAll(*dir, 0o700); err != nil {
		log.Fatal(err)
	}

	srv := &tsnet.Server{
		Dir:       *dir,
		Hostname:  *nome,
		AuthKey:   os.Getenv("ARCHIVA_AUTHKEY"),
		Ephemeral: false,
		Logf:      func(string, ...any) {},
		UserLogf: func(f string, a ...any) {
			s := fmt.Sprintf(f, a...)
			if i := strings.Index(s, "https://login.tailscale.com/"); i >= 0 {
				mu.Lock()
				ultimaURL = strings.Fields(s[i:])[0]
				mu.Unlock()
			}
		},
	}
	if err := srv.Start(); err != nil {
		log.Fatal(err)
	}
	defer srv.Close()

	ctl, err := net.Listen("tcp", *controle)
	if err != nil {
		log.Fatal(err)
	}
	saida := map[string]string{"controle": ctl.Addr().String()}

	switch modo {
	case "servir":
		if *destino == "" {
			log.Fatal("--destino é obrigatório")
		}
		go servir(srv, *destino)
	case "ligar":
		if *alvo == "" {
			log.Fatal("--alvo é obrigatório")
		}
		ln, err := net.Listen("tcp", *local)
		if err != nil {
			log.Fatal(err)
		}
		saida["local"] = ln.Addr().String()
		go ligar(srv, ln, *alvo)
	default:
		log.Fatalf("modo desconhecido: %s", modo)
	}

	go controlar(srv, ctl, modo, *alvo)
	b, _ := json.Marshal(saida)
	fmt.Println(string(b))
	os.Stdout.Sync()

	// termina quando o Archiva fecha (a entrada padrão é fechada)
	io.Copy(io.Discard, os.Stdin)
}

// ------------------------------------------------------------------ servir

func servir(srv *tsnet.Server, destino string) {
	alvo, _ := url.Parse("http://" + destino)
	proxy := httputil.NewSingleHostReverseProxy(alvo)
	proxy.FlushInterval = 100 * time.Millisecond
	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		http.Error(w, `{"erro":"o Archiva deste computador não está compartilhando agora"}`, http.StatusServiceUnavailable)
	}
	for {
		ln, err := srv.Listen("tcp", ":80")
		if err != nil {
			anotarErro(err)
			time.Sleep(3 * time.Second)
			continue
		}
		s := &http.Server{Handler: proxy, ReadHeaderTimeout: 30 * time.Second}
		err = s.Serve(ln)
		anotarErro(err)
		time.Sleep(time.Second)
	}
}

// ------------------------------------------------------------------ ligar

func ligar(srv *tsnet.Server, ln net.Listener, alvo string) {
	resolver := &resolvedor{srv: srv, alvo: alvo}
	proxy := &httputil.ReverseProxy{
		Rewrite: func(pr *httputil.ProxyRequest) {
			pr.Out.URL.Scheme = "http"
			pr.Out.URL.Host = alvo
			pr.Out.Host = alvo
		},
		Transport: &http.Transport{
			DialContext: func(ctx context.Context, network, addr string) (net.Conn, error) {
				ip, err := resolver.ip(ctx)
				if err != nil {
					return nil, err
				}
				// ctx é o do pedido (cancelado quando o Archiva desiste); não encurtar aqui: cancelar o contexto
				// depois de conectar poderia derrubar a conexão
				return srv.Dial(ctx, "tcp", net.JoinHostPort(ip, "80"))
			},
			MaxIdleConnsPerHost:   8,
			IdleConnTimeout:       90 * time.Second,
			ResponseHeaderTimeout: 60 * time.Second,
		},
		FlushInterval: 100 * time.Millisecond,
		ErrorHandler: func(w http.ResponseWriter, r *http.Request, err error) {
			resolver.esquecer()
			http.Error(w, `{"erro":"o computador da biblioteca não respondeu"}`, http.StatusBadGateway)
		},
	}
	s := &http.Server{Handler: proxy, ReadHeaderTimeout: 30 * time.Second}
	anotarErro(s.Serve(ln))
}

type resolvedor struct {
	srv    *tsnet.Server
	alvo   string
	mu     sync.Mutex
	ipC    string
	quando time.Time
}

func (r *resolvedor) esquecer() {
	r.mu.Lock()
	r.ipC = ""
	r.mu.Unlock()
}

// ip procura o PC da biblioteca entre os da rede (pelo nome), sem depender do DNS do sistema.
func (r *resolvedor) ip(ctx context.Context) (string, error) {
	r.mu.Lock()
	if r.ipC != "" && time.Since(r.quando) < 5*time.Minute {
		ip := r.ipC
		r.mu.Unlock()
		return ip, nil
	}
	r.mu.Unlock()
	lc, err := r.srv.LocalClient()
	if err != nil {
		return "", err
	}
	st, err := lc.Status(ctx)
	if err != nil {
		return "", err
	}
	quer := strings.ToLower(r.alvo)
	for _, p := range st.Peer {
		dns := strings.ToLower(strings.TrimSuffix(p.DNSName, "."))
		curto := strings.SplitN(dns, ".", 2)[0]
		if strings.ToLower(p.HostName) == quer || curto == quer || dns == quer {
			if len(p.TailscaleIPs) > 0 {
				ip := p.TailscaleIPs[0].String()
				r.mu.Lock()
				r.ipC, r.quando = ip, time.Now()
				r.mu.Unlock()
				return ip, nil
			}
		}
	}
	return "", errors.New("o computador da biblioteca não está na rede")
}

// ------------------------------------------------------------------ controle

func controlar(srv *tsnet.Server, ln net.Listener, modo, alvo string) {
	mux := http.NewServeMux()
	mux.HandleFunc("/estado", func(w http.ResponseWriter, r *http.Request) {
		ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
		defer cancel()
		e := estado{Versao: versaoMotor, Segundos: int(time.Since(inicio).Seconds())}
		lc, err := srv.LocalClient()
		if err == nil {
			st, err2 := lc.Status(ctx)
			if err2 == nil {
				e.Estado = st.BackendState
				e.URLLogin = st.AuthURL
				if st.Self != nil {
					e.Nome = st.Self.HostName
					e.DNS = strings.TrimSuffix(st.Self.DNSName, ".")
					for _, ip := range st.Self.TailscaleIPs {
						e.IPs = append(e.IPs, ip.String())
					}
				}
				if st.CurrentTailnet != nil {
					e.Rede = st.CurrentTailnet.Name
				}
				e.Avisos = append(e.Avisos, st.Health...)
				for _, p := range st.Peer {
					via := ""
					if p.CurAddr != "" {
						via = "direto"
					} else if p.Relay != "" {
						via = "retransmissão " + p.Relay
					}
					e.Pares = append(e.Pares, par{Nome: p.HostName, DNS: strings.TrimSuffix(p.DNSName, "."), Online: p.Online, Via: via})
				}
				if modo == "ligar" && st.BackendState == "Running" {
					ok := false
					quer := strings.ToLower(alvo)
					for _, p := range st.Peer {
						curto := strings.SplitN(strings.ToLower(p.DNSName), ".", 2)[0]
						if strings.ToLower(p.HostName) == quer || curto == quer {
							ok = p.Online
							break
						}
					}
					e.AlvoOK = &ok
				}
			} else {
				err = err2
			}
		}
		mu.Lock()
		if e.URLLogin == "" {
			e.URLLogin = ultimaURL
		}
		if err != nil {
			e.Erro = err.Error()
		} else if ultimoErro != "" {
			e.Erro = ultimoErro
		}
		mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(e)
	})
	mux.HandleFunc("/teste", func(w http.ResponseWriter, r *http.Request) {
		// modo ligar: tenta chegar ao Archiva do outro computador e conta o tempo de cada passo
		res := map[string]any{}
		ctx, cancel := context.WithTimeout(r.Context(), 40*time.Second)
		defer cancel()
		resolver := &resolvedor{srv: srv, alvo: alvo}
		t0 := time.Now()
		ip, err := resolver.ip(ctx)
		res["procurar_ms"] = time.Since(t0).Milliseconds()
		if err != nil {
			res["erro"] = "procurar: " + err.Error()
		} else {
			res["ip"] = ip
			t1 := time.Now()
			dctx, c2 := context.WithTimeout(ctx, 20*time.Second)
			conn, err := srv.Dial(dctx, "tcp", net.JoinHostPort(ip, "80"))
			c2()
			res["conectar_ms"] = time.Since(t1).Milliseconds()
			if err != nil {
				res["erro"] = "conectar: " + err.Error()
			} else {
				conn.Close()
				t2 := time.Now()
				cli := srv.HTTPClient()
				cli.Timeout = 15 * time.Second
				resp, err := cli.Get("http://" + ip + "/api/info")
				res["pedido_ms"] = time.Since(t2).Milliseconds()
				if err != nil {
					res["erro"] = "pedido: " + err.Error()
				} else {
					res["http"] = resp.StatusCode
					resp.Body.Close()
				}
			}
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(res)
	})
	mux.HandleFunc("/sair", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "use POST", http.StatusMethodNotAllowed)
			return
		}
		lc, err := srv.LocalClient()
		if err == nil {
			err = lc.Logout(r.Context())
		}
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.Write([]byte(`{"ok":true}`))
	})
	http.Serve(ln, mux)
}

func anotarErro(err error) {
	if err == nil {
		return
	}
	mu.Lock()
	ultimoErro = err.Error()
	mu.Unlock()
}
