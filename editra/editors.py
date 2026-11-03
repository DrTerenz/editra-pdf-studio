"""Editor in linea sopra la pagina: testo formattato e testo semplice."""
from __future__ import annotations

import pymupdf
from PySide6.QtCore import QEvent, QPointF, QRectF, QSizeF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextOption
from PySide6.QtWidgets import (QColorDialog, QComboBox, QDoubleSpinBox, QFontComboBox, QFrame,
                               QGraphicsProxyWidget, QHBoxLayout, QLineEdit, QPlainTextEdit, QTextEdit,
                               QToolButton, QWidget)

from . import icons, theme
from .ops import textedit as TE

PX_PER_PT = 96 / 72

_ALIGN_TO_QT = {TE.ALIGN_LEFT: Qt.AlignLeft, TE.ALIGN_CENTER: Qt.AlignHCenter, TE.ALIGN_RIGHT: Qt.AlignRight,
                TE.ALIGN_JUSTIFY: Qt.AlignJustify}


def _qt_align_to_te(a) -> int:
    if a & Qt.AlignHCenter:
        return TE.ALIGN_CENTER
    if a & Qt.AlignRight:
        return TE.ALIGN_RIGHT
    if a & Qt.AlignJustify:
        return TE.ALIGN_JUSTIFY
    return TE.ALIGN_LEFT


class _InlineBase:
    def __init__(self, view, idx: int, rect_view: QRectF):
        self.view = view
        self.idx = idx
        self.rect_view = QRectF(rect_view)
        self.proxy: QGraphicsProxyWidget | None = None

    def _place(self, widget: QWidget, pad_pt: float = 2.0) -> None:
        item = self.view.items[self.idx]
        s = self.view.scale_px
        self.proxy = self.view.scene().addWidget(widget)
        self.proxy.setZValue(1000)
        r = self.rect_view.adjusted(-pad_pt, -pad_pt, pad_pt, pad_pt)
        self.proxy.setPos(item.pos() + r.topLeft() * s)
        widget.resize(int(r.width() * PX_PER_PT), int(r.height() * PX_PER_PT))
        self.proxy.setScale(self.view.zoom)

    def contains_viewport_point(self, pos) -> bool:
        sp = self.view.mapToScene(pos.toPoint())
        if self.proxy is not None and self.proxy.sceneBoundingRect().contains(sp):
            return True
        return False

    def close(self) -> None:
        if self.proxy is not None:
            w = self.proxy.widget()
            self.view.scene().removeItem(self.proxy)
            self.proxy.deleteLater()
            if w is not None:
                w.deleteLater()
            self.proxy = None


def _claim_keys(e) -> bool:
    """Riserva Esc e Invio all'editor (la finestra ha scorciatoie sugli stessi tasti)."""
    if e.type() == QEvent.ShortcutOverride and e.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
        e.accept()
        return True
    return False


class _RichEdit(QTextEdit):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def event(self, e):
        if _claim_keys(e):
            return True
        return super().event(e)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.owner.view.cancel_editor()
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and e.modifiers() & Qt.ControlModifier:
            self.owner.view.commit_editor()
            return
        super().keyPressEvent(e)

    def insertFromMimeData(self, source) -> None:
        # incolla solo testo: il formato arriva dalla posizione del cursore
        if source.hasText():
            self.insertPlainText(source.text())


