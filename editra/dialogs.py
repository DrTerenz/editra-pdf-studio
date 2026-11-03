"""Finestre di dialogo."""
from __future__ import annotations

import os

import pymupdf
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFontComboBox, QFormLayout, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QPushButton, QSlider, QSpinBox, QTableWidget, QTableWidgetItem,
                               QTabWidget, QTextBrowser, QToolButton, QVBoxLayout, QWidget)

from . import icons, settings, theme
from .ops.common import human_size
from .i18n import T


# ============================================================ modulo generico
class ColorButton(QToolButton):
    changed = Signal(object)

    def __init__(self, color: str | None, allow_none: bool = False):
        super().__init__()
        self.allow_none = allow_none
        self.setColor(color)
        self.clicked.connect(self._pick)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

    def setColor(self, c: str | None) -> None:
        self.color = c
        self.setIcon(icons.color_swatch(c))
        self.setText(c.upper() if c else T('Nessuno'))

    def _pick(self) -> None:
        from PySide6.QtWidgets import QMenu
        if self.allow_none:
            m = QMenu(self)
            m.addAction(T('Scegli colore…'), self._dialog)
            m.addAction(T('Nessun colore'), lambda: (self.setColor(None), self.changed.emit(None)))
            m.exec(self.mapToGlobal(self.rect().bottomLeft()))
        else:
            self._dialog()

    def _dialog(self) -> None:
        c = QColorDialog.getColor(QColor(self.color or "#000000"), self, T('Scegli colore'))
        if c.isValid():
            self.setColor(c.name())
            self.changed.emit(c.name())


class PathEdit(QWidget):
    def __init__(self, value: str, mode: str, filt: str = "", save_default: str = ""):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit(value)
        b = QPushButton(T('Sfoglia…'))
        b.clicked.connect(self._browse)
        lay.addWidget(self.edit)
        lay.addWidget(b)
        self.mode, self.filt = mode, filt

    def _browse(self) -> None:
        if self.mode == "dir":
            p = QFileDialog.getExistingDirectory(self, T('Scegli cartella'), self.edit.text())
        elif self.mode == "save":
            p, _ = QFileDialog.getSaveFileName(self, T('Salva come'), self.edit.text(), self.filt)
        else:
            p, _ = QFileDialog.getOpenFileName(self, T('Scegli file'), self.edit.text(), self.filt)
        if p:
            self.edit.setText(p)

    def text(self) -> str:
        return self.edit.text()


