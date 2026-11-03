"""Organizzazione delle pagine: unione, divisione, inserimento, rotazione, ritaglio."""
from __future__ import annotations

import os
from pathlib import Path

import pymupdf

from .common import PAPER_SIZES, parse_ranges


def open_any(path: str, password: str | None = None) -> pymupdf.Document:
    """Apre un PDF o lo converte (immagini, XPS, EPUB...)."""
    ext = Path(path).suffix.lower()
    if ext == ".pdf":
        d = pymupdf.open(path)
    else:
        src = pymupdf.open(path)
        d = pymupdf.open("pdf", src.convert_to_pdf())
        src.close()
    if d.needs_pass:
        if not password or not d.authenticate(password):
            raise PermissionError(f"Serve la password per aprire {os.path.basename(path)}")
    return d


def merge_files(items: list[tuple[str, str]], passwords: dict[str, str] | None = None,
                bookmarks: bool = True) -> pymupdf.Document:
    """items: [(percorso, intervallo pagine)] -> nuovo documento.

    Con bookmarks=True ogni file diventa un segnalibro di primo livello e i suoi
    segnalibri vengono spostati sotto.
    """
    out = pymupdf.open()
    toc = []
    for path, rng in items:
        src = open_any(path, (passwords or {}).get(path))
        pages = parse_ranges(rng, src.page_count)
        start = out.page_count
        src_toc = src.get_toc(simple=False) if bookmarks else []
        for p in pages:
            out.insert_pdf(src, from_page=p, to_page=p, links=True, annots=True, widgets=True)
        if bookmarks:
            toc.append([1, Path(path).stem, start + 1])
            mapping = {p + 1: start + i + 1 for i, p in enumerate(pages)}
            for lvl, title, pg, *rest in src_toc:
                if pg in mapping:
                    toc.append([lvl + 1, title, mapping[pg]])
        src.close()
    if bookmarks and toc:
        try:
            out.set_toc(_fix_toc_levels(toc))
        except Exception:
            pass
    return out


def _fix_toc_levels(toc):
    """Garantisce che i livelli crescano al massimo di 1 alla volta."""
    fixed = []
    prev = 0
    for lvl, title, pg in toc:
        lvl = min(lvl, prev + 1)
        fixed.append([lvl, title, pg])
        prev = lvl
    return fixed


def insert_from_file(doc: pymupdf.Document, path: str, at: int, rng: str = "", password: str | None = None) -> int:
    """Inserisce pagine di un altro file prima dell'indice `at`. Ritorna quante."""
    src = open_any(path, password)
    pages = parse_ranges(rng, src.page_count)
    for k, p in enumerate(pages):
        doc.insert_pdf(src, from_page=p, to_page=p, start_at=at + k)
    src.close()
    return len(pages)


def insert_blank(doc: pymupdf.Document, at: int, count: int = 1, size: tuple[float, float] | None = None) -> None:
    if size is None:
        ref = doc[min(max(at - 1, 0), doc.page_count - 1)] if doc.page_count else None
        size = (ref.rect.width, ref.rect.height) if ref else PAPER_SIZES["A4"]
    for k in range(count):
        doc.new_page(pno=at + k, width=size[0], height=size[1])


def delete_pages(doc: pymupdf.Document, pages: list[int]) -> None:
    if len(set(pages)) >= doc.page_count:
        raise ValueError("Non si possono eliminare tutte le pagine del documento")
    doc.delete_pages(sorted(set(pages)))


def rotate_pages(doc: pymupdf.Document, pages: list[int], angle: int) -> None:
    for p in pages:
        page = doc[p]
        page.set_rotation((page.rotation + angle) % 360)


def move_pages(doc: pymupdf.Document, pages: list[int], to: int) -> list[int]:
    """Sposta un gruppo di pagine prima dell'indice `to` (indice nel documento originale).

    Ritorna i nuovi indici delle pagine spostate.
    """
    pages = sorted(set(pages))
    order = [i for i in range(doc.page_count) if i not in pages]
    insert_at = len([i for i in order if i < to])
    new_order = order[:insert_at] + pages + order[insert_at:]
    doc.select(new_order)
    return list(range(insert_at, insert_at + len(pages)))