class RichTextEditor(_InlineBase):
    """Modifica di un blocco di testo con font, corpo, stile, colore e allineamento."""

    def __init__(self, view, idx: int, rect_view: QRectF, paras: list[TE.Para], block: TE.TextBlock | None):
        super().__init__(view, idx, rect_view)
        self.block = block
        self.orig_paras = paras
        self.edit = _RichEdit(self)
        self.edit.setFrameShape(QFrame.NoFrame)
        self.edit.setLineWrapMode(QTextEdit.WidgetWidth)
        self.edit.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.edit.document().setDocumentMargin(2)
        self.edit.setStyleSheet("QTextEdit { background: rgba(255,255,255,245); color: black;"
                                f" border: 1.5px solid {theme.current['accent']}; border-radius: 0; padding: 0; }}")
        self._load(paras)
        self.min_h = rect_view.height()
        self._place(self.edit)
        self.edit.document().contentsChanged.connect(self._grow)
        self.edit.cursorPositionChanged.connect(self._sync_toolbar)
        self.toolbar = _FormatBar(self)
        self.toolbar.setParent(self.view.viewport())
        self._reposition_toolbar()
        self.toolbar.show()
        self.view.horizontalScrollBar().valueChanged.connect(self._reposition_toolbar)
        self.view.verticalScrollBar().valueChanged.connect(self._reposition_toolbar)
        self.edit.setFocus()
        c = self.edit.textCursor()
        c.movePosition(QTextCursor.End)
        self.edit.setTextCursor(c)
        self._grow()
        self._sync_toolbar()

    # --------------------------------------------------------- contenuto
    def _load(self, paras: list[TE.Para]) -> None:
        doc = self.edit.document()
        doc.clear()
        cur = QTextCursor(doc)
        for i, p in enumerate(paras):
            bf = QTextBlockFormat()
            bf.setAlignment(_ALIGN_TO_QT.get(p.align, Qt.AlignLeft))
            bf.setLineHeight(p.line_height * 100, QTextBlockFormat.ProportionalHeight.value
                             if hasattr(QTextBlockFormat.ProportionalHeight, "value") else 1)
            if i == 0:
                cur.setBlockFormat(bf)
            else:
                cur.insertBlock(bf)
            for r in p.runs:
                cur.insertText(r.text, self._fmt(r))
            if not p.runs:
                cur.setCharFormat(self._fmt(TE.Run("", self.view.tools.text_family, self.view.tools.text_size)))
        if paras and paras[0].runs:
            self.edit.setCurrentCharFormat(self._fmt(paras[0].runs[-1]))
        else:
            self.edit.setCurrentCharFormat(self._fmt(TE.Run("", self.view.tools.text_family,
                                                            self.view.tools.text_size,
                                                            color=self.view.tools.color_for("text"))))

    @staticmethod
    def _fmt(r: TE.Run) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setFontFamilies([r.family])
        f.setFontPointSize(r.size)
        f.setFontWeight(QFont.Bold if r.bold else QFont.Normal)
        f.setFontItalic(r.italic)
        f.setFontUnderline(r.underline)
        f.setForeground(QColor(r.color))
        return f

    def read_paras(self) -> list[TE.Para]:
        doc = self.edit.document()
        paras = []
        block = doc.begin()
        k = 0
        while block.isValid():
            runs = []
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    cf = frag.charFormat()
                    fams = cf.fontFamilies()
                    family = (fams[0] if fams else None) or cf.font().family()
                    size = cf.fontPointSize() or cf.font().pointSizeF() or 11
                    color = cf.foreground().color().name() if cf.foreground().style() != Qt.NoBrush else "#000000"
                    text = frag.text().replace(" ", " ").replace(" ", " ")
                    runs.append(TE.Run(text, family, round(size * 2) / 2, cf.fontWeight() >= QFont.DemiBold,
                                       cf.fontItalic(), cf.fontUnderline(), color))
                it += 1
            lh = self.orig_paras[k].line_height if k < len(self.orig_paras) else 1.2
            paras.append(TE.Para(runs, _qt_align_to_te(block.blockFormat().alignment()), lh))
            block = block.next()
            k += 1
        # niente paragrafi vuoti in coda
        while paras and not paras[-1].text.strip():
            paras.pop()
        return paras

    def _changed(self, paras) -> bool:
        a = [(p.align, [(r.text, r.family, r.size, r.bold, r.italic, r.underline, r.color.lower()) for r in p.runs if r.text])
             for p in paras]
        b = [(p.align, [(r.text, r.family, r.size, r.bold, r.italic, r.underline, r.color.lower()) for r in p.runs if r.text])
             for p in self.orig_paras]
        return a != b

    # ------------------------------------------------------- geometria
    def _grow(self) -> None:
        if self.proxy is None:
            return
        h_px = self.edit.document().size().height() + 6
        min_px = (self.min_h + 4) * PX_PER_PT
        self.edit.resize(self.edit.width(), int(max(h_px, min_px)))
        self._reposition_toolbar()

    def _reposition_toolbar(self, *_):
        if self.proxy is None or not hasattr(self, "toolbar"):
            return
        r = self.proxy.sceneBoundingRect()
        tl = self.view.mapFromScene(r.topLeft())
        x = max(4, min(tl.x(), self.view.viewport().width() - self.toolbar.width() - 4))
        y = tl.y() - self.toolbar.height() - 6
        if y < 4:
            y = self.view.mapFromScene(r.bottomLeft()).y() + 6
        self.toolbar.move(int(x), int(y))

    # -------------------------------------------------------- formato
    def merge(self, fmt: QTextCharFormat) -> None:
        self.edit.mergeCurrentCharFormat(fmt)
        self.edit.setFocus()

    def set_align(self, align: int) -> None:
        self.edit.setAlignment(_ALIGN_TO_QT[align])
        self.edit.setFocus()

    def _sync_toolbar(self) -> None:
        if hasattr(self, "toolbar"):
            self.toolbar.sync(self.edit.currentCharFormat(), self.edit.alignment())

    # ------------------------------------------------------- conferma
    def commit(self) -> None:
        paras = self.read_paras()
        model = self.view.model
        if self.block is not None:
            if not self._changed(paras):
                return
            with model.edit("Modifica testo", [self.idx]):
                warn = TE.replace_block(model.page(self.idx), self.block, paras)
                model.fonts_inserted = True
        else:
            if not any(p.text.strip() for p in paras):
                return
            page = model.page(self.idx)
            w_pt = self.edit.width() / PX_PER_PT
            r = QRectF(self.rect_view.left(), self.rect_view.top(), max(w_pt, 20), self.rect_view.height())
            rect = self.view._pdf_rect(page, r)
            with model.edit("Aggiungi testo", [self.idx]):
                _, warn = TE.insert_paras(model.page(self.idx), rect, paras)
                model.fonts_inserted = True
        if warn:
            self.view.status.emit("; ".join(warn))

    def delete_block(self) -> None:
        if self.block is not None:
            model = self.view.model
            b = self.block
            self.block = None
            self.view.cancel_editor()
            with model.edit("Elimina testo", [self.idx]):
                TE.delete_block(model.page(self.idx), b)
        else:
            self.view.cancel_editor()

    def close(self) -> None:
        try:
            self.view.horizontalScrollBar().valueChanged.disconnect(self._reposition_toolbar)
            self.view.verticalScrollBar().valueChanged.disconnect(self._reposition_toolbar)
        except Exception:
            pass
        if hasattr(self, "toolbar"):
            self.toolbar.hide()
            self.toolbar.deleteLater()
        super().close()