class FormDialog(QDialog):
    """Dialogo costruito da una lista di campi.

    Campo: (chiave, etichetta, tipo, valore predefinito, opzioni)
    tipi: str, text, int, float, bool, choice, color, color_none, open, save, dir, font, label, slider
    """

    def __init__(self, parent, title: str, fields: list, intro: str = "", ok_text: str = "OK", width: int = 460):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        lay = QVBoxLayout(self)
        if intro:
            l = QLabel(intro)
            l.setWordWrap(True)
            l.setObjectName("muted")
            lay.addWidget(l)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        lay.addLayout(form)
        self.widgets = {}
        for f in fields:
            key, label, typ = f[0], f[1], f[2]
            default = f[3] if len(f) > 3 else None
            opt = f[4] if len(f) > 4 else None
            w = self._make(typ, default, opt)
            self.widgets[key] = (typ, w)
            if typ == "bool":
                form.addRow("", w)
                w.setText(label)
            elif typ == "label":
                form.addRow(w)
            elif typ == "section":
                s = QLabel(label)
                s.setStyleSheet("font-weight:600; padding-top:8px;")
                form.addRow(s)
            else:
                form.addRow(label, w)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(ok_text)
        bb.button(QDialogButtonBox.Cancel).setText(T('Annulla'))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _make(self, typ, default, opt):
        if typ == "str":
            w = QLineEdit("" if default is None else str(default))
            if opt and opt.get("password"):
                w.setEchoMode(QLineEdit.Password)
            if opt and opt.get("placeholder"):
                w.setPlaceholderText(opt["placeholder"])
            return w
        if typ == "text":
            w = QPlainTextEdit("" if default is None else str(default))
            w.setMinimumHeight(80)
            return w
        if typ == "int":
            w = QSpinBox()
            lo, hi = (opt or (0, 100000))[:2]
            w.setRange(lo, hi)
            w.setValue(int(default or 0))
            return w
        if typ == "float":
            w = QDoubleSpinBox()
            lo, hi = (opt or (0, 100000))[:2]
            w.setRange(lo, hi)
            w.setDecimals(2)
            w.setValue(float(default or 0))
            return w
        if typ == "slider":
            w = QSlider(Qt.Horizontal)
            w.setRange(*(opt or (0, 100)))
            w.setValue(int(default or 0))
            return w
        if typ == "bool":
            w = QCheckBox()
            w.setChecked(bool(default))
            return w
        if typ == "choice":
            w = QComboBox()
            for o in opt:
                if isinstance(o, tuple):
                    w.addItem(o[0], o[1])
                else:
                    w.addItem(str(o), o)
            if default is not None:
                i = w.findData(default)
                if i < 0:
                    i = w.findText(str(default))
                w.setCurrentIndex(max(0, i))
            return w
        if typ in ("color", "color_none"):
            return ColorButton(default, allow_none=typ == "color_none")
        if typ in ("open", "save", "dir"):
            return PathEdit(default or "", typ, opt or "")
        if typ == "font":
            w = QFontComboBox()
            if default:
                w.setCurrentFont(QFont(default))
            return w
        if typ == "label":
            l = QLabel(str(default or ""))
            l.setWordWrap(True)
            l.setObjectName("muted")
            return l
        if typ == "section":
            return QLabel()
        raise ValueError(typ)

    def values(self) -> dict:
        out = {}
        for k, (typ, w) in self.widgets.items():
            if typ == "str":
                out[k] = w.text()
            elif typ == "text":
                out[k] = w.toPlainText()
            elif typ in ("int", "float", "slider"):
                out[k] = w.value()
            elif typ == "bool":
                out[k] = w.isChecked()
            elif typ == "choice":
                out[k] = w.currentData()
            elif typ in ("color", "color_none"):
                out[k] = w.color
            elif typ in ("open", "save", "dir"):
                out[k] = w.text()
            elif typ == "font":
                out[k] = w.currentFont().family()
        return out


def ask(parent, title: str, fields: list, intro: str = "", ok_text: str = "OK", width: int = 460) -> dict | None:
    d = FormDialog(parent, title, fields, intro, ok_text, width)
    if d.exec() == QDialog.Accepted:
        return d.values()
    return None


# ================================================================ unione file
class MergeDialog(QDialog):
    def __init__(self, parent, initial: list[str] | None = None):
        super().__init__(parent)
        self.setWindowTitle(T('Combina file in un unico PDF'))
        self.resize(640, 460)
        lay = QVBoxLayout(self)
        intro = QLabel(T("Aggiungi PDF, immagini o altri documenti. Trascinali per cambiare l'ordine; nella colonna Pagine puoi indicare quali pagine prendere (es. 1-3, 5)."))
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        lay.addWidget(intro)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels([T('File'), T('Pagine'), T('Dimensione')])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 360)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 90)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.verticalHeader().setVisible(False)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        for text, fn in ((T('Aggiungi file…'), self.add), (T('Rimuovi'), self.remove), ("Su", lambda: self.move(-1)),
                         (T('Giù'), lambda: self.move(1)), (T('Ordina per nome'), self.sort)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        self.bookmarks = QCheckBox(T('Crea un segnalibro per ogni file'))
        self.bookmarks.setChecked(True)
        lay.addWidget(self.bookmarks)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(T('Combina'))
        bb.button(QDialogButtonBox.Cancel).setText(T('Annulla'))
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        for p in initial or []:
            self._append(p)

    def _append(self, p: str) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        it = QTableWidgetItem(os.path.basename(p))
        it.setData(Qt.UserRole, p)
        it.setToolTip(p)
        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(r, 0, it)
        self.table.setItem(r, 1, QTableWidgetItem(T("tutte")))
        sz = QTableWidgetItem(human_size(os.path.getsize(p)) if os.path.exists(p) else "")
        sz.setFlags(sz.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(r, 2, sz)

    def add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, T('Aggiungi file'), "", FILE_FILTER_ALL)
        for p in paths:
            self._append(p)

    def remove(self) -> None:
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r)

    def _rows(self):
        return [(self.table.item(r, 0).data(Qt.UserRole), self.table.item(r, 1).text())
                for r in range(self.table.rowCount())]

    def _set_rows(self, rows):
        self.table.setRowCount(0)
        for p, rng in rows:
            self._append(p)
            self.table.item(self.table.rowCount() - 1, 1).setText(rng)

    def move(self, d: int) -> None:
        r = self.table.currentRow()
        rows = self._rows()
        j = r + d
        if r < 0 or not 0 <= j < len(rows):
            return
        rows[r], rows[j] = rows[j], rows[r]
        self._set_rows(rows)
        self.table.selectRow(j)

    def sort(self) -> None:
        self._set_rows(sorted(self._rows(), key=lambda x: os.path.basename(x[0]).lower()))

    def _ok(self) -> None:
        if self.table.rowCount() < 1:
            QMessageBox.information(self, T('Combina file'), T('Aggiungi almeno un file.'))
            return
        self.accept()

    def items(self) -> list[tuple[str, str]]:
        return [(p, "" if rng.strip().lower() in ("tutte", "all", T("tutte").lower(), "") else rng) for p, rng in self._rows()]


