"""Stampa con finestra propria e anteprima dal vivo.

La finestra di stampa di Windows 11 non mostra l'anteprima per i programmi
desktop come questo, quindi la stampa ha un dialogo suo: anteprima del foglio
e opzioni (pagine, adattamento, più pagine per foglio, orientamento, colore,
fronte/retro). Lo stesso codice disegna il foglio nell'anteprima e sulla
stampante: quello che si vede è quello che esce.
"""
from __future__ import annotations

from dataclasses import dataclass

import pymupdf
from PySide6.QtCore import QMarginsF, QRectF, QSize, QSizeF, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter, QPen, QPixmap
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrinterInfo
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFormLayout, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QProgressDialog, QPushButton, QScrollArea, QSpinBox,
                               QToolButton, QVBoxLayout, QWidget)

from . import icons, theme
from .i18n import T
from .ops.common import parse_ranges

# griglia (colonne, righe) per più pagine per foglio
_GRID_LANDSCAPE = {1: (1, 1), 2: (2, 1), 4: (2, 2), 6: (3, 2), 9: (3, 3), 16: (4, 4)}
_GRID_PORTRAIT = {1: (1, 1), 2: (1, 2), 4: (2, 2), 6: (2, 3), 9: (3, 3), 16: (4, 4)}
CELL_GAP = 8.0   # punti fra le pagine nello stesso foglio


@dataclass
class PrintOptions:
    pages: str = "all"            # all | current | range | odd | even
    range_text: str = ""
    reverse: bool = False
    annots: bool = True
    scale: str = "fit"            # fit | actual | shrink | custom
    custom_pct: int = 100
    per_sheet: int = 1
    borders: bool = False
    orientation: str = "auto"     # auto | portrait | landscape
    grayscale: bool = False
    dpi: int = 300
    copies: int = 1
    collate: bool = True
    duplex: str = "none"          # none | long | short


# ------------------------------------------------------------------ calcoli
def select_pages(page_count: int, current: int, opt: PrintOptions) -> list[int]:
    if opt.pages == "current":
        pages = [current]
    elif opt.pages == "range":
        pages = parse_ranges(opt.range_text, page_count)
    elif opt.pages == "odd":
        pages = list(range(0, page_count, 2))
    elif opt.pages == "even":
        pages = list(range(1, page_count, 2))
    else:
        pages = list(range(page_count))
    return list(reversed(pages)) if opt.reverse else pages


def make_sheets(pages: list[int], per_sheet: int) -> list[list[int]]:
    n = max(1, per_sheet)
    return [pages[i:i + n] for i in range(0, len(pages), n)]


def job_landscape(doc: pymupdf.Document, pages: list[int], opt: PrintOptions) -> bool:
    """Orientamento del foglio per tutto il lavoro di stampa."""
    if opt.orientation == "landscape":
        return True
    if opt.orientation == "portrait":
        return False
    if opt.per_sheet in (2, 6):
        return True
    if opt.per_sheet == 1 and pages:
        # come la maggior parte delle pagine da stampare
        wide = sum(1 for p in pages[:50] if doc[p].rect.width > doc[p].rect.height)
        return wide > len(pages[:50]) / 2
    return False


def _cells(area: QRectF, n: int, landscape: bool) -> list[QRectF]:
    cols, rows = (_GRID_LANDSCAPE if landscape else _GRID_PORTRAIT)[n]
    gap = CELL_GAP if n > 1 else 0.0
    cw = (area.width() - gap * (cols - 1)) / cols
    ch = (area.height() - gap * (rows - 1)) / rows
    return [QRectF(area.left() + c * (cw + gap), area.top() + r * (ch + gap), cw, ch)
            for r in range(rows) for c in range(cols)]


def paint_sheet(painter: QPainter, area: QRectF, doc: pymupdf.Document, sheet: list[int], opt: PrintOptions,
                landscape: bool, px_per_pt: float, cache: dict | None = None) -> None:
    """Disegna un foglio. Il pittore lavora in punti tipografici; area = zona stampabile."""
    n = opt.per_sheet if opt.per_sheet in _GRID_PORTRAIT else 1
    for cell, pno in zip(_cells(area, n, landscape), sheet):
        page = doc[pno]
        pw, ph = page.rect.width, page.rect.height
        rotate = (pw > ph) != (cell.width() > cell.height()) and abs(pw - ph) > 1
        bw, bh = (ph, pw) if rotate else (pw, ph)          # ingombro dopo l'eventuale rotazione
        fit = min(cell.width() / bw, cell.height() / bh)
        if n > 1 or opt.scale == "fit":
            k = fit
        elif opt.scale == "actual":
            k = 1.0
        elif opt.scale == "shrink":
            k = min(1.0, fit)
        else:
            k = max(0.05, opt.custom_pct / 100)
        img = _page_image(page, k * px_per_pt, opt, cache)
        w, h = pw * k, ph * k
        painter.save()
        painter.setClipRect(cell)
        painter.translate(cell.center())
        if rotate:
            painter.rotate(90)
        target = QRectF(-w / 2, -h / 2, w, h)
        painter.drawImage(target, img)
        if opt.borders:
            pen = QPen(QColor("#555555"), 0.5)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(target)
        painter.restore()


