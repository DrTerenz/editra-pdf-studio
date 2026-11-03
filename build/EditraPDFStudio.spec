# Specifica PyInstaller di Editra PDF Studio (cartella unica, senza console).
# Uso: .venv\Scripts\pyinstaller.exe build\EditraPDFStudio.spec --noconfirm --distpath dist --workpath build\tmp
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas, binaries, hidden = [], [], []
for pkg in ("pyhanko", "pyhanko_certvalidator", "pdf2docx"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hidden += h
hidden += collect_submodules("winrt")
hidden += ["PySide6.QtTextToSpeech", "PySide6.QtPrintSupport", "PySide6.QtNetwork", "openpyxl",
           "cryptography.hazmat.primitives.serialization.pkcs12", "tzlocal"]

excludes = [
    "tkinter", "matplotlib", "IPython", "pytest", "notebook", "pandas", "scipy",
    "onnxruntime", "pymupdf4llm", "pymupdf_layout", "networkx",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtWebSockets", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSql", "PySide6.QtBluetooth",
    "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSensors", "PySide6.QtSerialPort",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtHttpServer",
    "PySide6.QtTest", "PySide6.QtUiTools", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSvgWidgets",
]

a = Analysis(
    [os.path.join(ROOT, "EditraPDFStudio.pyw")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    excludes=excludes,
    noarchive=False,
)
# file inutili per questa app (video, OpenGL software, modulo PDF di Qt)
_drop = ("opencv_videoio_ffmpeg", "opengl32sw", "Qt6Pdf", "Qt6Quick", "Qt6Qml", "Qt6VirtualKeyboard")
a.binaries = [b for b in a.binaries if not any(k.lower() in os.path.basename(b[0]).lower() for k in _drop)]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EditraPDFStudio",
    icon=os.path.join(SPECPATH, "EditraPDFStudio.ico"),
    version=os.path.join(SPECPATH, "version_info.txt"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="EditraPDFStudio")
