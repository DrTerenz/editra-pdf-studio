"""Modello di un documento aperto: file, annulla/ripeti, salvataggio, cache del testo."""
from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pymupdf
from PySide6.QtCore import QObject, Signal

from .i18n import T
from .ops.common import DICT_FLAGS, WORD_FLAGS

MAX_UNDO = 30

# estensioni che PyMuPDF sa aprire e che convertiamo in PDF all'apertura
CONVERTIBLE = (".xps", ".oxps", ".epub", ".cbz", ".fb2", ".mobi", ".svg",
               ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".jxr", ".pnm", ".webp", ".txt")


class PasswordRequired(Exception):
    pass


class PdfModel(QObject):
    changed = Signal(object)          # set di indici pagina modificati, oppure None = tutte
    structure_changed = Signal()      # pagine aggiunte/rimosse/spostate
    modified_changed = Signal(bool)
    saved = Signal(str)

    def __init__(self, path: str | None = None, data: bytes | None = None,
                 password: str | None = None, title: str | None = None):
        super().__init__()
        self.path: str | None = None
        self.password = password
        self.modified = False
        self._undo: list[tuple[str, bytes]] = []
        self._redo: list[tuple[str, bytes]] = []
        self._rev: dict[int, int] = {}
        self.global_rev = 0
        self._text_cache: dict = {}
        # opzioni di cifratura da applicare al prossimo salvataggio
        self.encryption: dict | None = None
        self.fonts_inserted = False
        self.converted_from: str | None = None
        self._title = title
        self.workpath: str | None = None

        if path is not None:
            ext = Path(path).suffix.lower()
            if ext == ".pdf" or ext not in CONVERTIBLE:
                raw = Path(path).read_bytes()
                self.doc = pymupdf.open(stream=raw, filetype="pdf")
                self.path = str(path)
            else:
                src = pymupdf.open(path)
                pdf_bytes = src.convert_to_pdf()
                src.close()
                self.doc = pymupdf.open("pdf", pdf_bytes)
                self.converted_from = str(path)
                self._title = Path(path).stem + ".pdf"
                self.modified = True
        elif data is not None:
            self.doc = pymupdf.open(stream=data, filetype="pdf")
            self.modified = True
        else:
            self.doc = pymupdf.open()
            self.doc.new_page(width=595, height=842)
            self.modified = True

        if self.doc.needs_pass:
            if not password or not self.doc.authenticate(password):
                raise PasswordRequired()

        # PDF firmati: si lavora su una copia su disco e si salva in modo incrementale,
        # così le firme esistenti restano valide (le modifiche si aggiungono in coda).
        self.workpath: str | None = None
        if self.path and self.has_signatures():
            fd, self.workpath = tempfile.mkstemp(suffix=".pdf", prefix="editra_firmato_")
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
            self.doc.close()
            self._open_work()
            if self.doc.is_repaired or not self.doc.can_save_incrementally():
                # file danneggiato: niente salvataggi incrementali, si lavora in memoria
                self.doc.close()
                os.remove(self.workpath)
                self.workpath = None
                self.doc = pymupdf.open(stream=raw, filetype="pdf")
                if self.doc.needs_pass and password:
                    self.doc.authenticate(password)

    # ------------------------------------------------------------------ info
    @property
    def title(self) -> str:
        if self.path:
            return os.path.basename(self.path)
        return self._title or "Senza titolo.pdf"

    @property
    def page_count(self) -> int:
        return self.doc.page_count

    def page(self, i: int) -> pymupdf.Page:
        return self.doc[i]

    def page_rev(self, i: int) -> tuple[int, int]:
        return self.global_rev, self._rev.get(i, 0)

    def is_encrypted(self) -> bool:
        return bool(self.doc.is_encrypted) or bool(self.doc.metadata.get("encryption"))

    def has_signatures(self) -> bool:
        """True se nel documento c'è almeno una firma digitale apposta (non un campo vuoto)."""
        try:
            if self.doc.get_sigflags() <= 0:
                return False
            for page in self.doc:
                for w in page.widgets(types=[pymupdf.PDF_WIDGET_TYPE_SIGNATURE]):
                    if self._sig_value(w.xref):
                        return True
        except Exception:
            return False
        return False

    def _sig_value(self, xref: int) -> bool:
        doc = self.doc
        kind, _ = doc.xref_get_key(xref, "V")
        if kind != "null":
            return True
        kind, val = doc.xref_get_key(xref, "Parent")
        if kind == "xref":
            return doc.xref_get_key(int(val.split()[0]), "V")[0] != "null"
        return False

    def permissions_ok(self, perm: int) -> bool:
        return bool(self.doc.permissions & perm)

    # --------------------------------------------------------------- testo
    def text_dict(self, i: int) -> dict:
        key = ("dict", i, self.page_rev(i))
        d = self._text_cache.get(key)
        if d is None:
            d = self.doc[i].get_text("dict", flags=DICT_FLAGS)
            self._text_cache[key] = d
        return d

    def words(self, i: int) -> list:
        key = ("words", i, self.page_rev(i))
        w = self._text_cache.get(key)
        if w is None:
            w = self.doc[i].get_text("words", sort=False, flags=WORD_FLAGS)
            self._text_cache[key] = w
        return w

    def _trim_cache(self) -> None:
        if len(self._text_cache) > 200:
            self._text_cache.clear()

    # --------------------------------------------------------- modifiche
    def _open_work(self) -> None:
        self.doc = pymupdf.open(self.workpath)
        if self.doc.needs_pass and self.password:
            self.doc.authenticate(self.password)

    def _flush_work(self) -> None:
        """Scrive in coda al file di lavoro le modifiche ancora in memoria."""
        if self.workpath and self.doc.is_dirty:
            if self.doc.can_save_incrementally():
                self.doc.saveIncr()
            else:
                # non più possibile: si passa al salvataggio completo
                data = self.doc.tobytes()
                with open(self.workpath, "wb") as f:
                    f.write(data)
                self.doc.close()
                self._open_work()

    def _snapshot(self) -> bytes:
        if self.workpath:
            self._flush_work()
            with open(self.workpath, "rb") as f:
                return f.read()
        return self.doc.tobytes()

    def current_bytes(self) -> bytes:
        """Byte del documento come verrebbe salvato ora (per verifica e firma)."""
        if self.workpath and self.encryption is None:
            return self._snapshot()
        return self.to_bytes()

    def _restore(self, data: bytes) -> None:
        self.doc.close()
        if self.workpath:
            with open(self.workpath, "wb") as f:
                f.write(data)
            self._open_work()
        else:
            self.doc = pymupdf.open(stream=data, filetype="pdf")
            if self.doc.needs_pass and self.password:
                self.doc.authenticate(self.password)
        self.global_rev += 1
        self._rev.clear()
        self._text_cache.clear()

    def _set_modified(self, value: bool) -> None:
        if self.modified != value:
            self.modified = value
            self.modified_changed.emit(value)

    @contextmanager
    def edit(self, label: str, pages=None, structure: bool = False):
        """Raggruppa una modifica annullabile.

        pages: indici delle pagine toccate (None = tutte). In caso di errore il
        documento torna allo stato precedente e l'eccezione risale al chiamante.
        """
        snap = self._snapshot()
        try:
            yield self.doc
        except Exception:
            self._restore(snap)
            self.structure_changed.emit()
            raise
        self._undo.append((label, snap))
        if len(self._undo) > MAX_UNDO:
            self._undo.pop(0)
        self._redo.clear()
        self._after_change(pages, structure)

    def _after_change(self, pages, structure: bool) -> None:
        self._trim_cache()
        if structure or pages is None:
            self.global_rev += 1
            self._rev.clear()
        else:
            for p in pages:
                self._rev[p] = self._rev.get(p, 0) + 1
        self._set_modified(True)
        if structure:
            self.structure_changed.emit()
        else:
            self.changed.emit(None if pages is None else set(pages))

    def replace_document(self, data: bytes, label: str) -> None:
        """Sostituisce l'intero documento (es. dopo la compressione), annullabile."""
        snap = self._snapshot()
        self._undo.append((label, snap))
        self._redo.clear()
        self._restore(data)
        self._set_modified(True)
        self.structure_changed.emit()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo_label(self) -> str:
        return self._undo[-1][0] if self._undo else ""

    def redo_label(self) -> str:
        return self._redo[-1][0] if self._redo else ""

    def undo(self) -> None:
        if not self._undo:
            return
        label, snap = self._undo.pop()
        self._redo.append((label, self._snapshot()))
        self._restore(snap)
        self._set_modified(True)
        self.structure_changed.emit()

    def redo(self) -> None:
        if not self._redo:
            return
        label, snap = self._redo.pop()
        self._undo.append((label, self._snapshot()))
        self._restore(snap)
        self._set_modified(True)
        self.structure_changed.emit()

    # -------------------------------------------------------- salvataggio
    def save_kwargs(self) -> dict:
        kw = dict(garbage=3, deflate=True, deflate_images=True, deflate_fonts=True)
        enc = self.encryption
        if enc is not None:
            if enc.get("remove"):
                kw["encryption"] = pymupdf.PDF_ENCRYPT_NONE
            else:
                kw["encryption"] = pymupdf.PDF_ENCRYPT_AES_256
                kw["owner_pw"] = enc.get("owner_pw") or enc.get("user_pw") or None
                kw["user_pw"] = enc.get("user_pw") or None
                kw["permissions"] = enc.get("permissions", -1)
        else:
            kw["encryption"] = pymupdf.PDF_ENCRYPT_KEEP
        return kw

    def to_bytes(self) -> bytes:
        if self.fonts_inserted and not self.workpath:
            try:
                self.doc.subset_fonts()
            except Exception:
                pass
        return self.doc.tobytes(**self.save_kwargs())

    def signatures_preserved_on_save(self) -> bool:
        """False se il prossimo salvataggio invaliderà le firme esistenti."""
        if not self.has_signatures():
            return True
        return bool(self.workpath) and self.encryption is None

    def save(self, path: str | None = None) -> str:
        path = path or self.path
        if not path:
            raise ValueError(T("Percorso di salvataggio mancante"))
        if self.workpath and self.encryption is None:
            data = self._snapshot()
        else:
            data = self.to_bytes()
        folder = os.path.dirname(os.path.abspath(path))
        fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=folder)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
        self.path = str(path)
        self.converted_from = None
        # dopo un salvataggio con cifratura il documento in memoria la riflette
        if self.encryption is not None:
            enc = self.encryption
            self.encryption = None
            self.doc.close()
            if self.workpath:
                with open(self.workpath, "wb") as f:
                    f.write(data)
                self.doc = pymupdf.open(self.workpath)
            else:
                self.doc = pymupdf.open(stream=data, filetype="pdf")
            if self.doc.needs_pass:
                pw = enc.get("owner_pw") or enc.get("user_pw")
                self.password = pw
                self.doc.authenticate(pw)
            elif enc.get("remove"):
                self.password = None
            self.global_rev += 1
            self._text_cache.clear()
        self._set_modified(False)
        self.saved.emit(self.path)
        return self.path

    def reload_from_bytes(self, data: bytes, path: str) -> None:
        """Ricarica il documento da byte appena scritti (es. dopo una firma digitale)."""
        self.doc.close()
        self.path = path
        self._undo.clear()
        self._redo.clear()
        if self.workpath is None:
            fd, self.workpath = tempfile.mkstemp(suffix=".pdf", prefix="editra_firmato_")
            os.close(fd)
        with open(self.workpath, "wb") as f:
            f.write(data)
        self._open_work()
        self.global_rev += 1
        self._rev.clear()
        self._text_cache.clear()
        self._set_modified(False)
        self.structure_changed.emit()

    def close(self) -> None:
        try:
            self.doc.close()
        except Exception:
            pass
        if self.workpath:
            try:
                os.remove(self.workpath)
            except OSError:
                pass
