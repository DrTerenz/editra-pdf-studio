"""Crea un PDF di prova con testo, immagine, tabella, modulo, segnalibri, link."""
import sys, pymupdf
out = sys.argv[1]
d = pymupdf.open()
F = r"C:\Windows\Fonts"
for i in range(4):
    p = d.new_page()
    p.insert_font(fontname="cal", fontfile=F + r"\calibri.ttf")
    p.insert_font(fontname="calb", fontfile=F + r"\calibrib.ttf")
    p.insert_text((72, 80), f"Relazione tecnica – capitolo {i+1}", fontname="calb", fontsize=20, color=(0.2, 0.1, 0.5))
    body = ("Questo è un paragrafo di prova con accenti àèìòù e il simbolo dell'euro €. "
            "Serve a verificare la modifica del testo, la ricerca, la copia e l'evidenziazione. ") * 3
    p.insert_textbox(pymupdf.Rect(72, 100, 523, 220), body, fontname="cal", fontsize=11)
    p.insert_text((72, 250), "Contatti: mario.rossi@example.com, www.example.com, tel. 051 1234567", fontname="cal", fontsize=10)
    # tabella
    y = 280
    rows = [["Voce", "Quantità", "Prezzo"], ["Cavo", "10", "12,50"], ["Interruttore", "3", "45,00"], ["Quadro", "1", "320,00"]]
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            rect = pymupdf.Rect(72 + c * 150, y + r * 22, 72 + (c + 1) * 150, y + (r + 1) * 22)
            p.draw_rect(rect, color=(0, 0, 0), width=0.5)
            p.insert_text((rect.x0 + 4, rect.y1 - 6), val, fontname="calb" if r == 0 else "cal", fontsize=10)
    # immagine
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 120, 80), False)
    pix.set_rect(pix.irect, (90, 160, 220))
    p.insert_image(pymupdf.Rect(72, 400, 252, 520), pixmap=pix)
    p.insert_text((72, 560), "Firma: ______________________", fontname="cal", fontsize=11)
    if i == 0:
        w = pymupdf.Widget(); w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT; w.field_name = "nome"
        w.rect = pymupdf.Rect(300, 600, 500, 620); w.field_value = ""; p.add_widget(w)
        w = pymupdf.Widget(); w.field_type = pymupdf.PDF_WIDGET_TYPE_CHECKBOX; w.field_name = "accetto"
        w.rect = pymupdf.Rect(300, 630, 314, 644); p.add_widget(w)
        p.insert_link({"kind": pymupdf.LINK_GOTO, "from": pymupdf.Rect(72, 700, 200, 715), "page": 0})
        p.insert_text((72, 712), "Vai al capitolo 3", fontname="cal", fontsize=11, color=(0, 0, 1))
d.set_toc([[1, f"Capitolo {i+1}", i + 1] for i in range(4)])
d.set_metadata({"title": "Documento di prova", "author": "Test"})
d.save(out, garbage=3, deflate=True)
print("creato", out, d.page_count)