def _page_image(page: pymupdf.Page, zoom: float, opt: PrintOptions, cache: dict | None) -> QImage:
    zoom = min(zoom, 12.0)
    key = (page.number, round(zoom, 3), opt.annots, opt.grayscale)
    if cache is not None and key in cache:
        return cache[key]
    cs = pymupdf.csGRAY if opt.grayscale else pymupdf.csRGB
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=cs, annots=opt.annots, alpha=False)
    fmt = QImage.Format_Grayscale8 if opt.grayscale else QImage.Format_RGB888
    img = QImage(pix.samples_mv, pix.width, pix.height, pix.stride, fmt).copy()
    if cache is not None:
        if len(cache) > 40:
            cache.clear()
        cache[key] = img
    return img


# ---------------------------------------------------------------- stampa
def configure_printer(printer: QPrinter, page_size: QPageSize | None, landscape: bool, opt: PrintOptions) -> None:
    if page_size is not None and page_size.isValid():
        printer.setPageSize(page_size)
    printer.setPageOrientation(QPageLayout.Landscape if landscape else QPageLayout.Portrait)
    printer.setColorMode(QPrinter.GrayScale if opt.grayscale else QPrinter.Color)
    printer.setDuplex({"long": QPrinter.DuplexLongSide, "short": QPrinter.DuplexShortSide}.get(opt.duplex,
                                                                                               QPrinter.DuplexNone))
    printer.setCopyCount(max(1, opt.copies))
    printer.setCollateCopies(opt.collate)
    printer.setFullPage(False)


def print_job(printer: QPrinter, doc: pymupdf.Document, opt: PrintOptions, current: int, parent=None,
              page_size: QPageSize | None = None, configure: bool = True) -> bool:
    pages = select_pages(doc.page_count, current, opt)
    if not pages:
        return False
    sheets = make_sheets(pages, opt.per_sheet)
    landscape = job_landscape(doc, pages, opt)
    if configure:
        configure_printer(printer, page_size, landscape, opt)
    # copie fatte da noi se il driver non le gestisce
    copies = 1 if printer.supportsMultipleCopies() else max(1, printer.copyCount())
    if copies > 1:
        seq = [s for _ in range(copies) for s in sheets] if opt.collate else [s for s in sheets for _ in range(copies)]
    else:
        seq = sheets
    painter = QPainter()
    if not painter.begin(printer):
        return False
    prog = None
    if parent is not None and len(seq) > 2:
        prog = QProgressDialog(T('Stampa in corso…'), T('Annulla'), 0, len(seq), parent)
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(300)
    try:
        res = printer.resolution()
        r = printer.pageLayout().paintRectPixels(res)
        area = QRectF(0, 0, r.width() * 72 / res, r.height() * 72 / res)
        painter.scale(res / 72, res / 72)
        cache: dict = {}
        for k, sheet in enumerate(seq):
            if prog:
                prog.setValue(k)
                QApplication.processEvents()
                if prog.wasCanceled():
                    printer.abort()
                    return False
            if k > 0:
                printer.newPage()
            paint_sheet(painter, area, doc, sheet, opt, landscape, opt.dpi / 72, cache)
    finally:
        painter.end()
        if prog:
            prog.close()
    return True


def render_to_printer(printer: QPrinter, doc: pymupdf.Document, pages: list[int], annots: bool = True,
                      fit: bool = True, max_dpi: int = 300, parent=None) -> bool:
    """Stampa diretta di un elenco di pagine (senza dialogo)."""
    opt = PrintOptions(pages="range", range_text=",".join(str(p + 1) for p in pages), annots=annots,
                       scale="fit" if fit else "actual", dpi=min(max_dpi, 600))
    return print_job(printer, doc, opt, 0, parent, configure=False)


