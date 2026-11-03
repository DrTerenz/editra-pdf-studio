"""Avvio dell'applicazione."""
from __future__ import annotations

import logging
import os
import sys
import traceback

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_ID, APP_NAME, ORG, VERSION
from .i18n import T

SERVER_NAME = f"{APP_ID}-{os.environ.get('USERNAME', 'utente')}"


def _send_to_running(paths: list[str]) -> bool:
    """Se l'app è già aperta le passa i file e ritorna True."""
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(400):
        return False
    payload = "\n".join(os.path.abspath(p) for p in paths) or "__show__"
    sock.write(QByteArray(payload.encode("utf-8")))
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


def _excepthook(exc_type, exc, tb):
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    try:
        from .settings import app_data_dir
        with open(os.path.join(app_data_dir(), "errori.log"), "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass
    sys.__stderr__ and sys.__stderr__.write(text)
    app = QApplication.instance()
    if app is not None:
        QMessageBox.critical(None, APP_NAME, T('Si è verificato un errore imprevisto:\n\n{}\n\nIl documento aperto non è stato perso: salva con un nuovo nome se necessario. Dettagli in errori.log.').format(exc))


def self_test(out_path: str, pdf: str | None) -> int:
    """Verifica che il programma installato contenga tutti i componenti (uso interno)."""
    lines = []

    def step(name, fn):
        try:
            r = fn()
            lines.append(T('OK   {}').format(name) + (f": {r}" if r not in (None, True) else ""))
        except Exception as ex:
            lines.append(T('FAIL {}: {}: {}').format(name, type(ex).__name__, ex))

    import pymupdf
    step("pymupdf", lambda: pymupdf.VersionFitz)
    step(T('fonts di sistema'), lambda: len(__import__("editra.fonts", fromlist=["x"]).system_fonts()))
    step(T('ocr windows'), lambda: __import__("editra.ops.ocr", fromlist=["x"]).languages())
    step(T('firme (pyhanko)'), lambda: bool(__import__("pyhanko.sign.validation", fromlist=["x"])))
    step(T('word (pdf2docx)'), lambda: bool(__import__("pdf2docx", fromlist=["Converter"]).Converter))
    step(T('excel (openpyxl)'), lambda: bool(__import__("openpyxl")))
    step("crittografia", lambda: bool(__import__("cryptography.hazmat.primitives.serialization.pkcs12", fromlist=["x"])))
    step("stampa", lambda: bool(__import__("PySide6.QtPrintSupport", fromlist=["x"]).QPrinter))
    step(T('sintesi vocale'), lambda: __import__("PySide6.QtTextToSpeech", fromlist=["x"]).QTextToSpeech.availableEngines())
    if pdf:
        from .ops import convert as CV, ocr as O, signatures as SG
        import tempfile
        tmp = tempfile.mkdtemp()

        def ocr_run():
            d = pymupdf.open(pdf)
            pix = d[0].get_pixmap(dpi=150)
            d2 = pymupdf.open()
            p2 = d2.new_page()
            p2.insert_image(p2.rect, pixmap=pix)
            return O.ocr_page(p2, None, 200)
        step(T('ocr su pagina'), ocr_run)
        step(T('export word'), lambda: CV.to_word(open(pdf, "rb").read(), os.path.join(tmp, "x.docx")) or
             os.path.getsize(os.path.join(tmp, "x.docx")))
        step(T('export excel'), lambda: CV.to_excel(pymupdf.open(pdf), os.path.join(tmp, "x.xlsx")))

        def sign_run():
            pfx = os.path.join(tmp, "id.pfx")
            SG.create_self_signed_id(pfx, "pw12", T('Prova'))
            signed = SG.sign_pdf(open(pdf, "rb").read(), SG.SignRequest(pfx, "pw12", "F1", 0, (50, 50, 250, 110)), 842)
            return SG.verify_pdf(signed)[0].status
        step(T('firma e verifica'), sign_run)
    from .mainwindow import MainWindow
    step("finestra", lambda: MainWindow() and True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0 if all(l.startswith("OK") for l in lines) else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    files = [a for a in argv[1:] if not a.startswith("-")] if "--self-test" not in argv else []
    logging.getLogger("pyhanko").setLevel(logging.CRITICAL)
    logging.getLogger("pyhanko_certvalidator").setLevel(logging.CRITICAL)
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{ORG}.{APP_ID}.{VERSION}")
    except Exception:
        pass
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG)
    app.setApplicationVersion(VERSION)
    # traduzioni dei testi standard di Qt (pulsanti Sì/No, dialoghi colore e stampa...)
    from PySide6.QtCore import QLibraryInfo, QTranslator
    from . import i18n
    qt_tr = QTranslator(app)
    if qt_tr.load(f"qtbase_{i18n.LANG}", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(qt_tr)

    if "--self-test" in argv:
        i = argv.index("--self-test")
        out = argv[i + 1]
        pdf = argv[i + 2] if len(argv) > i + 2 else None
        from . import theme
        theme.apply(app, "light")
        return self_test(out, pdf)

    if "--new-instance" not in argv and _send_to_running(files):
        return 0

    from . import icons, settings, theme
    from .mainwindow import MainWindow
    theme.apply(app, settings.get("theme", "light"))
    app.setWindowIcon(icons.app_icon())
    sys.excepthook = _excepthook

    win = MainWindow()
    win.apply_theme(settings.get("theme", "light"))

    server = QLocalServer()
    QLocalServer.removeServer(SERVER_NAME)
    server.listen(SERVER_NAME)

    def on_conn():
        s = server.nextPendingConnection()
        if s is None:
            return

        def read():
            data = bytes(s.readAll()).decode("utf-8", "replace")
            paths = [p for p in data.splitlines() if p and p != "__show__"]
            if win.isMinimized():
                win.showNormal()
            win.raise_()
            win.activateWindow()
            if paths:
                win.open_files(paths)
        s.readyRead.connect(read)
    server.newConnection.connect(on_conn)

    win.show()
    if files:
        QTimer.singleShot(0, lambda: win.open_files(files))
    elif settings.get("restore_session", False, bool):
        sess = settings.get("session", []) or []
        if isinstance(sess, str):
            sess = [sess]
        sess = [p for p in sess if os.path.exists(p)]
        if sess:
            QTimer.singleShot(0, lambda: win.open_files(sess))
    return app.exec()