class _FormatBar(QFrame):
    """Barra di formattazione mostrata sopra l'editor del testo."""

    def __init__(self, owner: RichTextEditor):
        super().__init__()
        self.owner = owner
        self.setObjectName("card")
        self.setStyleSheet(f"QFrame#card {{ background: {theme.current['panel']}; border: 1px solid "
                           f"{theme.current['border']}; border-radius: 8px; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(3)
        self._sync_lock = False
        self.font = QFontComboBox()
        self.font.setMaximumWidth(170)
        self.font.currentFontChanged.connect(self._font)
        self.size = QDoubleSpinBox()
        self.size.setRange(2, 400)
        self.size.setDecimals(1)
        self.size.setSingleStep(0.5)
        self.size.setSuffix(" pt")
        self.size.setFixedWidth(72)
        self.size.valueChanged.connect(self._size)
        lay.addWidget(self.font)
        lay.addWidget(self.size)
        self.b = self._btn("B", "Grassetto (Ctrl+B)", True, self._bold)
        self.i = self._btn("I", "Corsivo (Ctrl+I)", True, self._italic)
        self.u = self._btn("U", "Sottolineato (Ctrl+U)", True, self._under)
        f = self.b.font(); f.setBold(True); self.b.setFont(f)
        f = self.i.font(); f.setItalic(True); self.i.setFont(f)
        f = self.u.font(); f.setUnderline(True); self.u.setFont(f)
        for w in (self.b, self.i, self.u):
            lay.addWidget(w)
        self.color = QToolButton()
        self.color.setToolTip("Colore del testo")
        self.color.clicked.connect(self._color)
        lay.addWidget(self.color)
        self.align = QComboBox()
        self.align.addItems(["Sinistra", "Centro", "Destra", "Giustificato"])
        self.align.currentIndexChanged.connect(lambda i: None if self._sync_lock else owner.set_align(i))
        lay.addWidget(self.align)
        ok = QToolButton()
        ok.setIcon(icons.icon("accept"))
        ok.setToolTip("Conferma (Ctrl+Invio)")
        ok.clicked.connect(lambda: owner.view.commit_editor())
        cancel = QToolButton()
        cancel.setIcon(icons.icon("cancel"))
        cancel.setToolTip("Annulla (Esc)")
        cancel.clicked.connect(lambda: owner.view.cancel_editor())
        delete = QToolButton()
        delete.setIcon(icons.icon("delete"))
        delete.setToolTip("Elimina questo blocco di testo")
        delete.clicked.connect(owner.delete_block)
        lay.addWidget(ok)
        lay.addWidget(cancel)
        lay.addWidget(delete)
        from PySide6.QtGui import QKeySequence, QShortcut
        for seq, fn in (("Ctrl+B", self.b.click), ("Ctrl+I", self.i.click), ("Ctrl+U", self.u.click)):
            sc = QShortcut(QKeySequence(seq), owner.edit)
            sc.setContext(Qt.WidgetShortcut)
            sc.activated.connect(fn)
        self.adjustSize()

    def _btn(self, text, tip, checkable, fn) -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setCheckable(checkable)
        b.setFixedWidth(26)
        b.clicked.connect(fn)
        return b

    def sync(self, cf: QTextCharFormat, align) -> None:
        self._sync_lock = True
        fams = cf.fontFamilies()
        fam = (fams[0] if fams else None) or cf.font().family()
        self.font.blockSignals(True)
        self.font.setCurrentFont(QFont(fam))
        self.font.blockSignals(False)
        self.size.blockSignals(True)
        self.size.setValue(cf.fontPointSize() or cf.font().pointSizeF() or 11)
        self.size.blockSignals(False)
        self.b.setChecked(cf.fontWeight() >= QFont.DemiBold)
        self.i.setChecked(cf.fontItalic())
        self.u.setChecked(cf.fontUnderline())
        col = cf.foreground().color() if cf.foreground().style() != Qt.NoBrush else QColor("black")
        self._cur_color = col
        self.color.setIcon(icons.color_swatch(col))
        self.align.setCurrentIndex(_qt_align_to_te(align))
        self._sync_lock = False

    def _font(self, f: QFont) -> None:
        if self._sync_lock:
            return
        fmt = QTextCharFormat()
        fmt.setFontFamilies([f.family()])
        self.owner.merge(fmt)

    def _size(self, v: float) -> None:
        if self._sync_lock:
            return
        fmt = QTextCharFormat()
        fmt.setFontPointSize(v)
        self.owner.merge(fmt)

    def _bold(self, on: bool) -> None:
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Bold if on else QFont.Normal)
        self.owner.merge(fmt)

    def _italic(self, on: bool) -> None:
        fmt = QTextCharFormat()
        fmt.setFontItalic(on)
        self.owner.merge(fmt)

    def _under(self, on: bool) -> None:
        fmt = QTextCharFormat()
        fmt.setFontUnderline(on)
        self.owner.merge(fmt)

    def _color(self) -> None:
        c = QColorDialog.getColor(getattr(self, "_cur_color", QColor("black")), self, "Colore del testo")
        if c.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(c)
            self.owner.merge(fmt)
            self.color.setIcon(icons.color_swatch(c))


