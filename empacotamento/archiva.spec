# PyInstaller — gera dist\Archiva\Archiva.exe (pasta, sem console).
# Rodar a partir da raiz do repositório:  pyinstaller empacotamento\archiva.spec --noconfirm
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [
    (os.path.join(ROOT, "VERSION"), "."),
    (os.path.join(ROOT, "LEIA-ME.txt"), "."),
]
rec = os.path.join(ROOT, "app", "recursos")
for dirpath, _dirs, files in os.walk(rec):
    for f in files:
        if f.lower() == "archiva-logo.ttf":      # o logotipo vai como desenho (logo.json), não como fonte
            continue
        rel = os.path.relpath(dirpath, ROOT)
        datas.append((os.path.join(dirpath, f), rel))

# módulos do Qt que o Archiva não usa (deixa o instalador bem menor)
EXCLUDES = [
    "tkinter", "unittest", "pydoc_data",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtSql",
    "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtSerialPort", "PySide6.QtSensors", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
    "PySide6.QtTextToSpeech", "PySide6.QtWebSockets", "PySide6.QtWebChannel", "PySide6.QtNetworkAuth",
    "PySide6.QtLocation", "PySide6.QtGraphs", "PySide6.QtSpatialAudio",
]

a = Analysis(
    [os.path.join(ROOT, "gerenciador.pyw")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=["PySide6.QtSvg"],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Archiva",
    console=False,
    icon=os.path.join(rec, "icone.ico"),
    version=os.path.join(SPECPATH, "versao_exe.txt") if os.path.exists(os.path.join(SPECPATH, "versao_exe.txt")) else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Archiva", upx=False)
