"""Protezione: permessi, metadati, pulizia del documento, redazione."""
from __future__ import annotations

import re

import pymupdf

from .common import hex_to_rgb, search_page
from ..i18n import T

PERMISSIONS = [
    (T('Stampa'), pymupdf.PDF_PERM_PRINT),
    (T('Stampa ad alta qualità'), pymupdf.PDF_PERM_PRINT_HQ),
    (T('Modifica del contenuto'), pymupdf.PDF_PERM_MODIFY),
    (T('Copia di testo e immagini'), pymupdf.PDF_PERM_COPY),
    (T('Commenti e annotazioni'), pymupdf.PDF_PERM_ANNOTATE),
    (T('Compilazione moduli'), pymupdf.PDF_PERM_FORM),
    (T('Accessibilità'), pymupdf.PDF_PERM_ACCESSIBILITY),
    (T('Assemblaggio (inserire, ruotare, eliminare pagine)'), pymupdf.PDF_PERM_ASSEMBLE),
]

# modelli per la ricerca e redazione automatica
PATTERNS = {
    "Indirizzi e-mail": r"[\w.+-]+@[\w-]+\.[\w.-]+",
    "Numeri di telefono": r"(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)\d{3,4}[\s.-]?\d{3,4}",
    "Codice fiscale": r"\b[A-Z]{6}\d{2}[A-EHLMPR-T]\d{2}[A-Z]\d{3}[A-Z]\b",
    "IBAN": r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]){11,30}\b",
    "Partita IVA": r"\b(?:IT)?\d{11}\b",
    "Carte di pagamento": r"\b(?:\d[ -]?){13,19}\b",
    "Date": r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b",
    "Indirizzi web": r"(?:https?://|www\.)\S+",
}


