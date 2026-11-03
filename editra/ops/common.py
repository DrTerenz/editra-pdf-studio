"""Utilità comuni: intervalli di pagine, colori, coordinate, redazioni interne."""
from __future__ import annotations

import re

import pymupdf


def parse_ranges(text: str, page_count: int) -> list[int]:
    """'1-3, 5, 8-' -> indici a base zero, nell'ordine scritto, senza duplicati.

    Accetta anche 'tutte', 'pari', 'dispari' e 'fine' (ultima pagina).
    """
    t = (text or "").strip().lower()
    if t in ("", "tutte", "all", "*"):
        return list(range(page_count))
    if t in ("pari", "even"):
        return [i for i in range(page_count) if (i + 1) % 2 == 0]
    if t in ("dispari", "odd"):
        return [i for i in range(page_count) if (i + 1) % 2 == 1]
    out: list[int] = []
    seen = set()
    for part in re.split(r"[,;\s]+", t):
        if not part:
            continue
        part = part.replace("fine", str(page_count)).replace("end", str(page_count))
        m = re.fullmatch(r"(\d*)\s*-\s*(\d*)", part)
        if m:
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else page_count
            step = 1 if b >= a else -1
            nums = range(a, b + step, step)
        elif part.isdigit():
            nums = [int(part)]
        else:
            raise ValueError(f"Intervallo non valido: '{part}'")
        for n in nums:
            if n < 1 or n > page_count:
                raise ValueError(f"La pagina {n} non esiste (il documento ha {page_count} pagine)")
            if n - 1 not in seen:
                seen.add(n - 1)
                out.append(n - 1)
    return out


def format_ranges(indices: list[int]) -> str:
    """[0,1,2,4] -> '1-3, 5'"""
    if not indices:
        return ""
    s = sorted(set(indices))
    parts = []
    start = prev = s[0]
    for x in s[1:]:
        if x == prev + 1:
            prev = x
            continue
        parts.append(f"{start + 1}-{prev + 1}" if prev > start else f"{start + 1}")
        start = prev = x
    parts.append(f"{start + 1}-{prev + 1}" if prev > start else f"{start + 1}")
    return ", ".join(parts)


def hex_to_rgb(h: str | None):
    if not h:
        return None
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def rgb_to_hex(rgb) -> str | None:
    if rgb is None or len(rgb) == 0:
        return None
    if len(rgb) == 1:
        rgb = (rgb[0],) * 3
    if len(rgb) == 4:  # CMYK
        c, m, y, k = rgb
        rgb = ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    return "#" + "".join(f"{max(0, min(255, round(v * 255))):02x}" for v in rgb[:3])


def int_to_hex(color: int) -> str:
    return f"#{color:06x}"


def to_display(page: pymupdf.Page, obj):
    """Coordinate PDF (pagina non ruotata) -> coordinate come la pagina appare."""
    return obj * page.rotation_matrix


def to_pdf(page: pymupdf.Page, obj):
    """Coordinate come appare la pagina -> coordinate PDF (non ruotate)."""
    return obj * page.derotation_matrix


def apply_internal_redactions(page: pymupdf.Page, rects, *, text=True, images=False, graphics=False, fill=None):
    """Toglie contenuto in alcune aree senza applicare le redazioni dell'utente.

    Le annotazioni di redazione già presenti sulla pagina (segnate dall'utente
    ma non ancora applicate) vengono messe da parte e ricreate dopo.
    """
    saved = []
    for a in list(page.annots(types=[pymupdf.PDF_ANNOT_REDACT])):
        saved.append((a.rect, a.colors, a.info))
        page.delete_annot(a)
    for r in rects:
        page.add_redact_annot(r, fill=fill if fill is not None else False, cross_out=False)
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_REMOVE if images else pymupdf.PDF_REDACT_IMAGE_NONE,
        graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED if graphics else pymupdf.PDF_REDACT_LINE_ART_NONE,
        text=pymupdf.PDF_REDACT_TEXT_REMOVE if text else pymupdf.PDF_REDACT_TEXT_NONE,
    )
    for rect, colors, info in saved:
        a = page.add_redact_annot(rect, fill=colors.get("fill") or (0, 0, 0))
        a.set_info(info)
        a.update()


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return str(n)


PAPER_SIZES = {
    "A3": (842, 1191), "A4": (595, 842), "A5": (420, 595), "A6": (298, 420),
    "Letter": (612, 792), "Legal": (612, 1008), "Tabloid": (792, 1224),
    "B4": (709, 1001), "B5": (499, 709),
}


# flag di estrazione: le legature (ﬁ, ﬂ) vengono espanse, così ricerca e copia funzionano
TEXT_FLAGS = pymupdf.TEXTFLAGS_TEXT & ~pymupdf.TEXT_PRESERVE_LIGATURES
DICT_FLAGS = (pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_LIGATURES & ~pymupdf.TEXT_PRESERVE_IMAGES)
SEARCH_FLAGS = pymupdf.TEXTFLAGS_SEARCH & ~pymupdf.TEXT_PRESERVE_LIGATURES
WORD_FLAGS = pymupdf.TEXTFLAGS_WORDS & ~pymupdf.TEXT_PRESERVE_LIGATURES


def search_page(page: pymupdf.Page, text: str, quads: bool = False):
    return page.search_for(text, quads=quads, flags=SEARCH_FLAGS)
