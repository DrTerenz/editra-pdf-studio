"""Collaudo dell'interfaccia: comandi, strumenti col mouse, editor in linea.

Uso: python tests/test_gui.py <cartella_di_lavoro> <pdf_di_prova>
I dialoghi vengono sostituiti da risposte automatiche; ogni messaggio di errore
mostrato all'utente viene registrato come fallimento.
"""
import os
import shutil
import sys
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORK, SAMPLE = sys.argv[1], sys.argv[2]
os.makedirs(WORK, exist_ok=True)
os.environ["APPDATA"] = os.path.join(WORK, "appdata")

import pymupdf
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QInputDialog, QMessageBox

app = QApplication(sys.argv)
from editra import dialogs as D, theme
from editra import mainwindow as MW
from editra.ops.common import TEXT_FLAGS

errors = []
results = []
answers = {}           # titolo dialogo -> dict di valori
file_answers = []      # coda di percorsi per i dialoghi di file


def check(name, cond, info=""):
    results.append((name, bool(cond), info))
    print(("OK   " if cond else "FAIL ") + name + (f"  [{info}]" if info and not cond else ""))


# ----------------------------------------------------------- dialoghi finti
def fake_ask(parent, title, fields, intro="", ok_text="OK", width=460):
    vals = {}
    for f in fields:
        key, typ = f[0], f[2]
        default = f[3] if len(f) > 3 else None
        opt = f[4] if len(f) > 4 else None
        if typ == "choice":
            vals[key] = default if default is not None else (opt[0][1] if isinstance(opt[0], tuple) else opt[0])
        elif typ in ("section", "label"):
            continue
        else:
            vals[key] = default
    # le risposte sono indicate con il titolo italiano anche quando l'interfaccia è in inglese
    from editra.lang.en import STRINGS
    italian = {v: k for k, v in STRINGS.items()}
    vals.update(answers.get(italian.get(title, title), answers.get(title, {})))
    return vals


# nessun programma esterno deve aprirsi durante il collaudo
opened = []
os.startfile = lambda path, *a, **k: opened.append(path)
D.ask = fake_ask
MW.D.ask = fake_ask


def next_file(*a, **k):
    p = file_answers.pop(0) if file_answers else ""
    return p, ""


def next_files(*a, **k):
    p = file_answers.pop(0) if file_answers else []
    return (p if isinstance(p, list) else [p]), ""


QFileDialog.getOpenFileName = staticmethod(next_file)
QFileDialog.getSaveFileName = staticmethod(next_file)
QFileDialog.getOpenFileNames = staticmethod(next_files)
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: file_answers.pop(0) if file_answers else "")
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)


def _warn(parent, title, text, *a, **k):
    if a or k:
        return QMessageBox.Yes   # avviso con pulsanti Sì/No: è una conferma, non un errore
    errors.append(f"{title}: {text}")
    print("   !! messaggio:", title, "-", str(text)[:300])
    return QMessageBox.Yes


QMessageBox.warning = staticmethod(_warn)
QMessageBox.critical = staticmethod(_warn)
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QInputDialog.getText = staticmethod(lambda *a, **k: ("Testo di prova", True))
QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("Nota multilinea", True))
QInputDialog.getInt = staticmethod(lambda *a, **k: (2, True))
D.ReportDialog.exec = lambda self: 0
D.PropertiesDialog.exec = lambda self: QDialog.Accepted
D.MergeDialog.exec = lambda self: QDialog.Accepted
D.CompressDialog.exec = lambda self: QDialog.Accepted
D.EncryptDialog.exec = lambda self: QDialog.Accepted
D.SignaturePicker.exec = lambda self: QDialog.Accepted


def run(label, fn):
    n = len(errors)
    try:
        fn()
        app.processEvents()
    except Exception as ex:
        traceback.print_exc()
        check(label, False, repr(ex))
        return
    check(label, len(errors) == n, "; ".join(errors[n:])[:300])


