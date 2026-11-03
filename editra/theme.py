"""Tema grafico: palette Fusion + foglio di stile, chiaro e scuro."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from . import icons

ACCENT = "#6d3fd6"

LIGHT = {
    "bg": "#f4f2f8", "panel": "#ffffff", "panel2": "#faf9fc", "border": "#e2deea",
    "text": "#2b2838", "muted": "#6f6a80", "hover": "#ece7f7", "pressed": "#ddd3f3",
    "viewer": "#e6e3ec", "accent": ACCENT, "accent_text": "#ffffff", "icon": "#3d3852",
    "sel": "#d9cdf6",
}
DARK = {
    "bg": "#1d1b24", "panel": "#26232f", "panel2": "#2c2936", "border": "#3a3646",
    "text": "#ebe8f2", "muted": "#a29db3", "hover": "#363244", "pressed": "#443e58",
    "viewer": "#15131b", "accent": "#9b7bf0", "accent_text": "#ffffff", "icon": "#dcd7ea",
    "sel": "#4b3f73",
}

current: dict = LIGHT


def is_dark() -> bool:
    return current is DARK


def _qss(c: dict) -> str:
    return f"""
    QWidget {{ font-family: 'Segoe UI'; font-size: 9.5pt; color: {c['text']}; }}
    QMainWindow, QDialog {{ background: {c['bg']}; }}
    QMenuBar {{ background: {c['panel']}; border-bottom: 1px solid {c['border']}; padding: 2px; }}
    QMenuBar::item {{ padding: 5px 10px; border-radius: 5px; background: transparent; }}
    QMenuBar::item:selected {{ background: {c['hover']}; }}
    QMenu {{ background: {c['panel']}; border: 1px solid {c['border']}; padding: 5px; border-radius: 8px; }}
    QMenu::item {{ padding: 6px 28px 6px 26px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {c['hover']}; }}
    QMenu::item:disabled {{ color: {c['muted']}; }}
    QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}
    QMenu::icon {{ padding-left: 6px; }}
    QToolBar {{ background: {c['panel']}; border: none; spacing: 2px; padding: 3px 6px; }}
    QToolBar::separator {{ width: 1px; background: {c['border']}; margin: 6px 6px; }}
    QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 4px; }}
    QToolButton:hover {{ background: {c['hover']}; }}
    QToolButton:pressed {{ background: {c['pressed']}; }}
    QToolButton:checked {{ background: {c['sel']}; border-color: {c['accent']}; }}
    QToolButton[popupMode="1"] {{ padding-right: 14px; }}
    QTabBar#categories {{ background: {c['panel']}; }}
    QTabBar#categories::tab {{ padding: 7px 16px; margin: 0 2px; border: none; border-bottom: 3px solid transparent;
        background: transparent; color: {c['muted']}; font-weight: 600; }}
    QTabBar#categories::tab:selected {{ color: {c['accent']}; border-bottom: 3px solid {c['accent']}; }}
    QTabBar#categories::tab:hover {{ color: {c['text']}; }}
    QTabWidget#docs::pane {{ border: none; }}
    QTabWidget#docs > QTabBar::tab {{ background: {c['bg']}; padding: 6px 14px; border: 1px solid {c['border']};
        border-bottom: none; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 2px; color: {c['muted']}; }}
    QTabWidget#docs > QTabBar::tab:selected {{ background: {c['panel']}; color: {c['text']}; }}
    QStatusBar {{ background: {c['panel']}; border-top: 1px solid {c['border']}; }}
    QDockWidget {{ titlebar-close-icon: none; }}
    QDockWidget::title {{ background: {c['panel']}; padding: 6px; font-weight: 600; }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit, QDateEdit {{
        background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 4px 6px;
        selection-background-color: {c['accent']}; selection-color: white; }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
        border: 1px solid {c['accent']}; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QPushButton {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 6px 14px; }}
    QPushButton:hover {{ background: {c['hover']}; }}
    QPushButton:pressed {{ background: {c['pressed']}; }}
    QPushButton:default, QPushButton#primary {{ background: {c['accent']}; color: {c['accent_text']}; border-color: {c['accent']}; }}
    QPushButton:disabled {{ color: {c['muted']}; }}
    QListWidget, QTreeWidget, QTableWidget, QListView, QTreeView {{ background: {c['panel']}; border: none;
        alternate-background-color: {c['panel2']}; outline: none; }}
    QListWidget::item, QTreeWidget::item {{ padding: 3px; border-radius: 5px; }}
    QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {{ background: {c['sel']}; color: {c['text']}; }}
    QListWidget::item:hover, QTreeWidget::item:hover {{ background: {c['hover']}; }}
    QHeaderView::section {{ background: {c['panel2']}; border: none; border-bottom: 1px solid {c['border']}; padding: 4px; }}
    QGroupBox {{ border: 1px solid {c['border']}; border-radius: 8px; margin-top: 14px; padding-top: 6px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; font-weight: 600; }}
    QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 30px; margin: 2px; }}
    QScrollBar::handle:vertical:hover {{ background: {c['muted']}; }}
    QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 0; }}
    QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 5px; min-width: 30px; margin: 2px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QSlider::groove:horizontal {{ height: 4px; background: {c['border']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: {c['accent']}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
    QProgressBar {{ border: 1px solid {c['border']}; border-radius: 6px; text-align: center; background: {c['panel']}; }}
    QProgressBar::chunk {{ background: {c['accent']}; border-radius: 5px; }}
    QToolTip {{ background: {c['panel']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 4px; }}
    QFrame#sidebarRail {{ background: {c['panel']}; border-right: 1px solid {c['border']}; }}
    QFrame#sidePanel {{ background: {c['panel']}; border-right: 1px solid {c['border']}; }}
    QLabel#panelTitle {{ font-weight: 700; font-size: 10.5pt; padding: 8px 6px 4px 8px; }}
    QLabel#muted {{ color: {c['muted']}; }}
    QWidget#welcome {{ background: {c['bg']}; }}
    QLabel#welcomeTitle {{ font-size: 24pt; font-weight: 700; }}
    QPushButton#tile {{ text-align: left; padding: 14px; border-radius: 10px; font-size: 10.5pt; background: {c['panel']}; }}
    QPushButton#tile:hover {{ border-color: {c['accent']}; background: {c['hover']}; }}
    QFrame#card {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 12px; }}
    QGraphicsView {{ background: {c['viewer']}; border: none; }}
    """


def apply(app: QApplication, mode: str = "light") -> None:
    """mode: 'light', 'dark' oppure 'system'."""
    global current
    if mode == "system":
        try:
            from PySide6.QtCore import Qt
            dark = app.styleHints().colorScheme() == Qt.ColorScheme.Dark
        except Exception:
            dark = False
        mode = "dark" if dark else "light"
    current = DARK if mode == "dark" else LIGHT
    c = current
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(c["bg"]))
    pal.setColor(QPalette.WindowText, QColor(c["text"]))
    pal.setColor(QPalette.Base, QColor(c["panel"]))
    pal.setColor(QPalette.AlternateBase, QColor(c["panel2"]))
    pal.setColor(QPalette.Text, QColor(c["text"]))
    pal.setColor(QPalette.Button, QColor(c["panel"]))
    pal.setColor(QPalette.ButtonText, QColor(c["text"]))
    pal.setColor(QPalette.Highlight, QColor(c["accent"]))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ToolTipBase, QColor(c["panel"]))
    pal.setColor(QPalette.ToolTipText, QColor(c["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(c["muted"]))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(c["muted"]))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(c["muted"]))
    app.setPalette(pal)
    app.setStyleSheet(_qss(c))
    icons.set_icon_color(c["icon"])
