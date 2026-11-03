"""Collaudo delle operazioni sui PDF (senza interfaccia).

Uso: python tests/test_ops.py <cartella_di_lavoro> <pdf_di_prova>
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORK, SAMPLE = sys.argv[1], sys.argv[2]
os.makedirs(WORK, exist_ok=True)
os.environ["APPDATA"] = os.path.join(WORK, "appdata")

import pymupdf
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(["x", "-platform", "offscreen"])

from editra.model import PdfModel, PasswordRequired
from editra.ops import annots as A, compare as CP, compress as CMP, convert as CV, forms as F, images as IM
from editra.ops import ocr as O, pages as PG, security as SEC, signatures as SG, stamping as ST, textedit as TE
from editra.ops.common import parse_ranges, format_ranges, search_page, TEXT_FLAGS

results = []


def check(name, cond, info=""):
    results.append((name, bool(cond), info))
    print(("OK   " if cond else "FAIL ") + name + (f"  [{info}]" if info and not cond else ""))


def section(fn):
    try:
        fn()
    except Exception as ex:
        traceback.print_exc()
        check(fn.__name__ + " (eccezione)", False, repr(ex))


def sample():
    return pymupdf.open(SAMPLE)


def T(page):
    return page.get_text(flags=TEXT_FLAGS).replace(" ", " ")


def t_ranges():
    check("range 1-3,5", parse_ranges("1-3, 5", 10) == [0, 1, 2, 4])
    check("range 8-", parse_ranges("8-", 10) == [7, 8, 9])
    check("range pari", parse_ranges("pari", 5) == [1, 3])
    check("range fine", parse_ranges("3-fine", 4) == [2, 3])
    check("format", format_ranges([0, 1, 2, 4]) == "1-3, 5")
    try:
        parse_ranges("12", 5)
        check("range fuori limite", False)
    except ValueError:
        check("range fuori limite", True)


def t_textedit():
    for rot in (0, 90, 270):
        d = sample()
        p = d[0]
        p.set_rotation(rot)
        blocks = TE.read_blocks(p)
        body = next(b for b in blocks if "paragrafo di prova" in b.text)
        paras = body.paras
        paras[0].runs[0].text = "Testo nuovo modificato con àèìòù € e ﬁ."
        paras[0].runs[0].bold = True
        TE.replace_block(p, body, paras)
        txt = T(p)
        check(f"modifica blocco rot {rot}", "Testo nuovo modificato" in txt and "paragrafo di prova" not in txt.split("Contatti")[0],
              txt[:200])
        check(f"titolo intatto rot {rot}", "Relazione tecnica" in txt)
        check(f"contatti intatti rot {rot}", "Contatti:" in txt)
    d = sample()
    n, w = TE.find_replace(d, "Interruttore", "Sezionatore")
    t = T(d[0])
    check("trova e sostituisci", n == 4 and "Sezionatore" in t and "Interruttore" not in t, f"n={n}")
    p = d[1]
    TE.insert_paras(p, pymupdf.Rect(300, 400, 520, 440), [TE.Para([TE.Run("Nuovo testo in Times", "Times New Roman", 14, color="#ff0000")])])
    check("aggiungi testo", "Nuovo testo in Times" in T(p))
    fonts = [f[3] for f in p.get_fonts()]
    check("font incorporato Times", any("Times" in f for f in fonts), str(fonts))
    blocks = TE.read_blocks(d[2])
    b = blocks[0]
    TE.delete_block(d[2], b)
    check("elimina blocco", "capitolo 3" not in T(d[2]))


def t_pages():
    d = sample()
    PG.rotate_pages(d, [0, 1], 90)
    check("ruota", d[0].rotation == 90 and d[2].rotation == 0)
    PG.insert_blank(d, 1)
    check("pagina vuota", d.page_count == 5 and not T(d[1]).strip())
    PG.delete_pages(d, [1])
    check("elimina", d.page_count == 4)
    new = PG.move_pages(d, [3], 0)
    check("sposta", "capitolo 4" in T(d[0]) and new == [0])
    PG.duplicate_pages(d, [0])
    check("duplica", d.page_count == 5 and "capitolo 4" in T(d[1]))
    PG.reverse_pages(d)
    check("inverti", "capitolo 4" in T(d[4]))
    e = PG.extract_pages(d, [0, 1])
    check("estrai", e.page_count == 2)
    m = PG.merge_files([(SAMPLE, ""), (SAMPLE, "2-3")])
    check("combina", m.page_count == 6 and len(m.get_toc()) >= 2, str(m.get_toc()))
    out = os.path.join(WORK, "split")
    paths = PG.split_document(sample(), "every", 2, out, "prova")
    check("dividi ogni 2", len(paths) == 2)
    paths = PG.split_document(sample(), "bookmarks", None, out, "seg")
    check("dividi per segnalibri", len(paths) == 4)
    paths = PG.split_document(sample(), "ranges", "1; 2-4", out, "int")
    check("dividi per intervalli", len(paths) == 2)
    paths = PG.split_document(sample(), "size", 0.01, out, "dim")
    check("dividi per dimensione", len(paths) >= 2, str(len(paths)))
    d = sample()
    PG.crop_pages(d, [0], margins=(36, 36, 36, 36))
    check("ritaglio margini", abs(d[0].rect.width - (595 - 72)) < 1, str(d[0].rect))
    PG.reset_crop(d, [0])
    PG.crop_pages(d, [1], rect=pymupdf.Rect(50, 50, 300, 300))
    check("ritaglio rettangolo", abs(d[1].rect.width - 250) < 1)
    d = sample()
    PG.resize_pages(d, [0], (420, 595))
    check("cambia formato A5", abs(d[0].rect.width - 420) < 1 and "Relazione" in T(d[0]))
    n = PG.n_up(sample(), 4)
    check("4 per foglio", n.page_count == 1)
    il = PG.interleave(sample(), sample(), True)
    check("fronte/retro", il.page_count == 8)
    d = sample()
    PG.insert_blank(d, 2)
    check("rileva pagine vuote", PG.blank_pages(d) == [2])
    d = sample()
    k = PG.insert_from_file(d, SAMPLE, 1, "1-2")
    check("inserisci da file", k == 2 and d.page_count == 6)
    PG.replace_pages(d, [0], SAMPLE, "4")
    check("sostituisci pagina", "capitolo 4" in T(d[0]))


def t_annots():
    d = sample()
    p = d[0]
    st = A.Style(color="#ff0000", width=2, opacity=0.8, author="Tester")
    q = [r.quad for r in search_page(p, "paragrafo")]
    for kind in ("highlight", "underline", "strike", "squiggly"):
        A.add_markup(p, kind, q, st)
    A.add_note(p, pymupdf.Point(500, 100), "Nota di prova", "Comment", st)
    A.add_freetext(p, pymupdf.Rect(300, 650, 500, 690), "Casella di testo", st)
    A.add_freetext(p, pymupdf.Rect(300, 700, 500, 740), "Richiamo", st, callout=[pymupdf.Point(250, 760), pymupdf.Point(300, 720)])
    for kind, pts in (("line", [(100, 600), (200, 650)]), ("arrow", [(100, 660), (200, 700)]),
                      ("rect", [(400, 400), (500, 450)]), ("ellipse", [(400, 460), (500, 510)]),
                      ("polygon", [(300, 300), (350, 280), (380, 330)]), ("polyline", [(300, 350), (340, 370), (380, 350)])):
        A.add_shape(p, kind, [pymupdf.Point(*x) for x in pts], st)
    A.add_ink(p, [[pymupdf.Point(50, 50), pymupdf.Point(60, 70), pymupdf.Point(80, 60)]], st)
    A.add_stamp(p, pymupdf.Rect(350, 520, 530, 580), pymupdf.STAMP_Approved, st)
    A.add_text_stamp(p, pymupdf.Rect(60, 740, 240, 800), "Ricevuto", "#1565c0", st)
    a, label = A.add_measure(p, pymupdf.Point(100, 780), pymupdf.Point(200, 780), 1, "mm", st)
    check("misura 100 pt = 35,28 mm", label.startswith("35,28"), label)
    _, area = A.add_area_measure(p, [pymupdf.Point(0, 0), pymupdf.Point(72, 0), pymupdf.Point(72, 72), pymupdf.Point(0, 72)], 1, "mm", st)
    check("area 1 pollice²", "645,16" in area, area)
    att = os.path.join(WORK, "allegato.txt")
    open(att, "w").write("ciao")
    A.add_file_attachment(p, pymupdf.Point(550, 50), att, st)
    lst = A.list_annots(d)
    check("elenco annotazioni", len(lst) >= 18, str(len(lst)))
    # sposta tutte le annotazioni spostabili
    moved = 0
    for a in list(p.annots()):
        if A.can_move(a) and a.type[0] not in (pymupdf.PDF_ANNOT_POPUP,):
            r0 = pymupdf.Rect(a.rect)
            x = A.move_annot(p, a, 10, 5)
            a2 = A.annot_by_xref(p, x)
            if a2 and abs(a2.rect.x0 - r0.x0 - 10) < 2:
                moved += 1
    check("sposta annotazioni", moved >= 12, str(moved))
    a = next(a for a in p.annots() if a.type[0] == pymupdf.PDF_ANNOT_SQUARE)
    A.set_annot_props(a, {"color": "#00ff00", "fill": "#0000ff", "width": 4, "opacity": 0.5, "content": "x", "author": "Y"})
    pr = A.annot_props(A.annot_by_xref(p, a.xref))
    check("proprietà annotazione", pr["color"] == "#00ff00" and pr["author"] == "Y" and abs(pr["opacity"] - 0.5) < 0.01, str(pr))
    a = next(a for a in p.annots() if a.type[0] == pymupdf.PDF_ANNOT_FREE_TEXT)
    A.set_annot_props(a, {"color": "#123456", "fill": "#ffffff", "width": 1, "opacity": 1, "text_color": "#123456"})
    xr = A.resize_annot(p, a, pymupdf.Rect(300, 650, 560, 700))
    check("ridimensiona casella", abs(A.annot_by_xref(p, xr).rect.x1 - 560) < 2)
    html = A.comments_summary_html(d, "x")
    check("riepilogo commenti", "Nota di prova" in html)
    data = d.tobytes()
    d2 = pymupdf.open("pdf", data)
    A.flatten(d2)
    check("appiattisci", len(list(d2[0].annots())) == 0 and len(T(d2[0])) > 100)
    n = A.delete_all_annots(d)
    check("elimina tutti", n >= 18 and not list(d[0].annots()))


def t_images():
    d = sample()
    p = d[0]
    ims = IM.page_images(p)
    check("trova immagine", len(ims) == 1)
    im = ims[0]
    IM.move_image(p, im, pymupdf.Rect(300, 400, 480, 520))
    ims = IM.page_images(p)
    check("sposta immagine", len(ims) == 1 and abs(ims[0].rect.x0 - 300) < 1, str([i.rect for i in ims]))
    check("testo intatto dopo spostamento", "Firma:" in T(p))
    IM.rotate_image(p, ims[0], 90)
    ims = IM.page_images(p)
    check("ruota immagine", len(ims) == 1 and ims[0].rect.height > ims[0].rect.width, str(ims[0].rect))
    png = os.path.join(WORK, "img.png")
    pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False).save(png)
    IM.replace_image(p, ims[0], png)
    check("sostituisci immagine", len(IM.page_images(p)) == 1)
    IM.remove_image(p, IM.page_images(p)[0])
    check("elimina immagine", len(IM.page_images(p)) == 0)
    paths = IM.extract_all_images(sample(), os.path.join(WORK, "imgs"))
    check("estrai immagini", len(paths) >= 1)
    for rot in (90, 180):
        d = sample()
        p = d[1]
        p.set_rotation(rot)
        IM.insert_image(p, pymupdf.Rect(100, 100, 200, 150) * p.derotation_matrix, path=png)
        check(f"inserisci immagine su pagina ruotata {rot}", len(IM.page_images(p)) == 2)


def t_stamping():
    for rot in (0, 90):
        d = sample()
        if rot:
            for p in d:
                p.set_rotation(rot)
        pages = list(range(d.page_count))
        ST.watermark_text(d, pages, "BOZZA", rotation=45)
        ST.header_footer(d, pages, {"alto-sinistra": "Intestazione {file}", "basso-centro": "Pagina {n} di {N}"},
                         "Helvetica", 9, "#333333", 36, 24, 1, "prova.pdf")
        ST.bates(d, pages, "DOC-", "", 1, 6, "basso-destra", "Helvetica", 9, "#000000")
        ST.page_numbers(d, pages, "{n}", "alto-destra")
        ST.background(d, pages, color="#fff8e1")
        t = T(d[1])
        check(f"intestazioni rot {rot}", "Pagina 2 di 4" in t and "DOC-000002" in t and "Intestazione prova.pdf" in t, t[-300:])
        check(f"filigrana rot {rot}", "BOZZA" in T(d[0]))
        # la riga dell'intestazione è orizzontale come appare a schermo
        words = [w for w in d[1].get_text("words") if w[4] == "Intestazione"]
        if words:
            r = pymupdf.Rect(words[0][:4]) * d[1].rotation_matrix
            check(f"intestazione in alto rot {rot}", r.y0 < 60 and r.width > r.height, str(r))
    png = os.path.join(WORK, "wm.png")
    pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 50, 50), False).save(png)
    d = sample()
    ST.watermark_image(d, [0], png, 0.3)
    check("filigrana immagine", len(d[0].get_images()) >= 2)
    n = ST.detect_urls(d)
    check("link automatici", n >= 1, str(n))
    ST.add_link(d[0], pymupdf.Rect(10, 10, 50, 20), uri="https://example.com")
    ST.add_link(d[0], pymupdf.Rect(10, 30, 50, 40), page_target=2)
    kinds = [l["kind"] for l in d[0].get_links()]
    check("collegamenti", pymupdf.LINK_URI in kinds and pymupdf.LINK_GOTO in kinds)


def t_compress():
    d = pymupdf.open()
    p = d.new_page()
    import random
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 1500, 1500), False)
    random.seed(1)
    buf = bytearray(random.getrandbits(8) for _ in range(1500 * 1500 * 3))
    pix = pymupdf.Pixmap(pymupdf.csRGB, 1500, 1500, bytes(buf), False)
    p.insert_image(pymupdf.Rect(0, 0, 300, 300), pixmap=pix)
    data = d.tobytes()
    out = CMP.compress(data, CMP.CompressOptions(dpi_threshold=100, dpi_target=72, quality=50))
    check("compressione", len(out) < len(data) * 0.5, f"{len(data)} -> {len(out)}")
    check("compresso apribile", pymupdf.open("pdf", out).page_count == 1)


def t_security():
    m = PdfModel(SAMPLE)
    m.encryption = {"user_pw": "apri", "owner_pw": "padrone", "permissions": pymupdf.PDF_PERM_PRINT}
    path = os.path.join(WORK, "protetto.pdf")
    m.save(path)
    d = pymupdf.open(path)
    check("cifratura richiede password", d.needs_pass)
    check("password utente", d.authenticate("apri") > 0)
    check("permessi limitati", not (d.permissions & pymupdf.PDF_PERM_MODIFY))
    try:
        PdfModel(path)
        check("apertura senza password rifiutata", False)
    except PasswordRequired:
        check("apertura senza password rifiutata", True)
    m2 = PdfModel(path, password="padrone")
    m2.encryption = {"remove": True}
    p2 = os.path.join(WORK, "sprotetto.pdf")
    m2.save(p2)
    check("rimozione protezione", not pymupdf.open(p2).needs_pass)
    d = sample()
    hits = SEC.find_pattern(d, SEC.PATTERNS["Indirizzi e-mail"])
    check("trova e-mail", len(hits) == 4 and hits[0][2] == "mario.rossi@example.com", str(hits[:1]))
    hits += SEC.find_pattern(d, "Quadro", regex=False)
    SEC.mark_redactions(d, hits)
    check("redazioni in sospeso", SEC.pending_redactions(d) == 8)
    SEC.apply_redactions(d)
    t = T(d[0])
    check("redazione applicata", "mario.rossi" not in t and "Quadro" not in t and "Contatti" in t, t[:400])
    SEC.sanitize(d)
    check("pulizia metadati", not (d.metadata.get("author")))
    SEC.set_metadata(d, {"title": "Nuovo titolo", "author": "Io"})
    check("metadati", d.metadata["title"] == "Nuovo titolo")
    info = SEC.document_info(sample(), SAMPLE, os.path.getsize(SAMPLE))
    check("info documento", any(k == "Pagine" and v == "4" for k, v in info))


def t_forms():
    d = sample()
    p = d[1]
    for kind in F.FIELD_TYPES:
        F.create_field(p, kind, pymupdf.Rect(100, 100 + 40 * list(F.FIELD_TYPES).index(kind), 250,
                                             125 + 40 * list(F.FIELD_TYPES).index(kind)), F.unique_name(d, kind),
                       choices=["A", "B"])
    names = [w.field_name for w in p.widgets()]
    check("crea campi", len(names) == 7, str(names))
    w = next(w for w in d[0].widgets() if w.field_name == "nome")
    F.set_value(d[0], w.xref, "Giacomo")
    cb = next(w for w in d[0].widgets() if w.field_name == "accetto")
    F.toggle(d[0], cb.xref)
    path = os.path.join(WORK, "dati.json")
    F.export_data(d, path)
    import json
    data = json.load(open(path, encoding="utf-8"))
    check("esporta dati", data.get("nome") == "Giacomo" and data.get("accetto") not in ("Off", False), str(data))
    F.reset_form(d)
    check("svuota", next(w for w in d[0].widgets() if w.field_name == "nome").field_value in ("", None))
    n = F.import_data(d, path)
    check("importa dati", n >= 2 and next(w for w in d[0].widgets() if w.field_name == "nome").field_value == "Giacomo")
    d2 = sample()
    n = F.auto_detect_fields(d2)
    check("riconosci campi", n >= 4, str(n))
    data = d.tobytes()
    d3 = pymupdf.open("pdf", data)
    A.flatten(d3, annots=False, widgets=True)
    check("appiattisci modulo", not list(d3[0].widgets()) and "Giacomo" in T(d3[0]))


def t_convert():
    d = sample()
    paths = CV.to_images(d, [0, 1], os.path.join(WORK, "img_out"), "p", "png", 72)
    check("esporta PNG", len(paths) == 2 and os.path.getsize(paths[0]) > 1000)
    paths = CV.to_images(d, [0], os.path.join(WORK, "img_out"), "p", "jpg", 72)
    check("esporta JPEG", os.path.exists(paths[0]))
    paths = CV.to_images(d, [0], os.path.join(WORK, "img_out"), "p", "tiff", 72)
    check("esporta TIFF", os.path.exists(paths[0]))
    CV.to_text(d, os.path.join(WORK, "t.txt"))
    check("esporta testo", "paragrafo di prova" in open(os.path.join(WORK, "t.txt"), encoding="utf-8").read())
    CV.to_html(d, os.path.join(WORK, "t.html"))
    check("esporta html", os.path.getsize(os.path.join(WORK, "t.html")) > 1000)
    CV.to_markdown(d, os.path.join(WORK, "t.md"))
    check("esporta markdown", "#" in open(os.path.join(WORK, "t.md"), encoding="utf-8").read())
    n = CV.to_excel(d, os.path.join(WORK, "t.xlsx"))
    check("esporta excel (tabelle)", n >= 1, str(n))
    CV.to_word(open(SAMPLE, "rb").read(), os.path.join(WORK, "t.docx"))
    check("esporta word", os.path.getsize(os.path.join(WORK, "t.docx")) > 5000)
    png = paths[0]
    im = CV.images_to_pdf([os.path.join(WORK, "img_out", "p_pag001.png")])
    check("immagini in PDF", im.page_count == 1)
    t = CV.text_to_pdf("riga uno\nriga due " * 200)
    check("testo in PDF", t.page_count >= 1 and "riga uno" in T(t[0]))
    h = CV.html_to_pdf("<h1>Titolo</h1><p>Paragrafo</p>")
    check("html in PDF", "Titolo" in T(h[0]))
    open(os.path.join(WORK, "a.txt"), "w", encoding="utf-8").write("ciao àè")
    check("any_to_pdf testo", "ciao" in CV.any_to_pdf(os.path.join(WORK, "a.txt"))[0].get_text())


def t_ocr():
    if not O.available():
        check("OCR disponibile", False)
        return
    d = pymupdf.open()
    p = d.new_page()
    p.insert_text((72, 100), "Riconoscimento ottico del testo", fontsize=24)
    pix = p.get_pixmap(dpi=150)
    d2 = pymupdf.open()
    p2 = d2.new_page()
    p2.insert_image(p2.rect, pixmap=pix)
    check("pagina scansione senza testo", O.needs_ocr(p2))
    n = O.ocr_page(p2, None, 300)
    t = T(p2)
    check("OCR riconosce", n >= 3 and "Riconoscimento" in t, t)
    hit = p2.search_for("Riconoscimento")
    check("OCR posizione", hit and abs(hit[0].x0 - 72) < 15 and abs(hit[0].y1 - 100) < 12, str(hit))
    for rot in (90, 180, 270):
        p3 = d2.new_page()
        p3.set_rotation(rot)
        IM.insert_image(p3, p3.rect * p3.derotation_matrix, data=pix.tobytes("png"))
        n = O.ocr_page(p3, None, 200)
        hit = p3.search_for("Riconoscimento")
        disp = hit[0] * p3.rotation_matrix if hit else None
        check(f"OCR pagina ruotata {rot}", n >= 3 and disp is not None and disp.width > disp.height * 3,
              f"{T(p3)!r} {disp}")
    # la filigrana su pagina ruotata deve apparire leggibile
    d4 = pymupdf.open()
    p4 = d4.new_page()
    p4.set_rotation(90)
    ST.watermark_text(d4, [0], "BOZZA", rotation=0, size=80, opacity=1)
    words = [w[0] for w in O.recognize_page(p4, None, 100)]
    check("filigrana dritta su pagina ruotata", "BOZZA" in words, str(words))


def t_compare():
    a = sample()
    b = sample()
    TE.find_replace(b, "Quadro", "Armadio")
    diffs = CP.compare(a, b)
    changed = [x for x in diffs if x.changed]
    check("confronto trova differenze", len(changed) == 4)
    CP.annotate(a, b, diffs)
    check("confronto evidenzia", len(list(a[0].annots())) == 1)
    html = CP.report_html(diffs, "a", "b")
    check("report confronto", "Armadio" in html)


def t_model():
    m = PdfModel(SAMPLE)
    with m.edit("ruota", structure=True):
        m.doc[0].set_rotation(90)
    with m.edit("testo", [1]):
        m.doc[1].insert_text((72, 700), "aggiunta")
    check("modificato", m.modified and m.can_undo())
    m.undo()
    check("annulla", "aggiunta" not in m.doc[1].get_text() and m.doc[0].rotation == 90)
    m.redo()
    check("ripeti", "aggiunta" in m.doc[1].get_text())
    try:
        with m.edit("errore", [0]):
            m.doc[0].insert_text((72, 720), "perso")
            raise RuntimeError("x")
    except RuntimeError:
        pass
    check("rollback su errore", "perso" not in m.doc[0].get_text())
    p = os.path.join(WORK, "salvato.pdf")
    m.save(p)
    check("salva", os.path.exists(p) and not m.modified and "aggiunta" in pymupdf.open(p)[1].get_text())
    # salvataggio sullo stesso file
    with m.edit("altro", [2]):
        m.doc[2].insert_text((72, 700), "seconda")
    m.save()
    check("salva sullo stesso file", "seconda" in pymupdf.open(p)[2].get_text())
    m.close()
    # immagine aperta come PDF
    png = os.path.join(WORK, "img.png")
    m = PdfModel(png)
    check("apre immagine", m.page_count == 1 and m.path is None and m.title == "img.pdf")


def t_signed_workflow():
    pfx = os.path.join(WORK, "id.pfx")
    SG.create_self_signed_id(pfx, "pw1234", "Giacomo Test", "g@example.com")
    data = open(SAMPLE, "rb").read()
    signed = SG.sign_pdf(data, SG.SignRequest(pfx, "pw1234", "Firma1", 0, (300, 700, 500, 760), "Test", "Bologna"),
                         842)
    sp = os.path.join(WORK, "firmato.pdf")
    open(sp, "wb").write(signed)
    v = SG.verify_pdf(signed)
    check("firma valida", len(v) == 1 and v[0].status == "valida", v[0].summary if v else "")
    m = PdfModel(sp)
    check("aperto in modalità incrementale", m.workpath is not None and m.signatures_preserved_on_save())
    with m.edit("nota", [1]):
        A.add_note(m.doc[1], pymupdf.Point(100, 100), "commento dopo la firma", "Note", A.Style())
    m.undo()
    m.redo()
    out = os.path.join(WORK, "firmato_annotato.pdf")
    m.save(out)
    v = SG.verify_pdf(open(out, "rb").read())
    check("firma intatta dopo annotazione", v and v[0].intact and v[0].valid, v[0].summary if v else "")
    # seconda firma su documento già firmato
    signed2 = SG.sign_pdf(open(out, "rb").read(), SG.SignRequest(pfx, "pw1234", "Firma2", 1, None), 842)
    v = SG.verify_pdf(signed2)
    check("doppia firma", len(v) == 2 and all(x.intact and x.valid for x in v), str([x.summary for x in v]))
    m.close()


ONLY = sys.argv[3].split(",") if len(sys.argv) > 3 else None
for fn in (t_ranges, t_textedit, t_pages, t_annots, t_images, t_stamping, t_compress, t_security, t_forms,
           t_convert, t_ocr, t_compare, t_model, t_signed_workflow):
    if ONLY and fn.__name__ not in ONLY:
        continue
    print(f"--- {fn.__name__}")
    section(fn)

fails = [r for r in results if not r[1]]
print(f"\n{len(results) - len(fails)} / {len(results)} verifiche superate")
for f in fails:
    print("FALLITA:", f[0], f[2][:300])
sys.exit(1 if fails else 0)
