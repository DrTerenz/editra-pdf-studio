"""Pannelli laterali e scheda documento."""
from __future__ import annotations

import os
import re
import tempfile

import pymupdf
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QFileDialog, QFrame, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
                               QPushButton, QSplitter, QStackedWidget, QTextBrowser, QToolButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from . import icons, theme
from .model import PdfModel
from .ops import annots as A
from .ops import pages as PG
from .ops.common import SEARCH_FLAGS, format_ranges, human_size
from .view import DocumentView


def _title(text: str) -> QLabel:
    l = QLabel(text)
    l.setObjectName("panelTitle")
    return l


def _tool(icon_name: str, tip: str, fn) -> QToolButton:
    b = QToolButton()
    b.setIcon(icons.icon(icon_name))
    b.setProperty("icon_name", icon_name)
    b.setToolTip(tip)
    b.setAutoRaise(True)
    b.clicked.connect(fn)
    return b


# ====================================================================== miniature
class ThumbList(QListWidget):
    moved = Signal(list, int)   # pagine, posizione di destinazione

    def __init__(self):
        super().__init__()
        self.setViewMode(QListWidget.IconMode)
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Snap)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSpacing(6)
        self.setUniformItemSizes(True)

    def dropEvent(self, e) -> None:
        rows = sorted(self.row(i) for i in self.selectedItems())
        target_item = self.itemAt(e.position().toPoint())
        if target_item is None:
            to = self.count()
        else:
            to = self.row(target_item)
            r = self.visualItemRect(target_item)
            if e.position().x() > r.center().x():
                to += 1
        e.ignore()
        if rows and not (rows[0] <= to <= rows[-1] + 1 and len(rows) == rows[-1] - rows[0] + 1):
            self.moved.emit(rows, to)


