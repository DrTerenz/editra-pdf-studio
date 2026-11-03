"""Impostazioni persistenti dell'app e impostazioni degli strumenti di disegno."""
from __future__ import annotations

import os

from PySide6.QtCore import QObject, QSettings, Signal

from . import APP_ID, ORG


def app_data_dir(*sub: str) -> str:
    base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_ID, *sub)
    os.makedirs(base, exist_ok=True)
    return base


def qsettings() -> QSettings:
    # file INI nella cartella dell'app (niente registro): facile da copiare o cancellare
    return QSettings(os.path.join(app_data_dir(), "impostazioni.ini"), QSettings.IniFormat)


def get(key: str, default=None, typ=None):
    s = qsettings()
    if typ is not None:
        return s.value(key, default, type=typ)
    return s.value(key, default)


def put(key: str, value) -> None:
    qsettings().setValue(key, value)


def recent_files() -> list[str]:
    v = get("recent", [])
    if isinstance(v, str):
        v = [v]
    return [p for p in (v or []) if os.path.exists(p)]


def add_recent(path: str) -> None:
    lst = [p for p in recent_files() if os.path.normcase(p) != os.path.normcase(path)]
    lst.insert(0, path)
    put("recent", lst[:15])


def clear_recent() -> None:
    put("recent", [])


# strumenti e colori predefiniti
DEFAULT_COLORS = {
    "highlight": "#ffeb3b", "underline": "#1e88e5", "strike": "#e53935", "squiggly": "#43a047",
    "note": "#ffd54f", "freetext": "#1e88e5", "callout": "#1e88e5", "ink": "#1e3a8a",
    "line": "#e53935", "arrow": "#e53935", "rect": "#e53935", "ellipse": "#e53935",
    "polygon": "#e53935", "polyline": "#e53935", "cloud": "#e53935", "measure": "#d81b60",
    "area": "#d81b60", "stamp": "#c62828", "text": "#000000",
}

SHAPE_TOOLS = ("line", "arrow", "rect", "ellipse", "polygon", "polyline", "ink", "measure", "area")
MARKUP_TOOLS = ("highlight", "underline", "strike", "squiggly")


class ToolSettings(QObject):
    changed = Signal()
    tool_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.tool = "select"
        self.colors = dict(DEFAULT_COLORS)
        stored = get("tool_colors")
        if isinstance(stored, dict):
            self.colors.update(stored)
        self.fill: str | None = None
        self.width = float(get("tool_width", 1.5))
        self.opacity = float(get("tool_opacity", 1.0))
        self.font_size = float(get("tool_font_size", 12))
        self.font = "helv"
        self.text_family = get("text_family", "Arial")
        self.text_size = float(get("text_size", 12))
        self.note_icon = "Comment"
        self.stamp_index = 0              # indice in annots.STAMPS, -1 = timbro personalizzato
        self.custom_stamp_text = "RICEVUTO"
        self.custom_stamp_color = "#1565c0"
        self.measure_scale = float(get("measure_scale", 1.0))
        self.measure_unit = get("measure_unit", "mm")
        self.author = get("author", os.environ.get("USERNAME", ""))
        self.signature_path: str | None = get("signature_path", None)
        self.keep_tool = bool(get("keep_tool", True, bool))

    def color_for(self, tool: str | None = None) -> str:
        return self.colors.get(tool or self.tool, "#e53935")

    def set_color(self, color: str, tool: str | None = None) -> None:
        self.colors[tool or self.tool] = color
        put("tool_colors", self.colors)
        self.changed.emit()

    def set_tool(self, tool: str) -> None:
        if tool != self.tool:
            self.tool = tool
            self.tool_changed.emit(tool)

    def persist(self) -> None:
        put("tool_width", self.width)
        put("tool_opacity", self.opacity)
        put("tool_font_size", self.font_size)
        put("text_family", self.text_family)
        put("text_size", self.text_size)
        put("measure_scale", self.measure_scale)
        put("measure_unit", self.measure_unit)
        put("author", self.author)
        if self.signature_path:
            put("signature_path", self.signature_path)
