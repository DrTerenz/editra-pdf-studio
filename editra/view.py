"""Area di visualizzazione: pagine, zoom, selezione e strumenti di modifica col mouse.

Sistemi di coordinate:
- "PDF": punti della pagina non ruotata (quelli usati da PyMuPDF per testo e annotazioni);
- "vista": punti della pagina come appare (ruotata), origine in alto a sinistra;
- "scena": pixel logici di Qt = punti vista × scala (zoom × 96/72).
"""
from __future__ import annotations

import math

import pymupdf
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QBrush, QColor, QCursor, QImage, QKeySequence, QPainter, QPainterPath, QPen,
                           QPixmap, QPolygonF)
from PySide6.QtWidgets import (QApplication, QGraphicsItem, QGraphicsScene, QGraphicsView, QMenu,
                               QMessageBox)

from . import theme
from .model import PdfModel
from .ops import annots as A
from .ops import forms as F
from .ops import images as IM
from .ops import textedit as TE
from .ops.common import to_display, to_pdf
from .settings import MARKUP_TOOLS, ToolSettings
from .i18n import T

PX_PER_PT = 96 / 72
GAP = 14
MARGIN = 20
MAX_PIXELS = 36_000_000
HANDLE = 4.0   # mezza dimensione delle maniglie, in pixel

RECT_TOOLS = ("rect", "ellipse", "freetext", "callout", "link", "redact", "crop", "snapshot", "image",
              "stamp", "signature", "sign_digital", "form_text", "form_checkbox", "form_radio",
              "form_combobox", "form_listbox", "form_signature", "form_button", "zoom_area")
LINE_TOOLS = ("line", "arrow", "measure")
VERTEX_TOOLS = ("polygon", "polyline", "area")

CURSORS = {
    "hand": Qt.OpenHandCursor, "select": Qt.ArrowCursor, "edit_text": Qt.IBeamCursor,
    "edit_object": Qt.ArrowCursor, "note": Qt.PointingHandCursor, "eraser": Qt.PointingHandCursor,
}


class PageItem(QGraphicsItem):
    def __init__(self, view: T('DocumentView'), index: int, w: float, h: float):
        super().__init__()
        self.view = view
        self.index = index
        self.w_pt = w
        self.h_pt = h
        self.setCacheMode(QGraphicsItem.NoCache)

    def boundingRect(self) -> QRectF:
        s = self.view.scale_px
        return QRectF(-6, -6, self.w_pt * s + 12, self.h_pt * s + 12)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        self.view._paint_page(painter, self)