class ThumbnailPanel(QWidget):
    def __init__(self, tab: "DocumentTab"):
        super().__init__()
        self.tab = tab
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.addWidget(_title("Pagine"))
        head.addStretch()
        head.addWidget(_tool("rotate", "Ruota a destra le pagine selezionate", lambda: self._act("rotate_right")))
        head.addWidget(_tool("delete", "Elimina le pagine selezionate", lambda: self._act("delete")))
        head.addWidget(_tool("add", "Inserisci pagina vuota dopo", lambda: self._act("blank_after")))
        lay.addLayout(head)
        self.list = ThumbList()
        lay.addWidget(self.list)
        self.size = 110
        self.list.setIconSize(QSize(self.size, int(self.size * 1.42)))
        self.list.itemClicked.connect(lambda it: tab.view.go_to_page(self.list.row(it)))
        self.list.itemActivated.connect(lambda it: tab.view.go_to_page(self.list.row(it)))
        self.list.moved.connect(self._moved)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.verticalScrollBar().valueChanged.connect(lambda _: self._timer.start())
        self._timer = QTimer(self, singleShot=True, interval=60, timeout=self._render_visible)
        self._revs: dict[int, tuple] = {}
        tab.model.structure_changed.connect(self.rebuild)
        tab.model.changed.connect(self._changed)
        tab.view.page_changed.connect(self.set_current)
        self.rebuild()

    def selected_pages(self) -> list[int]:
        rows = sorted(self.list.row(i) for i in self.list.selectedItems())
        return rows or [self.tab.view.current]

    def rebuild(self) -> None:
        self.list.clear()
        self._revs.clear()
        blank = QPixmap(self.size, int(self.size * 1.42))
        blank.fill(Qt.white)
        for i in range(self.tab.model.page_count):
            it = QListWidgetItem(QIcon(blank), str(i + 1))
            it.setTextAlignment(Qt.AlignHCenter)
            it.setSizeHint(QSize(self.size + 22, int(self.size * 1.42) + 30))
            self.list.addItem(it)
        self.set_current(self.tab.view.current)
        self._timer.start()

    def _changed(self, pages) -> None:
        if pages is None:
            self._revs.clear()
        else:
            for p in pages:
                self._revs.pop(p, None)
        self._timer.start()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._timer.start()

    def _render_visible(self) -> None:
        if not self.isVisible():
            return
        vr = self.list.viewport().rect()
        model = self.tab.model
        done = 0
        for i in range(self.list.count()):
            it = self.list.item(i)
            if not self.list.visualItemRect(it).intersects(vr):
                continue
            rev = model.page_rev(i)
            if self._revs.get(i) == rev:
                continue
            page = model.page(i)
            z = self.size * 2 / max(page.rect.width, page.rect.height * 0.705)
            try:
                pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
            except Exception:
                continue
            img = QImage(pix.samples_mv, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
            pm = QPixmap.fromImage(img)
            pm.setDevicePixelRatio(2)
            it.setIcon(QIcon(pm))
            self._revs[i] = rev
            done += 1
            if done >= 6:
                self._timer.start(10)
                break

    def set_current(self, idx: int) -> None:
        if 0 <= idx < self.list.count():
            it = self.list.item(idx)
            if not it.isSelected() or len(self.list.selectedItems()) <= 1:
                self.list.blockSignals(True)
                self.list.setCurrentRow(idx)
                self.list.blockSignals(False)
            self.list.scrollToItem(it)

    def _moved(self, rows: list, to: int) -> None:
        model = self.tab.model
        with model.edit("Sposta pagine", structure=True):
            new = PG.move_pages(model.doc, rows, to)
        self.tab.view.go_to_page(new[0])

    def _act(self, what: str) -> None:
        self.tab.window().page_action(what, self.selected_pages())

    def _menu(self, pos) -> None:
        pages = self.selected_pages()
        m = QMenu(self)
        label = f"pagine {format_ranges(pages)}" if len(pages) > 1 else f"pagina {pages[0] + 1}"
        m.addSection(label.capitalize())
        for what, text, ic in (("rotate_right", "Ruota a destra", "rotate"), ("rotate_left", "Ruota a sinistra", "rotate"),
                               ("rotate_180", "Ruota di 180°", "rotate"), (None, None, None),
                               ("duplicate", "Duplica", "copy"), ("extract", "Estrai in un nuovo file…", "extract"),
                               ("export_images", "Esporta come immagini…", "image"), (None, None, None),
                               ("blank_before", "Inserisci pagina vuota prima", "blank"),
                               ("blank_after", "Inserisci pagina vuota dopo", "blank"),
                               ("insert_file", "Inserisci da file…", "import"),
                               ("replace", "Sostituisci con pagine di un altro file…", "replace"), (None, None, None),
                               ("crop", "Ritaglia…", "crop"), ("delete", "Elimina", "delete")):
            if what is None:
                m.addSeparator()
                continue
            m.addAction(icons.icon(ic), text, lambda w=what: self._act(w))
        m.exec(self.list.mapToGlobal(pos))


# ===================================================================== segnalibri
class BookmarkPanel(QWidget):
    def __init__(self, tab: "DocumentTab"):
        super().__init__()
        self.tab = tab
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.addWidget(_title("Segnalibri"))
        head.addStretch()
        head.addWidget(_tool("add", "Nuovo segnalibro per la pagina corrente", self.add))
        head.addWidget(_tool("edit", "Rinomina", self.rename))
        head.addWidget(_tool("delete", "Elimina", self.delete))
        lay.addLayout(head)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(_tool("up", "Sposta su", lambda: self.move(-1)))
        row.addWidget(_tool("down", "Sposta giù", lambda: self.move(1)))
        row.addWidget(_tool("prev", "Livello superiore", self.outdent))
        row.addWidget(_tool("next", "Sotto il precedente", self.indent))
        lay.addLayout(row)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._go)
        self.tree.itemDoubleClicked.connect(lambda it, c: self.rename())
        lay.addWidget(self.tree)
        self.empty = QLabel("Nessun segnalibro.\nUsa + per crearne uno sulla pagina corrente.")
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)
        lay.addWidget(self.empty)
        tab.model.structure_changed.connect(self.load)
        self.load()

    def load(self) -> None:
        self.tree.clear()
        try:
            toc = self.tab.model.doc.get_toc(simple=False)
        except Exception:
            toc = []
        parents = {0: self.tree.invisibleRootItem()}
        for lvl, title, page, *rest in toc:
            parent = parents.get(lvl - 1, self.tree.invisibleRootItem())
            it = QTreeWidgetItem(parent, [title])
            dest = rest[0] if rest else {}
            y = None
            if isinstance(dest, dict) and dest.get("to") is not None:
                try:
                    y = float(dest["to"].y)
                except Exception:
                    y = None
            it.setData(0, Qt.UserRole, (page, y))
            it.setToolTip(0, f"Pagina {page}")
            parents[lvl] = it
        self.tree.expandToDepth(0)
        self.empty.setVisible(not toc)

    def _go(self, it, col=0) -> None:
        page, y = it.data(0, Qt.UserRole)
        if page and page > 0:
            self.tab.view.go_to_page(page - 1)

    def _collect(self) -> list:
        out = []

        def walk(item, lvl):
            for i in range(item.childCount()):
                c = item.child(i)
                page, y = c.data(0, Qt.UserRole)
                out.append([lvl, c.text(0), page])
                walk(c, lvl + 1)
        walk(self.tree.invisibleRootItem(), 1)
        return out

    def _save(self, label: str) -> None:
        toc = self._collect()
        with self.tab.model.edit(label, pages=[]):
            self.tab.model.doc.set_toc(toc)
        self.empty.setVisible(not toc)

    def add(self, page: int | None = None, title: str | None = None) -> None:
        p = self.tab.view.current if page is None else page
        default = title or (self.tab.view.sel_text.strip().split("\n")[0][:80] if self.tab.view.sel_text else
                            f"Pagina {p + 1}")
        text, ok = QInputDialog.getText(self, "Nuovo segnalibro", "Titolo:", text=default)
        if not ok or not text.strip():
            return
        it = QTreeWidgetItem([text.strip()])
        it.setData(0, Qt.UserRole, (p + 1, None))
        cur = self.tree.currentItem()
        parent = cur.parent() if cur else None
        (parent or self.tree.invisibleRootItem()).addChild(it)
        self._sort_siblings(parent or self.tree.invisibleRootItem())
        self._save("Aggiungi segnalibro")

    @staticmethod
    def _sort_siblings(parent) -> None:
        kids = [parent.takeChild(0) for _ in range(parent.childCount())]
        kids.sort(key=lambda c: c.data(0, Qt.UserRole)[0] or 0)
        for k in kids:
            parent.addChild(k)

    def rename(self) -> None:
        it = self.tree.currentItem()
        if not it:
            return
        text, ok = QInputDialog.getText(self, "Rinomina segnalibro", "Titolo:", text=it.text(0))
        if ok and text.strip():
            it.setText(0, text.strip())
            self._save("Rinomina segnalibro")

    def delete(self) -> None:
        it = self.tree.currentItem()
        if not it:
            return
        (it.parent() or self.tree.invisibleRootItem()).removeChild(it)
        self._save("Elimina segnalibro")

    def move(self, d: int) -> None:
        it = self.tree.currentItem()
        if not it:
            return
        parent = it.parent() or self.tree.invisibleRootItem()
        i = parent.indexOfChild(it)
        j = i + d
        if 0 <= j < parent.childCount():
            parent.takeChild(i)
            parent.insertChild(j, it)
            self.tree.setCurrentItem(it)
            self._save("Sposta segnalibro")

    def indent(self) -> None:
        it = self.tree.currentItem()
        if not it:
            return
        parent = it.parent() or self.tree.invisibleRootItem()
        i = parent.indexOfChild(it)
        if i == 0:
            return
        prev = parent.child(i - 1)
        parent.takeChild(i)
        prev.addChild(it)
        prev.setExpanded(True)
        self.tree.setCurrentItem(it)
        self._save("Sposta segnalibro")

    def outdent(self) -> None:
        it = self.tree.currentItem()
        if not it or not it.parent():
            return
        parent = it.parent()
        gp = parent.parent() or self.tree.invisibleRootItem()
        parent.removeChild(it)
        gp.insertChild(gp.indexOfChild(parent) + 1, it)
        self.tree.setCurrentItem(it)
        self._save("Sposta segnalibro")


