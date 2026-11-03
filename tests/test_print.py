"""Collaudo della finestra di stampa con anteprima (stampa su file PDF, nessuna stampante reale).

Uso: python tests/test_print.py <cartella_di_lavoro> <pdf_di_prova>
"""
import os
import sys
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORK, SAMPLE = sys.argv[1], sys.argv[2]
os.makedirs(WORK, exist_ok=True)
os.environ["APPDATA"] = os.path.join(WORK, "appdata")

import pymupdf
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

app = QApplication(sys.argv)
from editra import printing as P, theme
from editra.model import PdfModel

theme.apply(app, "light")
results = []
warnings = []
QMessageBox.warning = staticmethod(lambda *a, **k: warnings.append(a[1:3]))


def check(name, cond, info=""):
    results.append((name, bool(cond), info))
    print(("OK   " if cond else "FAIL ") + name + (f"  [{info}]" if info and not cond else ""))


def pdf_printer(name):
    pr = QPrinter(QPrinter.HighResolution)
    pr.setOutputFormat(QPrinter.PdfFormat)
    path = os.path.join(WORK, name)
    pr.setOutputFileName(path)
    return pr, path


def set_combo(combo, data):
    i = combo.findData(data)
    assert i >= 0, data
    combo.setCurrentIndex(i)


try:
    # calcoli puri
    opt = P.PrintOptions(pages="range", range_text="2-3", reverse=True)
    check("pagine: intervallo al contrario", P.select_pages(4, 0, opt) == [2, 1])
    check("pagine: dispari", P.select_pages(5, 0, P.PrintOptions(pages="odd")) == [0, 2, 4])
    check("pagine: pari", P.select_pages(5, 0, P.PrintOptions(pages="even")) == [1, 3])
    check("pagine: corrente", P.select_pages(5, 3, P.PrintOptions(pages="current")) == [3])
    check("fogli: 4 per foglio", P.make_sheets(list(range(10)), 4) == [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9]])

    m = PdfModel(SAMPLE)
    m.doc[1].set_rotation(90)   # una pagina orizzontale nel mezzo
    dlg = P.PrintDialog(None, m, 1)
    dlg.show()
    QTest.qWait(300)
    pm = dlg.preview.pixmap()
    check("anteprima disegnata", pm is not None and not pm.isNull() and pm.width() > 100)
    check("contatore fogli", dlg.sheet_lbl.text().endswith("4"), dlg.sheet_lbl.text())
    dlg.next_btn.click()
    QTest.qWait(50)
    check("scorrimento fogli", dlg.sheet_index == 1)
    # opzioni che cambiano l'anteprima
    for combo, data in ((dlg.per_sheet, 4), (dlg.orient, "landscape"), (dlg.color, True), (dlg.scale, "fit")):
        set_combo(combo, data)
        dlg._refresh()
    check("anteprima 4 per foglio", dlg.sheet_lbl.text().endswith("1"), dlg.sheet_lbl.text())
    set_combo(dlg.pages_box, "range")
    dlg.range_edit.setText("99")
    dlg._refresh()
    check("intervallo non valido segnalato", not dlg.print_btn.isEnabled())

    def run(name, **kw):
        d = P.PrintDialog(None, m, 0)
        d.show()
        QTest.qWait(50)
        for key, value in kw.items():
            w = getattr(d, key)
            if hasattr(w, "findData") and w.findData(value) >= 0:
                set_combo(w, value)
            elif hasattr(w, "setChecked"):
                w.setChecked(value)
            elif hasattr(w, "setValue"):
                w.setValue(value)
            else:
                w.setText(value)
        d._refresh()
        pr, path = pdf_printer(name)
        d.printer = pr
        d._print()
        out = pymupdf.open(path) if os.path.exists(path) else None
        return out

    out = run("tutte.pdf")
    check("stampa tutte le pagine", out is not None and out.page_count == 4, str(out and out.page_count))
    out = run("due_per_foglio.pdf", per_sheet=2)
    check("2 per foglio: 2 fogli orizzontali", out.page_count == 2 and out[0].rect.width > out[0].rect.height,
          str(out[0].rect))
    out = run("intervallo.pdf", pages_box="range", range_edit="2-4", reverse=True)
    check("intervallo 2-4", out.page_count == 3)
    out = run("copie.pdf", copies=2, collate=True)
    check("2 copie fascicolate", out.page_count == 8, str(out.page_count))
    out = run("bn.pdf", color=True, dpi=150, scale="actual")
    pix = out[0].get_pixmap(dpi=40)
    colored = any(abs(pix.pixel(x, y)[0] - pix.pixel(x, y)[1]) > 25 or abs(pix.pixel(x, y)[1] - pix.pixel(x, y)[2]) > 25
                  for x in range(0, pix.width, 3) for y in range(0, pix.height, 3))
    check("bianco e nero senza colori", not colored)
    out = run("orizzontale.pdf", orient="landscape", pages_box="current")
    check("pagina corrente su foglio orizzontale", out.page_count == 1 and out[0].rect.width > out[0].rect.height)
    out = run("scala.pdf", scale="custom", pct=50)
    check("scala personalizzata", out.page_count == 4)
    # funzione di stampa diretta usata da altre parti
    pr, path = pdf_printer("diretta.pdf")
    check("stampa diretta", P.render_to_printer(pr, m.doc, [0, 2], max_dpi=100) and pymupdf.open(path).page_count == 2)
    check("nessun avviso", not warnings, str(warnings))
except Exception as ex:
    traceback.print_exc()
    check("eccezione", False, repr(ex))

fails = [r for r in results if not r[1]]
print(f"\n{len(results) - len(fails)} / {len(results)} verifiche superate")
for f in fails:
    print("FALLITA:", f[0], f[2][:300])
# chiusura esplicita: i dialoghi senza finestra madre non vanno lasciati alla pulizia dell'interprete
for w in QApplication.topLevelWidgets():
    w.close()
    w.deleteLater()
app.processEvents()
sys.stdout.flush()
os._exit(1 if fails else 0)
