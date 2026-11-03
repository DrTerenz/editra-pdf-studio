"""Riduzione delle dimensioni del file."""
from __future__ import annotations

from dataclasses import dataclass

import pymupdf
from ..i18n import T

PRESETS = {
    "Alta qualità (stampa)": dict(dpi_threshold=250, dpi_target=200, quality=85),
    "Equilibrata": dict(dpi_threshold=180, dpi_target=150, quality=72),
    "Massima compressione (schermo)": dict(dpi_threshold=110, dpi_target=96, quality=55),
    "Solo pulizia (senza toccare le immagini)": None,
}


@dataclass
class CompressOptions:
    images: bool = True
    dpi_threshold: int = 180
    dpi_target: int = 150
    quality: int = 72
    grayscale: bool = False
    subset_fonts: bool = True
    remove_metadata: bool = False
    remove_thumbnails: bool = True
    remove_embedded_files: bool = False
    remove_annotations: bool = False
    flatten_forms: bool = False
    object_streams: bool = True


def compress(data: bytes, opt: CompressOptions, password: str | None = None, progress=None) -> bytes:
    """Ritorna i byte del PDF compresso (il documento originale non viene toccato)."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    if doc.needs_pass and password:
        doc.authenticate(password)
    step = lambda m: progress(m) if progress else None
    if opt.remove_annotations:
        step(T('Rimozione annotazioni'))
        for page in doc:
            for a in list(page.annots()):
                page.delete_annot(a)
    if opt.flatten_forms:
        step(T('Appiattimento moduli'))
        try:
            doc.bake(annots=False, widgets=True)
        except Exception:
            pass
    if opt.images:
        step(T('Ricompressione immagini'))
        try:
            doc.rewrite_images(dpi_threshold=opt.dpi_threshold, dpi_target=opt.dpi_target,
                               quality=opt.quality, set_to_gray=opt.grayscale)
        except Exception:
            pass
    if opt.subset_fonts:
        step(T('Riduzione dei font'))
        try:
            doc.subset_fonts()
        except Exception:
            pass
    if opt.remove_embedded_files:
        for name in list(doc.embfile_names()):
            doc.embfile_del(name)
    if opt.remove_metadata or opt.remove_thumbnails:
        step(T('Pulizia'))
        try:
            doc.scrub(attached_files=False, clean_pages=False, embedded_files=False, hidden_text=False,
                      javascript=False, metadata=opt.remove_metadata, redactions=False, redact_images=0,
                      remove_links=False, reset_fields=False, reset_responses=False,
                      thumbnails=opt.remove_thumbnails, xml_metadata=opt.remove_metadata)
        except Exception:
            pass
    step(T('Scrittura'))
    out = doc.tobytes(garbage=4, deflate=True, deflate_images=True, deflate_fonts=True, clean=True,
                      use_objstms=1 if opt.object_streams else 0)
    doc.close()
    return out