# ------------------------------------------------------------------ dialogo
class PrintDialog(QDialog):
    def __init__(self, parent, model, current: int):
        super().__init__(parent)
        self.model = model
        self.doc = model.doc
        self.current = current
        self.sheet_index = 0
        self.cache: dict = {}
        self.setWindowTitle(T('Stampa – {}').format(model.title))
        self.resize(1080, 760)
        lay = QHBoxLayout(self)

        # --- opzioni
        side = QWidget()
        form = QFormLayout(side)
        form.setLabelAlignment(Qt.AlignRight)
        self.printer_box = QComboBox()
        names = QPrinterInfo.availablePrinterNames()
        self.printer_box.addItems(names)
        default = QPrinterInfo.defaultPrinterName()
        if default in names:
            self.printer_box.setCurrentText(default)
        form.addRow(T('Stampante:'), self.printer_box)
        self.status = QLabel()
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        form.addRow("", self.status)
        self.copies = QSpinBox()
        self.copies.setRange(1, 999)
        self.collate = QCheckBox(T('Fascicola'))
        self.collate.setChecked(True)
        row = QHBoxLayout()
        row.addWidget(self.copies)
        row.addWidget(self.collate)
        form.addRow(T('Copie:'), row)

        form.addRow(self._section(T('Pagine')))
        self.pages_box = QComboBox()
        for label, code in ((T('Tutte'), "all"), (T('Pagina corrente'), "current"), (T('Intervallo'), "range"),
                            (T('Solo dispari'), "odd"), (T('Solo pari'), "even")):
            self.pages_box.addItem(label, code)
        form.addRow(T('Stampa:'), self.pages_box)
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText(T('es. 1-3, 5, 8-fine'))
        form.addRow(T('Intervallo:'), self.range_edit)
        self.reverse = QCheckBox(T('Ordine inverso'))
        form.addRow("", self.reverse)
        self.content = QComboBox()
        self.content.addItem(T('Documento e commenti'), True)
        self.content.addItem(T('Solo il documento'), False)
        form.addRow(T('Contenuto:'), self.content)

        form.addRow(self._section(T('Impaginazione')))
        self.size_box = QComboBox()
        form.addRow(T('Formato carta:'), self.size_box)
        self.orient = QComboBox()
        for label, code in ((T('Automatico'), "auto"), (T('Verticale'), "portrait"), (T('Orizzontale'), "landscape")):
            self.orient.addItem(label, code)
        form.addRow(T('Orientamento:'), self.orient)
        self.per_sheet = QComboBox()
        for n in (1, 2, 4, 6, 9, 16):
            self.per_sheet.addItem(str(n), n)
        form.addRow(T('Pagine per foglio:'), self.per_sheet)
        self.borders = QCheckBox(T('Bordo intorno alle pagine'))
        form.addRow("", self.borders)
        self.scale = QComboBox()
        for label, code in ((T('Adatta al foglio'), "fit"), (T('Dimensione reale'), "actual"),
                            (T('Riduci se troppo grande'), "shrink"), (T('Personalizzata'), "custom")):
            self.scale.addItem(label, code)
        form.addRow(T('Dimensioni:'), self.scale)
        self.pct = QSpinBox()
        self.pct.setRange(5, 400)
        self.pct.setValue(100)
        self.pct.setSuffix(" %")
        form.addRow(T('Scala:'), self.pct)

        form.addRow(self._section(T('Qualità')))
        self.color = QComboBox()
        self.color.addItem(T('A colori'), False)
        self.color.addItem(T('Bianco e nero'), True)
        form.addRow(T('Colore:'), self.color)
        self.duplex = QComboBox()
        for label, code in ((T('Solo fronte'), "none"), (T('Fronte/retro, lato lungo'), "long"),
                            (T('Fronte/retro, lato corto'), "short")):
            self.duplex.addItem(label, code)
        form.addRow(T('Fronte/retro:'), self.duplex)
        self.dpi = QComboBox()
        for label, d in ((T('Bozza (150 dpi)'), 150), (T('Normale (300 dpi)'), 300), (T('Alta (600 dpi)'), 600)):
            self.dpi.addItem(label, d)
        self.dpi.setCurrentIndex(1)
        form.addRow(T('Qualità:'), self.dpi)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(side)
        scroll.setFixedWidth(370)

        # --- anteprima
        right = QVBoxLayout()
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumSize(420, 420)
        self.preview.setStyleSheet(f"background: {theme.current['viewer']}; border-radius: 8px;")
        right.addWidget(self.preview, 1)
        nav = QHBoxLayout()
        self.prev_btn = QToolButton()
        self.prev_btn.setIcon(icons.icon("prev"))
        self.prev_btn.clicked.connect(lambda: self._go(-1))
        self.next_btn = QToolButton()
        self.next_btn.setIcon(icons.icon("next"))
        self.next_btn.clicked.connect(lambda: self._go(1))
        self.sheet_lbl = QLabel()
        self.sheet_lbl.setAlignment(Qt.AlignCenter)
        self.paper_lbl = QLabel()
        self.paper_lbl.setObjectName("muted")
        nav.addWidget(self.paper_lbl)
        nav.addStretch()
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.sheet_lbl)
        nav.addWidget(self.next_btn)
        nav.addStretch()
        right.addLayout(nav)
        buttons = QHBoxLayout()
        system = QPushButton(T('Dialogo di sistema…'))
        system.setToolTip(T('Apre la finestra di stampa di Windows per le impostazioni avanzate della stampante'))
        system.clicked.connect(self._system_dialog)
        buttons.addWidget(system)
        buttons.addStretch()
        cancel = QPushButton(T('Annulla'))
        cancel.clicked.connect(self.reject)
        self.print_btn = QPushButton(T('Stampa'))
        self.print_btn.setObjectName("primary")
        self.print_btn.setDefault(True)
        self.print_btn.clicked.connect(self._print)
        buttons.addWidget(cancel)
        buttons.addWidget(self.print_btn)
        right.addLayout(buttons)
        lay.addWidget(scroll)
        lay.addLayout(right, 1)

        self._timer = QTimer(self, singleShot=True, interval=120, timeout=self._refresh)
        self.printer: QPrinter | None = None
        for w in (self.pages_box, self.content, self.orient, self.per_sheet, self.scale, self.color, self.size_box):
            w.currentIndexChanged.connect(self._changed)
        for w in (self.reverse, self.borders):
            w.toggled.connect(self._changed)
        self.range_edit.textChanged.connect(self._changed)
        self.pct.valueChanged.connect(self._changed)
        self.printer_box.currentTextChanged.connect(self._printer_changed)
        self._printer_changed(self.printer_box.currentText())
        if not names:
            self.status.setText(T('Nessuna stampante installata in Windows.'))
            self.print_btn.setEnabled(False)

    @staticmethod
    def _section(text: str) -> QLabel:
        l = QLabel(text)
        l.setStyleSheet("font-weight: 600; padding-top: 10px;")
        return l

    # -------------------------------------------------------- stampante
    def _printer_changed(self, name: str) -> None:
        info = QPrinterInfo.printerInfo(name) if name else QPrinterInfo()
        self.printer = QPrinter(info, QPrinter.HighResolution) if name else QPrinter(QPrinter.HighResolution)
        self.printer.setDocName(self.model.title)
        sizes = info.supportedPageSizes() if name else []
        default = info.defaultPageSize() if name else QPageSize(QPageSize.A4)
        self.size_box.blockSignals(True)
        self.size_box.clear()
        for s in sizes or [QPageSize(QPageSize.A4), QPageSize(QPageSize.Letter)]:
            self.size_box.addItem(s.name(), s)
        idx = next((i for i in range(self.size_box.count())
                    if self.size_box.itemData(i).isEquivalentTo(default)), 0)
        self.size_box.setCurrentIndex(idx)
        self.size_box.blockSignals(False)
        duplex_ok = bool(name) and any(m != QPrinter.DuplexNone for m in info.supportedDuplexModes())
        self.duplex.setEnabled(duplex_ok)
        if not duplex_ok:
            self.duplex.setCurrentIndex(0)
        state = []
        if name and info.isDefault():
            state.append(T('Stampante predefinita'))
        if name and info.isRemote():
            state.append(T('Stampante di rete'))
        self.status.setText(" · ".join(state))
        self._changed()

    # ----------------------------------------------------------- opzioni
    def options(self) -> PrintOptions:
        return PrintOptions(
            pages=self.pages_box.currentData(), range_text=self.range_edit.text(), reverse=self.reverse.isChecked(),
            annots=self.content.currentData(), scale=self.scale.currentData(), custom_pct=self.pct.value(),
            per_sheet=self.per_sheet.currentData(), borders=self.borders.isChecked(),
            orientation=self.orient.currentData(), grayscale=self.color.currentData(), dpi=self.dpi.currentData(),
            copies=self.copies.value(), collate=self.collate.isChecked(), duplex=self.duplex.currentData())

    def _changed(self, *_):
        self.range_edit.setEnabled(self.pages_box.currentData() == "range")
        multi = self.per_sheet.currentData() != 1
        self.scale.setEnabled(not multi)
        self.borders.setEnabled(multi)
        self.pct.setEnabled(not multi and self.scale.currentData() == "custom")
        self._timer.start()

    def _sheets(self):
        opt = self.options()
        try:
            pages = select_pages(self.doc.page_count, self.current, opt)
            self.range_edit.setStyleSheet("")
        except ValueError as ex:
            self.range_edit.setStyleSheet("border: 1px solid #d33;")
            self.range_edit.setToolTip(str(ex))
            pages = []
        return opt, pages, make_sheets(pages, opt.per_sheet)

    def _layout(self, landscape: bool) -> QPageLayout:
        size = self.size_box.currentData() or QPageSize(QPageSize.A4)
        p = self.printer
        p.setPageSize(size)
        p.setPageOrientation(QPageLayout.Landscape if landscape else QPageLayout.Portrait)
        return p.pageLayout()

    # -------------------------------------------------------- anteprima
    def _refresh(self) -> None:
        opt, pages, sheets = self._sheets()
        self.print_btn.setEnabled(bool(sheets) and self.printer_box.count() > 0)
        if not sheets:
            self.preview.setText(T('Nessuna pagina da stampare'))
            self.sheet_lbl.setText("")
            return
        self.sheet_index = max(0, min(self.sheet_index, len(sheets) - 1))
        landscape = job_landscape(self.doc, pages, opt)
        layout = self._layout(landscape)
        paper = layout.fullRect(QPageLayout.Point)
        printable = layout.paintRect(QPageLayout.Point)
        avail = self.preview.size() - QSize(40, 40)
        s = min(avail.width() / paper.width(), avail.height() / paper.height())
        dpr = self.devicePixelRatioF()
        img = QImage(int(paper.width() * s * dpr) + 8, int(paper.height() * s * dpr) + 8, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(s * dpr, s * dpr)
        # ombra e foglio
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawRect(QRectF(3 / s, 4 / s, paper.width(), paper.height()))
        p.setBrush(Qt.white)
        p.drawRect(QRectF(0, 0, paper.width(), paper.height()))
        # margini non stampabili
        pen = QPen(QColor("#b9b4c8"), 0)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(printable)
        paint_sheet(p, printable, self.doc, sheets[self.sheet_index], opt, landscape, s * dpr, self.cache)
        p.end()
        pm = QPixmap.fromImage(img)
        pm.setDevicePixelRatio(dpr)
        self.preview.setPixmap(pm)
        self.sheet_lbl.setText(T('Foglio {} di {}').format(self.sheet_index + 1, len(sheets)))
        self.prev_btn.setEnabled(self.sheet_index > 0)
        self.next_btn.setEnabled(self.sheet_index < len(sheets) - 1)
        mm = lambda v: v * 25.4 / 72
        copies = opt.copies
        self.paper_lbl.setText(T('{} · {:.0f} × {:.0f} mm · pagine: {} · fogli: {}').format(
            self.size_box.currentText(), mm(paper.width()), mm(paper.height()), len(pages), len(sheets) * copies))

    def _go(self, d: int) -> None:
        self.sheet_index += d
        self._refresh()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        self._timer.start()

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self._timer.start()

    # ------------------------------------------------------------ stampa
    def _print(self, configured: bool = False) -> None:
        opt, pages, sheets = self._sheets()
        if not sheets:
            return
        ok = print_job(self.printer, self.doc, opt, self.current, self, self.size_box.currentData(),
                       configure=not configured)
        if ok:
            self.accept()
        else:
            QMessageBox.warning(self, T('Stampa'), T('Stampa non riuscita o annullata.'))

    def _system_dialog(self) -> None:
        opt, pages, sheets = self._sheets()
        if not sheets:
            return
        configure_printer(self.printer, self.size_box.currentData(), job_landscape(self.doc, pages, opt), opt)
        dlg = QPrintDialog(self.printer, self)
        dlg.setOption(QPrintDialog.PrintPageRange, False)
        dlg.setOption(QPrintDialog.PrintCurrentPage, False)
        if dlg.exec() == QPrintDialog.Accepted:
            # le scelte fatte nel dialogo di Windows (stampante, carta, driver) restano valide
            self._print(configured=True)


def print_document(parent, model, current: int) -> None:
    if not model.doc.permissions & pymupdf.PDF_PERM_PRINT:
        QMessageBox.warning(parent, T('Stampa'), T("L'autore del documento non consente la stampa."))
        return
    PrintDialog(parent, model, current).exec()


def print_preview(parent, model, current: int) -> None:
    print_document(parent, model, current)