# ======================================================================= commenti
class CommentsPanel(QWidget):
    def __init__(self, tab: "DocumentTab"):
        super().__init__()
        self.tab = tab
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.addWidget(_title("Commenti"))
        head.addStretch()
        head.addWidget(_tool("export", "Riepilogo dei commenti (HTML)", lambda: tab.window().run_action("comments_summary")))
        head.addWidget(_tool("delete", "Elimina il commento selezionato", self.delete))
        lay.addLayout(head)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filtra per testo, autore o tipo…")
        self.filter.textChanged.connect(self.load)
        lay.addWidget(self.filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setWordWrap(True)
        self.tree.itemClicked.connect(self._go)
        self.tree.itemDoubleClicked.connect(self._props)
        lay.addWidget(self.tree)
        self.count = QLabel()
        self.count.setObjectName("muted")
        lay.addWidget(self.count)
        self._dirty = True
        tab.model.changed.connect(self._mark)
        tab.model.structure_changed.connect(self._mark)

    def _mark(self, *_):
        self._dirty = True
        if self.isVisible():
            self.load()

    def showEvent(self, e):
        super().showEvent(e)
        if self._dirty:
            self.load()

    def load(self) -> None:
        self._dirty = False
        self.tree.clear()
        q = self.filter.text().strip().lower()
        items = [d for d in A.list_annots(self.tab.model.doc) if d["type"] != pymupdf.PDF_ANNOT_REDACT]
        n = 0
        groups = {}
        for d in items:
            text = d.get("content") or d.get("marked_text") or ""
            hay = f"{text} {d['author']} {d['type_name']}".lower()
            if q and q not in hay:
                continue
            g = groups.get(d["page"])
            if g is None:
                g = groups[d["page"]] = QTreeWidgetItem(self.tree, [f"Pagina {d['page'] + 1}"])
                f = g.font(0)
                f.setBold(True)
                g.setFont(0, f)
            label = f"{d['type_name']}" + (f" · {d['author']}" if d["author"] else "")
            if text:
                label += "\n" + (text if len(text) < 160 else text[:157] + "…")
            it = QTreeWidgetItem(g, [label])
            it.setData(0, Qt.UserRole, (d["page"], d["xref"]))
            if d.get("color"):
                it.setIcon(0, icons.color_swatch(d["color"], 12))
            n += 1
        self.tree.expandAll()
        self.count.setText(f"  {n} commenti" if n != 1 else "  1 commento")

    def _go(self, it, col=0):
        data = it.data(0, Qt.UserRole)
        if not data:
            return
        idx, xref = data
        view = self.tab.view
        page = self.tab.model.page(idx)
        a = A.annot_by_xref(page, xref)
        if a is None:
            return
        view.sel_annot = (idx, xref)
        view.ensure_visible(idx, view._vrect(page, a.rect))
        view.annot_selected.emit((idx, xref))
        view.viewport().update()

    def _props(self, it, col=0):
        data = it.data(0, Qt.UserRole)
        if data:
            self.tab.view.request_annot_props.emit(*data)

    def delete(self):
        it = self.tree.currentItem()
        data = it.data(0, Qt.UserRole) if it else None
        if not data:
            return
        self._go(it)
        self.tab.view.delete_selected()


# ======================================================================= allegati
BLOCKED_EXT = (".exe", ".bat", ".cmd", ".com", ".scr", ".js", ".vbs", ".ps1", ".msi", ".jar", ".hta", ".lnk", ".pif")


class AttachmentsPanel(QWidget):
    def __init__(self, tab: "DocumentTab"):
        super().__init__()
        self.tab = tab
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.addWidget(_title("Allegati"))
        head.addStretch()
        head.addWidget(_tool("add", "Allega un file al documento", self.add))
        head.addWidget(_tool("save", "Salva l'allegato selezionato", self.extract))
        head.addWidget(_tool("open", "Apri l'allegato selezionato", self.open))
        head.addWidget(_tool("delete", "Elimina l'allegato selezionato", self.delete))
        lay.addLayout(head)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda it: self.open())
        lay.addWidget(self.list)
        tab.model.structure_changed.connect(self.load)
        tab.model.changed.connect(lambda _: self.load())
        self.load()

    def load(self) -> None:
        self.list.clear()
        doc = self.tab.model.doc
        for name in doc.embfile_names():
            try:
                info = doc.embfile_info(name)
                size = info.get("size") or info.get("length") or 0
            except Exception:
                size = 0
            it = QListWidgetItem(icons.icon("attach"), f"{name}  ({human_size(size)})")
            it.setData(Qt.UserRole, ("emb", name))
            self.list.addItem(it)
        for pno, page in enumerate(doc):
            for a in page.annots(types=[pymupdf.PDF_ANNOT_FILE_ATTACHMENT]):
                try:
                    info = a.file_info
                    it = QListWidgetItem(icons.icon("pin"), f"{info.get('filename')}  (pag. {pno + 1})")
                    it.setData(Qt.UserRole, ("annot", pno, a.xref))
                    self.list.addItem(it)
                except Exception:
                    continue

    def _data(self):
        it = self.list.currentItem()
        if not it:
            return None, None
        d = it.data(Qt.UserRole)
        doc = self.tab.model.doc
        if d[0] == "emb":
            return d[1], doc.embfile_get(d[1])
        page = doc[d[1]]
        a = A.annot_by_xref(page, d[2])
        return a.file_info.get("filename"), a.get_file()

    def add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Allega file")
        if not paths:
            return
        with self.tab.model.edit("Allega file", pages=[]):
            for p in paths:
                name = os.path.basename(p)
                existing = set(self.tab.model.doc.embfile_names())
                base, ext = os.path.splitext(name)
                k = 2
                while name in existing:
                    name = f"{base}_{k}{ext}"
                    k += 1
                with open(p, "rb") as f:
                    self.tab.model.doc.embfile_add(name, f.read(), filename=os.path.basename(p))
        self.load()

    def extract(self) -> None:
        name, data = self._data()
        if data is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Salva allegato", name)
        if path:
            with open(path, "wb") as f:
                f.write(data)

    def open(self) -> None:
        name, data = self._data()
        if data is None:
            return
        if os.path.splitext(name or "")[1].lower() in BLOCKED_EXT:
            QMessageBox.warning(self, "Allegato bloccato",
                                "Per sicurezza i programmi e gli script allegati non vengono aperti.\n"
                                "Puoi salvarli e controllarli con l'antivirus.")
            return
        d = tempfile.mkdtemp(prefix="editra_allegato_")
        p = os.path.join(d, os.path.basename(name or "allegato"))
        with open(p, "wb") as f:
            f.write(data)
        os.startfile(p)

    def delete(self) -> None:
        it = self.list.currentItem()
        if not it:
            return
        d = it.data(Qt.UserRole)
        with self.tab.model.edit("Elimina allegato", pages=None if d[0] == "emb" else [d[1]]):
            doc = self.tab.model.doc
            if d[0] == "emb":
                doc.embfile_del(d[1])
            else:
                page = doc[d[1]]
                a = A.annot_by_xref(page, d[2])
                if a is not None:
                    page.delete_annot(a)
        self.load()


