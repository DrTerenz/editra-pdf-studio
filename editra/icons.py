"""Icone disegnate a partire dai font di simboli di Windows.

Su Windows 11 c'è "Segoe Fluent Icons", su Windows 10 "Segoe MDL2 Assets":
i codici dei glifi sono in gran parte gli stessi. Se nessuno dei due è presente
l'icona è una lettera, così l'interfaccia resta usabile.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap

# nome logico -> codice del glifo
GLYPHS = {
    "open": 0xE8E5, "folder": 0xE838, "save": 0xE74E, "saveas": 0xE792,
    "print": 0xE749, "undo": 0xE7A7, "redo": 0xE7A6, "zoomin": 0xE8A3,
    "zoomout": 0xE71F, "fullscreen": 0xE740, "search": 0xE721, "page": 0xE7C3,
    "document": 0xE8A5, "copy": 0xE8C8, "paste": 0xE77F, "cut": 0xE8C6,
    "delete": 0xE74D, "add": 0xE710, "edit": 0xE70F, "rotate": 0xE7AD,
    "highlight": 0xE7E6, "underline": 0xE8DC, "strike": 0xEDE0, "squiggly": 0xE8D2,
    "font": 0xE8D2, "fontsize": 0xE8E9, "comment": 0xE90A, "note": 0xE70B,
    "attach": 0xE723, "lock": 0xE72E, "unlock": 0xE785, "image": 0xE8B9,
    "link": 0xE71B, "settings": 0xE713, "info": 0xE946, "help": 0xE897,
    "prev": 0xE76B, "next": 0xE76C, "first": 0xE892, "last": 0xE893,
    "up": 0xE74A, "down": 0xE74B, "ink": 0xE76D, "rect": 0xE739,
    "ellipse": 0xEA3A, "line": 0xE738, "arrow": 0xE72A, "polygon": 0xE7C2,
    "stamp": 0xE8EC, "certificate": 0xEB95, "shield": 0xEA18, "fingerprint": 0xE928,
    "merge": 0xE8F1, "split": 0xE8C6, "crop": 0xE7A8, "ruler": 0xED5E,
    "bookmarks": 0xE8A4, "list": 0xEA37, "thumbs": 0xE8A9, "hand": 0xE7C9,
    "select": 0xE8B3, "text": 0xE8D2, "mail": 0xE715, "refresh": 0xE72C,
    "contrast": 0xE7A1, "color": 0xE790, "accept": 0xE8FB, "cancel": 0xE711,
    "check": 0xE73E, "checkbox": 0xE739, "radio": 0xECCB, "combo": 0xE70D,
    "listbox": 0xE8FD, "button": 0xE7C9, "volume": 0xE767, "stop": 0xE71A,
    "compress": 0xE7B8, "scan": 0xE8FE, "person": 0xE77B, "warning": 0xE7BA,
    "error": 0xE783, "calendar": 0xE787, "home": 0xE80F, "twopage": 0xE89A,
    "layers": 0xE81E, "view": 0xE890, "eraser": 0xE75C, "compare": 0xE8AB,
    "export": 0xEDE1, "import": 0xE8B5, "newdoc": 0xE8A5, "close": 0xE711,
    "word": 0xE8A5, "table": 0xE80A, "watermark": 0xE7E7, "header": 0xE8BC,
    "number": 0xE8EF, "redact": 0xE7EF, "sign": 0xEE56, "pen": 0xED63,
    "camera": 0xE722, "moon": 0xE708, "sun": 0xE706, "form": 0xE8A1,
    "flatten": 0xE81E, "clean": 0xE894, "blank": 0xE7C3, "extract": 0xE8B7,
    "replace": 0xE8AB, "reverse": 0xE8CB, "measure": 0xED5E, "area": 0xE7C2,
    "polyline": 0xE738, "readmode": 0xE736, "pin": 0xE718,
}

_FONT_FAMILY: str | None = None
_cache: dict[tuple[str, str], QIcon] = {}
_color = QColor("#3b4252")


def _family() -> str:
    global _FONT_FAMILY
    if _FONT_FAMILY is None:
        families = set(QFontDatabase.families())
        for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets"):
            if f in families:
                _FONT_FAMILY = f
                break
        else:
            _FONT_FAMILY = ""
    return _FONT_FAMILY


def set_icon_color(color: str) -> None:
    """Cambia il colore delle icone (tema chiaro/scuro) e svuota la cache."""
    global _color
    _color = QColor(color)
    _cache.clear()


def glyph_pixmap(name: str, size: int, color: QColor | None = None, dpr: float = 2.0) -> QPixmap:
    color = color or _color
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)
    fam = _family()
    p.setPen(color)
    if fam:
        f = QFont(fam)
        f.setPixelSize(int(size * 0.8))
        p.setFont(f)
        p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, chr(GLYPHS.get(name, 0xE7C3)))
    else:
        f = QFont("Segoe UI")
        f.setPixelSize(int(size * 0.6))
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, name[:1].upper())
    p.end()
    return pm


def icon(name: str) -> QIcon:
    key = (name, _color.name())
    ic = _cache.get(key)
    if ic is None:
        ic = QIcon()
        for s in (16, 20, 24, 32):
            ic.addPixmap(glyph_pixmap(name, s), QIcon.Normal)
            ic.addPixmap(glyph_pixmap(name, s, QColor(_color.red(), _color.green(), _color.blue(), 90)), QIcon.Disabled)
        _cache[key] = ic
    return ic


def color_swatch(color: QColor | str | None, size: int = 16) -> QIcon:
    """Piccolo quadrato colorato per i pulsanti colore."""
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    r = QRectF(1, 1, size - 2, size - 2)
    if color is None:
        p.setPen(QColor("#999"))
        p.setBrush(Qt.white)
        p.drawRoundedRect(r, 3, 3)
        p.setPen(QColor("#d33"))
        p.drawLine(QPointF(2, size - 2), QPointF(size - 2, 2))
    else:
        p.setPen(QColor("#777"))
        p.setBrush(QColor(color))
        p.drawRoundedRect(r, 3, 3)
    p.end()
    return QIcon(pm)


def app_icon_pixmap(size: int = 256) -> QPixmap:
    """Logo dell'applicazione: un foglio con l'angolo piegato e una penna stilizzata."""
    from PySide6.QtGui import QLinearGradient, QPainterPath, QPen

    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 256.0
    # sfondo arrotondato
    g = QLinearGradient(0, 0, size, size)
    g.setColorAt(0, QColor("#7b3fe4"))
    g.setColorAt(1, QColor("#e0457b"))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(QRectF(8 * s, 8 * s, 240 * s, 240 * s), 52 * s, 52 * s)
    # foglio
    path = QPainterPath()
    path.moveTo(72 * s, 48 * s)
    path.lineTo(156 * s, 48 * s)
    path.lineTo(196 * s, 88 * s)
    path.lineTo(196 * s, 208 * s)
    path.lineTo(72 * s, 208 * s)
    path.closeSubpath()
    p.setBrush(QColor("#ffffff"))
    p.drawPath(path)
    fold = QPainterPath()
    fold.moveTo(156 * s, 48 * s)
    fold.lineTo(156 * s, 88 * s)
    fold.lineTo(196 * s, 88 * s)
    fold.closeSubpath()
    p.setBrush(QColor("#d9c8f7"))
    p.drawPath(fold)
    # righe di testo
    p.setBrush(QColor("#c9b6ef"))
    for i, w in enumerate((92, 104, 80)):
        p.drawRoundedRect(QRectF(92 * s, (112 + i * 24) * s, w * s, 10 * s), 5 * s, 5 * s)
    # "P" in evidenza
    pen = QPen(QColor("#7b3fe4"))
    pen.setWidthF(4 * s)
    f = QFont("Segoe UI")
    f.setPixelSize(int(64 * s))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#e0457b"))
    p.drawText(QRectF(84 * s, 52 * s, 80 * s, 64 * s), Qt.AlignLeft | Qt.AlignVCenter, "E")
    p.end()
    return pm


def app_icon() -> QIcon:
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(app_icon_pixmap(s))
    return ic
