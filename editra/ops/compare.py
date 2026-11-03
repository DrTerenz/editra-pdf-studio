"""Confronto del testo di due documenti, parola per parola."""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field

import pymupdf

from .common import WORD_FLAGS


@dataclass
class PageDiff:
    page_a: int | None
    page_b: int | None
    removed: list[tuple[pymupdf.Rect, str]] = field(default_factory=list)   # in A
    added: list[tuple[pymupdf.Rect, str]] = field(default_factory=list)     # in B
    ops: list[tuple[str, str, str]] = field(default_factory=list)           # (tipo, testo A, testo B)

    @property
    def changed(self) -> bool:
        return bool(self.removed or self.added)


def _words(page: pymupdf.Page):
    return [(pymupdf.Rect(w[:4]), w[4]) for w in page.get_text("words", sort=True, flags=WORD_FLAGS)]


def compare(a: pymupdf.Document, b: pymupdf.Document) -> list[PageDiff]:
    out = []
    n = max(a.page_count, b.page_count)
    for i in range(n):
        wa = _words(a[i]) if i < a.page_count else []
        wb = _words(b[i]) if i < b.page_count else []
        d = PageDiff(i if i < a.page_count else None, i if i < b.page_count else None)
        sm = difflib.SequenceMatcher(a=[w for _, w in wa], b=[w for _, w in wb], autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            ta = " ".join(w for _, w in wa[i1:i2])
            tb = " ".join(w for _, w in wb[j1:j2])
            kind = {"replace": "Modificato", "delete": "Eliminato", "insert": "Aggiunto"}[tag]
            d.ops.append((kind, ta, tb))
            d.removed.extend(wa[i1:i2])
            d.added.extend(wb[j1:j2])
        out.append(d)
    return out


def annotate(a: pymupdf.Document, b: pymupdf.Document, diffs: list[PageDiff]) -> None:
    """Evidenzia in rosso le parole tolte (in A) e in verde quelle aggiunte (in B)."""
    for d in diffs:
        if d.page_a is not None and d.removed:
            p = a[d.page_a]
            h = p.add_highlight_annot([r for r, _ in d.removed])
            h.set_colors(stroke=(1, 0.45, 0.45))
            h.set_info(title="Confronto", content="Testo eliminato o modificato")
            h.update()
        if d.page_b is not None and d.added:
            p = b[d.page_b]
            h = p.add_highlight_annot([r for r, _ in d.added])
            h.set_colors(stroke=(0.45, 0.9, 0.45))
            h.set_info(title="Confronto", content="Testo aggiunto o modificato")
            h.update()


def report_html(diffs: list[PageDiff], name_a: str, name_b: str) -> str:
    import html
    rows = []
    changed = [d for d in diffs if d.changed]
    for d in changed:
        pg = (d.page_a if d.page_a is not None else d.page_b) + 1
        for kind, ta, tb in d.ops:
            color = {"Modificato": "#fff3cd", "Eliminato": "#fde2e2", "Aggiunto": "#e2f6e2"}[kind]
            rows.append(f"<tr style='background:{color}'><td>{pg}</td><td>{kind}</td>"
                        f"<td>{html.escape(ta)}</td><td>{html.escape(tb)}</td></tr>")
    head = (f"<h2>Confronto documenti</h2><p><b>A:</b> {html.escape(name_a)}<br><b>B:</b> {html.escape(name_b)}</p>"
            f"<p>Pagine con differenze: <b>{len(changed)}</b> su {len(diffs)}.</p>")
    if not rows:
        return head + "<p>Nessuna differenza nel testo.</p>"
    return (head + "<table border='1' cellspacing='0' cellpadding='4' width='100%'>"
            "<tr><th>Pag.</th><th>Tipo</th><th>Testo in A</th><th>Testo in B</th></tr>" + "".join(rows) + "</table>")