# ========================================================================== firme
class SignaturesPanel(QWidget):
    def __init__(self, tab: "DocumentTab"):
        super().__init__()
        self.tab = tab
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        head.addWidget(_title("Firme digitali"))
        head.addStretch()
        head.addWidget(_tool("refresh", "Verifica di nuovo", self.verify))
        lay.addLayout(head)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.itemClicked.connect(self._go)
        self.list.itemDoubleClicked.connect(self._details)
        lay.addWidget(self.list)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setObjectName("muted")
        lay.addWidget(self.info)
        btns = QHBoxLayout()
        b1 = QPushButton("Dettagli")
        b1.clicked.connect(lambda: self._details(self.list.currentItem()))
        b2 = QPushButton("Considera attendibile")
        b2.setToolTip("Aggiunge il certificato del firmatario a quelli attendibili")
        b2.clicked.connect(self.trust)
        btns.addWidget(b1)
        btns.addWidget(b2)
        lay.addLayout(btns)
        self.results = []
        self._done = False
        tab.model.saved.connect(lambda _: self.verify())

    def showEvent(self, e):
        super().showEvent(e)
        if not self._done:
            self.verify()

    def verify(self) -> None:
        from .ops import signatures as SG
        self._done = True
        self.list.clear()
        model = self.tab.model
        if not model.has_signatures():
            self.info.setText("Il documento non contiene firme digitali.\n"
                              "Per firmare: Proteggi › Firma con certificato.")
            self.results = []
            return
        self.info.setText("Verifica in corso…")
        self.repaint()
        try:
            data = model.current_bytes()
            self.results = SG.verify_pdf(data)
        except Exception as ex:
            self.info.setText(f"Impossibile verificare le firme: {ex}")
            return
        locs = SG.locate_signature_fields(model.doc)
        icons_by = {"valida": ("check", "#2e7d32"), "sconosciuta": ("warning", "#f9a825"),
                    "modificata": ("warning", "#ef6c00"), "non_valida": ("error", "#c62828")}
        for r in self.results:
            loc = locs.get(r.field)
            if loc:
                r.page, r.rect = loc
            st = r.status
            label = {"valida": "Firma valida", "sconosciuta": "Firma integra, identità non verificata",
                     "modificata": "Firma valida, documento modificato dopo", "non_valida": "Firma NON valida"}[st]
            it = QListWidgetItem(f"{label}\n{r.signer}" + (f" · {r.time}" if r.time else ""))
            ic, col = icons_by[st]
            it.setIcon(QIcon(icons.glyph_pixmap(ic, 20, QColor(col))))
            it.setData(Qt.UserRole, r)
            it.setToolTip(r.summary)
            self.list.addItem(it)
        ok = all(r.status == "valida" for r in self.results)
        self.info.setText(("Tutte le firme sono valide." if ok else "Alcune firme richiedono attenzione.")
                          + ("" if model.signatures_preserved_on_save() else
                             "\nAttenzione: il prossimo salvataggio invaliderà le firme."))

    def _go(self, it) -> None:
        r = it.data(Qt.UserRole)
        if r and r.page is not None:
            self.tab.view.go_to_page(r.page)

    def _details(self, it) -> None:
        if not it:
            return
        r = it.data(Qt.UserRole)
        rows = [("Esito", r.summary), ("Firmatario", r.signer), ("E-mail", r.email), ("Emesso da", r.issuer),
                ("Data della firma", r.time), ("Motivo", r.reason), ("Luogo", r.location),
                ("Certificato valido dal", r.cert_valid_from), ("al", r.cert_valid_to), ("Numero di serie", r.serial),
                ("Campo", r.field)]
        html = "<table cellpadding='4'>" + "".join(
            f"<tr><td><b>{k}</b></td><td>{v}</td></tr>" for k, v in rows if v) + "</table>"
        if r.errors:
            html += "<p><b>Problemi:</b><br>" + "<br>".join(r.errors) + "</p>"
        if r.details:
            html += "<details><pre style='font-size:8pt'>" + r.details.replace("<", "&lt;") + "</pre>"
        QMessageBox.information(self, "Dettagli firma", html)

    def trust(self) -> None:
        from .ops import signatures as SG
        it = self.list.currentItem()
        if not it:
            return
        r = it.data(Qt.UserRole)
        if QMessageBox.question(self, "Certificato attendibile",
                                f"Considerare attendibile il certificato di «{r.signer}» (emesso da {r.issuer})?\n\n"
                                "Fallo solo se sei sicuro dell'identità del firmatario.") != QMessageBox.Yes:
            return
        der = SG.cert_der_from_signature(self.tab.model.current_bytes(), r.field)
        if der:
            SG.add_trusted_cert(der, r.signer)
            self.verify()


