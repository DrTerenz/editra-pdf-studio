"""Immagini nel contenuto della pagina: elenco, inserimento, spostamento, sostituzione."""
from __future__ import annotations

from dataclasses import dataclass

import pymupdf

from .common import apply_internal_redactions


@dataclass
class PageImage:
    xref: int
    rect: pymupdf.Rect          # coordinate PDF
    width: int
    height: int
    transform: tuple


def page_images(page: pymupdf.Page) -> list[PageImage]:
    out = []
    page._image_info = None  # PyMuPDF tiene in cache l'elenco: dopo una modifica va riletto
    for info in page.get_image_info(xrefs=True):
        r = pymupdf.Rect(info["bbox"])
        if r.is_empty or r.width < 2 or r.height < 2:
            continue
        out.append(PageImage(info.get("xref", 0), r, info.get("width", 0), info.get("height", 0),
                             tuple(info.get("transform", (1, 0, 0, 1, 0, 0)))))
    return out


def image_at(page: pymupdf.Page, point: pymupdf.Point) -> PageImage | None:
    best = None
    for im in page_images(page):
        if point in im.rect and (best is None or im.rect.get_area() < best.rect.get_area()):
            best = im
    return best


def image_bytes(doc: pymupdf.Document, xref: int) -> tuple[bytes, str]:
    """Immagine come PNG (con eventuale trasparenza) oppure nel formato originale se JPEG."""
    info = doc.extract_image(xref)
    smask = info.get("smask", 0)
    if info.get("ext") in ("jpeg", "jpg", "png") and not smask:
        return info["image"], info["ext"]
    pix = pymupdf.Pixmap(doc, xref)
    if smask:
        try:
            mask = pymupdf.Pixmap(doc, smask)
            pix = pymupdf.Pixmap(pix, mask)
        except Exception:
            pass
    if pix.colorspace and pix.colorspace.n > 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    return pix.tobytes("png"), "png"


def remove_image(page: pymupdf.Page, im: PageImage) -> None:
    """Toglie l'immagine da quell'area senza toccare testo e grafica."""
    r = pymupdf.Rect(im.rect)
    c = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
    # un rettangolo piccolo al centro basta: le immagini che lo toccano vengono rimosse
    small = pymupdf.Rect(c[0] - 0.5, c[1] - 0.5, c[0] + 0.5, c[1] + 0.5)
    apply_internal_redactions(page, [small], text=False, images=True)


def insert_image(page: pymupdf.Page, rect: pymupdf.Rect, data: bytes | None = None, path: str | None = None,
                 keep_proportion: bool = True, overlay: bool = True, rotate: int = 0) -> int:
    kw = {"stream": data} if data is not None else {"filename": path}
    # sulle pagine ruotate l'immagine va ruotata come la pagina per apparire dritta
    return page.insert_image(rect, keep_proportion=keep_proportion, overlay=overlay,
                             rotate=(rotate + page.rotation) % 360, **kw)


def move_image(page: pymupdf.Page, im: PageImage, new_rect: pymupdf.Rect, rotate: int = 0) -> None:
    data, _ = image_bytes(page.parent, im.xref)
    remove_image(page, im)
    insert_image(page, new_rect, data=data, keep_proportion=False, rotate=rotate)


def replace_image(page: pymupdf.Page, im: PageImage, path: str) -> None:
    remove_image(page, im)
    insert_image(page, im.rect, path=path, keep_proportion=True)


def rotate_image(page: pymupdf.Page, im: PageImage, angle: int) -> None:
    data, _ = image_bytes(page.parent, im.xref)
    remove_image(page, im)
    r = im.rect
    if angle % 180:
        cx, cy = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
        r = pymupdf.Rect(cx - r.height / 2, cy - r.width / 2, cx + r.height / 2, cy + r.width / 2)
    insert_image(page, r, data=data, keep_proportion=False, rotate=angle % 360)


def extract_all_images(doc: pymupdf.Document, out_dir: str, min_size: int = 16) -> list[str]:
    import os
    os.makedirs(out_dir, exist_ok=True)
    seen = set()
    paths = []
    for pno, page in enumerate(doc):
        for img in page.get_images(full=True):
            xref = img[0]
            if xref in seen:
                continue
            seen.add(xref)
            try:
                data, ext = image_bytes(doc, xref)
            except Exception:
                continue
            if img[2] < min_size or img[3] < min_size:
                continue
            p = os.path.join(out_dir, f"pag{pno + 1:03d}_img{xref}.{ext}")
            with open(p, "wb") as f:
                f.write(data)
            paths.append(p)
    return paths