def duplicate_pages(doc: pymupdf.Document, pages: list[int]) -> None:
    for p in sorted(pages, reverse=True):
        doc.fullcopy_page(p, p + 1)


def reverse_pages(doc: pymupdf.Document) -> None:
    doc.select(list(range(doc.page_count - 1, -1, -1)))


def extract_pages(doc: pymupdf.Document, pages: list[int]) -> pymupdf.Document:
    out = pymupdf.open()
    for p in pages:
        out.insert_pdf(doc, from_page=p, to_page=p)
    return out


def replace_pages(doc: pymupdf.Document, pages: list[int], path: str, src_range: str = "",
                  password: str | None = None) -> None:
    """Sostituisce le pagine indicate con quelle di un altro file (stesso numero)."""
    src = open_any(path, password)
    src_pages = parse_ranges(src_range, src.page_count)
    if len(src_pages) < len(pages):
        raise ValueError(f"Il file sorgente ha solo {len(src_pages)} pagine nell'intervallo scelto, ne servono {len(pages)}")
    for target, sp in zip(sorted(pages, reverse=True), list(reversed(src_pages[:len(pages)]))):
        doc.insert_pdf(src, from_page=sp, to_page=sp, start_at=target)
        doc.delete_page(target + 1)
    src.close()


def split_document(doc: pymupdf.Document, mode: str, value, out_dir: str, base: str) -> list[str]:
    """Divide il documento.

    mode: 'every' (ogni N pagine), 'ranges' (lista di intervalli separati da ';'),
          'bookmarks' (un file per segnalibro di primo livello), 'size' (max MB per file).
    """
    os.makedirs(out_dir, exist_ok=True)
    groups: list[tuple[str, list[int]]] = []
    n = doc.page_count
    if mode == "every":
        k = max(1, int(value))
        for i, s in enumerate(range(0, n, k), 1):
            groups.append((f"{base}_parte{i}", list(range(s, min(n, s + k)))))
    elif mode == "ranges":
        for i, part in enumerate([p for p in str(value).split(";") if p.strip()], 1):
            groups.append((f"{base}_parte{i}", parse_ranges(part, n)))
    elif mode == "bookmarks":
        toc = [t for t in doc.get_toc() if t[0] == 1 and t[2] > 0]
        if not toc:
            raise ValueError("Il documento non ha segnalibri di primo livello")
        starts = [t[2] - 1 for t in toc]
        for i, (t, s) in enumerate(zip(toc, starts)):
            e = starts[i + 1] if i + 1 < len(starts) else n
            if e > s:
                safe = "".join(c for c in t[1] if c not in '\\/:*?"<>|').strip()[:60] or f"parte{i + 1}"
                groups.append((f"{base}_{i + 1:02d}_{safe}", list(range(s, e))))
    elif mode == "size":
        limit = float(value) * 1024 * 1024
        cur: list[int] = []
        idx = 1
        for p in range(n):
            trial = cur + [p]
            size = len(extract_pages(doc, trial).tobytes(garbage=3, deflate=True))
            if size > limit and cur:
                groups.append((f"{base}_parte{idx}", cur))
                idx += 1
                cur = [p]
            else:
                cur = trial
        if cur:
            groups.append((f"{base}_parte{idx}", cur))
    else:
        raise ValueError(mode)
    paths = []
    for name, pages in groups:
        if not pages:
            continue
        out = extract_pages(doc, pages)
        path = os.path.join(out_dir, name + ".pdf")
        out.save(path, garbage=3, deflate=True)
        out.close()
        paths.append(path)
    return paths