def find_pattern(doc: pymupdf.Document, pattern: str, pages=None, regex: bool = True,
                 match_case: bool = False) -> list[tuple[int, pymupdf.Rect, str]]:
    """Occorrenze di un modello (regex sul testo di ogni riga) con i rettangoli dei caratteri."""
    hits = []
    flags = 0 if match_case else re.IGNORECASE
    rx = re.compile(pattern if regex else re.escape(pattern), flags)
    for pno in (pages if pages is not None else range(doc.page_count)):
        page = doc[pno]
        if not regex:
            for r in search_page(page, pattern):
                hits.append((pno, r, page.get_textbox(r).strip()))
            continue
        raw = page.get_text("rawdict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
        for b in raw["blocks"]:
            for l in b.get("lines", []):
                chars = [c for s in l["spans"] for c in s["chars"]]
                text = "".join(c["c"] for c in chars)
                for m in rx.finditer(text):
                    if m.end() <= m.start():
                        continue
                    r = pymupdf.Rect()
                    for c in chars[m.start():m.end()]:
                        r |= pymupdf.Rect(c["bbox"])
                    if not r.is_empty:
                        hits.append((pno, r, m.group(0)))
    return hits


def mark_redactions(doc: pymupdf.Document, hits, fill: str = "#000000", overlay_text: str = "") -> int:
    for pno, rect, _ in hits:
        page = doc[pno]
        a = page.add_redact_annot(rect, text=overlay_text or None, fill=hex_to_rgb(fill),
                                  text_color=(1, 1, 1), fontsize=8)
        a.set_colors(stroke=(1, 0, 0))
        a.update()
    return len(hits)


def mark_area(page: pymupdf.Page, rect: pymupdf.Rect, fill: str = "#000000", overlay_text: str = ""):
    a = page.add_redact_annot(rect, text=overlay_text or None, fill=hex_to_rgb(fill), text_color=(1, 1, 1),
                              fontsize=8)
    a.set_colors(stroke=(1, 0, 0))
    a.update()
    return a


def pending_redactions(doc: pymupdf.Document) -> int:
    return sum(len(list(p.annots(types=[pymupdf.PDF_ANNOT_REDACT]))) for p in doc)


def apply_redactions(doc: pymupdf.Document, images: str = "pixels") -> int:
    """Applica tutte le redazioni: il contenuto sotto viene eliminato definitivamente."""
    mode = {"pixels": pymupdf.PDF_REDACT_IMAGE_PIXELS, "remove": pymupdf.PDF_REDACT_IMAGE_REMOVE,
            "none": pymupdf.PDF_REDACT_IMAGE_NONE}[images]
    n = 0
    for page in doc:
        k = len(list(page.annots(types=[pymupdf.PDF_ANNOT_REDACT])))
        if k:
            page.apply_redactions(images=mode, graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                                  text=pymupdf.PDF_REDACT_TEXT_REMOVE)
            n += k
    return n


def sanitize(doc: pymupdf.Document, *, metadata=True, javascript=True, embedded_files=True, hidden_text=True,
             links=False, thumbnails=True, xml_metadata=True, reset_fields=False, comments=False) -> None:
    """Rimuove informazioni nascoste (come la 'pulizia del documento' dei programmi professionali)."""
    if comments:
        for page in doc:
            for a in list(page.annots()):
                if a.type[0] != pymupdf.PDF_ANNOT_REDACT:
                    page.delete_annot(a)
    doc.scrub(attached_files=embedded_files, clean_pages=True, embedded_files=embedded_files,
              hidden_text=hidden_text, javascript=javascript, metadata=metadata, redactions=False,
              redact_images=0, remove_links=links, reset_fields=reset_fields, reset_responses=comments,
              thumbnails=thumbnails, xml_metadata=xml_metadata)


METADATA_FIELDS = [("title", T('Titolo')), ("author", T('Autore')), ("subject", T('Oggetto')),
                   ("keywords", T('Parole chiave')), ("creator", T('Applicazione di origine')),
                   ("producer", T('Produttore PDF'))]


def set_metadata(doc: pymupdf.Document, values: dict) -> None:
    md = dict(doc.metadata or {})
    md.update({k: v for k, v in values.items() if k in dict(METADATA_FIELDS)})
    md["modDate"] = pymupdf.get_pdf_now()
    doc.set_metadata(md)


def document_info(doc: pymupdf.Document, path: str | None, size: int | None) -> list[tuple[str, str]]:
    md = doc.metadata or {}
    page = doc[0] if doc.page_count else None

    def d(s):
        if s and s.startswith("D:") and len(s) >= 16:
            return f"{s[8:10]}/{s[6:8]}/{s[2:6]} {s[10:12]}:{s[12:14]}"
        return s or "—"

    from .common import human_size
    fonts = set()
    for p in doc:
        for f in p.get_fonts():
            fonts.add(f"{f[3]} ({f[1]}{T(', incorporato') if f[1] not in ('n/a', '') else ''})")
        if len(fonts) > 60:
            break
    rows = [
        (T('File'), path or "—"), (T('Dimensione'), human_size(size) if size else "—"),
        (T('Pagine'), str(doc.page_count)),
        (T('Formato pagina'), T('{:.0f} × {:.0f} mm').format(page.rect.width * 25.4 / 72, page.rect.height * 25.4 / 72) if page else "—"),
        (T('Versione PDF'), md.get("format", "—")), (T('Titolo'), md.get("title") or "—"),
        (T('Autore'), md.get("author") or "—"), (T('Oggetto'), md.get("subject") or "—"),
        (T('Parole chiave'), md.get("keywords") or "—"), (T('Creato con'), md.get("creator") or "—"),
        (T('Produttore'), md.get("producer") or "—"), (T('Creato il'), d(md.get("creationDate"))),
        (T('Modificato il'), d(md.get("modDate"))), (T('Cifratura'), md.get("encryption") or T('Nessuna')),
        (T('Moduli'), T('Sì') if doc.is_form_pdf else "No"),
        (T('Firme digitali'), T('Sì') if (doc.get_sigflags() > 0) else "No"),
        (T('Allegati'), str(doc.embfile_count())), (T('Font'), "\n".join(sorted(fonts)) or "—"),
    ]
    return rows
