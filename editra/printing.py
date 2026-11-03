"""Stampa e anteprima di stampa."""
from __future__ import annotations

import pymupdf
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPageLayout, QPainter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import QApplication, QCheckBox, QMessageBox, QProgressDialog

from .ops.common import parse_ranges
from .i18n import T


def _pages_to_print(printer: QPrinter, total: int, current: int) -> list[int]:
    rng = printer.printRange()
    if rng == QPrinter.PageRange:
        a, b = printer.fromPage(), printer.toPage()
        if a <= 0:
            return list(range(total))
        return list(range(a - 1, min(b, total)))
    if rng == QPrinter.CurrentPage:
        return [current]
    return list(range(total))


def render_to_printer(printer: QPrinter, doc: pymupdf.Document, pages: list[int], annots: bool = True,
                      fit: bool = True, max_dpi: int = 300, parent=None) -> bool:
    painter = QPainter()
    if not painter.begin(printer):
        return False
    dpi = min(printer.resolution(), max_dpi)
    prog = None
    if parent is not None and len(pages) > 3:
        prog = QProgressDialog(T('Stampa in corso…'), T('Annulla'), 0, len(pages), parent)
        prog.setWindowModality(Qt.WindowModal)
        prog.setMinimumDuration(300)
    try:
        copies = printer.copyCount() if not printer.supportsMultipleCopies() else 1
        seq = []
        for _ in range(max(1, copies)):
            seq.extend(pages)
        for k, pno in enumerate(seq):
            if prog:
                prog.setValue(k)
                QApplication.processEvents()
                if prog.wasCanceled():
                    printer.abort()
                    return False
            if k > 0:
                printer.newPage()
            page = doc[pno]
            pix = page.get_pixmap(dpi=dpi, annots=annots, alpha=False)
            img = QImage(pix.samples_mv, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
            target = printer.pageLayout().paintRectPixels(printer.resolution())
            area = QRectF(0, 0, target.width(), target.height())
            iw, ih = img.width(), img.height()
            # pagina orizzontale su foglio verticale: ruota per sfruttare il foglio
            rotate = (iw > ih) != (area.width() > area.height())
            painter.save()
            if rotate:
                painter.translate(area.width(), 0)
                painter.rotate(90)
                area = QRectF(0, 0, area.height(), area.width())
            if fit:
                k_ = min(area.width() / iw, area.height() / ih)
            else:
                # dimensione reale: 1 punto PDF = 1/72 di pollice
                k_ = printer.resolution() / dpi
            w, h = iw * k_, ih * k_
            painter.drawImage(QRectF((area.width() - w) / 2, (area.height() - h) / 2, w, h), img)
            painter.restore()
    finally:
        painter.end()
        if prog:
            prog.close()
    return True


def print_document(parent, model, current: int) -> None:
    doc = model.doc
    if not doc.permissions & pymupdf.PDF_PERM_PRINT:
        QMessageBox.warning(parent, T('Stampa'), T("L'autore del documento non consente la stampa."))
        return
    printer = QPrinter(QPrinter.HighResolution)
    printer.setDocName(model.title)
    printer.setFromTo(1, doc.page_count)
    dlg = QPrintDialog(printer, parent)
    dlg.setWindowTitle(T('Stampa – {}').format(model.title))
    dlg.setOption(QPrintDialog.PrintCurrentPage, True)
    dlg.setOption(QPrintDialog.PrintPageRange, True)
    dlg.setMinMax(1, doc.page_count)
    annots = QCheckBox(T('Stampa commenti e annotazioni'))
    annots.setChecked(True)
    dlg.setOptionTabs([])
    if dlg.exec() != QPrintDialog.Accepted:
        return
    pages = _pages_to_print(printer, doc.page_count, current)
    render_to_printer(printer, doc, pages, annots=True, parent=parent)


def print_preview(parent, model, current: int) -> None:
    doc = model.doc
    printer = QPrinter(QPrinter.HighResolution)
    printer.setDocName(model.title)
    prev = QPrintPreviewDialog(printer, parent)
    prev.setWindowTitle(T('Anteprima di stampa – {}').format(model.title))
    prev.resize(1000, 760)

    def paint(p: QPrinter):
        pages = _pages_to_print(p, doc.page_count, current)
        render_to_printer(p, doc, pages, max_dpi=110)

    prev.paintRequested.connect(paint)
    prev.exec()


def print_pages(parent, model, page_text: str) -> None:
    pages = parse_ranges(page_text, model.page_count)
    printer = QPrinter(QPrinter.HighResolution)
    dlg = QPrintDialog(printer, parent)
    if dlg.exec() == QPrintDialog.Accepted:
        render_to_printer(printer, model.doc, pages, parent=parent)