# ---------------------------------------------------------------- avvio
theme.apply(app, "light")
win = MW.MainWindow()
win.apply_theme("light")
win.resize(1400, 900)
win.show()
app.processEvents()
shutil.copy(SAMPLE, os.path.join(WORK, "doc.pdf"))
DOC = os.path.join(WORK, "doc.pdf")
win.open_files([DOC])
app.processEvents()
QTest.qWait(200)
check("documento aperto", win.model() is not None and win.model().page_count == 4)
v = win.view()
m = win.model()
v.set_fit("width")
QTest.qWait(100)
app.processEvents()
win.grab().save(os.path.join(WORK, "screen_1_aperto.png"))


def vp(idx, x, y):
    """Punto della vista (coordinate pagina come appare) -> punto del viewport."""
    it = v.items[idx]
    sp = it.pos() + QPointF(x, y) * v.scale_px
    return v.mapFromScene(sp)


def show_page(idx, y=0):
    v.go_to_page(idx, y_pt=y)
    app.processEvents()


def drag(p0, p1, steps=6, mod=Qt.NoModifier):
    vpw = v.viewport()
    QTest.mousePress(vpw, Qt.LeftButton, mod, p0)
    for k in range(1, steps + 1):
        pt = QPoint(p0.x() + (p1.x() - p0.x()) * k // steps, p0.y() + (p1.y() - p0.y()) * k // steps)
        QTest.mouseMove(vpw, pt)
    QTest.mouseRelease(vpw, Qt.LeftButton, mod, p1)
    app.processEvents()


def click(p, double=False):
    if double:
        QTest.mouseDClick(v.viewport(), Qt.LeftButton, Qt.NoModifier, p)
    else:
        QTest.mouseClick(v.viewport(), Qt.LeftButton, Qt.NoModifier, p)
    app.processEvents()


_pages_alive = []


def annots(idx):
    page = m.page(idx)
    _pages_alive.append(page)   # le annotazioni restano valide solo finché la pagina esiste
    return list(page.annots())


# ------------------------------------------------------- visualizzazione
def t_view():
    for mode in ("single", "two", "two_cover", "continuous"):
        v.set_layout(mode)
        app.processEvents()
    v.set_zoom(2.0)
    v.zoom_in()
    v.zoom_out()
    v.set_fit("page")
    v.set_fit("width")
    v.next_page()
    v.prev_page()
    v.go_to_page(3)
    v.go_to_page(0)
    win.toggle_night() if False else None
    v.set_night(True)
    v.set_night(False)
    win.actions["dark_theme"].setChecked(True)
    win.toggle_theme()
    win.grab().save(os.path.join(WORK, "screen_2_scuro.png"))
    win.actions["dark_theme"].setChecked(False)
    win.toggle_theme()
    for key in ("thumbs", "bookmarks", "comments", "search", "attachments", "signatures", "layers"):
        win.tab().show_panel(key)
        app.processEvents()
    win.tab().show_panel("thumbs")
    win._chrome(False)
    win._chrome(True)


run("visualizzazione", t_view)


# -------------------------------------------------------- selezione testo
def t_select_text():
    win.set_tool("select")
    show_page(0)
    drag(vp(0, 75, 105), vp(0, 300, 125))
    check("testo selezionato", "paragrafo" in v.sel_text, repr(v.sel_text))
    v.copy_selection()
    check("copia negli appunti", "paragrafo" in QApplication.clipboard().text())
    n = len(annots(0))
    v.markup_selection("highlight")
    check("evidenzia selezione", len(annots(0)) == n + 1)


run("selezione testo", t_select_text)


def t_markup_tools():
    for tool in ("underline", "strike", "squiggly", "highlight"):
        win.set_tool(tool)
        n = len(annots(1))
        show_page(1)
        drag(vp(1, 75, 245), vp(1, 300, 250))
        check(f"strumento {tool}", len(annots(1)) == n + 1, str(len(annots(1))))
    # evidenziazione di un'area senza testo
    win.set_tool("highlight")
    n = len(annots(1))
    drag(vp(1, 300, 420), vp(1, 450, 480))
    check("evidenzia area", len(annots(1)) == n + 1)


run("strumenti di marcatura", t_markup_tools)


def t_shapes():
    show_page(2)
    for tool, a, b in (("rect", (300, 300), (400, 360)), ("ellipse", (300, 380), (400, 430)),
                       ("line", (100, 600), (250, 650)), ("arrow", (100, 660), (250, 700)),
                       ("measure", (100, 720), (300, 720))):
        win.set_tool(tool)
        n = len(annots(2))
        drag(vp(2, *a), vp(2, *b))
        check(f"forma {tool}", len(annots(2)) > n)
    win.set_tool("ink")
    n = len(annots(2))
    drag(vp(2, 400, 600), vp(2, 500, 680))
    QTest.keyClick(v, Qt.Key_Return)
    app.processEvents()
    check("penna", len(annots(2)) == n + 1)
    for tool in ("polygon", "polyline", "area"):
        win.set_tool(tool)
        n = len(annots(2))
        for pt in ((420, 700), (480, 720), (460, 780)):
            click(vp(2, *pt))
        QTest.keyClick(v, Qt.Key_Return)
        app.processEvents()
        check(f"forma {tool}", len(annots(2)) > n)
    win.set_tool("note")
    n = len(annots(2))
    click(vp(2, 520, 80))
    check("nota", len(annots(2)) == n + 1)
    win.set_tool("stamp")
    n = len(annots(2))
    click(vp(2, 330, 520))
    check("timbro", len(annots(2)) == n + 1)
    win.tools.stamp_index = -1
    t0 = m.page(2).get_text()
    click(vp(2, 60, 520))
    check("timbro personalizzato", "RICEVUTO" in m.page(2).get_text())
    win.tools.stamp_index = 0
    win.set_tool("freetext")
    n = len(annots(2))
    click(vp(2, 330, 250))
    check("editor casella di testo aperto", v.editor is not None)
    v.editor.w.setPlainText("Casella di prova")
    v.commit_editor()
    check("casella di testo", len(annots(2)) == n + 1)
    win.set_tool("callout")
    n = len(annots(2))
    drag(vp(2, 330, 160), vp(2, 500, 200))
    v.editor.w.setPlainText("Richiamo")
    v.commit_editor()
    check("richiamo", len(annots(2)) == n + 1)


run("forme e commenti", t_shapes)


def t_select_move_annot():
    win.set_tool("select")
    show_page(2)
    a = next(a for a in annots(2) if a.type[0] == pymupdf.PDF_ANNOT_SQUARE)
    r0 = pymupdf.Rect(a.rect)
    c = ((r0.x0 + r0.x1) / 2, r0.y0 + 1)
    drag(vp(2, *c), vp(2, c[0] + 50, c[1] + 30))
    a2 = next(a for a in annots(2) if a.type[0] == pymupdf.PDF_ANNOT_SQUARE)
    check("sposta annotazione col mouse", abs(a2.rect.x0 - r0.x0 - 50) < 3, f"{r0} -> {a2.rect}")
    # maniglia: ridimensiona
    r1 = pymupdf.Rect(a2.rect)
    click(vp(2, (r1.x0 + r1.x1) / 2, r1.y0 + 1))
    drag(vp(2, r1.x1, r1.y1), vp(2, r1.x1 + 40, r1.y1 + 20))
    a3 = next(a for a in annots(2) if a.type[0] == pymupdf.PDF_ANNOT_SQUARE)
    check("ridimensiona con maniglia", a3.rect.width > r1.width + 30, f"{r1} -> {a3.rect}")
    # linea (ricreata quando si sposta)
    ln = next(a for a in annots(2) if a.type[0] == pymupdf.PDF_ANNOT_LINE)
    v0 = ln.vertices[0]
    p = ((ln.vertices[0][0] + ln.vertices[1][0]) / 2, (ln.vertices[0][1] + ln.vertices[1][1]) / 2)
    drag(vp(2, *p), vp(2, p[0] + 20, p[1] + 10))
    lines = [a for a in annots(2) if a.type[0] == pymupdf.PDF_ANNOT_LINE]
    check("sposta linea", any(abs(l.vertices[0][0] - v0[0] - 20) < 3 for l in lines))
    # tastiera
    click(vp(2, (a3.rect.x0 + a3.rect.x1) / 2, a3.rect.y0 + 1))
    x0 = a3.rect.x0
    QTest.keyClick(v, Qt.Key_Right, Qt.ShiftModifier)
    app.processEvents()
    a4 = next(a for a in annots(2) if a.type[0] == pymupdf.PDF_ANNOT_SQUARE)
    check("sposta con le frecce", abs(a4.rect.x0 - x0 - 10) < 2)
    # proprietà
    MW.MainWindow.annot_properties(win, 2, a4.xref) if False else None
    answers["Proprietà annotazione"] = {"color": "#00aa00", "opacity": 50, "content": "modificato"}
    win.annot_properties(2, a4.xref)
    a5 = next(a for a in annots(2) if a.type[0] == pymupdf.PDF_ANNOT_SQUARE)
    check("proprietà dal dialogo", a5.info.get("content") == "modificato")
    n = len(annots(2))
    v.sel_annot = (2, a5.xref)
    QTest.keyClick(v, Qt.Key_Delete)
    app.processEvents()
    check("elimina con Canc", len(annots(2)) == n - 1)
    win.set_tool("eraser")
    n = len(annots(2))
    e = next(a for a in annots(2) if a.type[0] == pymupdf.PDF_ANNOT_CIRCLE)
    click(vp(2, e.rect.x0 + 2, (e.rect.y0 + e.rect.y1) / 2))
    check("gomma", len(annots(2)) == n - 1)
    win.set_tool("select")


run("selezione e spostamento annotazioni", t_select_move_annot)


def t_undo():
    n = len(annots(2))
    win._undo(True)
    check("annulla", len(annots(2)) == n + 1)
    win._undo(False)
    check("ripeti", len(annots(2)) == n)


run("annulla/ripeti", t_undo)


def t_edit_text():
    win.set_tool("edit_text")
    show_page(0)
    click(vp(0, 200, 120))
    ed = v.editor
    check("editor testo aperto", ed is not None and ed.block is not None)
    from PySide6.QtGui import QTextCursor
    cur = ed.edit.textCursor()
    cur.movePosition(QTextCursor.Start)
    cur.movePosition(QTextCursor.EndOfWord, QTextCursor.KeepAnchor)
    ed.edit.setTextCursor(cur)
    ed.edit.insertPlainText("MODIFICATO")
    cur.movePosition(QTextCursor.Start)
    cur.movePosition(QTextCursor.EndOfWord, QTextCursor.KeepAnchor)
    ed.edit.setTextCursor(cur)
    ed.toolbar.b.click()
    ed.toolbar.size.setValue(14)
    from PySide6.QtGui import QTextCharFormat
    fmt = QTextCharFormat()
    fmt.setFontFamilies(["Georgia"])
    ed.merge(fmt)
    app.processEvents()
    v.commit_editor()
    t = m.page(0).get_text(flags=TEXT_FLAGS).replace("\xa0", " ")
    check("testo modificato nella pagina", "MODIFICATO" in t and "Relazione tecnica" in t, t[:300])
    fonts = [f[3] for f in m.page(0).get_fonts()]
    check("font Georgia incorporato", any("Georgia" in f for f in fonts), str(fonts))
    # testo nuovo in uno spazio vuoto
    click(vp(0, 320, 470))
    ed = v.editor
    check("editor nuovo testo", ed is not None and ed.block is None)
    ed.edit.insertPlainText("Testo aggiunto a mano")
    v.commit_editor()
    check("testo aggiunto", "Testo aggiunto a mano" in m.page(0).get_text(flags=TEXT_FLAGS).replace("\xa0", " "))
    # digitazione vera: lettere che sono anche scorciatoie degli strumenti, frecce, Home
    click(vp(0, 400, 520))
    ed = v.editor
    check("editor per la digitazione", ed is not None)
    if ed:
        QTest.keyClicks(v.viewport(), "Pane VHTONPRXZU")
        QTest.keyClick(v.viewport(), Qt.Key_Left)
        QTest.keyClick(v.viewport(), Qt.Key_Home)
        QTest.keyClicks(v.viewport(), ">")
        app.processEvents()
        check("le lettere non cambiano strumento", win.tools.tool == "edit_text", win.tools.tool)
        check("testo digitato nell'editor", ed.edit.toPlainText() == ">Pane VHTONPRXZU", repr(ed.edit.toPlainText()))
        check("le frecce non cambiano pagina", v.current == 0)
        QTest.keyClick(v.viewport(), Qt.Key_Return, Qt.ControlModifier)
        app.processEvents()
        check("Ctrl+Invio conferma", v.editor is None and "Pane VHTONPRXZU" in m.page(0).get_text().replace(" ", " "))
    # annulla con Esc
    click(vp(0, 200, 245))
    if v.editor:
        v.editor.edit.insertPlainText("NON DEVE RESTARE")
        QTest.keyClick(v.editor.edit, Qt.Key_Escape)
        app.processEvents()
    check("Esc annulla", "NON DEVE RESTARE" not in m.page(0).get_text() and v.editor is None)
    win.grab().save(os.path.join(WORK, "screen_3_testo.png"))
    win.set_tool("select")


run("modifica testo", t_edit_text)


def t_edit_object():
    win.set_tool("edit_object")
    show_page(1, 380)
    from editra.ops import images as IM
    im = IM.page_images(m.page(1))[0]
    c = ((im.rect.x0 + im.rect.x1) / 2, (im.rect.y0 + im.rect.y1) / 2)
    drag(vp(1, *c), vp(1, c[0] + 100, c[1] + 20))
    ims = IM.page_images(m.page(1))
    check("sposta immagine col mouse", len(ims) == 1 and abs(ims[0].rect.x0 - im.rect.x0 - 100) < 3,
          f"{im.rect} -> {[i.rect for i in ims]}")
    v.sel_image = (1, ims[0])
    QTest.keyClick(v, Qt.Key_Delete)
    app.processEvents()
    check("elimina immagine", len(IM.page_images(m.page(1))) == 0)
    # sposta un blocco di testo
    t0 = m.page(1).get_text()
    drag(vp(1, 100, 247), vp(1, 100, 380))
    words = [w for w in m.page(1).get_text("words") if w[4].startswith("Contatti")]
    check("sposta blocco di testo", words and words[0][1] > 360, str(words[:1]))
    win.set_tool("select")


run("modifica oggetti", t_edit_object)


def t_forms_fill():
    win.set_tool("select")
    show_page(0, 580)
    w = next(w for w in m.page(0).widgets() if w.field_name == "nome")
    click(vp(0, w.rect.x0 + 5, w.rect.y0 + 5))
    check("editor campo modulo", v.editor is not None)
    if v.editor:
        v.editor.w.setText("Giacomo")
        v.commit_editor()
    w = next(w for w in m.page(0).widgets() if w.field_name == "nome")
    check("campo compilato", w.field_value == "Giacomo", repr(w.field_value))
    cb = next(w for w in m.page(0).widgets() if w.field_name == "accetto")
    click(vp(0, cb.rect.x0 + 3, cb.rect.y0 + 3))
    cb = next(w for w in m.page(0).widgets() if w.field_name == "accetto")
    check("casella spuntata", cb.field_value not in ("Off", False), repr(cb.field_value))
    for kind, x in (("form_text", 60), ("form_checkbox", 260), ("form_combobox", 300), ("form_listbox", 450),
                    ("form_radio", 230), ("form_button", 120), ("form_signature", 330)):
        win.set_tool(kind)
        n = len(list(m.page(3).widgets()))
        show_page(3, 600)
        drag(vp(3, x, 640), vp(3, x + 60, 665))
        check(f"crea {kind}", len(list(m.page(3).widgets())) == n + 1)
    win.set_tool("select")
    file_answers.append(os.path.join(WORK, "dati.json"))
    win.form_export()
    win.form_reset()
    file_answers.append(os.path.join(WORK, "dati.json"))
    win.form_import()
    w = next(w for w in m.page(0).widgets() if w.field_name == "nome")
    check("dati reimportati", w.field_value == "Giacomo")
    win.form_list()
    win.form_detect()


run("moduli", t_forms_fill)


def t_links():
    win.set_tool("link")
    show_page(3)
    answers["Nuovo collegamento"] = {"kind": "page", "page": 1}
    drag(vp(3, 60, 60), vp(3, 200, 80))
    check("crea collegamento", any(l["kind"] == pymupdf.LINK_GOTO for l in m.page(3).get_links()))
    win.set_tool("select")
    show_page(0, 680)
    v.go_to_page(0)
    link = next(l for l in m.page(0).get_links() if l["kind"] == pymupdf.LINK_GOTO)
    r = link["from"]
    click(vp(0, r.x0 + 5, r.y0 + 5))
    check("segui collegamento", v.current == link["page"], f"{v.current} vs {link['page']}")
    win.detect_urls()


run("collegamenti", t_links)


def t_page_ops():
    print("   modello:", win.model().title, win.model().workpath, win.model().has_signatures(), win.model().doc.get_sigflags())
    n = m.page_count
    win.page_action("blank_after", [0])
    check("inserisci vuota", m.page_count == n + 1)
    win.page_action("duplicate", [1])
    check("duplica", m.page_count == n + 2)
    win.page_action("rotate_right", [0, 1])
    check("ruota", m.page(0).rotation == 90)
    win.page_action("rotate_left", [0, 1])
    win.page_action("delete", [1, 2])
    check("elimina", m.page_count == n)
    thumbs = win.tab().panels["thumbs"]
    thumbs.list.moved.emit([3], 0)
    app.processEvents()
    check("riordina dalle miniature", "capitolo 4" in m.page(0).get_text().replace("\xa0", " "))
    win._undo(True)
    file_answers.append(SAMPLE)
    answers["Inserisci pagine"] = {"pages": "1-2", "where": "end"}
    win.insert_from_file(1)
    check("inserisci da file", m.page_count == n + 2)
    win.delete_pages_dialog.__func__ if False else None
    answers["Elimina pagine"] = {"pages": f"{n + 1}-{n + 2}"}
    win.delete_pages_dialog()
    check("elimina da dialogo", m.page_count == n)
    file_answers.append(os.path.join(WORK, "estratte.pdf"))
    answers["Estrai pagine"] = {"pages": "1-2", "separate": False, "delete": False}
    win.extract_dialog()
    check("estrai", os.path.exists(os.path.join(WORK, "estratte.pdf")))
    check("estratte aperte in una scheda", win.model().path.endswith("estratte.pdf"))
    win.close_tab(win.tabs.currentIndex())
    win.tabs.setCurrentWidget(win.tabs.widget(0))
    answers["Dividi documento"] = {"mode": "every", "n": 2, "dir": os.path.join(WORK, "div")}
    win.split()
    check("dividi", len(os.listdir(os.path.join(WORK, "div"))) == 2)
    answers["Ritaglia pagine"] = {"l": 5, "t": 5, "rr": 5, "b": 5, "pages": "1"}
    w0 = m.page(0).rect.width
    win.crop_dialog()
    check("ritaglia margini", m.page(0).rect.width < w0 - 20)
    win.actions["pg_uncrop"].trigger()
    app.processEvents()
    check("rimuovi ritaglio", abs(m.page(0).rect.width - w0) < 1)
    win.set_tool("crop")
    show_page(1)
    answers["Ritaglia"] = {"pages": "2"}
    drag(vp(1, 50, 50), vp(1, 400, 500))
    check("strumento ritaglia", abs(m.page(1).rect.width - 350) < 3, str(m.page(1).rect))
    win._undo(True)
    answers["Cambia formato pagine"] = {"size": "A5", "pages": "1"}
    win.resize_pages()
    check("cambia formato", abs(m.page(0).rect.width - 420) < 2)
    win._undo(True)
    answers["Ruota pagine"] = {"pages": "tutte", "angle": 180}
    win.rotate_dialog()
    check("ruota da dialogo", all(p.rotation == 180 for p in m.doc))
    win._undo(True)
    win.actions["pg_reverse"].trigger()
    win._undo(True)
    win.remove_blank()
    answers["Più pagine per foglio"] = {"n": 4}
    k = win.tabs.count()
    win.nup()
    check("N per foglio (nuova scheda)", win.tabs.count() == k + 1)
    win.close_tab(win.tabs.currentIndex()) if win.model().modified is False else None
    win.tabs.setCurrentIndex(0)


run("pagine", t_page_ops)
v = win.view()
m = win.model()


def t_edit_menu():
    answers["Trova e sostituisci"] = {"find": "Cavo", "repl": "Filo", "case": False, "pages": "tutte"}
    win.find_replace()
    check("trova e sostituisci", "Filo" in m.page(1).get_text() and "Cavo" not in m.page(1).get_text())
    answers["Filigrana"] = {"kind": "text", "text": "COPIA", "pages": "tutte"}
    win.watermark()
    check("filigrana", "COPIA" in m.page(2).get_text())
    answers["Intestazione e piè di pagina"] = {"alto-centro": "Titolo {file}", "basso-centro": "Pagina {n} di {N}"}
    win.header_footer()
    check("intestazione", "Pagina 3 di" in m.page(2).get_text().replace("\xa0", " "))
    win.page_numbers()
    answers["Numerazione Bates"] = {"prefix": "ATTO-"}
    win.bates()
    check("bates", "ATTO-000001" in m.page(0).get_text())
    win.background()
    win.find()
    sp = win.tab().panels["search"]
    sp.search("capitolo")
    check("ricerca", len(sp.hits) >= 4, str(len(sp.hits)))
    sp.step(1)
    sp.highlight_all()
    win.search_box.setText("paragrafo")
    win._quick_search()
    check("ricerca rapida", len(sp.hits) >= 4)


run("menu modifica", t_edit_menu)


def t_protect():
    answers["Cerca e redigi"] = {"text": "", "p_Indirizzi e-mail": True}
    win.redact_search()
    from editra.ops import security as SEC
    check("contrassegna redazioni", SEC.pending_redactions(m.doc) >= 1)
    win.set_tool("redact")
    show_page(2)
    drag(vp(2, 72, 280), vp(2, 300, 300))
    win.apply_redactions()
    check("applica redazioni", "mario.rossi" not in m.page(0).get_text() and SEC.pending_redactions(m.doc) == 0)
    win.sanitize()
    win.set_tool("select")


run("protezione", t_protect)


def t_signature():
    from PySide6.QtGui import QImage, QColor
    img = QImage(300, 100, QImage.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    from PySide6.QtGui import QPainter
    p = QPainter(img)
    p.drawLine(10, 50, 290, 60)
    p.end()
    sig = os.path.join(WORK, "firma.png")
    img.save(sig)
    win.tools.signature_path = sig
    win.set_tool("signature")
    show_page(0, 500)
    n = len(m.page(0).get_images())
    click(vp(0, 300, 560))
    check("firma autografa", len(m.page(0).get_images()) == n + 1)
    win.set_tool("select")
    # ID digitale e firma
    pfx = os.path.join(WORK, "id_gui.pfx")
    answers["Crea ID digitale"] = {"name": "Test GUI", "pw": "abcd", "pw2": "abcd", "path": pfx}
    win.create_digital_id()
    check("crea ID digitale", os.path.exists(pfx))
    file_answers.append(os.path.join(WORK, "salvato_prima.pdf"))
    win.save_as()
    answers["Firma con certificato digitale"] = {"pfx": pfx, "pw": "abcd"}
    out = os.path.join(WORK, "firmato_gui.pdf")
    file_answers.append(out)
    win.set_tool("sign_digital")
    show_page(3)
    drag(vp(3, 300, 700), vp(3, 520, 770))
    check("firma digitale", os.path.exists(out) and win.model().path == out)
    sp = win.tab().panels["signatures"]
    check("pannello firme", sp.results and sp.results[0].status == "valida",
          sp.results[0].summary if sp.results else "nessun risultato")
    # annotazione dopo la firma e salvataggio incrementale
    win.set_tool("note")
    click(vp(3, 100, 100))
    win.set_tool("select")
    win.save()
    from editra.ops import signatures as SG
    res = SG.verify_pdf(open(out, "rb").read())
    check("firma valida dopo un commento", res and res[0].intact and res[0].valid, res[0].summary if res else "")


run("firme", t_signature)
v = win.view()
m = win.model()


def t_tools():
    from editra.ops import ocr as O
    answers["Riconosci testo (OCR)"] = {"which": "range", "range": "1"}
    win.ocr()
    file_answers.append(os.path.join(WORK, "esportato.docx"))
    win.export_word()
    win._worker.wait(120000)
    app.processEvents()
    check("esporta word", os.path.exists(os.path.join(WORK, "esportato.docx")))
    file_answers.append(os.path.join(WORK, "esportato.xlsx"))
    win.export_excel()
    check("esporta excel", os.path.exists(os.path.join(WORK, "esportato.xlsx")))
    answers["Esporta come immagini"] = {"dir": os.path.join(WORK, "png"), "dpi": 50}
    win.export_images()
    check("esporta immagini", len(os.listdir(os.path.join(WORK, "png"))) >= 4)
    for k in ("txt", "html", "md"):
        file_answers.append(os.path.join(WORK, "esportato." + k))
        win.export_simple(k)
        check(f"esporta {k}", os.path.exists(os.path.join(WORK, "esportato." + k)))
    file_answers.append(os.path.join(WORK, "imm"))
    win.extract_images()
    win.properties()
    win.comments_summary()
    answers["Confronta documenti"] = {"a": SAMPLE, "b": out_signed if False else os.path.join(WORK, "salvato_prima.pdf")}
    k = win.tabs.count()
    win.compare()
    check("confronta", win.tabs.count() == k + 2)


run("strumenti", t_tools)
win.tabs.setCurrentIndex(0)
v = win.view()
m = win.model()


def t_compress_encrypt():
    tabs0 = win.tabs.count()
    win.merge()
    check("combina (scheda nuova)", win.tabs.count() == tabs0 + 1)
    m2 = win.model()
    win.compress()
    p = os.path.join(WORK, "cifrato.pdf")
    D.EncryptDialog.result_options = lambda self: {"user_pw": "x1", "owner_pw": "y2", "permissions": pymupdf.PDF_PERM_PRINT}
    file_answers.append(p)
    win.encrypt()
    check("salvato cifrato", os.path.exists(p) and pymupdf.open(p).needs_pass)


run("compressione e cifratura", t_compress_encrypt)


def t_files():
    win.new_blank()
    check("nuovo documento", win.model().page_count == 1)
    png = os.path.join(WORK, "png", os.listdir(os.path.join(WORK, "png"))[0])
    file_answers.append([png, os.path.join(WORK, "esportato.txt")])
    win.create_from_files()
    check("crea da file", win.model().page_count >= 2)
    from PySide6.QtGui import QImage
    QApplication.clipboard().setText("Testo dagli appunti")
    win.create_from_clipboard()
    check("crea dagli appunti", "appunti" in win.model().page(0).get_text())
    # p7m
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.serialization import Encoding, pkcs12, pkcs7
    key, cert, _ = pkcs12.load_key_and_certificates(open(os.path.join(WORK, "id_gui.pfx"), "rb").read(), b"abcd")
    data = open(SAMPLE, "rb").read()
    p7 = pkcs7.PKCS7SignatureBuilder().set_data(data).add_signer(cert, key, hashes.SHA256()).sign(Encoding.DER, [pkcs7.PKCS7Options.Binary])
    pp = os.path.join(WORK, "contratto.pdf.p7m")
    open(pp, "wb").write(p7)
    win.open_files([pp])
    check("apre p7m", win.model().title == "contratto.pdf" and win.model().page_count == 4)
    win.goto_page()
    check("vai alla pagina", win.view().current == 1)
    win.show_shortcuts()
    # stampa su file PDF (stessa resa della stampante)
    from PySide6.QtPrintSupport import QPrinter
    from editra import printing
    pr = QPrinter(QPrinter.HighResolution)
    pr.setOutputFormat(QPrinter.PdfFormat)
    out_print = os.path.join(WORK, "stampa.pdf")
    pr.setOutputFileName(out_print)
    ok = printing.render_to_printer(pr, win.model().doc, [0, 1, 2], max_dpi=100)
    check("stampa", ok and pymupdf.open(out_print).page_count == 3)
    win.print_preview.__name__
    # chiusura con modifiche: salvataggio richiesto
    while win.tabs.count():
        mm = win.model()
        if mm.modified and not mm.path:
            file_answers.append(os.path.join(WORK, f"chiusura_{win.tabs.count()}.pdf"))
        if not win.close_tab(win.tabs.currentIndex()):
            break
    check("chiusura schede", win.tabs.count() == 0)


run("file", t_files)
win.grab().save(os.path.join(WORK, "screen_4_benvenuto.png"))

fails = [r for r in results if not r[1]]
print(f"\n{len(results) - len(fails)} / {len(results)} verifiche superate")
for f in fails:
    print("FALLITA:", f[0], f[2][:300])
sys.exit(1 if fails else 0)