# ========================================================================= livelli
class LayersPanel(QWidget):
    def __init__(self, tab: "DocumentTab"):
        super().__init__()
        self.tab = tab
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(_title("Livelli"))
        self.box = QVBoxLayout()
        lay.addLayout(self.box)
        lay.addStretch()
        tab.model.structure_changed.connect(self.load)
        self.load()

    def load(self) -> None:
        while self.box.count():
            w = self.box.takeAt(0).widget()
            if w:
                w.deleteLater()
        try:
            cfgs = self.tab.model.doc.layer_ui_configs()
        except Exception:
            cfgs = []
        if not cfgs:
            l = QLabel("Il documento non ha livelli (contenuto opzionale).")
            l.setObjectName("muted")
            l.setWordWrap(True)
            self.box.addWidget(l)
            return
        for c in cfgs:
            cb = QCheckBox(("    " * c.get("depth", 0)) + (c.get("text") or "Livello"))
            cb.setChecked(bool(c.get("on")))
            cb.setEnabled(not c.get("locked"))
            cb.toggled.connect(lambda on, n=c["number"]: self._toggle(n, on))
            self.box.addWidget(cb)

    def _toggle(self, n: int, on: bool) -> None:
        self.tab.model.doc.set_layer_ui_config(n, 0 if on else 2)
        self.tab.model.global_rev += 1
        self.tab.view.refresh()