FILE_FILTER_ALL = (T('Documenti supportati (*.pdf *.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp *.xps *.oxps *.epub *.cbz *.svg *.txt *.html *.htm *.doc *.docx *.rtf *.odt *.xls *.xlsx *.ods *.csv *.ppt *.pptx *.odp);;PDF (*.pdf);;Tutti i file (*)'))


# ============================================================ firma a mano
class SignaturePad(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(520, 200)
        self.strokes: list[list[QPointF]] = []
        self.pen_color = QColor("#1a237e")
        self.pen_width = 2.6
        self.setCursor(Qt.CrossCursor)

    def mousePressEvent(self, e):
        self.strokes.append([e.position()])
        self.update()

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton and self.strokes:
            self.strokes[-1].append(e.position())
            self.update()

    def clear(self):
        self.strokes = []
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), Qt.white)
        p.setPen(QPen(QColor("#cfcfdf"), 1, Qt.DashLine))
        y = self.height() * 0.75
        p.drawLine(20, int(y), self.width() - 20, int(y))
        pen = QPen(self.pen_color, self.pen_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        for s in self.strokes:
            if len(s) == 1:
                p.drawPoint(s[0])
            path = QPainterPath()
            path.moveTo(s[0])
            for q in s[1:]:
                path.lineTo(q)
            p.drawPath(path)

    def to_image(self) -> QImage | None:
        pts = [q for s in self.strokes for q in s]
        if not pts:
            return None
        xs = [q.x() for q in pts]
        ys = [q.y() for q in pts]
        pad = 8
        r = QRectF(min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad)
        k = 3
        img = QImage(int(r.width() * k), int(r.height() * k), QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(k, k)
        p.translate(-r.topLeft())
        p.setPen(QPen(self.pen_color, self.pen_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for s in self.strokes:
            path = QPainterPath()
            path.moveTo(s[0])
            for q in s[1:]:
                path.lineTo(q)
            if len(s) == 1:
                p.drawPoint(s[0])
            p.drawPath(path)
        p.end()
        return img


class SignatureDialog(QDialog):
    """Crea una firma autografa: disegnata, scritta con un font calligrafico o da immagine."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(T('Crea la tua firma'))
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        lay.addWidget(self.tabs)
        # disegno
        w1 = QWidget()
        l1 = QVBoxLayout(w1)
        self.pad = SignaturePad()
        l1.addWidget(self.pad)
        r1 = QHBoxLayout()
        clear = QPushButton(T('Cancella'))
        clear.clicked.connect(self.pad.clear)
        self.color = ColorButton("#1a237e")
        self.color.changed.connect(lambda c: (setattr(self.pad, "pen_color", QColor(c)), self.pad.update()))
        r1.addWidget(QLabel(T('Colore:')))
        r1.addWidget(self.color)
        r1.addStretch()
        r1.addWidget(clear)
        l1.addLayout(r1)
        self.tabs.addTab(w1, T('Disegna'))
        # testo
        w2 = QWidget()
        l2 = QFormLayout(w2)
        self.name = QLineEdit(settings.get("author", os.environ.get("USERNAME", "")))
        self.font = QFontComboBox()
        for fam in (T('Segoe Script'), T('Ink Free'), T('Lucida Handwriting'), T('Brush Script MT'), T('Gabriola')):
            if QFont(fam).exactMatch() or fam in QFontComboBox().currentFont().families():
                self.font.setCurrentFont(QFont(fam))
                break
        else:
            self.font.setCurrentFont(QFont("Segoe Script"))
        self.preview = QLabel()
        self.preview.setMinimumHeight(110)
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet("background:white; border:1px solid #ddd; color:#1a237e;")
        self.name.textChanged.connect(self._prev)
        self.font.currentFontChanged.connect(self._prev)
        l2.addRow(T('Nome:'), self.name)
        l2.addRow(T('Carattere:'), self.font)
        l2.addRow(self.preview)
        self.tabs.addTab(w2, T('Scrivi'))
        # immagine
        w3 = QWidget()
        l3 = QVBoxLayout(w3)
        self.img_path = PathEdit("", "open", T('Immagini (*.png *.jpg *.jpeg *.bmp)'))
        l3.addWidget(QLabel(T('Immagine della firma (meglio PNG con sfondo trasparente o bianco):')))
        l3.addWidget(self.img_path)
        self.remove_white = QCheckBox(T('Rendi trasparente lo sfondo bianco'))
        self.remove_white.setChecked(True)
        l3.addWidget(self.remove_white)
        l3.addStretch()
        self.tabs.addTab(w3, T('Immagine'))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(T('Salva firma'))
        bb.button(QDialogButtonBox.Cancel).setText(T('Annulla'))
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.result_path = None
        self._prev()

    def _prev(self, *_):
        f = self.font.currentFont()
        f.setPointSize(36)
        self.preview.setFont(f)
        self.preview.setText(self.name.text() or T('Firma'))

    def _text_image(self) -> QImage:
        f = self.font.currentFont()
        f.setPixelSize(140)
        from PySide6.QtGui import QFontMetrics
        fm = QFontMetrics(f)
        text = self.name.text() or T('Firma')
        w = fm.horizontalAdvance(text) + 60
        h = fm.height() + 40
        img = QImage(w, h, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(f)
        p.setPen(QColor("#1a237e"))
        p.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, text)
        p.end()
        return img

    def _ok(self):
        tab = self.tabs.currentIndex()
        if tab == 0:
            img = self.pad.to_image()
            if img is None:
                QMessageBox.information(self, T('Firma'), T('Disegna la firma nel riquadro.'))
                return
        elif tab == 1:
            if not self.name.text().strip():
                return
            img = self._text_image()
        else:
            path = self.img_path.text()
            if not os.path.exists(path):
                QMessageBox.information(self, T('Firma'), T("Scegli un'immagine."))
                return
            img = QImage(path).convertToFormat(QImage.Format_ARGB32)
            if self.remove_white.isChecked():
                for y in range(img.height()):
                    for x in range(img.width()):
                        c = img.pixelColor(x, y)
                        if c.red() > 235 and c.green() > 235 and c.blue() > 235:
                            img.setPixelColor(x, y, QColor(255, 255, 255, 0))
        import time
        out = os.path.join(settings.app_data_dir("firme"), f"firma_{int(time.time())}.png")
        img.save(out, "PNG")
        self.result_path = out
        self.accept()


class SignaturePicker(QDialog):
    """Sceglie una firma salvata (o ne crea una nuova)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(T('Firme salvate'))
        self.resize(520, 380)
        lay = QVBoxLayout(self)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(QSize(200, 80))
        self.list.setSpacing(10)
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        lay.addWidget(self.list)
        row = QHBoxLayout()
        b = QPushButton(T('Nuova firma…'))
        b.clicked.connect(self.new)
        d = QPushButton(T('Elimina'))
        d.clicked.connect(self.delete)
        row.addWidget(b)
        row.addWidget(d)
        row.addStretch()
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(T('Usa questa firma'))
        bb.button(QDialogButtonBox.Cancel).setText(T('Annulla'))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.load()
        if self.list.count() == 0:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self.new)

    def load(self):
        self.list.clear()
        d = settings.app_data_dir("firme")
        for fn in sorted(os.listdir(d), reverse=True):
            if fn.lower().endswith(".png"):
                p = os.path.join(d, fn)
                pm = QPixmap(p).scaled(200, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                it = QListWidgetItem(pm, "")
                it.setData(Qt.UserRole, p)
                self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)

    def new(self):
        d = SignatureDialog(self)
        if d.exec() == QDialog.Accepted:
            self.load()

    def delete(self):
        it = self.list.currentItem()
        if it and QMessageBox.question(self, T('Elimina firma'), T('Eliminare la firma selezionata?')) == QMessageBox.Yes:
            os.remove(it.data(Qt.UserRole))
            self.load()

    def path(self) -> str | None:
        it = self.list.currentItem()
        return it.data(Qt.UserRole) if it else None


# ============================================================== compressione
class CompressDialog(QDialog):
    def __init__(self, parent, size_now: int):
        super().__init__(parent)
        from .ops.compress import PRESETS
        self.setWindowTitle(T('Riduci dimensione file'))
        lay = QVBoxLayout(self)
        l = QLabel(T('Dimensione attuale: <b>{}</b>').format(human_size(size_now)))
        lay.addWidget(l)
        self.preset = QComboBox()
        for name in PRESETS:
            self.preset.addItem(T(name), name)
        self.preset.addItem(T('Personalizzata'), "Personalizzata")
        self.preset.setCurrentIndex(1)
        f = QFormLayout()
        f.addRow(T('Livello:'), self.preset)
        self.dpi = QSpinBox()
        self.dpi.setRange(36, 600)
        self.dpi.setValue(150)
        self.dpi.setSuffix(" dpi")
        self.q = QSpinBox()
        self.q.setRange(10, 100)
        self.q.setValue(72)
        self.q.setSuffix(" %")
        f.addRow(T('Risoluzione immagini:'), self.dpi)
        f.addRow(T('Qualità JPEG:'), self.q)
        lay.addLayout(f)
        self.gray = QCheckBox(T('Converti le immagini in scala di grigi'))
        self.fonts = QCheckBox(T('Riduci i font incorporati ai soli caratteri usati'))
        self.fonts.setChecked(True)
        self.meta = QCheckBox(T('Rimuovi metadati'))
        self.thumbs = QCheckBox(T('Rimuovi miniature incorporate'))
        self.thumbs.setChecked(True)
        self.emb = QCheckBox(T('Rimuovi file allegati'))
        self.ann = QCheckBox(T('Rimuovi annotazioni e commenti'))
        self.flat = QCheckBox(T('Appiattisci i moduli'))
        for w in (self.gray, self.fonts, self.meta, self.thumbs, self.emb, self.ann, self.flat):
            lay.addWidget(w)
        self.preset.currentIndexChanged.connect(lambda _i: self._preset(self.preset.currentData()))
        self._preset(self.preset.currentData())
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(T('Comprimi'))
        bb.button(QDialogButtonBox.Cancel).setText(T('Annulla'))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _preset(self, name):
        from .ops.compress import PRESETS
        p = PRESETS.get(name)
        custom = name == "Personalizzata"
        self.dpi.setEnabled(custom or bool(p))
        self.q.setEnabled(custom or bool(p))
        if p:
            self.dpi.setValue(p["dpi_target"])
            self.q.setValue(p["quality"])

    def options(self):
        from .ops.compress import PRESETS, CompressOptions
        name = self.preset.currentData()
        images = PRESETS.get(name, True) is not None
        return CompressOptions(images=images, dpi_threshold=int(self.dpi.value() * 1.2), dpi_target=self.dpi.value(),
                               quality=self.q.value(), grayscale=self.gray.isChecked(),
                               subset_fonts=self.fonts.isChecked(), remove_metadata=self.meta.isChecked(),
                               remove_thumbnails=self.thumbs.isChecked(), remove_embedded_files=self.emb.isChecked(),
                               remove_annotations=self.ann.isChecked(), flatten_forms=self.flat.isChecked())


# ============================================================== protezione
class EncryptDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        from .ops.security import PERMISSIONS
        self.setWindowTitle(T('Proteggi con password'))
        lay = QVBoxLayout(self)
        g1 = QGroupBox(T('Password di apertura'))
        f1 = QFormLayout(g1)
        self.use_user = QCheckBox(T('Richiedi una password per aprire il documento'))
        self.user = QLineEdit()
        self.user.setEchoMode(QLineEdit.Password)
        self.user2 = QLineEdit()
        self.user2.setEchoMode(QLineEdit.Password)
        f1.addRow(self.use_user)
        f1.addRow(T('Password:'), self.user)
        f1.addRow(T('Conferma:'), self.user2)
        lay.addWidget(g1)
        g2 = QGroupBox(T('Restrizioni (password dei permessi)'))
        v2 = QVBoxLayout(g2)
        self.use_owner = QCheckBox(T('Limita stampa e modifica'))
        self.use_owner.setChecked(True)
        v2.addWidget(self.use_owner)
        f2 = QFormLayout()
        self.owner = QLineEdit()
        self.owner.setEchoMode(QLineEdit.Password)
        f2.addRow(T('Password dei permessi:'), self.owner)
        v2.addLayout(f2)
        self.perms = []
        for label, flag in PERMISSIONS:
            cb = QCheckBox(T('Consenti: {}').format(label))
            cb.setChecked(flag in (pymupdf.PDF_PERM_PRINT, pymupdf.PDF_PERM_PRINT_HQ, pymupdf.PDF_PERM_ACCESSIBILITY,
                                   pymupdf.PDF_PERM_FORM))
            self.perms.append((cb, flag))
            v2.addWidget(cb)
        lay.addWidget(g2)
        note = QLabel(T('Cifratura AES a 256 bit. La protezione viene applicata al salvataggio.'))
        note.setObjectName("muted")
        lay.addWidget(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(T('Applica'))
        bb.button(QDialogButtonBox.Cancel).setText(T('Annulla'))
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _ok(self):
        if self.use_user.isChecked():
            if not self.user.text():
                QMessageBox.warning(self, T('Password'), T('Inserisci la password di apertura.'))
                return
            if self.user.text() != self.user2.text():
                QMessageBox.warning(self, T('Password'), T('Le due password di apertura non coincidono.'))
                return
        if self.use_owner.isChecked() and not self.owner.text():
            QMessageBox.warning(self, T('Password'), T('Inserisci la password dei permessi.'))
            return
        if self.use_owner.isChecked() and self.use_user.isChecked() and self.owner.text() == self.user.text():
            QMessageBox.warning(self, T('Password'), T('La password dei permessi deve essere diversa da quella di apertura.'))
            return
        if not self.use_user.isChecked() and not self.use_owner.isChecked():
            QMessageBox.warning(self, T('Protezione'), T('Scegli almeno una delle due protezioni.'))
            return
        self.accept()

    def result_options(self) -> dict:
        perms = 0
        for cb, flag in self.perms:
            if cb.isChecked() or not self.use_owner.isChecked():
                perms |= flag
        import secrets
        owner = self.owner.text() if self.use_owner.isChecked() else secrets.token_urlsafe(16)
        return {"user_pw": self.user.text() if self.use_user.isChecked() else "", "owner_pw": owner,
                "permissions": perms}


# ================================================================== proprietà
class PropertiesDialog(QDialog):
    def __init__(self, parent, model):
        super().__init__(parent)
        from .ops import security as SEC
        self.setWindowTitle(T('Proprietà del documento'))
        self.resize(620, 560)
        self.model = model
        lay = QVBoxLayout(self)
        tabs = QTabWidget()
        lay.addWidget(tabs)
        # descrizione (modificabile)
        w = QWidget()
        f = QFormLayout(w)
        md = model.doc.metadata or {}
        self.fields = {}
        for key, label in SEC.METADATA_FIELDS:
            e = QLineEdit(md.get(key, "") or "")
            self.fields[key] = e
            f.addRow(label + ":", e)
        tabs.addTab(w, T('Descrizione'))
        # informazioni
        size = os.path.getsize(model.path) if model.path and os.path.exists(model.path) else None
        rows = SEC.document_info(model.doc, model.path, size)
        t = QTableWidget(len(rows), 2)
        t.setHorizontalHeaderLabels([T('Proprietà'), T('Valore')])
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setStretchLastSection(True)
        t.setColumnWidth(0, 160)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setWordWrap(True)
        for i, (k, v) in enumerate(rows):
            t.setItem(i, 0, QTableWidgetItem(k))
            t.setItem(i, 1, QTableWidgetItem(v))
        t.resizeRowsToContents()
        tabs.addTab(t, T('Informazioni'))
        # permessi
        perm = QWidget()
        pv = QVBoxLayout(perm)
        for label, flag in SEC.PERMISSIONS:
            ok = bool(model.doc.permissions & flag)
            pv.addWidget(QLabel(("✔  " if ok else "✖  ") + label))
        pv.addStretch()
        tabs.addTab(perm, T('Sicurezza'))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(T('Salva proprietà'))
        bb.button(QDialogButtonBox.Cancel).setText(T('Chiudi'))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def values(self) -> dict:
        return {k: e.text() for k, e in self.fields.items()}


# ===================================================================== report
class ReportDialog(QDialog):
    def __init__(self, parent, title: str, html: str, save_name: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(780, 560)
        lay = QVBoxLayout(self)
        self.browser = QTextBrowser()
        self.browser.setHtml(html)
        lay.addWidget(self.browser)
        row = QHBoxLayout()
        row.addStretch()
        if save_name:
            b = QPushButton(T('Salva come HTML…'))
            b.clicked.connect(lambda: self._save(html, save_name))
            row.addWidget(b)
        c = QPushButton(T('Chiudi'))
        c.clicked.connect(self.accept)
        row.addWidget(c)
        lay.addLayout(row)

    def _save(self, html, name):
        p, _ = QFileDialog.getSaveFileName(self, T('Salva report'), name, T('HTML (*.html)'))
        if p:
            with open(p, "w", encoding="utf-8") as f:
                f.write(html)


# ================================================================ impostazioni
def settings_dialog(parent, tools) -> dict | None:
    from . import i18n
    return ask(parent, T('Impostazioni'), [
        ("section", T('Aspetto'), "section"),
        ("language", T("Lingua dell'interfaccia"), "choice", i18n.LANG, [(name, code) for code, name in i18n.LANGUAGES]),
        ("theme", T('Tema'), "choice", settings.get("theme", "light"),
         [(T('Chiaro'), "light"), (T('Scuro'), "dark"), (T('Come Windows'), "system")]),
        ("zoom", T("Zoom all'apertura"), "choice", settings.get("open_zoom", "width"),
         [(T('Adatta alla larghezza'), "width"), (T('Pagina intera'), "page"), ("100%", "100")]),
        ("layout", T("Visualizzazione all'apertura"), "choice", settings.get("open_layout", "continuous"),
         [(T('Pagine continue'), "continuous"), (T('Pagina singola'), "single"), (T('Due pagine affiancate'), "two")]),
        ("section", T('Commenti e modifica'), "section"),
        ("author", T('Nome autore'), "str", tools.author),
        ("keep_tool", T("Mantieni lo strumento attivo dopo l'uso"), "bool", tools.keep_tool),
        ("text_family", T('Font predefinito per il testo nuovo'), "font", tools.text_family),
        ("text_size", T('Corpo predefinito (pt)'), "float", tools.text_size, (4, 200)),
        ("section", T('Generale'), "section"),
        ("restore", T("Riapri i documenti dell'ultima sessione"), "bool", settings.get("restore_session", False, bool)),
        ("highlight_fields", T('Evidenzia i campi dei moduli'), "bool", settings.get("highlight_fields", True, bool)),
    ], ok_text=T('Salva'))