class DocumentView(QGraphicsView):
    page_changed = Signal(int)
    zoom_changed = Signal(float)
    status = Signal(str)
    selection_changed = Signal()
    annot_selected = Signal(object)        # (pagina, xref) oppure None
    request_annot_props = Signal(int, int)
    request_sign_field = Signal(str)
    request_tool = Signal(str)
    edit_finished = Signal()

    def __init__(self, model: PdfModel, tools: ToolSettings, parent=None):
        super().__init__(parent)
        self.model = model
        self.tools = tools
        self.scene_ = QGraphicsScene(self)
        self.setScene(self.scene_)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.NoAnchor)
        self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(False)

        self.zoom = 1.0
        self.fit_mode = "width"          # 'width', 'page' oppure None
        self.layout_mode = "continuous"  # 'continuous', 'single', 'two', 'two_cover'
        self.night = False
        self.highlight_fields = True
        self.items: list[PageItem] = []
        self.current = 0
        self._cache: dict[int, tuple[QPixmap, float, tuple]] = {}
        self._pending: set[int] = set()
        self._render_timer = QTimer(self, singleShot=True, interval=0, timeout=self._render_pending)

        # stato delle sovrapposizioni (coordinate vista)
        self.search_hits: dict[int, list[QRectF]] = {}
        self.current_hit: tuple[int, QRectF] | None = None
        self.text_sel: dict[int, list[QRectF]] = {}
        self.sel_text = ""
        self._sel_quads: list = []          # (pagina, rettangoli PDF per riga)
        self.hover: tuple[int, QRectF] | None = None
        self.sel_annot: tuple[int, int] | None = None
        self.sel_image: tuple[int, IM.PageImage] | None = None
        self.sel_block: tuple[int, TE.TextBlock] | None = None
        self.temp: dict | None = None
        self._press = None
        self._pan = None
        self.editor = None           # editor in linea attivo

        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        model.changed.connect(self._on_model_changed)
        model.structure_changed.connect(self.rebuild)
        tools.tool_changed.connect(self._on_tool_changed)
        tools.changed.connect(self.viewport().update)
        self.rebuild()

    # ============================================================ layout
    @property
    def scale_px(self) -> float:
        return self.zoom * PX_PER_PT

    def rebuild(self) -> None:
        self.cancel_editor()
        cur = self.current
        self.scene_.clear()
        self.items = []
        self._cache.clear()
        self.clear_overlays(keep_search=False)
        doc = self.model.doc
        for i in range(doc.page_count):
            r = doc[i].rect
            it = PageItem(self, i, r.width, r.height)
            self.scene_.addItem(it)
            self.items.append(it)
        self.current = min(cur, max(0, doc.page_count - 1))
        self.relayout()
        QTimer.singleShot(0, lambda: self.go_to_page(self.current, keep_offset=True))

    def relayout(self) -> None:
        s = self.scale_px
        n = len(self.items)
        rows: list[list[PageItem]] = []
        if self.layout_mode in ("two", "two_cover"):
            idx = 0
            if self.layout_mode == "two_cover" and n:
                rows.append([self.items[0]])
                idx = 1
            while idx < n:
                rows.append(self.items[idx:idx + 2])
                idx += 2
        else:
            rows = [[it] for it in self.items]
        if self.layout_mode == "single":
            vis_rows = [r for r in rows if self.current in [it.index for it in r]] or rows[:1]
        elif self.layout_mode in ("two", "two_cover") and self.property("single_spread"):
            vis_rows = [r for r in rows if self.current in [it.index for it in r]] or rows[:1]
        else:
            vis_rows = rows
        for it in self.items:
            it.prepareGeometryChange()
            it.setVisible(False)
        maxw = 0.0
        for r in vis_rows:
            maxw = max(maxw, sum(it.w_pt for it in r) * s + GAP * (len(r) - 1))
        y = MARGIN
        for r in vis_rows:
            roww = sum(it.w_pt for it in r) * s + GAP * (len(r) - 1)
            x = (maxw - roww) / 2 + MARGIN
            rowh = max(it.h_pt for it in r) * s
            for it in r:
                it.setPos(x, y + (rowh - it.h_pt * s) / 2)
                it.setVisible(True)
                x += it.w_pt * s + GAP
            y += rowh + GAP
        self.scene_.setSceneRect(QRectF(0, 0, maxw + 2 * MARGIN, y + MARGIN - GAP))
        self._rows = rows
        self.viewport().update()

    def _fit_zoom(self) -> float | None:
        if not self.items:
            return None
        vw = self.viewport().width() - 2 * MARGIN - 4
        vh = self.viewport().height() - 2 * MARGIN
        if self.layout_mode in ("two", "two_cover"):
            ws = [sum(it.w_pt for it in r) + GAP / PX_PER_PT for r in getattr(self, "_rows", [[self.items[0]]])]
            w = max(ws) if ws else self.items[0].w_pt
        else:
            w = max(it.w_pt for it in self.items[:50])
        it = self.items[min(self.current, len(self.items) - 1)]
        if self.fit_mode == "width":
            return max(0.05, vw / (w * PX_PER_PT))
        if self.fit_mode == "page":
            return max(0.05, min(vw / (w * PX_PER_PT), vh / (it.h_pt * PX_PER_PT)))
        return None

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self.fit_mode:
            z = self._fit_zoom()
            if z and abs(z - self.zoom) > 0.002:
                self.set_zoom(z, keep_fit=True)

    def set_zoom(self, z: float, anchor: QPointF | None = None, keep_fit: bool = False) -> None:
        z = max(0.05, min(z, 16.0))
        if not keep_fit:
            self.fit_mode = None
        if anchor is None:
            anchor = QPointF(self.viewport().width() / 2, self.viewport().height() / 3)
        sp = self.mapToScene(anchor.toPoint())
        hit = self.page_at_scene(sp, clamp=True)
        self.cancel_editor()
        self.zoom = z
        self.relayout()
        if hit:
            idx, vpt = hit
            item = self.items[idx]
            new_sp = item.pos() + vpt * self.scale_px
            self._scroll_scene_to(new_sp, anchor)
        self.zoom_changed.emit(self.zoom)

    def set_fit(self, mode: str | None) -> None:
        self.fit_mode = mode
        z = self._fit_zoom()
        if z:
            self.set_zoom(z, keep_fit=True)

    def zoom_in(self) -> None:
        self.set_zoom(self._next_step(self.zoom, +1))

    def zoom_out(self) -> None:
        self.set_zoom(self._next_step(self.zoom, -1))

    @staticmethod
    def _next_step(z: float, d: int) -> float:
        steps = [0.1, 0.25, 0.33, 0.5, 0.67, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 5.0, 6.4, 8.0, 12.0, 16.0]
        if d > 0:
            return next((s for s in steps if s > z + 0.001), steps[-1])
        return next((s for s in reversed(steps) if s < z - 0.001), steps[0])

    def set_layout(self, mode: str) -> None:
        self.layout_mode = mode
        self.relayout()
        if self.fit_mode:
            self.set_fit(self.fit_mode)
        self.go_to_page(self.current)

    def _scroll_scene_to(self, scene_pt: QPointF, viewport_pt: QPointF) -> None:
        hs, vs = self.horizontalScrollBar(), self.verticalScrollBar()
        # con NoAnchor lo scroll corrisponde allo spostamento della scena
        cur = self.mapToScene(viewport_pt.toPoint())
        hs.setValue(int(hs.value() + (scene_pt.x() - cur.x())))
        vs.setValue(int(vs.value() + (scene_pt.y() - cur.y())))

    # ======================================================= navigazione
    def go_to_page(self, index: int, keep_offset: bool = False, y_pt: float | None = None) -> None:
        if not self.items:
            return
        index = max(0, min(index, len(self.items) - 1))
        old = self.current
        self.current = index
        if self.layout_mode == "single":
            self.relayout()
        item = self.items[index]
        y = item.pos().y() - 8
        if y_pt is not None:
            y = item.pos().y() + y_pt * self.scale_px - 40
        self.verticalScrollBar().setValue(int(y))
        if old != index or keep_offset:
            self.page_changed.emit(index)

    def next_page(self) -> None:
        step = 2 if self.layout_mode in ("two", "two_cover") else 1
        self.go_to_page(self.current + step)

    def prev_page(self) -> None:
        step = 2 if self.layout_mode in ("two", "two_cover") else 1
        self.go_to_page(self.current - step)

    def _on_scroll(self, _v) -> None:
        if not self.items or self.layout_mode == "single":
            return
        top = self.mapToScene(0, 0).y()
        h = self.viewport().height()
        probe = top + h * 0.35
        best = self.current
        for it in self.items:
            if not it.isVisible():
                continue
            y0 = it.pos().y()
            y1 = y0 + it.h_pt * self.scale_px
            if y0 - GAP <= probe <= y1:
                best = it.index
                break
        if best != self.current:
            self.current = best
            self.page_changed.emit(best)

    def visible_pages(self) -> list[int]:
        r = self.mapToScene(self.viewport().rect()).boundingRect()
        return [it.index for it in self.items if it.isVisible() and it.sceneBoundingRect().intersects(r)]

    # ========================================================= rendering
    def _paint_page(self, p: QPainter, item: PageItem) -> None:
        s = self.scale_px
        rect = QRectF(0, 0, item.w_pt * s, item.h_pt * s)
        # ombra
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 40 if not theme.is_dark() else 90))
        p.drawRoundedRect(rect.adjusted(1, 2, 3, 4), 2, 2)
        cached = self._cache.get(item.index)
        rev = self.model.page_rev(item.index)
        if cached:
            pm, cs, crev = cached
            p.drawPixmap(rect, pm, QRectF(pm.rect()))
            if abs(cs - s) > 1e-6 or crev != rev:
                self._request(item.index)
        else:
            p.fillRect(rect, QColor("#2a2a2a") if self.night else Qt.white)
            self._request(item.index)
        self._paint_overlays(p, item.index, s)

    def _request(self, index: int) -> None:
        self._pending.add(index)
        if not self._render_timer.isActive():
            self._render_timer.start()

    def _render_pending(self) -> None:
        if not self._pending:
            return
        visible = set(self.visible_pages())
        todo = [i for i in self._pending if i in visible]
        self._pending.clear()
        # una pagina alla volta per non bloccare l'interfaccia
        if todo:
            todo.sort(key=lambda i: abs(i - self.current))
            i = todo[0]
            self._render(i)
            self.items[i].update()
            for j in todo[1:]:
                self._pending.add(j)
            if self._pending:
                self._render_timer.start()
        # tiene in cache solo le pagine vicine
        if len(self._cache) > 16:
            for k in sorted(self._cache, key=lambda k: -abs(k - self.current))[:len(self._cache) - 16]:
                del self._cache[k]

    def _render(self, i: int) -> None:
        if i >= self.model.page_count:
            return
        s = self.scale_px
        dpr = self.devicePixelRatioF()
        page = self.model.page(i)
        z = s * dpr
        r = page.rect
        if r.width * r.height * z * z > MAX_PIXELS:
            z = math.sqrt(MAX_PIXELS / (r.width * r.height))
        try:
            pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), annots=True, alpha=False)
        except Exception:
            return
        if self.night:
            pix.invert_irect(pix.irect)
        img = QImage(pix.samples_mv, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        pm = QPixmap.fromImage(img)
        self._cache[i] = (pm, s, self.model.page_rev(i))

    def refresh(self, pages=None) -> None:
        if pages is None:
            self._cache.clear()
        else:
            for p in pages:
                self._cache.pop(p, None)
        self.viewport().update()

    def _on_model_changed(self, pages) -> None:
        # le pagine possono aver cambiato dimensione (ritaglio, rotazione)
        doc = self.model.doc
        resized = False
        for i, it in enumerate(self.items):
            if pages is not None and i not in pages:
                continue
            r = doc[i].rect
            if abs(r.width - it.w_pt) > 0.01 or abs(r.height - it.h_pt) > 0.01:
                it.prepareGeometryChange()
                it.w_pt, it.h_pt = r.width, r.height
                resized = True
        if resized:
            self.relayout()
        self.clear_overlays(keep_search=True)
        self.viewport().update()

    def set_night(self, on: bool) -> None:
        self.night = on
        self.refresh()

    # ===================================================== sovrapposizioni
    def clear_overlays(self, keep_search: bool = True) -> None:
        if not keep_search:
            self.search_hits = {}
            self.current_hit = None
        self.text_sel = {}
        self.sel_text = ""
        self._sel_quads = []
        self.hover = None
        self.sel_annot = None
        self.sel_image = None
        self.sel_block = None
        self.temp = None
        self.viewport().update()

    def _paint_overlays(self, p: QPainter, idx: int, s: float) -> None:
        p.save()
        p.scale(s, s)
        acc = QColor(theme.current["accent"])
        # campi modulo
        if self.highlight_fields and self.model.doc.is_form_pdf and self.tools.tool in ("select", "hand"):
            page = self.model.page(idx)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(80, 140, 255, 40))
            for w in page.widgets():
                p.drawRect(self._vrect(page, w.rect))
        # risultati di ricerca
        hits = self.search_hits.get(idx)
        if hits:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 196, 0, 90))
            for r in hits:
                p.drawRect(r)
        if self.current_hit and self.current_hit[0] == idx:
            p.setBrush(QColor(255, 120, 0, 130))
            p.setPen(QPen(QColor(230, 90, 0), 0))
            p.drawRect(self.current_hit[1])
        # selezione di testo
        sel = self.text_sel.get(idx)
        if sel:
            p.setPen(Qt.NoPen)
            c = QColor(acc)
            c.setAlpha(80)
            p.setBrush(c)
            for r in sel:
                p.drawRect(r)
        # elemento sotto il puntatore
        if self.hover and self.hover[0] == idx:
            pen = QPen(acc, 0, Qt.DashLine)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(QColor(acc.red(), acc.green(), acc.blue(), 18))
            p.drawRect(self.hover[1])
        # annotazione / immagine / blocco selezionati
        for selected in (self._sel_rect_view(idx),):
            if selected is not None:
                self._draw_selection(p, selected, s)
        # forma temporanea
        t = self.temp
        if t and t.get("page") == idx:
            self._draw_temp(p, t, s)
        p.restore()

    def _draw_selection(self, p: QPainter, r: QRectF, s: float) -> None:
        acc = QColor(theme.current["accent"])
        pen = QPen(acc, 1.5)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(r)
        hs = HANDLE / s
        p.setBrush(Qt.white)
        for c in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
            p.drawRect(QRectF(c.x() - hs, c.y() - hs, 2 * hs, 2 * hs))

    def _sel_rect_view(self, idx: int) -> QRectF | None:
        page = None
        if self.sel_annot and self.sel_annot[0] == idx:
            page = self.model.page(idx)
            a = A.annot_by_xref(page, self.sel_annot[1])
            if a is None:
                return None
            r = self._vrect(page, a.rect)
        elif self.sel_image and self.sel_image[0] == idx:
            page = self.model.page(idx)
            r = self._vrect(page, self.sel_image[1].rect)
        elif self.sel_block and self.sel_block[0] == idx:
            page = self.model.page(idx)
            r = self._vrect(page, self.sel_block[1].rect)
        else:
            return None
        t = self.temp
        if t and t.get("kind") in ("move", "resize") and t.get("page") == idx:
            return t["rect"]
        return r

    def _draw_temp(self, p: QPainter, t: dict, s: float) -> None:
        kind = t["kind"]
        color = QColor(self.tools.color_for(t.get("tool")))
        pen = QPen(color, max(self.tools.width, 1.0))
        if kind in ("band",):
            pen = QPen(QColor(theme.current["accent"]), 1, Qt.DashLine)
            pen.setCosmetic(True)
            p.setPen(pen)
            p.setBrush(QColor(110, 70, 220, 25))
            p.drawRect(QRectF(t["p0"], t["p1"]).normalized())
            return
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        tool = t.get("tool")
        if kind == "drag":
            r = QRectF(t["p0"], t["p1"]).normalized()
            if tool == "ellipse":
                p.drawEllipse(r)
            elif tool in LINE_TOOLS:
                p.drawLine(t["p0"], t["p1"])
                if tool == "measure":
                    self._draw_measure_label(p, t, s)
            else:
                dash = QPen(color if tool in ("rect",) else QColor(theme.current["accent"]), 1,
                            Qt.SolidLine if tool == "rect" else Qt.DashLine)
                dash.setCosmetic(tool != "rect")
                if tool == "rect":
                    dash.setWidthF(max(self.tools.width, 1.0))
                p.setPen(dash)
                if tool == "redact":
                    p.setBrush(QColor(0, 0, 0, 90))
                p.drawRect(r)
        elif kind == "ink":
            path = QPainterPath()
            for stroke in t["strokes"]:
                if not stroke:
                    continue
                path.moveTo(stroke[0])
                for q in stroke[1:]:
                    path.lineTo(q)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.drawPath(path)
        elif kind == "vertices":
            pts = t["pts"] + ([t["cursor"]] if t.get("cursor") else [])
            if len(pts) > 1:
                if tool in ("polygon", "area"):
                    p.drawPolygon(QPolygonF(pts))
                else:
                    p.drawPolyline(QPolygonF(pts))
            for q in t["pts"]:
                p.drawEllipse(q, 2 / s * 2, 2 / s * 2)

    def _draw_measure_label(self, p: QPainter, t: dict, s: float) -> None:
        d = math.hypot(t["p1"].x() - t["p0"].x(), t["p1"].y() - t["p0"].y())
        mm = d * 25.4 / 72 * self.tools.measure_scale
        label = A._format_measure(mm, self.tools.measure_unit)
        f = p.font()
        f.setPointSizeF(9 / s * 1.0)
        p.setFont(f)
        p.drawText(t["p1"] + QPointF(4 / s, -4 / s), label)

    # ======================================================== coordinate
    def page_at_scene(self, sp: QPointF, clamp: bool = False) -> tuple[int, QPointF] | None:
        s = self.scale_px
        best = None
        bestd = 1e18
        for it in self.items:
            if not it.isVisible():
                continue
            r = QRectF(it.pos(), it.pos() + QPointF(it.w_pt * s, it.h_pt * s))
            if r.contains(sp):
                return it.index, (sp - it.pos()) / s
            if clamp:
                d = abs(sp.y() - r.center().y())
                if d < bestd:
                    bestd, best = d, it
        if clamp and best is not None:
            v = (sp - best.pos()) / s
            return best.index, QPointF(min(max(v.x(), 0), best.w_pt), min(max(v.y(), 0), best.h_pt))
        return None

    def hit(self, pos) -> tuple[int, QPointF] | None:
        return self.page_at_scene(self.mapToScene(pos.toPoint() if hasattr(pos, "toPoint") else pos))

    def _vrect(self, page: pymupdf.Page, r: pymupdf.Rect) -> QRectF:
        d = pymupdf.Rect(r) * page.rotation_matrix
        d.normalize()
        return QRectF(d.x0, d.y0, d.width, d.height)

    @staticmethod
    def _pdf_pt(page: pymupdf.Page, v: QPointF) -> pymupdf.Point:
        return pymupdf.Point(v.x(), v.y()) * page.derotation_matrix

    def _pdf_rect(self, page: pymupdf.Page, r: QRectF) -> pymupdf.Rect:
        rr = pymupdf.Rect(r.left(), r.top(), r.right(), r.bottom()) * page.derotation_matrix
        rr.normalize()
        return rr

    def view_rect_to_viewport(self, idx: int, r: QRectF) -> QRectF:
        it = self.items[idx]
        s = self.scale_px
        tl = self.mapFromScene(it.pos() + r.topLeft() * s)
        br = self.mapFromScene(it.pos() + r.bottomRight() * s)
        return QRectF(tl, br)

    def ensure_visible(self, idx: int, r: QRectF) -> None:
        if self.layout_mode == "single" and idx != self.current:
            self.go_to_page(idx)
        it = self.items[idx]
        s = self.scale_px
        sr = QRectF(it.pos() + r.topLeft() * s, r.size() * s)
        self.ensureVisible(sr, 60, 80)

    # ========================================================= strumenti
    def _on_tool_changed(self, tool: str) -> None:
        self.commit_editor()
        self.temp = None
        self.hover = None
        self.sel_block = None
        self.sel_image = None
        if tool not in ("select", "hand"):
            self.sel_annot = None
            self.annot_selected.emit(None)
        self.setCursor(CURSORS.get(tool, Qt.CrossCursor))
        self.viewport().update()

    def _tool_done(self) -> None:
        if not self.tools.keep_tool:
            self.request_tool.emit("select")

    # --------------------------------------------------------- eventi
    def event(self, e) -> bool:
        # mentre si scrive in un editor sulla pagina, i tasti vanno all'editor e non alle
        # scorciatoie della finestra (lettere degli strumenti, frecce, Home/Fine...)
        if e.type() == e.Type.ShortcutOverride and self.editor is not None:
            e.accept()
            return True
        return super().event(e)

    def wheelEvent(self, e) -> None:
        if e.modifiers() & Qt.ControlModifier:
            d = e.angleDelta().y() / 120
            self.set_zoom(self.zoom * (1.12 ** d), anchor=e.position())
            e.accept()
            return
        if self.layout_mode == "single":
            vs = self.verticalScrollBar()
            dy = e.angleDelta().y()
            if dy < 0 and vs.value() >= vs.maximum():
                self.next_page()
                self.verticalScrollBar().setValue(0)
                return
            if dy > 0 and vs.value() <= vs.minimum() and self.current > 0:
                self.prev_page()
                self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
                return
        super().wheelEvent(e)

    def mousePressEvent(self, e) -> None:
        self.setFocus()
        pos = e.position()
        if e.button() == Qt.MiddleButton or (e.button() == Qt.LeftButton and self.tools.tool == "hand"):
            self._pan = (pos, self.horizontalScrollBar().value(), self.verticalScrollBar().value(), False)
            self.setCursor(Qt.ClosedHandCursor)
            return
        if e.button() == Qt.RightButton:
            return
        if e.button() != Qt.LeftButton:
            return
        if self.editor is not None:
            # clic fuori dall'editor in linea: conferma
            if not self.editor.contains_viewport_point(pos):
                self.commit_editor()
            else:
                super().mousePressEvent(e)
                return
        h = self.hit(pos)
        tool = self.tools.tool
        if h is None:
            self.clear_selection()
            return
        idx, v = h
        page = self.model.page(idx)
        pt = self._pdf_pt(page, v)
        self._press = {"idx": idx, "v": v, "pt": pt, "pos": pos, "moved": False}

        if tool == "select":
            self._press_select(idx, page, v, pt, e)
        elif tool in MARKUP_TOOLS:
            self._start_text_selection(idx, v)
            self._press["area_fallback"] = True
        elif tool == "edit_text":
            self._press_edit_text(idx, page, v, pt)
        elif tool == "edit_object":
            self._press_edit_object(idx, page, v, pt)
        elif tool in RECT_TOOLS or tool in LINE_TOOLS:
            self.temp = {"kind": "drag", "tool": tool, "page": idx, "p0": v, "p1": v}
        elif tool == "ink":
            if self.temp and self.temp.get("kind") == "ink" and self.temp["page"] == idx:
                self.temp["strokes"].append([v])
            else:
                self._commit_ink()
                self.temp = {"kind": "ink", "tool": "ink", "page": idx, "strokes": [[v]]}
        elif tool in VERTEX_TOOLS:
            t = self.temp
            if t and t.get("kind") == "vertices" and t["page"] == idx:
                t["pts"].append(v)
            else:
                self.temp = {"kind": "vertices", "tool": tool, "page": idx, "pts": [v], "cursor": v}
        elif tool == "note":
            self._add_note(idx, page, pt)
        elif tool == "eraser":
            self._erase_at(idx, page, pt)
        elif tool == "attach":
            self._add_attachment(idx, page, pt)
        self.viewport().update()

    def mouseMoveEvent(self, e) -> None:
        pos = e.position()
        if self._pan is not None:
            p0, hx, vy, _ = self._pan
            d = pos - p0
            self.horizontalScrollBar().setValue(int(hx - d.x()))
            self.verticalScrollBar().setValue(int(vy - d.y()))
            if abs(d.x()) + abs(d.y()) > 3:
                self._pan = (p0, hx, vy, True)
            return
        if self.editor is not None and self._press is None:
            super().mouseMoveEvent(e)
            return
        h = self.hit(pos)
        tool = self.tools.tool
        pr = self._press
        if pr and e.buttons() & Qt.LeftButton:
            if (pos - pr["pos"]).manhattanLength() > 3:
                pr["moved"] = True
            idx = pr["idx"]
            v = self._clamp_to_page(idx, self.mapToScene(pos.toPoint()))
            t = self.temp
            if t and t["kind"] == "drag":
                t["p1"] = v
                if e.modifiers() & Qt.ShiftModifier and t["tool"] in LINE_TOOLS:
                    t["p1"] = self._snap45(t["p0"], v)
            elif t and t["kind"] == "band":
                t["p1"] = v
            elif t and t["kind"] == "ink":
                t["strokes"][-1].append(v)
            elif t and t["kind"] in ("move", "resize"):
                self._update_move(t, v)
            elif pr.get("textsel"):
                self._update_text_selection(idx, v)
            self.viewport().update()
            return
        # passaggio del mouse
        if self.temp and self.temp.get("kind") == "vertices" and h and h[0] == self.temp["page"]:
            self.temp["cursor"] = h[1]
            self.viewport().update()
        self._hover(h, tool)

    def mouseReleaseEvent(self, e) -> None:
        if self._pan is not None:
            p0, _, _, moved = self._pan
            self._pan = None
            self.setCursor(CURSORS.get(self.tools.tool, Qt.CrossCursor))
            if not moved and self.tools.tool == "hand" and e.button() == Qt.LeftButton:
                h = self.hit(e.position())
                if h:
                    page = self.model.page(h[0])
                    pt = self._pdf_pt(page, h[1])
                    if not self._follow_link(page, pt):
                        self._click_widget(h[0], page, pt)
            return
        if e.button() != Qt.LeftButton:
            return
        pr = self._press
        self._press = None
        if pr is None:
            super().mouseReleaseEvent(e)
            return
        tool = self.tools.tool
        t = self.temp
        try:
            if t and t["kind"] == "drag":
                self.temp = None
                self._finish_drag(t, pr)
            elif t and t["kind"] == "band":
                self.temp = None
                if tool in MARKUP_TOOLS:
                    self._finish_markup(pr, band=t)
            elif t and t["kind"] in ("move", "resize"):
                self.temp = None
                self._finish_move(t, pr)
            elif pr.get("textsel"):
                if tool in MARKUP_TOOLS:
                    self._finish_markup(pr)
                elif not pr["moved"] and pr.get("link"):
                    self._follow_link(self.model.page(pr["idx"]), pr["pt"])
            elif tool == "select" and not pr["moved"] and pr.get("link"):
                self._follow_link(self.model.page(pr["idx"]), pr["pt"])
        except Exception as ex:
            self._error(ex)
        self.viewport().update()

    def mouseDoubleClickEvent(self, e) -> None:
        h = self.hit(e.position())
        tool = self.tools.tool
        t = self.temp
        if t and t.get("kind") == "vertices":
            # il doppio clic aggiunge un vertice in più: lo togliamo e chiudiamo
            if len(t["pts"]) > 1 and (t["pts"][-1] - t["pts"][-2]).manhattanLength() < 2:
                t["pts"].pop()
            self._finish_vertices()
            return
        if t and t.get("kind") == "ink":
            self._commit_ink()
            return
        if h and tool == "select":
            idx, v = h
            page = self.model.page(idx)
            pt = self._pdf_pt(page, v)
            a = A.annot_at(page, pt)
            if a is not None:
                self.request_annot_props.emit(idx, a.xref)
                return
            self._select_word(idx, v)
            return
        if h and tool == "edit_text" and self.editor is None:
            return
        super().mouseDoubleClickEvent(e)

    def keyPressEvent(self, e) -> None:
        if self.editor is not None:
            super().keyPressEvent(e)
            return
        k = e.key()
        if k == Qt.Key_Escape:
            if self.temp and self.temp.get("kind") == "ink":
                self._commit_ink()
            elif self.temp and self.temp.get("kind") == "vertices":
                self._finish_vertices()
            else:
                self.clear_selection()
                if self.tools.tool != "select":
                    self.request_tool.emit("select")
            return
        if k in (Qt.Key_Return, Qt.Key_Enter) and self.temp and self.temp.get("kind") in ("vertices", "ink"):
            if self.temp["kind"] == "ink":
                self._commit_ink()
            else:
                self._finish_vertices()
            return
        if k in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
            return
        if e.matches(QKeySequence.Copy):
            self.copy_selection()
            return
        if e.matches(QKeySequence.SelectAll):
            self.select_all_text(self.current)
            return
        if k == Qt.Key_PageDown or (k == Qt.Key_Right and self.fit_mode == "page") or (k == Qt.Key_Space and not e.modifiers()):
            if self.layout_mode == "single" or self.fit_mode == "page":
                self.next_page()
                return
        if k == Qt.Key_PageUp or (k == Qt.Key_Left and self.fit_mode == "page"):
            if self.layout_mode == "single" or self.fit_mode == "page":
                self.prev_page()
                return
        if k == Qt.Key_Home and e.modifiers() & Qt.ControlModifier:
            self.go_to_page(0)
            return
        if k == Qt.Key_End and e.modifiers() & Qt.ControlModifier:
            self.go_to_page(len(self.items) - 1)
            return
        if self.sel_annot and k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            step = 10 if e.modifiers() & Qt.ShiftModifier else 1
            dx = {Qt.Key_Left: -step, Qt.Key_Right: step}.get(k, 0)
            dy = {Qt.Key_Up: -step, Qt.Key_Down: step}.get(k, 0)
            self._nudge_annot(dx, dy)
            return
        super().keyPressEvent(e)

    def contextMenuEvent(self, e) -> None:
        if self.editor is not None:
            super().contextMenuEvent(e)
            return
        h = self.hit(QPointF(e.pos()))
        menu = QMenu(self)
        if h:
            idx, v = h
            page = self.model.page(idx)
            pt = self._pdf_pt(page, v)
            a = A.annot_at(page, pt)
            if a is not None:
                xref = a.xref
                a_content = A.annot_props(a)["content"]
                self.sel_annot = (idx, xref)
                self.annot_selected.emit((idx, xref))
                self.viewport().update()
                menu.addAction(T('Proprietà…'), lambda: self.request_annot_props.emit(idx, xref))
                menu.addAction(T('Elimina annotazione'), self.delete_selected)
                menu.addAction(T('Copia testo del commento'),
                               lambda: QApplication.clipboard().setText(a_content))
                menu.addSeparator()
            if self.sel_text:
                menu.addAction(T('Copia'), self.copy_selection)
                for name, label in (("highlight", T('Evidenzia')), ("underline", T('Sottolinea')),
                                    ("strike", T('Barra')), ("squiggly", T('Sottolineatura ondulata'))):
                    menu.addAction(label, lambda n=name: self.markup_selection(n))
                menu.addAction(T('Contrassegna per redazione'), self.redact_selection)
                menu.addAction(T('Crea collegamento…'), self.link_from_selection)
                menu.addSeparator()
            im = IM.image_at(page, pt) if self.tools.tool == "edit_object" else None
            if im is not None:
                self.sel_image = (idx, im)
                self.viewport().update()
                menu.addAction(T('Sostituisci immagine…'), self.replace_selected_image)
                menu.addAction(T('Salva immagine come…'), self.save_selected_image)
                menu.addAction(T('Ruota a destra'), lambda: self.rotate_selected_image(-90))
                menu.addAction(T('Ruota a sinistra'), lambda: self.rotate_selected_image(90))
                menu.addAction(T('Elimina immagine'), self.delete_selected)
                menu.addSeparator()
            menu.addAction(T('Incolla'), lambda: self.paste_at(idx, pt))
            menu.addAction(T('Aggiungi nota qui'), lambda: self._add_note(idx, page, pt))
            menu.addAction(T('Seleziona tutto il testo della pagina'), lambda: self.select_all_text(idx))
            menu.addSeparator()
            menu.addAction(T('Ruota pagina a destra'), lambda: self.window().run_action("rotate_right_current", idx))
            menu.addAction(T('Ruota pagina a sinistra'), lambda: self.window().run_action("rotate_left_current", idx))
            menu.addAction(T('Elimina pagina'), lambda: self.window().run_action("delete_current", idx))
            menu.addAction(T('Aggiungi segnalibro per questa pagina'),
                           lambda: self.window().run_action("bookmark_here", idx))
        menu.exec(e.globalPos())

    # -------------------------------------------------------- passaggio
    def _hover(self, h, tool: str) -> None:
        old = self.hover
        self.hover = None
        cursor = CURSORS.get(tool, Qt.CrossCursor)
        if h is not None:
            idx, v = h
            page = self.model.page(idx)
            pt = self._pdf_pt(page, v)
            if tool == "edit_text":
                b = TE.block_at(self._blocks(idx), pt)
                if b is not None:
                    self.hover = (idx, self._vrect(page, b.rect))
            elif tool == "edit_object":
                handle = self._handle_at(idx, v)
                if handle:
                    cursor = Qt.SizeFDiagCursor if handle in ("tl", "br") else Qt.SizeBDiagCursor
                else:
                    im = IM.image_at(page, pt)
                    if im is not None:
                        self.hover = (idx, self._vrect(page, im.rect))
                        cursor = Qt.SizeAllCursor
                    else:
                        b = TE.block_at(self._blocks(idx), pt)
                        if b is not None:
                            self.hover = (idx, self._vrect(page, b.rect))
                            cursor = Qt.SizeAllCursor
            elif tool in ("select", "hand"):
                if self._link_at(page, pt):
                    cursor = Qt.PointingHandCursor
                elif tool == "select":
                    w = F.widget_at(page, pt) if self.model.doc.is_form_pdf else None
                    if w is not None:
                        cursor = Qt.PointingHandCursor if w.field_type != pymupdf.PDF_WIDGET_TYPE_TEXT else Qt.IBeamCursor
                    elif self._handle_at(idx, v):
                        cursor = Qt.SizeFDiagCursor
                    elif A.annot_at(page, pt) is not None:
                        cursor = Qt.SizeAllCursor
                    elif self._word_near(idx, v, 1.5) is not None:
                        cursor = Qt.IBeamCursor
            elif tool == "eraser":
                a = A.annot_at(page, pt)
                if a is not None:
                    self.hover = (idx, self._vrect(page, a.rect))
        self.viewport().setCursor(cursor)
        if old != self.hover:
            self.viewport().update()

    # ------------------------------------------------- selezione/annot
    def _press_select(self, idx, page, v, pt, e) -> None:
        handle = self._handle_at(idx, v)
        if handle and self.sel_annot and self.sel_annot[0] == idx:
            a = A.annot_by_xref(page, self.sel_annot[1])
            if a is not None:
                self.temp = {"kind": "resize", "page": idx, "handle": handle, "orig": self._vrect(page, a.rect),
                             "rect": self._vrect(page, a.rect), "start": v, "target": "annot"}
                return
        if self.model.doc.is_form_pdf:
            w = F.widget_at(page, pt)
            if w is not None:
                self._click_widget(idx, page, pt)
                self._press = None
                return
        a = A.annot_at(page, pt)
        if a is not None:
            self.clear_text_selection()
            self.sel_annot = (idx, a.xref)
            self.annot_selected.emit((idx, a.xref))
            locked = bool(a.flags & pymupdf.PDF_ANNOT_IS_LOCKED)
            if A.can_move(a) and not locked:
                r = self._vrect(page, a.rect)
                self.temp = {"kind": "move", "page": idx, "orig": r, "rect": r, "start": v, "target": "annot"}
            return
        if self.sel_annot:
            self.sel_annot = None
            self.annot_selected.emit(None)
        link = self._link_at(page, pt)
        self._start_text_selection(idx, v)
        self._press["link"] = link

    def _start_text_selection(self, idx: int, v: QPointF) -> None:
        self.text_sel = {}
        self.sel_text = ""
        self._sel_quads = []
        self._press["textsel"] = True
        self._press["anchor"] = self._word_near(idx, v, 25)
        self._press["anchor_v"] = v
        self.selection_changed.emit()

    def _sorted_words(self, idx: int):
        key = ("sorted", idx, self.model.page_rev(idx))
        cache = getattr(self, "_wcache", None)
        if cache is None or cache[0] != key:
            ws = sorted(self.model.words(idx), key=lambda w: (w[5], w[6], w[7]))
            page = self.model.page(idx)
            disp = [self._vrect(page, pymupdf.Rect(w[:4])) for w in ws]
            self._wcache = (key, ws, disp)
        return self._wcache[1], self._wcache[2]

    def _word_near(self, idx: int, v: QPointF, maxd: float) -> int | None:
        ws, disp = self._sorted_words(idx)
        best, bd = None, maxd
        for i, r in enumerate(disp):
            if r.contains(v):
                return i
            dx = max(r.left() - v.x(), 0, v.x() - r.right())
            dy = max(r.top() - v.y(), 0, v.y() - r.bottom())
            d = math.hypot(dx, dy * 2)
            if d < bd:
                bd, best = d, i
        return best

    def _update_text_selection(self, idx: int, v: QPointF) -> None:
        pr = self._press
        a = pr.get("anchor")
        if a is None:
            if pr.get("area_fallback"):
                self.temp = {"kind": "band", "tool": "rect_area", "page": idx, "p0": pr["anchor_v"], "p1": v}
            return
        b = self._word_near(idx, v, 400)
        if b is None:
            return
        self._set_word_selection(idx, min(a, b), max(a, b))

    def _set_word_selection(self, idx: int, i0: int, i1: int) -> None:
        ws, disp = self._sorted_words(idx)
        page = self.model.page(idx)
        lines: dict = {}
        order = []
        for i in range(i0, i1 + 1):
            w = ws[i]
            key = (w[5], w[6])
            if key not in lines:
                lines[key] = [pymupdf.Rect(w[:4]), [w[4]]]
                order.append(key)
            else:
                lines[key][0] |= pymupdf.Rect(w[:4])
                lines[key][1].append(w[4])
        self._sel_quads = [(idx, [lines[k][0] for k in order])]
        self.text_sel = {idx: [self._vrect(page, lines[k][0]) for k in order]}
        self.sel_text = "\n".join(" ".join(lines[k][1]) for k in order)
        self.selection_changed.emit()

    def _select_word(self, idx: int, v: QPointF) -> None:
        i = self._word_near(idx, v, 3)
        if i is not None:
            self._set_word_selection(idx, i, i)
            self.viewport().update()

    def select_all_text(self, idx: int) -> None:
        ws, _ = self._sorted_words(idx)
        if ws:
            self._set_word_selection(idx, 0, len(ws) - 1)
            self.viewport().update()

    def clear_text_selection(self) -> None:
        self.text_sel = {}
        self.sel_text = ""
        self._sel_quads = []
        self.selection_changed.emit()

    def clear_selection(self) -> None:
        self.clear_text_selection()
        if self.sel_annot:
            self.annot_selected.emit(None)
        self.sel_annot = None
        self.sel_image = None
        self.sel_block = None
        self.viewport().update()

    def copy_selection(self) -> None:
        if self.sel_text:
            QApplication.clipboard().setText(self.sel_text)
            self.status.emit(T('Testo copiato negli appunti'))
        elif self.sel_image:
            idx, im = self.sel_image
            data, _ = IM.image_bytes(self.model.doc, im.xref)
            img = QImage.fromData(data)
            QApplication.clipboard().setImage(img)
            self.status.emit(T('Immagine copiata negli appunti'))

    def markup_selection(self, kind: str) -> None:
        if not self._sel_quads:
            return
        idx, rects = self._sel_quads[0]
        st = self._style(kind)
        with self.model.edit(T('Annotazione'), [idx]):
            A.add_markup(self.model.page(idx), kind, [r.quad for r in rects], st)
        self.clear_text_selection()

    def redact_selection(self) -> None:
        if not self._sel_quads:
            return
        from .ops import security as SEC
        idx, rects = self._sel_quads[0]
        with self.model.edit(T('Contrassegna redazione'), [idx]):
            for r in rects:
                SEC.mark_area(self.model.page(idx), r)
        self.clear_text_selection()
        self.status.emit(T('Area contrassegnata: usa «Applica redazioni» per eliminare il contenuto'))

    def link_from_selection(self) -> None:
        if not self._sel_quads:
            return
        idx, rects = self._sel_quads[0]
        r = pymupdf.Rect()
        for x in rects:
            r |= x
        self.window().create_link(idx, r)

    def _finish_markup(self, pr, band: dict | None = None) -> None:
        tool = self.tools.tool
        if self._sel_quads:
            self.markup_selection(tool)
        elif band is not None:
            # nessun testo: evidenziazione di un'area (utile sulle scansioni)
            idx = pr["idx"]
            page = self.model.page(idx)
            r = self._pdf_rect(page, QRectF(band["p0"], band["p1"]).normalized())
            if r.width > 2 and r.height > 2:
                with self.model.edit(T('Annotazione'), [idx]):
                    A.add_markup(page, tool, [r.quad], self._style(tool))
        self._tool_done()

    # ----------------------------------------------- spostamento/resize
    def _handle_at(self, idx: int, v: QPointF) -> str | None:
        r = self._sel_rect_view(idx)
        if r is None:
            return None
        tol = (HANDLE + 2) / self.scale_px
        for name, c in (("tl", r.topLeft()), ("tr", r.topRight()), ("bl", r.bottomLeft()), ("br", r.bottomRight())):
            if abs(v.x() - c.x()) <= tol and abs(v.y() - c.y()) <= tol:
                return name
        return None

    def _update_move(self, t: dict, v: QPointF) -> None:
        d = v - t["start"]
        o = QRectF(t["orig"])
        if t["kind"] == "move":
            t["rect"] = o.translated(d)
        else:
            h = t["handle"]
            r = QRectF(o)
            if "l" in h:
                r.setLeft(o.left() + d.x())
            if "r" in h:
                r.setRight(o.right() + d.x())
            if "t" in h:
                r.setTop(o.top() + d.y())
            if "b" in h:
                r.setBottom(o.bottom() + d.y())
            if QApplication.keyboardModifiers() & Qt.ShiftModifier and o.width() and o.height():
                k = r.width() / o.width()
                r.setHeight(o.height() * k)
            t["rect"] = r.normalized()

    def _finish_move(self, t: dict, pr) -> None:
        if not pr["moved"]:
            return
        idx = t["page"]
        page = self.model.page(idx)
        new = self._pdf_rect(page, t["rect"])
        if t["target"] == "annot" and self.sel_annot:
            xref = self.sel_annot[1]
            with self.model.edit(T('Sposta annotazione'), [idx]):
                page = self.model.page(idx)
                a = A.annot_by_xref(page, xref)
                if a is None:
                    return
                if t["kind"] == "move":
                    old = self._pdf_rect(page, t["orig"])
                    nx = A.move_annot(page, a, new.x0 - old.x0, new.y0 - old.y0)
                else:
                    nx = A.resize_annot(page, a, new)
            self.sel_annot = (idx, nx)
            self.annot_selected.emit((idx, nx))
        elif t["target"] == "image" and self.sel_image:
            im = self.sel_image[1]
            with self.model.edit(T('Sposta immagine'), [idx]):
                IM.move_image(self.model.page(idx), im, new)
            self.sel_image = None
            self._reselect_image(idx, new)
        elif t["target"] == "block" and self.sel_block:
            b = self.sel_block[1]
            dx, dy = new.x0 - b.rect.x0, new.y0 - b.rect.y0
            with self.model.edit(T('Sposta testo'), [idx]):
                page = self.model.page(idx)
                TE.delete_block(page, b)
                r = pymupdf.Rect(b.rect.x0 + dx - 1, b.rect.y0 + dy - 1, b.rect.x1 + dx + max(2, b.rect.width * 0.02),
                                 b.rect.y1 + dy)
                _, warn = TE.insert_paras(page, r, b.paras, b.embedded, rotate=TE.dir_to_rotate(b.dir))
                self.model.fonts_inserted = True
            self.sel_block = None
            if warn:
                self.status.emit("; ".join(warn))

    def _reselect_image(self, idx: int, rect: pymupdf.Rect) -> None:
        page = self.model.page(idx)
        best = None
        for im in IM.page_images(page):
            if im.rect.intersects(rect) and (best is None or abs(im.rect.x0 - rect.x0) + abs(im.rect.y0 - rect.y0)
                                             < abs(best.rect.x0 - rect.x0) + abs(best.rect.y0 - rect.y0)):
                best = im
        self.sel_image = (idx, best) if best else None

    def _nudge_annot(self, dx: float, dy: float) -> None:
        idx, xref = self.sel_annot
        page = self.model.page(idx)
        a = A.annot_by_xref(page, xref)
        if a is None or not A.can_move(a):
            return
        p0 = self._pdf_pt(page, QPointF(0, 0))
        p1 = self._pdf_pt(page, QPointF(dx, dy))
        with self.model.edit(T('Sposta annotazione'), [idx]):
            page = self.model.page(idx)
            a = A.annot_by_xref(page, xref)
            nx = A.move_annot(page, a, p1.x - p0.x, p1.y - p0.y)
        self.sel_annot = (idx, nx)

    def delete_selected(self) -> None:
        try:
            if self.sel_annot:
                idx, xref = self.sel_annot
                with self.model.edit(T('Elimina annotazione'), [idx]):
                    page = self.model.page(idx)
                    a = A.annot_by_xref(page, xref)
                    if a is not None:
                        page.delete_annot(a)
                self.sel_annot = None
                self.annot_selected.emit(None)
            elif self.sel_image:
                idx, im = self.sel_image
                with self.model.edit(T('Elimina immagine'), [idx]):
                    IM.remove_image(self.model.page(idx), im)
                self.sel_image = None
            elif self.sel_block:
                idx, b = self.sel_block
                with self.model.edit(T('Elimina testo'), [idx]):
                    TE.delete_block(self.model.page(idx), b)
                self.sel_block = None
        except Exception as ex:
            self._error(ex)
        self.viewport().update()

    # ---------------------------------------------------- oggetti (immagini)
    def _press_edit_object(self, idx, page, v, pt) -> None:
        handle = self._handle_at(idx, v)
        cur = self._sel_rect_view(idx)
        if handle and cur is not None and (self.sel_image or self.sel_block):
            target = "image" if self.sel_image else "block"
            if target == "block":
                handle = None  # i blocchi di testo si spostano soltanto
            else:
                self.temp = {"kind": "resize", "page": idx, "handle": handle, "orig": cur, "rect": cur,
                             "start": v, "target": target}
                return
        im = IM.image_at(page, pt)
        if im is not None:
            self.sel_block = None
            self.sel_image = (idx, im)
            r = self._vrect(page, im.rect)
            self.temp = {"kind": "move", "page": idx, "orig": r, "rect": r, "start": v, "target": "image"}
            self.status.emit(T('Immagine {}×{} px · trascina per spostare, maniglie per ridimensionare, Canc per eliminare, tasto destro per altre opzioni').format(im.width, im.height))
            return
        b = TE.block_at(self._blocks(idx), pt)
        if b is not None:
            self.sel_image = None
            self.sel_block = (idx, b)
            r = self._vrect(page, b.rect)
            self.temp = {"kind": "move", "page": idx, "orig": r, "rect": r, "start": v, "target": "block"}
            self.status.emit(T('Blocco di testo · trascina per spostare, Canc per eliminare'))
            return
        self.sel_image = None
        self.sel_block = None

    def replace_selected_image(self) -> None:
        if not self.sel_image:
            return
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, T('Sostituisci immagine'), "",
                                              T('Immagini (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp)'))
        if not path:
            return
        idx, im = self.sel_image
        with self.model.edit(T('Sostituisci immagine'), [idx]):
            IM.replace_image(self.model.page(idx), im, path)
        self.sel_image = None

    def save_selected_image(self) -> None:
        if not self.sel_image:
            return
        from PySide6.QtWidgets import QFileDialog
        idx, im = self.sel_image
        data, ext = IM.image_bytes(self.model.doc, im.xref)
        path, _ = QFileDialog.getSaveFileName(self, T('Salva immagine'), T('immagine.{}').format(ext), T('Immagine (*.{})').format(ext))
        if path:
            with open(path, "wb") as f:
                f.write(data)

    def rotate_selected_image(self, angle: int) -> None:
        if not self.sel_image:
            return
        idx, im = self.sel_image
        with self.model.edit(T('Ruota immagine'), [idx]):
            IM.rotate_image(self.model.page(idx), im, angle)
        self.sel_image = None

    def paste_at(self, idx: int, pt: pymupdf.Point) -> None:
        cb = QApplication.clipboard()
        md = cb.mimeData()
        page = self.model.page(idx)
        if md.hasImage():
            img = cb.image()
            if img.isNull():
                return
            from PySide6.QtCore import QBuffer, QByteArray, QIODevice
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.WriteOnly)
            img.save(buf, "PNG")
            w = img.width() * 0.75
            h = img.height() * 0.75
            k = min(1.0, page.rect.width * 0.8 / max(w, 1), page.rect.height * 0.8 / max(h, 1))
            r = pymupdf.Rect(pt.x, pt.y, pt.x + w * k, pt.y + h * k)
            with self.model.edit(T('Incolla immagine'), [idx]):
                IM.insert_image(self.model.page(idx), r, data=bytes(ba))
        elif md.hasText() and md.text().strip():
            paras = [TE.Para([TE.Run(line, self.tools.text_family, self.tools.text_size,
                                     color=self.tools.color_for("text"))]) for line in md.text().splitlines()]
            r = pymupdf.Rect(pt.x, pt.y, min(pt.x + 400, page.mediabox.x1), pt.y + 40)
            with self.model.edit(T('Incolla testo'), [idx]):
                TE.insert_paras(self.model.page(idx), r, paras)
                self.model.fonts_inserted = True

    # ---------------------------------------------------- modifica testo
    def _blocks(self, idx: int) -> list[TE.TextBlock]:
        key = ("blocks", idx, self.model.page_rev(idx))
        c = getattr(self, "_bcache", None)
        if c is None or c[0] != key:
            page = self.model.page(idx)
            self._bcache = (key, TE.read_blocks(page, self.model.text_dict(idx)))
        return self._bcache[1]

    def _press_edit_text(self, idx, page, v, pt) -> None:
        from .editors import RichTextEditor
        b = TE.block_at(self._blocks(idx), pt)
        if b is not None:
            self.editor = RichTextEditor(self, idx, self._vrect(page, b.rect), b.paras, block=b)
        else:
            para = TE.Para([TE.Run("", self.tools.text_family, self.tools.text_size,
                                   color=self.tools.color_for("text"))])
            r = QRectF(v.x(), v.y() - self.tools.text_size * 0.2, 240, self.tools.text_size * 1.6)
            self.editor = RichTextEditor(self, idx, r, [para], block=None)
        self.hover = None
        self._press = None

    def commit_editor(self) -> None:
        ed = self.editor
        if ed is None:
            return
        self.editor = None
        try:
            ed.commit()
        except Exception as ex:
            self._error(ex)
        finally:
            ed.close()
        self.setFocus()
        self.edit_finished.emit()

    def cancel_editor(self) -> None:
        ed = self.editor
        if ed is None:
            return
        self.editor = None
        ed.close()
        self.edit_finished.emit()

    # --------------------------------------------- strumenti a trascinamento
    def _clamp_to_page(self, idx: int, sp: QPointF) -> QPointF:
        it = self.items[idx]
        v = (sp - it.pos()) / self.scale_px
        return QPointF(min(max(v.x(), 0), it.w_pt), min(max(v.y(), 0), it.h_pt))

    @staticmethod
    def _snap45(p0: QPointF, p1: QPointF) -> QPointF:
        d = p1 - p0
        ang = math.atan2(d.y(), d.x())
        ang = round(ang / (math.pi / 4)) * (math.pi / 4)
        r = math.hypot(d.x(), d.y())
        return p0 + QPointF(r * math.cos(ang), r * math.sin(ang))

    def _style(self, tool: str) -> A.Style:
        t = self.tools
        return A.Style(color=t.color_for(tool), fill=t.fill, width=t.width, opacity=t.opacity, author=t.author,
                       fontsize=t.font_size, font=t.font, text_color=t.color_for("text"))

    def _finish_drag(self, t: dict, pr) -> None:
        tool = t["tool"]
        idx = t["page"]
        page = self.model.page(idx)
        r_view = QRectF(t["p0"], t["p1"]).normalized()
        small = r_view.width() < 3 and r_view.height() < 3
        mw = self.window()
        if tool in LINE_TOOLS:
            if small:
                return
            p0 = self._pdf_pt(page, t["p0"])
            p1 = self._pdf_pt(page, t["p1"])
            with self.model.edit(T('Disegno'), [idx]):
                page = self.model.page(idx)
                if tool == "measure":
                    _, label = A.add_measure(page, p0, p1, self.tools.measure_scale, self.tools.measure_unit,
                                             self._style(tool))
                    self.status.emit(T('Distanza: {}').format(label))
                else:
                    A.add_shape(page, tool, [p0, p1], self._style(tool))
            self._tool_done()
            return
        # strumenti che accettano anche un semplice clic (dimensione predefinita)
        defaults = {"freetext": (200, 40), "callout": (200, 40), "stamp": (180, 60), "signature": (180, 70),
                    "image": (0, 0), "form_text": (160, 22), "form_checkbox": (14, 14), "form_radio": (14, 14),
                    "form_combobox": (140, 22), "form_listbox": (140, 60), "form_signature": (200, 60),
                    "form_button": (90, 24), "sign_digital": (200, 70)}
        if small:
            if tool not in defaults:
                return
            dw, dh = defaults[tool]
            r_view = QRectF(t["p0"].x(), t["p0"].y(), dw, dh)
        rect = self._pdf_rect(page, r_view)
        if tool == "rect" or tool == "ellipse":
            with self.model.edit(T('Disegno'), [idx]):
                A.add_shape(self.model.page(idx), tool, [rect.tl, rect.br], self._style(tool))
            self._tool_done()
        elif tool in ("freetext", "callout"):
            from .editors import PlainEditor

            def done(text, rect=rect, r_view=r_view):
                if not text.strip():
                    return
                callout = None
                if tool == "callout":
                    # freccia dal bordo sinistro verso un punto sotto a sinistra
                    a = pymupdf.Point(rect.x0 - 40, rect.y1 + 30)
                    b = pymupdf.Point(rect.x0, (rect.y0 + rect.y1) / 2)
                    callout = [a, b]
                with self.model.edit(T('Casella di testo'), [idx]):
                    A.add_freetext(self.model.page(idx), rect, text, self._style(tool), callout)
                self._tool_done()
            self.editor = PlainEditor(self, idx, r_view, "", done, multiline=True,
                                      font_pt=self.tools.font_size)
        elif tool == "link":
            mw.create_link(idx, rect)
        elif tool == "redact":
            from .ops import security as SEC
            with self.model.edit(T('Contrassegna redazione'), [idx]):
                SEC.mark_area(self.model.page(idx), rect)
            self.status.emit(T('Area contrassegnata: usa «Applica redazioni» per eliminare il contenuto'))
        elif tool == "crop":
            mw.crop_with_rect(idx, rect)
        elif tool == "snapshot":
            self._snapshot(idx, rect)
        elif tool == "zoom_area":
            vw = self.viewport().width() - 40
            self.set_zoom(vw / (r_view.width() * PX_PER_PT))
            self.ensure_visible(idx, r_view)
        elif tool == "image":
            mw.insert_image_at(idx, rect, small)
        elif tool == "stamp":
            self._place_stamp(idx, rect)
        elif tool == "signature":
            mw.place_signature(idx, rect)
        elif tool == "sign_digital":
            mw.sign_digital(idx, rect)
        elif tool.startswith("form_"):
            mw.create_form_field(tool[5:], idx, rect)
        self.viewport().update()

    def _place_stamp(self, idx: int, rect: pymupdf.Rect) -> None:
        t = self.tools
        with self.model.edit(T('Timbro'), [idx]):
            page = self.model.page(idx)
            if t.stamp_index >= 0:
                A.add_stamp(page, rect, A.STAMPS[t.stamp_index][1], self._style("stamp"))
            else:
                A.add_text_stamp(page, rect, t.custom_stamp_text, t.custom_stamp_color, self._style("stamp"))
        self._tool_done()

    def _snapshot(self, idx: int, rect: pymupdf.Rect) -> None:
        page = self.model.page(idx)
        pix = page.get_pixmap(dpi=200, clip=rect)
        img = QImage(pix.samples_mv, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        QApplication.clipboard().setImage(img)
        self.status.emit(T('Istantanea copiata negli appunti'))

    def _commit_ink(self) -> None:
        t = self.temp
        if not t or t.get("kind") != "ink":
            return
        self.temp = None
        strokes = [s for s in t["strokes"] if len(s) > 1]
        if not strokes:
            return
        idx = t["page"]
        page = self.model.page(idx)
        pts = [[self._pdf_pt(page, q) for q in s] for s in strokes]
        with self.model.edit(T('Disegno a mano'), [idx]):
            A.add_ink(self.model.page(idx), pts, self._style("ink"))
        self._tool_done()
        self.viewport().update()

    def _finish_vertices(self) -> None:
        t = self.temp
        self.temp = None
        if not t or len(t["pts"]) < 2:
            self.viewport().update()
            return
        idx = t["page"]
        page = self.model.page(idx)
        pts = [self._pdf_pt(page, q) for q in t["pts"]]
        tool = t["tool"]
        try:
            with self.model.edit(T('Disegno'), [idx]):
                page = self.model.page(idx)
                if tool == "area":
                    if len(pts) < 3:
                        raise ValueError(T("Servono almeno 3 punti per misurare un'area"))
                    _, label = A.add_area_measure(page, pts, self.tools.measure_scale, self.tools.measure_unit,
                                                  self._style("area"))
                    self.status.emit(label)
                else:
                    A.add_shape(page, tool, pts, self._style(tool))
        except Exception as ex:
            self._error(ex)
        self._tool_done()
        self.viewport().update()

    def _add_note(self, idx: int, page, pt) -> None:
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getMultiLineText(self, T('Nuova nota'), T('Testo della nota:'))
        if not ok:
            return
        with self.model.edit(T('Nota'), [idx]):
            A.add_note(self.model.page(idx), pt, text, self.tools.note_icon, self._style("note"))
        self._tool_done()

    def _add_attachment(self, idx: int, page, pt) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(self, T('Allega file alla pagina'))
        if not path:
            return
        with self.model.edit(T('Allegato'), [idx]):
            A.add_file_attachment(self.model.page(idx), pt, path, self._style("note"))
        self._tool_done()

    def _erase_at(self, idx: int, page, pt) -> None:
        a = A.annot_at(page, pt)
        if a is None:
            return
        with self.model.edit(T('Elimina annotazione'), [idx]):
            p = self.model.page(idx)
            a = A.annot_at(p, pt)
            if a is not None:
                p.delete_annot(a)

    # --------------------------------------------------- link e moduli
    def _link_at(self, page, pt):
        for l in page.get_links():
            if pt in pymupdf.Rect(l["from"]):
                return l
        return None

    def _follow_link(self, page, pt) -> bool:
        l = self._link_at(page, pt)
        if not l:
            return False
        kind = l.get("kind")
        if kind == pymupdf.LINK_GOTO and l.get("page", -1) >= 0:
            to = l.get("to")
            target = l["page"]
            y = None
            if to is not None and target < self.model.page_count:
                tp = self.model.page(target)
                y = (pymupdf.Point(to) * tp.rotation_matrix).y if to else None
            self.go_to_page(target, y_pt=y)
            return True
        if kind == pymupdf.LINK_NAMED:
            name = l.get("name") or l.get("nameddest")
            target = l.get("page", -1)
            if target is not None and target >= 0:
                self.go_to_page(target)
            elif name in (T('NextPage'),):
                self.next_page()
            elif name in (T('PrevPage'),):
                self.prev_page()
            elif name == "FirstPage":
                self.go_to_page(0)
            elif name == "LastPage":
                self.go_to_page(self.model.page_count - 1)
            return True
        if kind == pymupdf.LINK_URI and l.get("uri"):
            uri = l["uri"]
            if QMessageBox.question(self, T('Apri collegamento'),
                                    T('Aprire questo indirizzo nel browser?\n\n{}').format(uri)) == QMessageBox.Yes:
                from PySide6.QtCore import QUrl
                from PySide6.QtGui import QDesktopServices
                QDesktopServices.openUrl(QUrl(uri))
            return True
        if kind in (pymupdf.LINK_LAUNCH, pymupdf.LINK_GOTOR):
            self.status.emit(T('Collegamento a file esterno non aperto per sicurezza: {}').format(l.get('file', '')))
            return True
        return False

    def _click_widget(self, idx: int, page, pt) -> bool:
        w = F.widget_at(page, pt)
        if w is None:
            return False
        if w.field_flags & pymupdf.PDF_FIELD_IS_READ_ONLY:
            self.status.emit(T('Campo di sola lettura'))
            return True
        xref = w.xref
        ft = w.field_type
        try:
            if ft in (pymupdf.PDF_WIDGET_TYPE_CHECKBOX, pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON):
                with self.model.edit(T('Compila modulo'), [idx]):
                    F.toggle(self.model.page(idx), xref)
            elif ft == pymupdf.PDF_WIDGET_TYPE_TEXT:
                from .editors import PlainEditor
                multiline = bool(w.field_flags & pymupdf.PDF_TX_FIELD_IS_MULTILINE)
                value = w.field_value or ""
                fs = w.text_fontsize or min(12.0, max(8.0, w.rect.height * 0.6))

                def done(text, xref=xref):
                    if text != value:
                        with self.model.edit(T('Compila modulo'), [idx]):
                            F.set_value(self.model.page(idx), xref, text)
                self.editor = PlainEditor(self, idx, self._vrect(page, w.rect), value, done, multiline=multiline,
                                          font_pt=fs, max_len=w.text_maxlen or 0)
            elif ft in (pymupdf.PDF_WIDGET_TYPE_COMBOBOX, pymupdf.PDF_WIDGET_TYPE_LISTBOX):
                m = QMenu(self)
                for c in w.choice_values or []:
                    label = c[1] if isinstance(c, (list, tuple)) else c
                    val = c[0] if isinstance(c, (list, tuple)) else c
                    act = m.addAction(str(label))
                    act.setCheckable(True)
                    act.setChecked(str(val) == str(w.field_value))
                    act.setData(val)
                chosen = m.exec(QCursor.pos())
                if chosen is not None:
                    with self.model.edit(T('Compila modulo'), [idx]):
                        F.set_value(self.model.page(idx), xref, chosen.data())
            elif ft == pymupdf.PDF_WIDGET_TYPE_SIGNATURE:
                self.request_sign_field.emit(w.field_name)
        except Exception as ex:
            self._error(ex)
        return True

    # ------------------------------------------------------------ errori
    def _error(self, ex: Exception) -> None:
        QMessageBox.warning(self, T('Operazione non riuscita'), str(ex) or type(ex).__name__)