# ========================================================================== ricerca
class SearchPanel(QWidget):
    def __init__(self, tab: "DocumentTab"):
        super().__init__()
        self.tab = tab
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(_title("Cerca"))
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Testo da cercare…")
        self.edit.setClearButtonEnabled(True)
        self.edit.returnPressed.connect(self.search)
        lay.addWidget(self.edit)
        opts = QHBoxLayout()
        self.case = QCheckBox("Maiuscole/minuscole")
        self.whole = QCheckBox("Parole intere")
        opts.addWidget(self.case)
        opts.addWidget(self.whole)
        lay.addLayout(opts)
        btns = QHBoxLayout()
        go = QPushButton("Cerca")
        go.setObjectName("primary")
        go.clicked.connect(self.search)
        prev = _tool("up", "Risultato precedente (Maiusc+F3)", lambda: self.step(-1))
        nxt = _tool("down", "Risultato successivo (F3)", lambda: self.step(1))
        btns.addWidget(go)
        btns.addStretch()
        btns.addWidget(prev)
        btns.addWidget(nxt)
        lay.addLayout(btns)
        self.summary = QLabel()
        self.summary.setObjectName("muted")
        lay.addWidget(self.summary)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.itemClicked.connect(lambda it: self._show(self.list.row(it)))
        lay.addWidget(self.list)
        acts = QHBoxLayout()
        hl = QPushButton("Evidenzia tutti")
        hl.clicked.connect(self.highlight_all)
        rd = QPushButton("Redigi tutti")
        rd.clicked.connect(self.redact_all)
        rp = QPushButton("Sostituisci…")
        rp.clicked.connect(lambda: tab.window().run_action("find_replace"))
        acts.addWidget(hl)
        acts.addWidget(rd)
        acts.addWidget(rp)
        lay.addLayout(acts)
        self.hits: list[tuple[int, pymupdf.Rect]] = []
        self.pos = -1

    def search(self, text: str | None = None) -> None:
        if isinstance(text, str):
            self.edit.setText(text)
        q = self.edit.text()
        view = self.tab.view
        self.list.clear()
        self.hits = []
        self.pos = -1
        view.search_hits = {}
        view.current_hit = None
        if not q.strip():
            self.summary.setText("")
            view.viewport().update()
            return
        doc = self.tab.model.doc
        for pno in range(doc.page_count):
            page = doc[pno]
            rects = page.search_for(q, flags=SEARCH_FLAGS)
            if self.case.isChecked() or self.whole.isChecked():
                rects = [r for r in rects if self._accept(page, r, q)]
            if not rects:
                continue
            view.search_hits[pno] = [view._vrect(page, r) for r in rects]
            for r in rects:
                self.hits.append((pno, r))
                ctx = self._context(page, r)
                it = QListWidgetItem(f"Pag. {pno + 1}: {ctx}")
                self.list.addItem(it)
            QApplicationProcess()
        self.summary.setText(f"{len(self.hits)} risultati" if self.hits else "Nessun risultato")
        if self.hits:
            self._show(0)
        view.viewport().update()

    def _accept(self, page, r, q) -> bool:
        words = page.get_text("words", clip=r + (-2, -1, 2, 1), flags=SEARCH_FLAGS)
        text = " ".join(w[4] for w in words)
        if self.case.isChecked() and q not in text:
            return False
        if self.whole.isChecked():
            rx = re.compile(r"(?<!\w)" + re.escape(q) + r"(?!\w)", 0 if self.case.isChecked() else re.I)
            if not rx.search(text):
                return False
        return True

    @staticmethod
    def _context(page, r) -> str:
        clip = pymupdf.Rect(page.mediabox.x0, r.y0 - 1, page.mediabox.x1, r.y1 + 1)
        words = page.get_text("words", clip=clip, flags=SEARCH_FLAGS, sort=True)
        line = [w for w in words if abs((w[1] + w[3]) / 2 - (r.y0 + r.y1) / 2) < max(3, r.height / 2)]
        mid = [i for i, w in enumerate(line) if pymupdf.Rect(w[:4]).intersects(r)]
        if not mid:
            return ""
        a, b = max(0, mid[0] - 5), min(len(line), mid[-1] + 6)
        return ("… " if a > 0 else "") + " ".join(w[4] for w in line[a:b]) + (" …" if b < len(line) else "")

    def _show(self, i: int) -> None:
        if not self.hits:
            return
        self.pos = i % len(self.hits)
        pno, r = self.hits[self.pos]
        view = self.tab.view
        vr = view._vrect(self.tab.model.page(pno), r)
        view.current_hit = (pno, vr)
        view.ensure_visible(pno, vr)
        self.list.setCurrentRow(self.pos)
        self.summary.setText(f"Risultato {self.pos + 1} di {len(self.hits)}")
        view.viewport().update()

    def step(self, d: int) -> None:
        if not self.hits:
            if self.edit.text():
                self.search()
            return
        self._show(self.pos + d)

    def highlight_all(self) -> None:
        if not self.hits:
            return
        view = self.tab.view
        st = view._style("highlight")
        by_page = {}
        for pno, r in self.hits:
            by_page.setdefault(pno, []).append(r)
        with self.tab.model.edit("Evidenzia risultati", list(by_page)):
            for pno, rects in by_page.items():
                A.add_markup(self.tab.model.page(pno), "highlight", [r.quad for r in rects], st)

    def redact_all(self) -> None:
        if not self.hits:
            return
        from .ops import security as SEC
        hits = [(p, r, "") for p, r in self.hits]
        with self.tab.model.edit("Contrassegna redazioni", sorted({p for p, _ in self.hits})):
            SEC.mark_redactions(self.tab.model.doc, hits)
        self.tab.window().status(f"{len(hits)} aree contrassegnate. Usa «Applica redazioni» per eliminarle definitivamente.")


