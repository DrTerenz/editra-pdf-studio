"""Riconoscimento del testo (OCR) con il motore integrato in Windows 10/11.

Il testo riconosciuto viene scritto invisibile sopra l'immagine della pagina:
la pagina resta identica ma diventa ricercabile, selezionabile e copiabile.
Le lingue disponibili sono quelle installate in Windows (Impostazioni > Lingua).
"""
from __future__ import annotations

import asyncio
import os

import pymupdf


def available() -> bool:
    try:
        from winrt.windows.media.ocr import OcrEngine  # noqa: F401
        return True
    except Exception:
        return False


def languages() -> list[tuple[str, str]]:
    from winrt.windows.media.ocr import OcrEngine
    return [(l.language_tag, l.display_name) for l in OcrEngine.available_recognizer_languages]


async def _recognize(png: bytes, lang: str | None):
    from winrt.windows.globalization import Language
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    stream = InMemoryRandomAccessStream()
    w = DataWriter(stream)
    w.write_bytes(png)
    await w.store_async()
    await w.flush_async()
    w.detach_stream()
    stream.seek(0)
    dec = await BitmapDecoder.create_async(stream)
    bmp = await dec.get_software_bitmap_async()
    eng = OcrEngine.try_create_from_language(Language(lang)) if lang else OcrEngine.try_create_from_user_profile_languages()
    if eng is None:
        raise RuntimeError(f"Lingua OCR non disponibile: {lang}")
    res = await eng.recognize_async(bmp)
    out = []
    for line in res.lines:
        words = [(x.text, x.bounding_rect.x, x.bounding_rect.y, x.bounding_rect.width, x.bounding_rect.height)
                 for x in line.words]
        out.append(words)
    return out


def recognize_page(page: pymupdf.Page, lang: str | None = None, dpi: int = 300):
    """Ritorna [(testo, rettangolo in coordinate di visualizzazione)] parola per parola."""
    zoom = dpi / 72
    # immagine limitata a 10000 px per lato (limite del motore di Windows)
    max_side = max(page.rect.width, page.rect.height) * zoom
    if max_side > 9800:
        zoom *= 9800 / max_side
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), annots=False)
    lines = asyncio.run(_recognize(pix.tobytes("png"), lang))
    words = []
    for line in lines:
        for text, x, y, w, h in line:
            words.append((text, pymupdf.Rect(x / zoom, y / zoom, (x + w) / zoom, (y + h) / zoom)))
    return words


_FONT = None


def _font_file() -> str | None:
    p = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf")
    return p if os.path.exists(p) else None


def ocr_page(page: pymupdf.Page, lang: str | None = None, dpi: int = 300) -> int:
    """Aggiunge lo strato di testo invisibile. Ritorna il numero di parole."""
    words = recognize_page(page, lang, dpi)
    if not words:
        return 0
    ff = _font_file()
    fontname = "OcrF"
    if ff:
        page.insert_font(fontname=fontname, fontfile=ff)
        font = pymupdf.Font(fontfile=ff)
    else:
        fontname = "helv"
        font = pymupdf.Font("helv")
    rot = page.rotation % 360
    for text, r_disp in words:
        size = max(4.0, r_disp.height * 0.85)
        tl = font.text_length(text, fontsize=size) or 1
        # punto base in basso a sinistra della parola, come appare a schermo
        base_disp = pymupdf.Point(r_disp.x0, r_disp.y1 - r_disp.height * 0.18)
        pt = base_disp * page.derotation_matrix
        sx = r_disp.width / tl
        kw = {}
        if rot == 0 and 0.2 < sx < 5:
            kw["morph"] = (pt, pymupdf.Matrix(sx, 1))
        try:
            page.insert_text(pt, text, fontsize=size, fontname=fontname, render_mode=3, rotate=rot, **kw)
        except Exception:
            page.insert_text(pt, text, fontsize=size, fontname="helv", render_mode=3, rotate=rot)
    return len(words)


def needs_ocr(page: pymupdf.Page) -> bool:
    """Vero se la pagina non ha testo estraibile ma contiene immagini."""
    return not page.get_text().strip() and bool(page.get_images())