def crop_pages(doc: pymupdf.Document, pages: list[int], margins: tuple[float, float, float, float] | None = None,
               rect: pymupdf.Rect | None = None) -> None:
    """Ritaglia: margini (sinistro, alto, destro, basso) in punti oppure rettangolo (coordinate PDF)."""
    for p in pages:
        page = doc[p]
        mb = page.mediabox
        if rect is not None:
            r = pymupdf.Rect(rect) & mb
        else:
            l, t, r_, b = margins
            cur = page.cropbox
            r = pymupdf.Rect(cur.x0 + l, cur.y0 + t, cur.x1 - r_, cur.y1 - b)
        if r.is_empty or r.width < 10 or r.height < 10:
            raise ValueError("Il ritaglio lascerebbe una pagina vuota")
        page.set_cropbox(r)


def reset_crop(doc: pymupdf.Document, pages: list[int]) -> None:
    for p in pages:
        page = doc[p]
        page.set_cropbox(page.mediabox)


def resize_pages(doc: pymupdf.Document, pages: list[int], size: tuple[float, float], fit: bool = True) -> None:
    """Porta le pagine a un nuovo formato scalando il contenuto (mantiene le proporzioni)."""
    src = pymupdf.open("pdf", doc.tobytes())
    for p in sorted(pages, reverse=True):
        old = src[p]
        w, h = size
        if (old.rect.width > old.rect.height) != (w > h):
            w, h = h, w  # mantiene l'orientamento della pagina
        doc.delete_page(p)
        newp = doc.new_page(pno=p, width=w, height=h)
        newp.show_pdf_page(newp.rect, src, p, keep_proportion=fit)
    src.close()


def n_up(doc: pymupdf.Document, per_sheet: int, size: tuple[float, float] = PAPER_SIZES["A4"]) -> pymupdf.Document:
    """Più pagine per foglio (2, 4, 6, 9, 16)."""
    layout = {2: (2, 1), 4: (2, 2), 6: (3, 2), 9: (3, 3), 16: (4, 4)}[per_sheet]
    cols, rows = layout
    w, h = size
    if per_sheet in (2, 6):
        w, h = h, w  # foglio orizzontale
    out = pymupdf.open()
    cw, ch = w / cols, h / rows
    for i in range(0, doc.page_count, per_sheet):
        sheet = out.new_page(width=w, height=h)
        for k in range(per_sheet):
            if i + k >= doc.page_count:
                break
            c, r = k % cols, k // cols
            cell = pymupdf.Rect(c * cw, r * ch, (c + 1) * cw, (r + 1) * ch) + (6, 6, -6, -6)
            sheet.show_pdf_page(cell, doc, i + k)
    return out


def interleave(front: pymupdf.Document, back: pymupdf.Document, reverse_back: bool = True) -> pymupdf.Document:
    """Unisce fronte e retro scansionati separatamente (1A, 1B, 2A, 2B...)."""
    out = pymupdf.open()
    b_pages = list(range(back.page_count))
    if reverse_back:
        b_pages.reverse()
    for i in range(max(front.page_count, len(b_pages))):
        if i < front.page_count:
            out.insert_pdf(front, from_page=i, to_page=i)
        if i < len(b_pages):
            out.insert_pdf(back, from_page=b_pages[i], to_page=b_pages[i])
    return out


def blank_pages(doc: pymupdf.Document, threshold: float = 0.995) -> list[int]:
    """Pagine (quasi) vuote: senza testo e con pixel quasi tutti bianchi."""
    found = []
    for i, page in enumerate(doc):
        if page.get_text().strip():
            continue
        pix = page.get_pixmap(matrix=pymupdf.Matrix(0.3, 0.3), colorspace=pymupdf.csGRAY)
        samples = pix.samples
        if not samples:
            found.append(i)
            continue
        white = sum(1 for b in samples if b > 245)
        if white / len(samples) >= threshold:
            found.append(i)
    return found


def set_page_labels(doc: pymupdf.Document, rules: list[dict]) -> None:
    """rules: [{'startpage': 0, 'prefix': '', 'style': 'D'|'r'|'R'|'a'|'A', 'firstpagenum': 1}]"""
    doc.set_page_labels(rules)