def QApplicationProcess():
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()


# =================================================================== scheda documento
class DocumentTab(QWidget):
    """Una scheda: barra laterale con i pannelli + area di visualizzazione."""

    PANELS = [("thumbs", "thumbs", "Miniature delle pagine"), ("bookmarks", "bookmarks", "Segnalibri"),
              ("comments", "comment", "Commenti"), ("search", "search", "Cerca"),
              ("attachments", "attach", "Allegati"), ("signatures", "certificate", "Firme digitali"),
              ("layers", "layers", "Livelli")]

    def __init__(self, model: PdfModel, tools, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.rail = QFrame()
        self.rail.setObjectName("sidebarRail")
        rl = QVBoxLayout(self.rail)
        rl.setContentsMargins(4, 8, 4, 8)
        rl.setSpacing(4)
        self.splitter = QSplitter(Qt.Horizontal)
        self.side = QFrame()
        self.side.setObjectName("sidePanel")
        sl = QVBoxLayout(self.side)
        sl.setContentsMargins(6, 0, 6, 6)
        self.stack = QStackedWidget()
        sl.addWidget(self.stack)
        self.view = DocumentView(model, tools)
        self.panels: dict[str, QWidget] = {}
        self.buttons: dict[str, QToolButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(False)
        factories = {"thumbs": ThumbnailPanel, "bookmarks": BookmarkPanel, "comments": CommentsPanel,
                     "search": SearchPanel, "attachments": AttachmentsPanel, "signatures": SignaturesPanel,
                     "layers": LayersPanel}
        for key, ic, tip in self.PANELS:
            panel = factories[key](self)
            self.panels[key] = panel
            self.stack.addWidget(panel)
            b = QToolButton()
            b.setIcon(icons.icon(ic))
            b.setProperty("icon_name", ic)
            b.setIconSize(QSize(20, 20))
            b.setToolTip(tip)
            b.setCheckable(True)
            b.setFixedSize(36, 36)
            b.clicked.connect(lambda on, k=key: self.toggle_panel(k, on))
            rl.addWidget(b)
            self.buttons[key] = b
        rl.addStretch()
        self.splitter.addWidget(self.side)
        self.splitter.addWidget(self.view)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([250, 1000])
        self.splitter.setCollapsible(1, False)
        lay.addWidget(self.rail)
        lay.addWidget(self.splitter)
        self.current_panel = None
        self.show_panel("thumbs")
        if model.has_signatures():
            QTimer.singleShot(300, lambda: self.show_panel("signatures"))
        elif self._has_toc():
            self.show_panel("bookmarks")

    def _has_toc(self) -> bool:
        try:
            return bool(self.model.doc.get_toc())
        except Exception:
            return False

    def show_panel(self, key: str) -> None:
        self.current_panel = key
        self.stack.setCurrentWidget(self.panels[key])
        self.side.show()
        for k, b in self.buttons.items():
            b.setChecked(k == key)
        if self.splitter.sizes()[0] < 60:
            self.splitter.setSizes([250, max(400, self.width() - 290)])

    def toggle_panel(self, key: str, on: bool) -> None:
        if on:
            self.show_panel(key)
        else:
            self.hide_panels()

    def hide_panels(self) -> None:
        self.side.hide()
        self.current_panel = None
        for b in self.buttons.values():
            b.setChecked(False)