class _PlainLine(QLineEdit):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def event(self, e):
        if _claim_keys(e):
            return True
        return super().event(e)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.owner.view.cancel_editor()
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Tab):
            self.owner.view.commit_editor()
            return
        super().keyPressEvent(e)

    def focusOutEvent(self, e) -> None:
        super().focusOutEvent(e)
        self.owner._focus_lost()


class _PlainMulti(QPlainTextEdit):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def event(self, e):
        if _claim_keys(e):
            return True
        return super().event(e)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self.owner.view.cancel_editor()
            return
        if e.key() in (Qt.Key_Return, Qt.Key_Enter) and e.modifiers() & Qt.ControlModifier:
            self.owner.view.commit_editor()
            return
        super().keyPressEvent(e)

    def focusOutEvent(self, e) -> None:
        super().focusOutEvent(e)
        self.owner._focus_lost()


class PlainEditor(_InlineBase):
    """Testo semplice: caselle di testo e campi dei moduli."""

    def __init__(self, view, idx: int, rect_view: QRectF, text: str, callback, multiline: bool = False,
                 font_pt: float = 11, max_len: int = 0):
        super().__init__(view, idx, rect_view)
        self.callback = callback
        self.multiline = multiline
        self.w = _PlainMulti(self) if multiline else _PlainLine(self)
        f = QFont("Arial")
        f.setPointSizeF(font_pt)
        self.w.setFont(f)
        self.w.setStyleSheet(f"background: rgba(255,255,250,250); color: black; border: 1.5px solid "
                             f"{theme.current['accent']}; border-radius: 0; padding: 0px 2px;")
        if multiline:
            self.w.setPlainText(text)
        else:
            self.w.setText(text)
            if max_len:
                self.w.setMaxLength(max_len)
        self._place(self.w, pad_pt=0.5)
        self.w.setFocus()
        if multiline:
            c = self.w.textCursor()
            c.movePosition(QTextCursor.End)
            self.w.setTextCursor(c)
        else:
            self.w.selectAll()
        view.status.emit("Invio per confermare" if not multiline else "Ctrl+Invio per confermare, Esc per annullare")

    def text(self) -> str:
        return self.w.toPlainText() if self.multiline else self.w.text()

    def _focus_lost(self) -> None:
        if self.view.editor is self:
            QTimer.singleShot(0, lambda: self.view.editor is self and self.view.commit_editor())

    def commit(self) -> None:
        self.callback(self.text())
