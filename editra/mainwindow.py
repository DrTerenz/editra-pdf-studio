"""Finestra principale."""
from __future__ import annotations

import os
import traceback
from pathlib import Path

import pymupdf
from PySide6.QtCore import QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDockWidget, QFileDialog, QFormLayout, QFrame,
                               QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu,
                               QMessageBox, QProgressDialog, QPushButton, QScrollArea, QSlider, QSpinBox,
                               QStackedWidget, QStyle, QTabBar, QTabWidget, QToolBar, QToolButton, QVBoxLayout,
                               QWidget, QDoubleSpinBox, QCheckBox)

from . import APP_NAME, VERSION, dialogs as D, icons, printing, settings, theme
from .model import PdfModel, PasswordRequired
from .ops import annots as A
from .ops import compress as CMP
from .ops import convert as CV
from .ops import forms as F
from .ops import images as IM
from .ops import pages as PG
from .ops import security as SEC
from .ops import stamping as ST
from .ops import textedit as TE
from .ops.common import PAPER_SIZES, format_ranges, human_size, parse_ranges
from .panels import DocumentTab
from .settings import ToolSettings

PDF_FILTER = "Documenti PDF (*.pdf)"
OPEN_FILTER = ("Documenti (*.pdf *.p7m *.xps *.oxps *.epub *.cbz *.fb2 *.svg *.png *.jpg *.jpeg *.bmp *.gif "
               "*.tif *.tiff *.webp *.txt);;PDF (*.pdf);;PDF firmati (*.p7m);;Tutti i file (*)")

TOOL_NAMES = {
    "select": "Seleziona", "hand": "Mano", "edit_text": "Modifica testo", "edit_object": "Modifica oggetti",
    "highlight": "Evidenzia", "underline": "Sottolinea", "strike": "Barrato", "squiggly": "Ondulata",
    "note": "Nota", "freetext": "Casella di testo", "callout": "Richiamo", "ink": "Penna", "line": "Linea",
    "arrow": "Freccia", "rect": "Rettangolo", "ellipse": "Ellisse", "polygon": "Poligono", "polyline": "Spezzata",
    "stamp": "Timbro", "attach": "Allega file", "eraser": "Gomma", "measure": "Misura distanza",
    "area": "Misura area", "image": "Aggiungi immagine", "link": "Collegamento", "redact": "Redazione",
    "crop": "Ritaglia", "snapshot": "Istantanea", "zoom_area": "Zoom area", "signature": "Firma autografa",
    "sign_digital": "Firma digitale", "form_text": "Campo di testo", "form_checkbox": "Casella di controllo",
    "form_radio": "Pulsante di scelta", "form_combobox": "Elenco a discesa", "form_listbox": "Casella di riepilogo",
    "form_signature": "Campo firma", "form_button": "Pulsante",
}

TOOL_ICONS = {
    "select": "select", "hand": "hand", "edit_text": "font", "edit_object": "image", "highlight": "highlight",
    "underline": "underline", "strike": "strike", "squiggly": "squiggly", "note": "note", "freetext": "text",
    "callout": "comment", "ink": "ink", "line": "line", "arrow": "arrow", "rect": "rect", "ellipse": "ellipse",
    "polygon": "polygon", "polyline": "polyline", "stamp": "stamp", "attach": "attach", "eraser": "eraser",
    "measure": "ruler", "area": "area", "image": "image", "link": "link", "redact": "redact", "crop": "crop",
    "snapshot": "camera", "zoom_area": "zoomin", "signature": "sign", "sign_digital": "certificate",
    "form_text": "text", "form_checkbox": "checkbox", "form_radio": "radio", "form_combobox": "combo",
    "form_listbox": "listbox", "form_signature": "sign", "form_button": "button",
}

TOOL_HINTS = {
    "select": "Clic per selezionare annotazioni o compilare campi, trascina per selezionare il testo",
    "edit_text": "Clic su un testo per modificarlo (font, corpo, colore), clic su uno spazio vuoto per aggiungerne",
    "edit_object": "Clic su un'immagine o un blocco di testo: trascina per spostare, Canc per eliminare",
    "highlight": "Trascina sul testo da evidenziare (sulle scansioni trascina un'area)",
    "ink": "Disegna a mano libera; Invio o doppio clic per terminare",
    "polygon": "Clic per aggiungere i vertici, doppio clic per chiudere",
    "polyline": "Clic per aggiungere i vertici, doppio clic per terminare",
    "area": "Clic sui vertici dell'area, doppio clic per terminare",
    "measure": "Trascina per misurare (Maiusc per angoli di 45°)",
    "redact": "Trascina sull'area da oscurare, poi «Applica redazioni»",
    "crop": "Trascina il rettangolo da mantenere",
    "snapshot": "Trascina l'area da copiare come immagine",
    "sign_digital": "Trascina il riquadro della firma visibile",
    "signature": "Clic o trascina dove apporre la firma",
}


class Worker(QThread):
    done = Signal(object, object)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn = fn
        self.args = args

    def run(self):
        try:
            self.done.emit(self.fn(*self.args), None)
        except Exception as ex:
            self.done.emit(None, ex)


# ================================================================ pannello proprietà
class PropertiesPanel(QWidget):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.win = win
        t = win.tools
        self.tools = t
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 10)
        self.title = QLabel()
        self.title.setObjectName("panelTitle")
        lay.addWidget(self.title)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setObjectName("muted")
        lay.addWidget(self.hint)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        lay.addLayout(form)
        self.rows = {}

        def row(key, label, w):
            lab = QLabel(label)
            form.addRow(lab, w)
            self.rows[key] = (lab, w)

        self.color = D.ColorButton(t.color_for())
        self.color.changed.connect(lambda c: t.set_color(c))
        row("color", "Colore:", self.color)
        self.fill = D.ColorButton(t.fill, allow_none=True)
        self.fill.changed.connect(lambda c: (setattr(t, "fill", c), t.changed.emit()))
        row("fill", "Riempimento:", self.fill)
        self.width = QDoubleSpinBox()
        self.width.setRange(0, 30)
        self.width.setSingleStep(0.5)
        self.width.setValue(t.width)
        self.width.setSuffix(" pt")
        self.width.valueChanged.connect(lambda v: (setattr(t, "width", v), t.persist(), t.changed.emit()))
        row("width", "Spessore:", self.width)
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(10, 100)
        self.opacity.setValue(int(t.opacity * 100))
        self.opacity.valueChanged.connect(lambda v: (setattr(t, "opacity", v / 100), t.persist()))
        row("opacity", "Opacità:", self.opacity)
        self.fontsize = QDoubleSpinBox()
        self.fontsize.setRange(4, 144)
        self.fontsize.setValue(t.font_size)
        self.fontsize.setSuffix(" pt")
        self.fontsize.valueChanged.connect(lambda v: (setattr(t, "font_size", v), t.persist()))
        row("fontsize", "Corpo testo:", self.fontsize)
        self.font = QComboBox()
        for label, code in (("Helvetica", "helv"), ("Times", "tiro"), ("Courier", "cour")):
            self.font.addItem(label, code)
        self.font.currentIndexChanged.connect(lambda i: setattr(t, "font", self.font.currentData()))
        row("font", "Carattere:", self.font)
        self.textcolor = D.ColorButton(t.color_for("text"))
        self.textcolor.changed.connect(lambda c: t.set_color(c, "text"))
        row("textcolor", "Colore testo:", self.textcolor)
        from PySide6.QtWidgets import QFontComboBox
        self.family = QFontComboBox()
        self.family.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.family.setMinimumContentsLength(10)
        from PySide6.QtGui import QFont
        self.family.setCurrentFont(QFont(t.text_family))
        self.family.currentFontChanged.connect(lambda f: (setattr(t, "text_family", f.family()), t.persist()))
        row("family", "Font:", self.family)
        self.tsize = QDoubleSpinBox()
        self.tsize.setRange(4, 200)
        self.tsize.setValue(t.text_size)
        self.tsize.setSuffix(" pt")
        self.tsize.valueChanged.connect(lambda v: (setattr(t, "text_size", v), t.persist()))
        row("tsize", "Corpo:", self.tsize)
        self.icon = QComboBox()
        for label, code in A.NOTE_ICONS:
            self.icon.addItem(label, code)
        self.icon.currentIndexChanged.connect(lambda i: setattr(t, "note_icon", self.icon.currentData()))
        row("icon", "Icona:", self.icon)
        self.stamp = QComboBox()
        for label, code in A.STAMPS:
            self.stamp.addItem(label, code)
        self.stamp.addItem("Personalizzato…", -1)
        self.stamp.currentIndexChanged.connect(self._stamp)
        row("stamp", "Timbro:", self.stamp)
        self.stamptext = QLineEdit(t.custom_stamp_text)
        self.stamptext.textChanged.connect(lambda s: setattr(t, "custom_stamp_text", s))
        row("stamptext", "Testo timbro:", self.stamptext)
        self.stampcolor = D.ColorButton(t.custom_stamp_color)
        self.stampcolor.changed.connect(lambda c: setattr(t, "custom_stamp_color", c))
        row("stampcolor", "Colore timbro:", self.stampcolor)
        self.scale = QDoubleSpinBox()
        self.scale.setRange(0.001, 1000000)
        self.scale.setDecimals(3)
        self.scale.setValue(t.measure_scale)
        self.scale.setPrefix("1 : ")
        self.scale.valueChanged.connect(lambda v: (setattr(t, "measure_scale", v), t.persist()))
        row("scale", "Scala:", self.scale)
        self.unit = QComboBox()
        self.unit.addItems(["mm", "cm", "m", "in", "pt"])
        self.unit.setCurrentText(t.measure_unit)
        self.unit.currentTextChanged.connect(lambda u: (setattr(t, "measure_unit", u), t.persist()))
        row("unit", "Unità:", self.unit)
        self.sig = QPushButton("Scegli o crea firma…")
        self.sig.clicked.connect(win.choose_signature)
        row("sig", "Firma:", self.sig)
        self.sigprev = QLabel()
        self.sigprev.setMinimumHeight(60)
        self.sigprev.setAlignment(Qt.AlignCenter)
        self.sigprev.setStyleSheet("background:white; border:1px solid #ddd; border-radius:6px;")
        row("sigprev", "", self.sigprev)
        self.author = QLineEdit(t.author)
        self.author.textChanged.connect(lambda s: (setattr(t, "author", s), t.persist()))
        row("author", "Autore:", self.author)
        self.keep = QCheckBox("Mantieni lo strumento attivo")
        self.keep.setChecked(t.keep_tool)
        self.keep.toggled.connect(lambda on: (setattr(t, "keep_tool", on), settings.put("keep_tool", on)))
        row("keep", "", self.keep)
        lay.addStretch()
        t.tool_changed.connect(self.update_for)
        self.update_for(t.tool)

    def _stamp(self, i):
        code = self.stamp.currentData()
        self.tools.stamp_index = i if code != -1 else -1
        self.update_for(self.tools.tool)

    def update_for(self, tool: str) -> None:
        self.title.setText(TOOL_NAMES.get(tool, tool))
        self.hint.setText(TOOL_HINTS.get(tool, ""))
        show = {"author"}
        if tool in ("highlight", "underline", "strike", "squiggly"):
            show |= {"color", "opacity"}
        elif tool in ("line", "arrow", "polyline", "ink"):
            show |= {"color", "width", "opacity"}
        elif tool in ("rect", "ellipse", "polygon"):
            show |= {"color", "fill", "width", "opacity"}
        elif tool in ("freetext", "callout"):
            show |= {"color", "fill", "width", "opacity", "fontsize", "font", "textcolor"}
        elif tool == "note":
            show |= {"color", "icon"}
        elif tool == "stamp":
            show |= {"stamp", "opacity"}
            if self.tools.stamp_index == -1:
                show |= {"stamptext", "stampcolor"}
        elif tool in ("measure", "area"):
            show |= {"color", "width", "scale", "unit"}
        elif tool == "edit_text":
            show = {"family", "tsize", "textcolor"}
        elif tool == "signature":
            show = {"sig", "sigprev"}
            self._sig_preview()
        elif tool in ("select", "hand", "edit_object"):
            show = set()
        if tool not in ("select", "hand", "edit_text", "edit_object"):
            show.add("keep")
        for k, (lab, w) in self.rows.items():
            lab.setVisible(k in show)
            w.setVisible(k in show)
        self.color.setColor(self.tools.color_for(tool))
        if not show:
            self.hint.setText(TOOL_HINTS.get(tool, "Scegli uno strumento dalla barra in alto per vederne le opzioni."))

    def _sig_preview(self):
        from PySide6.QtGui import QPixmap
        p = self.tools.signature_path
        if p and os.path.exists(p):
            self.sigprev.setPixmap(QPixmap(p).scaled(220, 60, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.sigprev.setText("Nessuna firma")


# ===================================================================== benvenuto
class Welcome(QWidget):
    def __init__(self, win: "MainWindow"):
        super().__init__()
        self.setObjectName("welcome")
        self.win = win
        outer = QVBoxLayout(self)
        outer.setContentsMargins(50, 36, 50, 30)
        top = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icons.app_icon_pixmap(72))
        top.addWidget(logo)
        tv = QVBoxLayout()
        t = QLabel(APP_NAME)
        t.setObjectName("welcomeTitle")
        s = QLabel("Visualizza, modifica, combina, firma e proteggi i tuoi PDF.")
        s.setObjectName("muted")
        tv.addWidget(t)
        tv.addWidget(s)
        top.addLayout(tv)
        top.addStretch()
        outer.addLayout(top)
        outer.addSpacing(20)
        grid = QGridLayout()
        grid.setSpacing(12)
        tiles = [("open", "Apri un file", "PDF, immagini, XPS, EPUB, .p7m", "open"),
                 ("new_blank", "Nuovo PDF vuoto", "Una pagina A4 da riempire", "newdoc"),
                 ("create_from", "Crea PDF da file", "Word, Excel, PowerPoint, immagini, testo", "add"),
                 ("merge", "Combina file", "Più documenti in un unico PDF", "merge"),
                 ("compress_file", "Riduci dimensione", "Comprimi un PDF", "compress"),
                 ("compare", "Confronta documenti", "Trova le differenze tra due versioni", "compare"),
                 ("ocr_file", "Riconosci testo (OCR)", "Rendi ricercabile una scansione", "scan"),
                 ("open_p7m", "Verifica un file firmato", "Firme PAdES e buste CAdES .p7m", "certificate")]
        for i, (key, title, sub, ic) in enumerate(tiles):
            b = QPushButton(f"  {title}\n  {sub}")
            b.setObjectName("tile")
            b.setIcon(icons.icon(ic))
            b.setIconSize(QSize(28, 28))
            b.setMinimumHeight(70)
            b.setMinimumWidth(150)   # su schermi stretti il testo si accorcia invece di allargare la finestra
            b.setToolTip(f"{title}: {sub}")
            b.clicked.connect(lambda _=False, k=key: win.run_action(k))
            grid.addWidget(b, i // 4, i % 4)
        outer.addLayout(grid)
        outer.addSpacing(18)
        rt = QLabel("File recenti")
        rt.setObjectName("panelTitle")
        outer.addWidget(rt)
        from PySide6.QtWidgets import QListWidget, QListWidgetItem
        self.recent = QListWidget()
        self.recent.setObjectName("recent")
        self.recent.setMinimumWidth(200)
        self.recent.setTextElideMode(Qt.ElideMiddle)
        self.recent.itemActivated.connect(lambda it: win.open_files([it.data(Qt.UserRole)]))
        self.recent.itemClicked.connect(lambda it: win.open_files([it.data(Qt.UserRole)]))
        outer.addWidget(self.recent, 1)
        hint = QLabel("Suggerimento: trascina qui uno o più file per aprirli.")
        hint.setObjectName("muted")
        outer.addWidget(hint)
        self.refresh()

    def refresh(self):
        from PySide6.QtWidgets import QListWidgetItem
        self.recent.clear()
        for p in settings.recent_files():
            it = QListWidgetItem(icons.icon("document"), f"{os.path.basename(p)}   —   {os.path.dirname(p)}")
            it.setData(Qt.UserRole, p)
            self.recent.addItem(it)
        if not self.recent.count():
            it = QListWidgetItem("Nessun file recente")
            it.setFlags(Qt.NoItemFlags)
            self.recent.addItem(it)


# ================================================================= finestra principale
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.resize(1360, 880)
        self.setAcceptDrops(True)
        self.tools = ToolSettings()
        self.actions: dict[str, QAction] = {}
        self.tool_actions: dict[str, QAction] = {}
        self._icon_names: dict[str, str] = {}
        self._tts = None

        self.stack = QStackedWidget()
        self.welcome = Welcome(self)
        welcome_scroll = QScrollArea()
        welcome_scroll.setWidgetResizable(True)
        welcome_scroll.setFrameShape(QFrame.NoFrame)
        welcome_scroll.setWidget(self.welcome)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("docs")
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.stack.addWidget(welcome_scroll)
        self.stack.addWidget(self.tabs)
        self._welcome_page = welcome_scroll
        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        self._build_actions()
        self._build_menus()
        self._build_toolstrip(cl)
        cl.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self._build_props()
        self._build_status()
        self.tools.tool_changed.connect(self._tool_changed)
        self._tab_changed()
        geo = settings.get("geometry")
        if geo is not None:
            try:
                self.restoreGeometry(geo)
            except Exception:
                pass

    # ============================================================= azioni
    def _act(self, key, text, ic=None, shortcut=None, fn=None, checkable=False, tip=None, needs_doc=True):
        a = QAction(text, self)
        if ic:
            a.setIcon(icons.icon(ic))
            self._icon_names[key] = ic
        if shortcut:
            if isinstance(shortcut, (list, tuple)):
                a.setShortcuts([QKeySequence(s) for s in shortcut])
            else:
                a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        if tip:
            a.setToolTip(tip)
            a.setStatusTip(tip)
        if fn is not None:
            a.triggered.connect(lambda checked=False, f=fn: self._safe(f))
        a.setProperty("needs_doc", needs_doc)
        self.addAction(a)
        self.actions[key] = a
        return a

    def _safe(self, fn, *args):
        try:
            return fn(*args)
        except PermissionError as ex:
            QMessageBox.warning(self, "Permesso negato", str(ex))
        except Exception as ex:
            traceback.print_exc()
            QMessageBox.warning(self, "Operazione non riuscita", f"{ex}" or type(ex).__name__)

    def run_action(self, key: str, *args):
        """Chiamata dai pannelli e dai menu contestuali."""
        direct = {
            "rotate_right_current": lambda i: self.page_action("rotate_right", [i]),
            "rotate_left_current": lambda i: self.page_action("rotate_left", [i]),
            "delete_current": lambda i: self.page_action("delete", [i]),
            "bookmark_here": lambda i: self.tab().panels["bookmarks"].add(i),
            "comments_summary": self.comments_summary, "find_replace": self.find_replace,
            "open": self.open_dialog, "new_blank": self.new_blank, "create_from": self.create_from_files,
            "merge": self.merge, "compress_file": self.compress_file, "compare": self.compare,
            "ocr_file": self.ocr_file, "open_p7m": self.open_p7m_dialog,
        }
        fn = direct.get(key)
        if fn is not None:
            return self._safe(fn, *args)
        a = self.actions.get(key)
        if a:
            a.trigger()

    def _build_actions(self):
        a = self._act
        # file
        a("new_blank", "Nuovo documento vuoto", "newdoc", "Ctrl+N", self.new_blank, needs_doc=False)
        a("open", "Apri…", "open", QKeySequence.Open, self.open_dialog, needs_doc=False)
        a("create_from", "Crea PDF da file…", "add", None, self.create_from_files, needs_doc=False,
          tip="Converte in PDF documenti Office, immagini, testo e altro")
        a("create_clipboard", "Crea PDF dagli appunti", "paste", None, self.create_from_clipboard, needs_doc=False)
        a("merge", "Combina file…", "merge", None, self.merge, needs_doc=False)
        a("open_p7m", "Apri file firmato .p7m…", "certificate", None, self.open_p7m_dialog, needs_doc=False)
        a("save", "Salva", "save", QKeySequence.Save, self.save)
        a("save_as", "Salva con nome…", "saveas", "Ctrl+Shift+S", self.save_as)
        a("save_copy", "Salva una copia…", "copy", None, self.save_copy)
        a("revert", "Ripristina versione salvata", "refresh", None, self.revert)
        a("reveal", "Apri la cartella del file", "folder", None, self.reveal)
        a("print", "Stampa…", "print", QKeySequence.Print, self.print_doc)
        a("print_preview", "Anteprima di stampa…", "view", "Ctrl+Shift+P", self.print_preview)
        a("properties", "Proprietà del documento…", "info", "Ctrl+D", self.properties)
        a("close_tab", "Chiudi documento", "close", QKeySequence.Close, lambda: self.close_tab(self.tabs.currentIndex()))
        a("close_all", "Chiudi tutti", None, "Ctrl+Shift+W", self.close_all)
        a("quit", "Esci", None, "Ctrl+Q", self.close, needs_doc=False)
        # esporta
        a("export_word", "Word (.docx)…", "word", None, self.export_word)
        a("export_excel", "Excel (.xlsx)…", "table", None, self.export_excel)
        a("export_images", "Immagini (PNG, JPEG, TIFF)…", "image", None, lambda: self.export_images())
        a("export_text", "Testo (.txt)…", "text", None, lambda: self.export_simple("txt"))
        a("export_html", "Pagina web (.html)…", "export", None, lambda: self.export_simple("html"))
        a("export_md", "Markdown (.md)…", "export", None, lambda: self.export_simple("md"))
        a("extract_images", "Estrai tutte le immagini…", "image", None, self.extract_images)
        # modifica
        a("undo", "Annulla", "undo", QKeySequence.Undo, lambda: self._undo(True))
        a("redo", "Ripeti", "redo", [QKeySequence.Redo, "Ctrl+Y"], lambda: self._undo(False))
        a("copy", "Copia", "copy", None, lambda: self.view().copy_selection())
        a("select_all", "Seleziona tutto il testo della pagina", None, None,
          lambda: self.view().select_all_text(self.view().current))
        a("find", "Cerca…", "search", QKeySequence.Find, self.find)
        a("find_next", "Trova successivo", None, "F3", lambda: self.tab().panels["search"].step(1))
        a("find_prev", "Trova precedente", None, "Shift+F3", lambda: self.tab().panels["search"].step(-1))
        a("find_replace", "Trova e sostituisci…", "replace", "Ctrl+H", self.find_replace)
        a("detect_urls", "Rendi cliccabili gli indirizzi web", "link", None, self.detect_urls)
        a("remove_links", "Rimuovi tutti i collegamenti", None, None, self.remove_links)
        a("watermark", "Filigrana…", "watermark", None, self.watermark)
        a("background", "Sfondo…", "color", None, self.background)
        a("header_footer", "Intestazione e piè di pagina…", "header", None, self.header_footer)
        a("page_numbers", "Numeri di pagina…", "number", None, self.page_numbers)
        a("bates", "Numerazione Bates…", "number", None, self.bates)
        a("preferences", "Impostazioni…", "settings", "Ctrl+,", self.preferences, needs_doc=False)
        # visualizza
        a("zoom_in", "Ingrandisci", "zoomin", [QKeySequence.ZoomIn, "Ctrl+="], lambda: self.view().zoom_in())
        a("zoom_out", "Riduci", "zoomout", QKeySequence.ZoomOut, lambda: self.view().zoom_out())
        a("zoom_100", "Dimensione reale", None, "Ctrl+0", lambda: self.view().set_zoom(1.0))
        a("fit_width", "Adatta alla larghezza", None, "Ctrl+2", lambda: self.view().set_fit("width"))
        a("fit_page", "Pagina intera", None, "Ctrl+1", lambda: self.view().set_fit("page"))
        g = QActionGroup(self)
        for key, text, mode, sc in (("layout_single", "Pagina singola", "single", None),
                                    ("layout_continuous", "Pagine continue", "continuous", None),
                                    ("layout_two", "Due pagine", "two", None),
                                    ("layout_cover", "Due pagine con copertina", "two_cover", None)):
            act = a(key, text, "twopage" if "two" in mode else "page", sc,
                    lambda m=mode: self.view().set_layout(m), checkable=True)
            g.addAction(act)
        self.actions["layout_continuous"].setChecked(True)
        a("first_page", "Prima pagina", "first", "Home", lambda: self.view().go_to_page(0))
        a("prev_page", "Pagina precedente", "prev", [QKeySequence("Left"), "Ctrl+PgUp"], lambda: self.view().prev_page())
        a("next_page", "Pagina successiva", "next", [QKeySequence("Right"), "Ctrl+PgDown"], lambda: self.view().next_page())
        a("last_page", "Ultima pagina", "last", "End", lambda: self.view().go_to_page(self.model().page_count - 1))
        a("goto", "Vai alla pagina…", None, "Ctrl+G", self.goto_page)
        a("fullscreen", "Schermo intero", "fullscreen", "F11", self.toggle_fullscreen, needs_doc=False)
        a("reading", "Modalità lettura", "readmode", "Ctrl+Shift+H", self.toggle_reading, checkable=True)
        a("present", "Presentazione", "view", "Ctrl+L", self.presentation)
        a("night", "Pagine scure (lettura notturna)", "moon", None, self.toggle_night, checkable=True)
        a("dark_theme", "Tema scuro", "contrast", None, self.toggle_theme, checkable=True, needs_doc=False)
        a("panels", "Pannello laterale", "thumbs", "F4", self.toggle_panels)
        a("props_panel", "Pannello proprietà", "settings", "F6", lambda: self.props_dock.setVisible(not self.props_dock.isVisible()), needs_doc=False)
        a("read_aloud", "Leggi la pagina ad alta voce", "volume", "Ctrl+Shift+Y", self.read_aloud)
        a("stop_reading", "Interrompi lettura", "stop", None, self.stop_reading)
        a("highlight_fields", "Evidenzia campi modulo", "form", None, self.toggle_fields, checkable=True)
        self.actions["highlight_fields"].setChecked(settings.get("highlight_fields", True, bool))
        a("rotate_view_right", "Ruota pagine a destra", "rotate", "Ctrl+Shift++",
          lambda: self.page_action("rotate_right", list(range(self.model().page_count))))
        a("rotate_view_left", "Ruota pagine a sinistra", "rotate", "Ctrl+Shift+-",
          lambda: self.page_action("rotate_left", list(range(self.model().page_count))))
        # strumenti (gruppo esclusivo)
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        shortcuts = {"select": "V", "hand": "H", "edit_text": "T", "edit_object": "O", "highlight": "U",
                     "note": "N", "ink": "P", "rect": "R", "freetext": "X", "zoom_area": "Z"}
        for key, name in TOOL_NAMES.items():
            act = a("tool_" + key, name, TOOL_ICONS[key], shortcuts.get(key),
                    lambda k=key: self.set_tool(k), checkable=True, tip=TOOL_HINTS.get(key, name))
            self.tool_group.addAction(act)
            self.tool_actions[key] = act
        self.tool_actions["select"].setChecked(True)
        # commenti
        a("comments_summary", "Riepilogo commenti…", "list", None, self.comments_summary)
        a("delete_comments", "Elimina tutti i commenti…", "delete", None, self.delete_all_comments)
        a("flatten_annots", "Appiattisci commenti…", "flatten", None, self.flatten_annots)
        a("choose_signature", "Gestisci le firme autografe…", "sign", None, self.choose_signature, needs_doc=False)
        # pagine
        a("pg_blank", "Inserisci pagina vuota", "blank", None, lambda: self.page_action("blank_after", [self.view().current]))
        a("pg_insert", "Inserisci da file…", "import", None, lambda: self.page_action("insert_file", [self.view().current]))
        a("pg_delete", "Elimina pagine…", "delete", None, self.delete_pages_dialog)
        a("pg_extract", "Estrai pagine…", "extract", None, self.extract_dialog)
        a("pg_split", "Dividi documento…", "split", None, self.split)
        a("pg_rotate_r", "Ruota a destra", "rotate", "Ctrl+Shift+R", lambda: self.page_action("rotate_right", self._sel_pages()))
        a("pg_rotate_l", "Ruota a sinistra", "rotate", "Ctrl+Shift+L", lambda: self.page_action("rotate_left", self._sel_pages()))
        a("pg_rotate_dialog", "Ruota pagine…", "rotate", None, self.rotate_dialog)
        a("pg_duplicate", "Duplica pagina", "copy", None, lambda: self.page_action("duplicate", self._sel_pages()))
        a("pg_replace", "Sostituisci pagine…", "replace", None, lambda: self.page_action("replace", self._sel_pages()))
        a("pg_crop", "Ritaglia pagine…", "crop", None, self.crop_dialog)
        a("pg_uncrop", "Rimuovi ritaglio", None, None, lambda: self._edit_pages("Rimuovi ritaglio", lambda d, p: PG.reset_crop(d, p), all_pages=True))
        a("pg_resize", "Cambia formato pagine…", "fullscreen", None, self.resize_pages)
        a("pg_nup", "Più pagine per foglio…", "thumbs", None, self.nup)
        a("pg_interleave", "Unisci fronte/retro…", "merge", None, self.interleave)
        a("pg_reverse", "Inverti ordine pagine", "reverse", None, lambda: self._edit_struct("Inverti ordine", PG.reverse_pages))
        a("pg_remove_blank", "Rimuovi pagine vuote…", "clean", None, self.remove_blank)
        a("pg_labels", "Numerazione delle pagine (etichette)…", "number", None, self.page_labels)
        # moduli
        a("form_detect", "Riconosci campi automaticamente", "scan", None, self.form_detect)
        a("form_export", "Esporta dati modulo…", "export", None, self.form_export)
        a("form_import", "Importa dati modulo…", "import", None, self.form_import)
        a("form_reset", "Svuota modulo", "refresh", None, self.form_reset)
        a("form_flatten", "Appiattisci modulo", "flatten", None, self.form_flatten)
        a("form_list", "Elenco campi…", "list", None, self.form_list)
        # proteggi
        a("encrypt", "Proteggi con password…", "lock", None, self.encrypt)
        a("decrypt", "Rimuovi protezione", "unlock", None, self.decrypt)
        a("redact_search", "Cerca e redigi…", "search", None, self.redact_search)
        a("redact_apply", "Applica redazioni", "accept", None, self.apply_redactions)
        a("sanitize", "Rimuovi informazioni nascoste…", "clean", None, self.sanitize)
        a("verify_sigs", "Verifica firme", "certificate", None, lambda: self.tab().show_panel("signatures"))
        a("create_id", "Crea ID digitale…", "fingerprint", None, self.create_digital_id, needs_doc=False)
        a("trusted", "Certificati attendibili…", "shield", None, self.show_trusted, needs_doc=False)
        # strumenti
        a("ocr", "Riconosci testo (OCR)…", "scan", None, self.ocr)
        a("ocr_file", "OCR di un file…", "scan", None, self.ocr_file, needs_doc=False)
        a("compress", "Riduci dimensione file…", "compress", None, self.compress)
        a("compress_file", "Riduci dimensione di un file…", "compress", None, self.compress_file, needs_doc=False)
        a("compare", "Confronta documenti…", "compare", None, self.compare, needs_doc=False)
        # aiuto
        a("shortcuts", "Scorciatoie da tastiera", "help", "F1", self.show_shortcuts, needs_doc=False)
        a("about", f"Informazioni su {APP_NAME}", "info", None, self.about, needs_doc=False)
        QShortcut(QKeySequence("Escape"), self, activated=self._escape)

    def _build_menus(self):
        mb = self.menuBar()
        A_ = self.actions

        def menu(title, keys):
            m = mb.addMenu(title)
            for k in keys:
                if k == "-":
                    m.addSeparator()
                elif isinstance(k, tuple):
                    sub = m.addMenu(icons.icon(k[1]), k[0])
                    for kk in k[2]:
                        if kk == "-":
                            sub.addSeparator()
                        else:
                            sub.addAction(A_[kk])
                elif k == "@recent":
                    self.recent_menu = m.addMenu("Apri recenti")
                    self.recent_menu.aboutToShow.connect(self._fill_recent)
                else:
                    m.addAction(A_[k])
            return m

        menu("&File", ["new_blank", "open", "@recent", "open_p7m", "-", "create_from", "create_clipboard", "merge", "-",
                       "save", "save_as", "save_copy", "revert", "-",
                       ("Esporta in", "export", ["export_word", "export_excel", "export_images", "export_text",
                                                 "export_html", "export_md", "-", "extract_images"]),
                       "-", "print", "print_preview", "-", "properties", "reveal", "-", "close_tab", "close_all",
                       "quit"])
        menu("&Modifica", ["undo", "redo", "-", "copy", "select_all", "-", "find", "find_next", "find_prev",
                           "find_replace", "-", "tool_edit_text", "tool_edit_object", "tool_image", "tool_link",
                           "detect_urls", "remove_links", "-", "watermark", "background", "header_footer",
                           "page_numbers", "bates", "-", "preferences"])
        menu("&Visualizza", ["zoom_in", "zoom_out", "zoom_100", "fit_width", "fit_page", "tool_zoom_area", "-",
                             ("Disposizione pagine", "twopage", ["layout_single", "layout_continuous", "layout_two",
                                                                 "layout_cover"]),
                             ("Vai a", "next", ["first_page", "prev_page", "next_page", "last_page", "goto"]), "-",
                             "rotate_view_right", "rotate_view_left", "-", "fullscreen", "reading", "present",
                             "night", "dark_theme", "-", "panels", "props_panel", "highlight_fields", "-",
                             "read_aloud", "stop_reading"])
        menu("&Commenti", ["tool_highlight", "tool_underline", "tool_strike", "tool_squiggly", "-", "tool_note",
                           "tool_freetext", "tool_callout", "tool_stamp", "tool_attach", "-", "tool_ink", "tool_line",
                           "tool_arrow", "tool_rect", "tool_ellipse", "tool_polygon", "tool_polyline", "-",
                           "tool_measure", "tool_area", "-", "tool_eraser", "comments_summary", "delete_comments",
                           "flatten_annots"])
        menu("&Pagine", ["pg_blank", "pg_insert", "pg_replace", "pg_duplicate", "pg_delete", "pg_extract", "pg_split",
                         "-", "pg_rotate_r", "pg_rotate_l", "pg_rotate_dialog", "-", "tool_crop", "pg_crop",
                         "pg_uncrop", "pg_resize", "-", "pg_nup", "pg_interleave", "pg_reverse", "pg_remove_blank",
                         "pg_labels"])
        menu("M&oduli", ["tool_form_text", "tool_form_checkbox", "tool_form_radio", "tool_form_combobox",
                         "tool_form_listbox", "tool_form_button", "tool_form_signature", "-", "form_detect",
                         "form_list", "-", "form_export", "form_import", "form_reset", "form_flatten", "-",
                         "highlight_fields"])
        menu("P&roteggi", ["encrypt", "decrypt", "-", "tool_redact", "redact_search", "redact_apply", "sanitize", "-",
                           "tool_signature", "choose_signature", "-", "tool_sign_digital", "verify_sigs", "create_id",
                           "trusted"])
        menu("S&trumenti", ["ocr", "compress", "compare", "-", "tool_snapshot", "extract_images", "-",
                            "read_aloud", "-", "properties"])
        menu("&Aiuto", ["shortcuts", "about"])

    def _build_toolstrip(self, layout):
        A_ = self.actions
        top = QToolBar()
        top.setIconSize(QSize(20, 20))
        top.setMovable(False)
        for k in ("open", "save", "print", "-", "undo", "redo", "-", "tool_select", "tool_hand", "tool_zoom_area"):
            if k == "-":
                top.addSeparator()
            else:
                top.addAction(A_[k])
        top.addSeparator()
        for k in ("prev_page",):
            top.addAction(A_[k])
        from PySide6.QtGui import QIntValidator
        self.page_spin = QLineEdit("1")
        self.page_spin.setFixedWidth(54)
        self.page_spin.setAlignment(Qt.AlignCenter)
        self.page_spin.setToolTip("Numero di pagina (Invio per andarci)")
        self._page_validator = QIntValidator(1, 1, self)
        self.page_spin.setValidator(self._page_validator)
        self.page_spin.returnPressed.connect(self._goto_from_box)
        top.addWidget(self.page_spin)
        self.page_total = QLabel(" / 0 ")
        top.addWidget(self.page_total)
        top.addAction(A_["next_page"])
        top.addSeparator()
        top.addAction(A_["zoom_out"])
        self.zoom_box = QComboBox()
        self.zoom_box.setEditable(True)
        self.zoom_box.setFixedWidth(150)
        for t in ("Adatta larghezza", "Pagina intera", "50%", "75%", "100%", "125%", "150%", "200%", "300%", "400%"):
            self.zoom_box.addItem(t)
        self.zoom_box.activated.connect(lambda i: self._zoom_from_box())
        self.zoom_box.lineEdit().returnPressed.connect(self._zoom_from_box)
        top.addWidget(self.zoom_box)
        top.addAction(A_["zoom_in"])
        top.addSeparator()
        top.addAction(A_["fit_width"])
        A_["fit_width"].setIcon(icons.icon("fullscreen"))
        self._icon_names["fit_width"] = "fullscreen"
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy().Expanding, spacer.sizePolicy().verticalPolicy())
        from PySide6.QtWidgets import QSizePolicy
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        top.addWidget(spacer)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Cerca nel documento (Ctrl+F)")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setFixedWidth(260)
        self.search_box.addAction(icons.icon("search"), QLineEdit.LeadingPosition)
        self.search_box.returnPressed.connect(self._quick_search)
        top.addWidget(self.search_box)
        top.addAction(A_["dark_theme"])
        layout.addWidget(top)
        self.topbar = top

        # barra a categorie
        cats = [
            ("Home", ["tool_select", "tool_hand", "tool_edit_text", "tool_highlight", "tool_note", "tool_signature",
                      "-", "merge", "compress", "ocr", "export_word", "-", "find_replace", "print"]),
            ("Modifica", ["tool_edit_text", "tool_edit_object", "tool_image", "tool_link", "-", "find_replace",
                          "detect_urls", "-", "watermark", "background", "header_footer", "page_numbers", "bates"]),
            ("Commenti", ["tool_highlight", "tool_underline", "tool_strike", "tool_squiggly", "-", "tool_note",
                          "tool_freetext", "tool_callout", "tool_stamp", "tool_attach", "-", "tool_ink", "tool_line",
                          "tool_arrow", "tool_rect", "tool_ellipse", "tool_polygon", "tool_polyline", "-",
                          "tool_measure", "tool_area", "tool_eraser", "-", "comments_summary"]),
            ("Pagine", ["pg_blank", "pg_insert", "pg_delete", "pg_extract", "pg_split", "merge", "-", "pg_rotate_l",
                        "pg_rotate_r", "tool_crop", "pg_resize", "-", "pg_duplicate", "pg_replace", "pg_nup",
                        "pg_interleave", "pg_remove_blank"]),
            ("Moduli", ["tool_form_text", "tool_form_checkbox", "tool_form_radio", "tool_form_combobox",
                        "tool_form_listbox", "tool_form_button", "tool_form_signature", "-", "form_detect",
                        "form_export", "form_import", "form_reset", "form_flatten"]),
            ("Firma e proteggi", ["tool_signature", "tool_sign_digital", "verify_sigs", "create_id", "-", "encrypt",
                                  "decrypt", "-", "tool_redact", "redact_search", "redact_apply", "sanitize"]),
            ("Converti", ["create_from", "merge", "-", "export_word", "export_excel", "export_images", "export_text",
                          "export_html", "-", "ocr", "compress"]),
            ("Strumenti", ["ocr", "compress", "compare", "tool_snapshot", "extract_images", "-", "tool_measure",
                           "tool_area", "-", "read_aloud", "stop_reading", "-", "properties", "preferences"]),
        ]
        self.cat_bar = QTabBar()
        self.cat_bar.setObjectName("categories")
        self.cat_bar.setDrawBase(False)
        self.cat_bar.setExpanding(False)
        self.cat_stack = QStackedWidget()
        short = {"tool_select": "Seleziona", "tool_hand": "Mano", "tool_edit_text": "Modifica testo",
                 "tool_edit_object": "Oggetti", "export_word": "In Word", "find_replace": "Sostituisci",
                 "tool_signature": "Firma", "tool_sign_digital": "Firma digitale", "verify_sigs": "Verifica",
                 "create_id": "ID digitale", "compress": "Comprimi", "ocr": "OCR", "merge": "Combina",
                 "pg_blank": "Vuota", "pg_insert": "Inserisci", "pg_delete": "Elimina", "pg_extract": "Estrai",
                 "pg_split": "Dividi", "pg_rotate_l": "Ruota sx", "pg_rotate_r": "Ruota dx", "pg_resize": "Formato",
                 "pg_duplicate": "Duplica", "pg_replace": "Sostituisci", "pg_nup": "N per foglio",
                 "pg_interleave": "Fronte/retro", "pg_remove_blank": "Togli vuote", "form_detect": "Riconosci",
                 "form_export": "Esporta dati", "form_import": "Importa dati", "form_reset": "Svuota",
                 "form_flatten": "Appiattisci", "encrypt": "Password", "decrypt": "Togli protezione",
                 "redact_search": "Cerca e redigi", "redact_apply": "Applica", "sanitize": "Pulisci",
                 "create_from": "Crea PDF", "export_excel": "In Excel", "export_images": "In immagini",
                 "export_text": "In testo", "export_html": "In HTML", "compare": "Confronta",
                 "extract_images": "Estrai immagini", "read_aloud": "Leggi", "stop_reading": "Stop",
                 "properties": "Proprietà", "preferences": "Impostazioni", "comments_summary": "Riepilogo",
                 "watermark": "Filigrana", "background": "Sfondo", "header_footer": "Intestazioni",
                 "page_numbers": "Numeri pag.", "bates": "Bates", "detect_urls": "Link automatici",
                 "tool_form_text": "Testo", "tool_form_checkbox": "Casella", "tool_form_radio": "Scelta",
                 "tool_form_combobox": "Elenco", "tool_form_listbox": "Riepilogo", "tool_form_button": "Pulsante",
                 "tool_form_signature": "Campo firma", "tool_measure": "Distanza", "tool_area": "Area",
                 "tool_freetext": "Testo", "tool_callout": "Richiamo", "print": "Stampa"}
        for title, keys in cats:
            tb = QToolBar()
            tb.setIconSize(QSize(22, 22))
            tb.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            tb.setMovable(False)
            for k in keys:
                if k == "-":
                    tb.addSeparator()
                    continue
                act = A_[k]
                btn = self._strip_button(act, short.get(k, act.text().replace("…", "")),
                                         self._icon_names.get(k, "page"))
                if k == "tool_stamp":
                    m = QMenu(btn)
                    for i, (label, _) in enumerate(A.STAMPS):
                        m.addAction(label, lambda i=i: (self.props.stamp.setCurrentIndex(i), self.set_tool("stamp")))
                    m.addAction("Personalizzato…", lambda: (self.props.stamp.setCurrentIndex(len(A.STAMPS)),
                                                           self.set_tool("stamp")))
                    btn.setMenu(m)
                    btn.setPopupMode(QToolButton.MenuButtonPopup)
                tb.addWidget(btn)
            self.cat_bar.addTab(title)
            self.cat_stack.addWidget(tb)
        self.cat_bar.currentChanged.connect(self.cat_stack.setCurrentIndex)
        frame = QFrame()
        frame.setObjectName("strip")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(0)
        fl.addWidget(self.cat_bar)
        fl.addWidget(self.cat_stack)
        frame.setStyleSheet(f"QFrame#strip {{ border-bottom: 1px solid {theme.current['border']}; }}")
        self.strip = frame
        layout.addWidget(frame)

    def _strip_button(self, act: QAction, label: str, icon_name: str) -> QToolButton:
        btn = QToolButton()
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setIcon(icons.icon(icon_name))
        btn.setProperty("icon_name", icon_name)
        btn.setIconSize(QSize(22, 22))
        btn.setText(label)
        btn.setToolTip(act.toolTip() or act.text())
        btn.setCheckable(act.isCheckable())
        btn.ensurePolished()
        # larghezza fissa: se la barra non basta, i pulsanti in più vanno nel menu »
        btn.setMinimumWidth(max(58, btn.sizeHint().width(), btn.fontMetrics().horizontalAdvance(label) + 20))
        btn.clicked.connect(lambda checked=False, a=act: a.trigger())
        act.toggled.connect(btn.setChecked)
        act.changed.connect(lambda a=act, b=btn: (b.setEnabled(a.isEnabled()), b.setChecked(a.isChecked())))
        btn.setEnabled(act.isEnabled())
        return btn

    def _build_props(self):
        self.props = PropertiesPanel(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self.props)
        scroll.setFrameShape(QFrame.NoFrame)
        self.props_dock = QDockWidget("Proprietà", self)
        self.props_dock.setObjectName("props")
        self.props_dock.setWidget(scroll)
        self.props_dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.props_dock.setMinimumWidth(280)
        self.addDockWidget(Qt.RightDockWidgetArea, self.props_dock)
        self.resizeDocks([self.props_dock], [290], Qt.Horizontal)
        self.props_dock.setVisible(settings.get("props_visible", True, bool))

    def _build_status(self):
        sb = self.statusBar()
        self.msg = QLabel()
        sb.addWidget(self.msg, 1)
        self.info_lbl = QLabel()
        self.info_lbl.setObjectName("muted")
        sb.addPermanentWidget(self.info_lbl)
        for k in ("layout_single", "layout_continuous", "layout_two"):
            b = QToolButton()
            b.setDefaultAction(self.actions[k])
            b.setAutoRaise(True)
            sb.addPermanentWidget(b)
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(10, 800)
        self.zoom_slider.setFixedWidth(140)
        self.zoom_slider.sliderMoved.connect(lambda v: self.view() and self.view().set_zoom(v / 100))
        sb.addPermanentWidget(self.zoom_slider)
        self.zoom_lbl = QLabel("100%")
        self.zoom_lbl.setFixedWidth(46)
        sb.addPermanentWidget(self.zoom_lbl)

    def status(self, text: str, ms: int = 6000) -> None:
        self.msg.setText(text)
        if ms:
            QTimer.singleShot(ms, lambda t=text: self.msg.text() == t and self.msg.setText(""))

    # ======================================================== schede
    def tab(self) -> DocumentTab | None:
        w = self.tabs.currentWidget()
        return w if isinstance(w, DocumentTab) else None

    def model(self) -> PdfModel | None:
        t = self.tab()
        return t.model if t else None

    def view(self):
        t = self.tab()
        return t.view if t else None

    def _require(self) -> PdfModel:
        m = self.model()
        if m is None:
            raise RuntimeError("Nessun documento aperto")
        return m

    def add_model(self, model: PdfModel, select: bool = True) -> DocumentTab:
        tab = DocumentTab(model, self.tools)
        idx = self.tabs.addTab(tab, icons.icon("document"), model.title)
        close = QToolButton()
        close.setIcon(icons.icon("close"))
        close.setProperty("icon_name", "close")
        close.setIconSize(QSize(12, 12))
        close.setAutoRaise(True)
        close.setToolTip("Chiudi documento")
        close.setFixedSize(20, 20)
        close.clicked.connect(lambda _=False, t=tab: self.close_tab(self.tabs.indexOf(t)))
        self.tabs.tabBar().setTabButton(idx, QTabBar.RightSide, close)
        tab.view.page_changed.connect(lambda i, t=tab: self._page_changed(t))
        tab.view.zoom_changed.connect(lambda z, t=tab: self._zoom_changed(t))
        tab.view.status.connect(self.status)
        tab.view.request_annot_props.connect(self.annot_properties)
        tab.view.request_sign_field.connect(self.sign_existing_field)
        tab.view.request_tool.connect(self.set_tool)
        tab.view.highlight_fields = self.actions["highlight_fields"].isChecked()
        model.modified_changed.connect(lambda m, t=tab: self._update_title(t))
        model.saved.connect(lambda p, t=tab: (self._update_title(t), settings.add_recent(p)))
        model.structure_changed.connect(lambda t=tab: self._page_changed(t))
        model.changed.connect(lambda _p, t=tab: self._update_undo())
        model.structure_changed.connect(self._update_undo)
        if select:
            self.tabs.setCurrentWidget(tab)
        self.stack.setCurrentWidget(self.tabs)
        mode = settings.get("open_layout", "continuous")
        if mode != "continuous":
            tab.view.set_layout(mode)
        zoom = settings.get("open_zoom", "width")
        QTimer.singleShot(0, lambda: tab.view.set_fit(zoom) if zoom in ("width", "page") else tab.view.set_zoom(1.0))
        self._update_title(tab)
        if model.path:
            settings.add_recent(model.path)
        if not (model.doc.permissions & pymupdf.PDF_PERM_MODIFY) and model.doc.is_encrypted:
            self.status("Il documento ha restrizioni di modifica impostate dall'autore", 10000)
        return tab

    def _update_title(self, tab: DocumentTab) -> None:
        i = self.tabs.indexOf(tab)
        if i < 0:
            return
        m = tab.model
        self.tabs.setTabText(i, ("● " if m.modified else "") + m.title)
        self.tabs.setTabToolTip(i, m.path or m.title)
        if tab is self.tab():
            self.setWindowTitle(f"{'● ' if m.modified else ''}{m.title} – {APP_NAME}")
        self._update_undo()

    def _tab_changed(self, *_):
        tab = self.tab()
        has = tab is not None
        for a in self.actions.values():
            if a.property("needs_doc"):
                a.setEnabled(has)
        if not has:
            self.stack.setCurrentWidget(self._welcome_page)
            self.welcome.refresh()
            self.setWindowTitle(APP_NAME)
            self.page_total.setText(" / 0 ")
            return
        self._update_title(tab)
        self._page_changed(tab)
        self._zoom_changed(tab)
        self.actions["night"].setChecked(tab.view.night)
        mode = tab.view.layout_mode
        key = {"single": "layout_single", "continuous": "layout_continuous", "two": "layout_two",
               "two_cover": "layout_cover"}[mode]
        self.actions[key].setChecked(True)

    def _page_changed(self, tab):
        if tab is not self.tab():
            return
        v = tab.view
        n = tab.model.page_count
        self._page_validator.setTop(max(1, n))
        if not self.page_spin.hasFocus():
            self.page_spin.setText(str(v.current + 1))
        self.page_total.setText(f" / {n} ")
        try:
            r = tab.model.page(v.current).rect
            self.info_lbl.setText(f"{r.width * 25.4 / 72:.0f} × {r.height * 25.4 / 72:.0f} mm   ")
        except Exception:
            pass

    def _zoom_changed(self, tab):
        if tab is not self.tab():
            return
        z = tab.view.zoom
        self.zoom_lbl.setText(f"{z * 100:.0f}%")
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(int(z * 100))
        self.zoom_slider.blockSignals(False)
        fm = tab.view.fit_mode
        self.zoom_box.setEditText("Adatta larghezza" if fm == "width" else "Pagina intera" if fm == "page" else f"{z * 100:.0f}%")

    def _goto_from_box(self):
        v = self.view()
        if v and self.page_spin.text().isdigit():
            v.go_to_page(int(self.page_spin.text()) - 1)
            v.setFocus()

    def _zoom_from_box(self):
        v = self.view()
        if not v:
            return
        t = self.zoom_box.currentText().strip()
        if t.startswith("Adatta"):
            v.set_fit("width")
        elif t.startswith("Pagina"):
            v.set_fit("page")
        else:
            try:
                v.set_zoom(float(t.replace("%", "").replace(",", ".")) / 100)
            except ValueError:
                pass

    def _update_undo(self):
        m = self.model()
        u, r = self.actions["undo"], self.actions["redo"]
        u.setEnabled(bool(m and m.can_undo()))
        r.setEnabled(bool(m and m.can_redo()))
        u.setText(f"Annulla {m.undo_label().lower()}" if m and m.can_undo() else "Annulla")
        r.setText(f"Ripeti {m.redo_label().lower()}" if m and m.can_redo() else "Ripeti")

    def _undo(self, undo: bool):
        m = self._require()
        v = self.view()
        v.cancel_editor()
        (m.undo if undo else m.redo)()
        self._update_undo()

    # ========================================================= strumenti
    def set_tool(self, tool: str):
        if self.tab() is None and tool != "select":
            return
        self.tools.set_tool(tool)

    def _tool_changed(self, tool: str):
        act = self.tool_actions.get(tool)
        if act and not act.isChecked():
            act.setChecked(True)
        if tool == "signature" and not (self.tools.signature_path and os.path.exists(self.tools.signature_path)):
            QTimer.singleShot(0, self.choose_signature)
        hint = TOOL_HINTS.get(tool)
        if hint:
            self.status(hint, 8000)
        for t in self._tabs():
            t.view.viewport().update()

    def _escape(self):
        v = self.view()
        if v is not None and v.editor is not None:
            v.cancel_editor()
            return
        if self.isFullScreen():
            self.toggle_fullscreen()
        elif self.actions["reading"].isChecked():
            self.actions["reading"].setChecked(False)
            self.toggle_reading()

    def _tabs(self):
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    # ======================================================= apertura
    def open_dialog(self):
        start = os.path.dirname(settings.recent_files()[0]) if settings.recent_files() else os.path.expanduser("~/Documents")
        paths, _ = QFileDialog.getOpenFileNames(self, "Apri", start, OPEN_FILTER)
        if paths:
            self.open_files(paths)

    def open_files(self, paths: list[str]):
        for p in paths:
            p = os.path.abspath(p)
            # già aperto?
            for t in self._tabs():
                if t.model.path and os.path.normcase(t.model.path) == os.path.normcase(p):
                    self.tabs.setCurrentWidget(t)
                    break
            else:
                if not os.path.exists(p):
                    QMessageBox.warning(self, "Apri", f"Il file non esiste più:\n{p}")
                    continue
                if p.lower().endswith(".p7m"):
                    self._safe(self.open_p7m, p)
                    continue
                self._safe(self._open_one, p)

    def _open_one(self, path: str):
        pw = None
        while True:
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                try:
                    model = PdfModel(path, password=pw)
                finally:
                    QApplication.restoreOverrideCursor()
                break
            except PasswordRequired:
                pw, ok = QInputDialog.getText(self, "Documento protetto",
                                              f"«{os.path.basename(path)}» è protetto.\n"
                                              + ("Password errata, riprova:" if pw else "Inserisci la password:"),
                                              QLineEdit.Password)
                if not ok:
                    return
            except Exception as ex:
                QMessageBox.warning(self, "Impossibile aprire il file", f"{os.path.basename(path)}\n\n{ex}")
                return
        self.add_model(model)

    def open_p7m_dialog(self):
        p, _ = QFileDialog.getOpenFileName(self, "Apri file firmato", "", "File firmati (*.p7m *.p7s);;Tutti i file (*)")
        if p:
            self.open_p7m(p)

    def open_p7m(self, path: str):
        from .ops import signatures as SG
        with open(path, "rb") as f:
            data = f.read()
        content, infos = SG.parse_p7m(data)
        html = f"<h3>{os.path.basename(path)}</h3>"
        for i in infos:
            color = {"valida": "#2e7d32", "sconosciuta": "#f9a825", "modificata": "#ef6c00",
                     "non_valida": "#c62828"}[i.status]
            html += (f"<p style='color:{color}'><b>{i.summary}</b></p><table cellpadding='3'>"
                     f"<tr><td><b>Firmatario</b></td><td>{i.signer}</td></tr>"
                     f"<tr><td><b>Emesso da</b></td><td>{i.issuer}</td></tr>"
                     f"<tr><td><b>Data</b></td><td>{i.time or '—'}</td></tr>"
                     f"<tr><td><b>Certificato valido</b></td><td>{i.cert_valid_from} – {i.cert_valid_to}</td></tr>"
                     "</table>" + ("<p>" + "<br>".join(i.errors) + "</p>" if i.errors else ""))
        if not infos:
            html += "<p>Nessuna firma trovata nella busta.</p>"
        inner_name = Path(path).name
        while inner_name.lower().endswith((".p7m", ".p7s")):
            inner_name = inner_name[:-4]
        D.ReportDialog(self, "Verifica busta firmata (CAdES)", html).exec()
        if content[:4] == b"%PDF":
            model = PdfModel(data=content, title=inner_name if inner_name.lower().endswith(".pdf") else inner_name + ".pdf")
            model.modified = False
            self.add_model(model)
        elif content:
            if QMessageBox.question(self, "Documento contenuto",
                                    f"Il documento firmato non è un PDF ({inner_name}).\nSalvarlo su disco?") == QMessageBox.Yes:
                out, _ = QFileDialog.getSaveFileName(self, "Salva documento", inner_name)
                if out:
                    with open(out, "wb") as f:
                        f.write(content)

    def new_blank(self):
        r = D.ask(self, "Nuovo documento", [
            ("size", "Formato", "choice", "A4", list(PAPER_SIZES)),
            ("orient", "Orientamento", "choice", "v", [("Verticale", "v"), ("Orizzontale", "o")]),
            ("pages", "Numero di pagine", "int", 1, (1, 500))])
        if not r:
            return
        w, h = PAPER_SIZES[r["size"]]
        if r["orient"] == "o":
            w, h = h, w
        doc = pymupdf.open()
        for _ in range(r["pages"]):
            doc.new_page(width=w, height=h)
        self.add_model(PdfModel(data=doc.tobytes(), title="Nuovo documento.pdf"))

    def create_from_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Crea PDF da file", "", D.FILE_FILTER_ALL)
        if not paths:
            return
        prog = self._progress("Conversione in PDF…", len(paths))
        out = pymupdf.open()
        try:
            for k, p in enumerate(paths):
                prog.setLabelText(f"Conversione di {os.path.basename(p)}…")
                prog.setValue(k)
                QApplication.processEvents()
                if prog.wasCanceled():
                    return
                d = CV.any_to_pdf(p)
                out.insert_pdf(d)
                d.close()
        finally:
            prog.close()
        title = Path(paths[0]).stem + ".pdf" if len(paths) == 1 else "Documento combinato.pdf"
        self.add_model(PdfModel(data=out.tobytes(garbage=3, deflate=True), title=title))

    def create_from_clipboard(self):
        cb = QApplication.clipboard()
        md = cb.mimeData()
        if md.hasImage():
            from PySide6.QtCore import QBuffer, QByteArray, QIODevice
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.WriteOnly)
            cb.image().save(buf, "PNG")
            img = pymupdf.open("png", bytes(ba))
            doc = pymupdf.open("pdf", img.convert_to_pdf())
        elif md.hasText() and md.text().strip():
            doc = CV.text_to_pdf(md.text())
        else:
            QMessageBox.information(self, "Appunti", "Negli appunti non c'è né un'immagine né del testo.")
            return
        self.add_model(PdfModel(data=doc.tobytes(), title="Dagli appunti.pdf"))

    def merge(self):
        initial = [self.model().path] if self.model() and self.model().path else []
        d = D.MergeDialog(self, initial)
        if d.exec() != QDialog.Accepted:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            out = PG.merge_files(d.items(), bookmarks=d.bookmarks.isChecked())
        finally:
            QApplication.restoreOverrideCursor()
        self.add_model(PdfModel(data=out.tobytes(garbage=3, deflate=True), title="Documento combinato.pdf"))
        self.status(f"Combinati {len(d.items())} file: {out.page_count} pagine")

    # ======================================================= salvataggio
    def _check_restrictions(self, m: PdfModel) -> bool:
        if m.doc.is_encrypted and not (m.doc.permissions & pymupdf.PDF_PERM_MODIFY) and m.encryption is None:
            pw, ok = QInputDialog.getText(self, "Documento con restrizioni",
                                          "L'autore ha limitato le modifiche a questo documento.\n"
                                          "Per salvare inserisci la password dei permessi:", QLineEdit.Password)
            if not ok:
                return False
            r = m.doc.authenticate(pw)
            if r < 4 and not (m.doc.permissions & pymupdf.PDF_PERM_MODIFY):
                QMessageBox.warning(self, "Password errata", "La password dei permessi non è corretta.")
                return False
            m.password = pw
        return True

    def save(self, model: PdfModel | None = None) -> bool:
        m = model or self._require()
        if model is None:
            self.view().commit_editor()
        if not m.path or m.converted_from:
            return self.save_as(m)
        if not self._check_restrictions(m):
            return False
        if not m.signatures_preserved_on_save():
            if QMessageBox.warning(self, "Firme digitali",
                                   "Salvando così le firme digitali del documento non saranno più valide.\n"
                                   "Vuoi continuare?", QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return False
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            m.save()
        except PermissionError:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Salva", "Impossibile scrivere il file: è aperto in un altro programma o in "
                                               "una cartella protetta. Usa «Salva con nome».")
            return False
        finally:
            if QApplication.overrideCursor():
                QApplication.restoreOverrideCursor()
        self.status(f"Salvato: {m.path}")
        return True

    def save_as(self, model: PdfModel | None = None) -> bool:
        m = model or self._require()
        if model is None and self.view():
            self.view().commit_editor()
        if not self._check_restrictions(m):
            return False
        start = m.path or os.path.join(os.path.dirname(settings.recent_files()[0]) if settings.recent_files()
                                       else os.path.expanduser("~/Documents"), m.title)
        path, _ = QFileDialog.getSaveFileName(self, "Salva con nome", start, PDF_FILTER)
        if not path:
            return False
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        if m.has_signatures() and not m.signatures_preserved_on_save():
            if QMessageBox.warning(self, "Firme digitali", "Le firme digitali non saranno più valide. Continuare?",
                                   QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return False
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            m.save(path)
        finally:
            QApplication.restoreOverrideCursor()
        self.status(f"Salvato: {path}")
        return True

    def save_copy(self):
        m = self._require()
        path, _ = QFileDialog.getSaveFileName(self, "Salva una copia", m.title.replace(".pdf", " - copia.pdf"), PDF_FILTER)
        if path:
            data = m.current_bytes() if m.workpath else m.to_bytes()
            with open(path, "wb") as f:
                f.write(data)
            self.status(f"Copia salvata: {path}")

    def revert(self):
        m = self._require()
        if not m.path:
            return
        if m.modified and QMessageBox.question(self, "Ripristina", "Annullare tutte le modifiche non salvate?") != QMessageBox.Yes:
            return
        i = self.tabs.currentIndex()
        path = m.path
        self.tabs.removeTab(i)
        m.close()
        self._open_one(path)

    def reveal(self):
        m = self._require()
        if m.path:
            import subprocess
            subprocess.Popen(["explorer", "/select,", os.path.normpath(m.path)])

    def close_tab(self, i: int) -> bool:
        if i < 0:
            return True
        tab = self.tabs.widget(i)
        m = tab.model
        tab.view.commit_editor()
        if m.modified:
            self.tabs.setCurrentIndex(i)
            r = QMessageBox.question(self, "Modifiche non salvate", f"Salvare le modifiche a «{m.title}»?",
                                     QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                return False
            if r == QMessageBox.Save and not self.save(m):
                return False
        self.tabs.removeTab(i)
        m.close()
        tab.deleteLater()
        return True

    def close_all(self) -> bool:
        while self.tabs.count():
            if not self.close_tab(self.tabs.count() - 1):
                return False
        return True

    def closeEvent(self, e):
        session = [t.model.path for t in self._tabs() if t.model.path]
        if not self.close_all():
            e.ignore()
            return
        settings.put("session", session)
        settings.put("geometry", self.saveGeometry())
        settings.put("props_visible", self.props_dock.isVisible())
        self.tools.persist()
        e.accept()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        pdfs = [p for p in paths if p.lower().endswith((".pdf", ".p7m"))]
        others = [p for p in paths if p not in pdfs]
        if pdfs:
            self.open_files(pdfs)
        if others:
            prog = self._progress("Conversione in PDF…", len(others))
            for k, p in enumerate(others):
                prog.setValue(k)
                QApplication.processEvents()
                try:
                    d = CV.any_to_pdf(p)
                    self.add_model(PdfModel(data=d.tobytes(), title=Path(p).stem + ".pdf"))
                except Exception as ex:
                    QMessageBox.warning(self, "Conversione", f"{os.path.basename(p)}: {ex}")
            prog.close()

    def _fill_recent(self):
        self.recent_menu.clear()
        files = settings.recent_files()
        for p in files:
            self.recent_menu.addAction(os.path.basename(p), lambda p=p: self.open_files([p])).setToolTip(p)
        if files:
            self.recent_menu.addSeparator()
            self.recent_menu.addAction("Svuota elenco", settings.clear_recent)
        else:
            self.recent_menu.addAction("Nessun file recente").setEnabled(False)

    # ================================================================ stampa
    def print_doc(self):
        m = self._require()
        printing.print_document(self, m, self.view().current)

    def print_preview(self):
        m = self._require()
        printing.print_preview(self, m, self.view().current)

    # ===================================================== utilità comuni
    def _progress(self, text: str, n: int) -> QProgressDialog:
        p = QProgressDialog(text, "Annulla", 0, n, self)
        p.setWindowTitle(APP_NAME)
        p.setWindowModality(Qt.WindowModal)
        p.setMinimumDuration(200)
        p.setValue(0)
        return p

    def _sel_pages(self) -> list[int]:
        t = self.tab()
        thumbs = t.panels["thumbs"]
        if t.current_panel == "thumbs" and len(thumbs.list.selectedItems()) > 1:
            return thumbs.selected_pages()
        return [t.view.current]

    def _pages_field(self, default: str = "tutte"):
        return ("pages", "Pagine", "str", default, {"placeholder": "es. 1-3, 5, 8-fine · tutte · pari · dispari"})

    def _edit_pages(self, label, fn, pages=None, all_pages=False):
        m = self._require()
        if pages is None:
            pages = list(range(m.page_count)) if all_pages else self._sel_pages()
        with m.edit(label, pages):
            fn(m.doc, pages)

    def _edit_struct(self, label, fn):
        m = self._require()
        with m.edit(label, structure=True):
            fn(m.doc)

    # ================================================================ pagine
    def page_action(self, what: str, pages: list[int]):
        m = self._require()
        v = self.view()
        v.commit_editor()
        if what in ("rotate_right", "rotate_left", "rotate_180"):
            ang = {"rotate_right": 90, "rotate_left": -90, "rotate_180": 180}[what]
            with m.edit("Ruota pagine", structure=True):
                PG.rotate_pages(m.doc, pages, ang)
        elif what == "delete":
            if len(pages) >= m.page_count:
                QMessageBox.warning(self, "Elimina pagine", "Non si possono eliminare tutte le pagine.")
                return
            if QMessageBox.question(self, "Elimina pagine",
                                    f"Eliminare {'le pagine ' + format_ranges(pages) if len(pages) > 1 else 'la pagina ' + str(pages[0] + 1)}?") != QMessageBox.Yes:
                return
            with m.edit("Elimina pagine", structure=True):
                PG.delete_pages(m.doc, pages)
        elif what == "duplicate":
            with m.edit("Duplica pagine", structure=True):
                PG.duplicate_pages(m.doc, pages)
        elif what in ("blank_before", "blank_after"):
            at = pages[0] if what == "blank_before" else pages[-1] + 1
            with m.edit("Inserisci pagina", structure=True):
                PG.insert_blank(m.doc, at)
            QTimer.singleShot(50, lambda: v.go_to_page(at))
        elif what == "insert_file":
            self.insert_from_file(pages[-1] + 1)
        elif what == "extract":
            self.extract_pages(pages)
        elif what == "export_images":
            self.export_images(pages)
        elif what == "replace":
            path, _ = QFileDialog.getOpenFileName(self, "Pagine sostitutive", "", D.FILE_FILTER_ALL)
            if not path:
                return
            r = D.ask(self, "Sostituisci pagine", [
                ("src", f"Pagine del file da usare ({len(pages)} richieste)", "str", "1-" + str(len(pages)))])
            if not r:
                return
            with m.edit("Sostituisci pagine", structure=True):
                PG.replace_pages(m.doc, pages, path, r["src"])
        elif what == "crop":
            self.crop_dialog(pages)

    def insert_from_file(self, at: int):
        m = self._require()
        path, _ = QFileDialog.getOpenFileName(self, "Inserisci pagine da file", "", D.FILE_FILTER_ALL)
        if not path:
            return
        r = D.ask(self, "Inserisci pagine", [
            self._pages_field(),
            ("where", "Posizione", "choice", "after",
             [(f"Dopo la pagina corrente ({at})", "after"), ("All'inizio", "start"), ("Alla fine", "end")])])
        if not r:
            return
        pos = {"after": at, "start": 0, "end": m.page_count}[r["where"]]
        ext = Path(path).suffix.lower()
        with m.edit("Inserisci pagine", structure=True):
            if ext == ".pdf":
                n = PG.insert_from_file(m.doc, path, pos, "" if r["pages"] == "tutte" else r["pages"])
            else:
                src = CV.any_to_pdf(path)
                pages = parse_ranges(r["pages"], src.page_count)
                for k, p in enumerate(pages):
                    m.doc.insert_pdf(src, from_page=p, to_page=p, start_at=pos + k)
                n = len(pages)
        self.status(f"Inserite {n} pagine")

    def delete_pages_dialog(self):
        m = self._require()
        r = D.ask(self, "Elimina pagine", [self._pages_field(format_ranges(self._sel_pages()))])
        if r:
            self.page_action("delete", parse_ranges(r["pages"], m.page_count))

    def extract_dialog(self):
        m = self._require()
        r = D.ask(self, "Estrai pagine", [
            self._pages_field(format_ranges(self._sel_pages())),
            ("separate", "Un file per ogni pagina", "bool", False),
            ("delete", "Elimina le pagine dal documento dopo l'estrazione", "bool", False)])
        if not r:
            return
        pages = parse_ranges(r["pages"], m.page_count)
        if r["separate"]:
            d = QFileDialog.getExistingDirectory(self, "Cartella di destinazione")
            if not d:
                return
            base = Path(m.title).stem
            for p in pages:
                out = PG.extract_pages(m.doc, [p])
                out.save(os.path.join(d, f"{base}_pag{p + 1}.pdf"), garbage=3, deflate=True)
            self.status(f"Estratte {len(pages)} pagine in {d}")
        else:
            self.extract_pages(pages, open_after=True)
        if r["delete"] and len(pages) < m.page_count:
            with m.edit("Elimina pagine estratte", structure=True):
                PG.delete_pages(m.doc, pages)

    def extract_pages(self, pages: list[int], open_after: bool = True):
        m = self._require()
        out = PG.extract_pages(m.doc, pages)
        name = f"{Path(m.title).stem}_pagine_{format_ranges(pages).replace(', ', '_')}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Salva pagine estratte", name, PDF_FILTER)
        if not path:
            return
        out.save(path, garbage=3, deflate=True)
        if open_after and QMessageBox.question(self, "Estrai pagine", "Aprire il file creato?") == QMessageBox.Yes:
            self.open_files([path])

    def split(self):
        m = self._require()
        r = D.ask(self, "Dividi documento", [
            ("mode", "Dividi", "choice", "every", [("Ogni N pagine", "every"), ("Per intervalli", "ranges"),
                                                   ("Per segnalibri di primo livello", "bookmarks"),
                                                   ("Per dimensione massima (MB)", "size")]),
            ("n", "N pagine", "int", 1, (1, 10000)),
            ("ranges", "Intervalli (separati da ;)", "str", "1-3; 4-6", {"placeholder": "es. 1-3; 4-10; 11-fine"}),
            ("mb", "Dimensione massima (MB)", "float", 5, (0.1, 2000)),
            ("dir", "Cartella di destinazione", "dir", os.path.dirname(m.path) if m.path else os.path.expanduser("~/Documents"))])
        if not r:
            return
        value = {"every": r["n"], "ranges": r["ranges"], "bookmarks": None, "size": r["mb"]}[r["mode"]]
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            paths = PG.split_document(m.doc, r["mode"], value, r["dir"], Path(m.title).stem)
        finally:
            QApplication.restoreOverrideCursor()
        QMessageBox.information(self, "Dividi documento", f"Creati {len(paths)} file in:\n{r['dir']}")

    def rotate_dialog(self):
        m = self._require()
        r = D.ask(self, "Ruota pagine", [
            self._pages_field(format_ranges(self._sel_pages())),
            ("angle", "Rotazione", "choice", 90, [("90° in senso orario", 90), ("90° in senso antiorario", -90),
                                                 ("180°", 180)])])
        if r:
            pages = parse_ranges(r["pages"], m.page_count)
            with m.edit("Ruota pagine", structure=True):
                PG.rotate_pages(m.doc, pages, r["angle"])

    def crop_dialog(self, pages=None):
        m = self._require()
        r = D.ask(self, "Ritaglia pagine", [
            ("label", "", "label", "Margini da togliere, in millimetri. Per ritagliare un'area precisa usa lo "
                                   "strumento Ritaglia e trascina sulla pagina."),
            ("l", "Sinistra (mm)", "float", 10, (0, 1000)), ("t", "Alto (mm)", "float", 10, (0, 1000)),
            ("rr", "Destra (mm)", "float", 10, (0, 1000)), ("b", "Basso (mm)", "float", 10, (0, 1000)),
            self._pages_field(format_ranges(pages) if pages else "tutte")])
        if not r:
            return
        k = 72 / 25.4
        pg = parse_ranges(r["pages"], m.page_count)
        with m.edit("Ritaglia", structure=True):
            PG.crop_pages(m.doc, pg, margins=(r["l"] * k, r["t"] * k, r["rr"] * k, r["b"] * k))

    def crop_with_rect(self, idx: int, rect):
        m = self._require()
        r = D.ask(self, "Ritaglia", [self._pages_field(str(idx + 1))],
                  intro="Il rettangolo disegnato diventa l'area visibile delle pagine scelte.")
        if not r:
            return
        with m.edit("Ritaglia", structure=True):
            PG.crop_pages(m.doc, parse_ranges(r["pages"], m.page_count), rect=rect)
        self.set_tool("select")

    def resize_pages(self):
        m = self._require()
        r = D.ask(self, "Cambia formato pagine", [
            ("size", "Nuovo formato", "choice", "A4", list(PAPER_SIZES)), self._pages_field(),
            ("label", "", "label", "Il contenuto viene scalato mantenendo le proporzioni.")])
        if not r:
            return
        with m.edit("Cambia formato", structure=True):
            PG.resize_pages(m.doc, parse_ranges(r["pages"], m.page_count), PAPER_SIZES[r["size"]])

    def nup(self):
        m = self._require()
        r = D.ask(self, "Più pagine per foglio", [
            ("n", "Pagine per foglio", "choice", 2, [("2", 2), ("4", 4), ("6", 6), ("9", 9), ("16", 16)]),
            ("size", "Formato del foglio", "choice", "A4", list(PAPER_SIZES))])
        if not r:
            return
        out = PG.n_up(m.doc, r["n"], PAPER_SIZES[r["size"]])
        self.add_model(PdfModel(data=out.tobytes(garbage=3, deflate=True), title=f"{Path(m.title).stem}_{r['n']}xfoglio.pdf"))

    def interleave(self):
        a, _ = QFileDialog.getOpenFileName(self, "File con i FRONTI", "", PDF_FILTER)
        if not a:
            return
        b, _ = QFileDialog.getOpenFileName(self, "File con i RETRI", os.path.dirname(a), PDF_FILTER)
        if not b:
            return
        rev = QMessageBox.question(self, "Fronte/retro", "I retri sono stati scansionati in ordine inverso "
                                                         "(dall'ultimo al primo)?") == QMessageBox.Yes
        out = PG.interleave(pymupdf.open(a), pymupdf.open(b), rev)
        self.add_model(PdfModel(data=out.tobytes(garbage=3, deflate=True), title=Path(a).stem + "_fronte_retro.pdf"))

    def remove_blank(self):
        m = self._require()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            blank = PG.blank_pages(m.doc)
        finally:
            QApplication.restoreOverrideCursor()
        if not blank:
            QMessageBox.information(self, "Pagine vuote", "Non ho trovato pagine vuote.")
            return
        if len(blank) >= m.page_count:
            QMessageBox.information(self, "Pagine vuote", "Tutte le pagine risultano vuote: non elimino nulla.")
            return
        if QMessageBox.question(self, "Pagine vuote", f"Trovate {len(blank)} pagine vuote ({format_ranges(blank)}).\n"
                                                      "Eliminarle?") == QMessageBox.Yes:
            with m.edit("Rimuovi pagine vuote", structure=True):
                PG.delete_pages(m.doc, blank)

    def page_labels(self):
        m = self._require()
        r = D.ask(self, "Etichette delle pagine", [
            ("start", "Dalla pagina", "int", 1, (1, m.page_count)),
            ("style", "Stile", "choice", "D", [("1, 2, 3", "D"), ("i, ii, iii", "r"), ("I, II, III", "R"),
                                               ("a, b, c", "a"), ("A, B, C", "A")]),
            ("prefix", "Prefisso", "str", ""), ("first", "Primo numero", "int", 1, (1, 100000))],
            intro="Le etichette cambiano il numero mostrato per le pagine (es. romani per l'introduzione).")
        if not r:
            return
        try:
            rules = m.doc.get_page_labels() or []
        except Exception:
            rules = []
        rules = [x for x in rules if x.get("startpage") != r["start"] - 1]
        rules.append({"startpage": r["start"] - 1, "prefix": r["prefix"], "style": r["style"],
                      "firstpagenum": r["first"]})
        rules.sort(key=lambda x: x["startpage"])
        with m.edit("Etichette pagine", pages=[]):
            PG.set_page_labels(m.doc, rules)

    # ============================================================ modifica
    def find(self):
        t = self.tab()
        if not t:
            return
        t.show_panel("search")
        sp = t.panels["search"]
        if t.view.sel_text:
            sp.edit.setText(t.view.sel_text.split("\n")[0])
        sp.edit.setFocus()
        sp.edit.selectAll()

    def _quick_search(self):
        t = self.tab()
        if not t:
            return
        t.show_panel("search")
        t.panels["search"].search(self.search_box.text())

    def find_replace(self):
        m = self._require()
        r = D.ask(self, "Trova e sostituisci", [
            ("find", "Trova", "str", self.view().sel_text.split("\n")[0] if self.view().sel_text else ""),
            ("repl", "Sostituisci con", "str", ""), ("case", "Maiuscole/minuscole", "bool", False),
            self._pages_field()],
            intro="Il testo viene sostituito nel contenuto della pagina mantenendo font, corpo e colore.",
            ok_text="Sostituisci tutto")
        if not r or not r["find"]:
            return
        pages = parse_ranges(r["pages"], m.page_count)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            with m.edit("Sostituisci testo", pages):
                n, warn = TE.find_replace(m.doc, r["find"], r["repl"], pages, r["case"])
                m.fonts_inserted = True
        finally:
            QApplication.restoreOverrideCursor()
        if n == 0:
            m.undo()
            m._redo.clear()
            self._update_undo()
            QMessageBox.information(self, "Trova e sostituisci", "Nessuna occorrenza trovata.")
        else:
            QMessageBox.information(self, "Trova e sostituisci", f"Sostituite {n} occorrenze."
                                    + ("\n\n" + "\n".join(warn) if warn else ""))

    def detect_urls(self):
        m = self._require()
        with m.edit("Collegamenti automatici", pages=None):
            n = ST.detect_urls(m.doc)
        self.status(f"Creati {n} collegamenti")

    def remove_links(self):
        m = self._require()
        if QMessageBox.question(self, "Collegamenti", "Rimuovere tutti i collegamenti del documento?") != QMessageBox.Yes:
            return
        with m.edit("Rimuovi collegamenti", pages=None):
            for page in m.doc:
                for l in page.get_links():
                    page.delete_link(l)

    def create_link(self, idx: int, rect):
        m = self._require()
        r = D.ask(self, "Nuovo collegamento", [
            ("kind", "Destinazione", "choice", "page", [("Pagina del documento", "page"), ("Indirizzo web", "uri")]),
            ("page", "Numero di pagina", "int", min(idx + 2, m.page_count), (1, m.page_count)),
            ("uri", "Indirizzo", "str", "https://")])
        if not r:
            return
        with m.edit("Collegamento", [idx]):
            if r["kind"] == "uri":
                ST.add_link(m.page(idx), rect, uri=r["uri"].strip())
            else:
                ST.add_link(m.page(idx), rect, page_target=r["page"] - 1)
        self.status("Collegamento creato")

    def insert_image_at(self, idx: int, rect, from_click: bool):
        m = self._require()
        path, _ = QFileDialog.getOpenFileName(self, "Inserisci immagine", "",
                                              "Immagini (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff *.webp)")
        if not path:
            return
        page = m.page(idx)
        if from_click or rect.width < 5:
            from PySide6.QtGui import QImageReader
            sz = QImageReader(path).size()
            w, h = sz.width() * 0.75, sz.height() * 0.75
            k = min(1.0, page.rect.width * 0.6 / max(w, 1), page.rect.height * 0.6 / max(h, 1))
            rect = pymupdf.Rect(rect.x0, rect.y0, rect.x0 + w * k, rect.y0 + h * k)
        with m.edit("Inserisci immagine", [idx]):
            IM.insert_image(m.page(idx), rect, path=path)
        self.view()._tool_done()

    def _stamp_common(self, title: str, extra: list) -> dict | None:
        m = self._require()
        return D.ask(self, title, extra + [self._pages_field()])

    def watermark(self):
        m = self._require()
        r = D.ask(self, "Filigrana", [
            ("kind", "Tipo", "choice", "text", [("Testo", "text"), ("Immagine", "image")]),
            ("text", "Testo", "text", "RISERVATO"),
            ("image", "Immagine", "open", "", "Immagini (*.png *.jpg *.jpeg *.bmp)"),
            ("font", "Carattere", "choice", "Helvetica grassetto", list(ST.BASE_FONTS)),
            ("size", "Corpo (pt)", "float", 72, (4, 500)), ("color", "Colore", "color", "#c62828"),
            ("opacity", "Opacità (%)", "slider", 25, (5, 100)), ("rotation", "Rotazione (°)", "int", 45, (-180, 180)),
            ("position", "Posizione", "choice", "centro", [("Centro", "centro"), ("Alto", "alto"), ("Basso", "basso")]),
            ("behind", "Dietro al contenuto", "bool", False), self._pages_field()])
        if not r:
            return
        pages = parse_ranges(r["pages"], m.page_count)
        with m.edit("Filigrana", pages):
            if r["kind"] == "image":
                if not os.path.exists(r["image"]):
                    raise ValueError("Scegli un'immagine per la filigrana")
                ST.watermark_image(m.doc, pages, r["image"], r["opacity"] / 100, r["rotation"], not r["behind"],
                                   r["position"])
            else:
                ST.watermark_text(m.doc, pages, r["text"], r["font"], r["size"], r["color"], r["opacity"] / 100,
                                  r["rotation"], not r["behind"], r["position"])

    def background(self):
        m = self._require()
        r = D.ask(self, "Sfondo", [
            ("kind", "Tipo", "choice", "color", [("Colore", "color"), ("Immagine", "image")]),
            ("color", "Colore", "color", "#fff8e1"), ("image", "Immagine", "open", "", "Immagini (*.png *.jpg *.jpeg)"),
            ("opacity", "Opacità (%)", "slider", 100, (5, 100)), self._pages_field()])
        if not r:
            return
        pages = parse_ranges(r["pages"], m.page_count)
        with m.edit("Sfondo", pages):
            if r["kind"] == "image":
                ST.background(m.doc, pages, image=r["image"])
            else:
                ST.background(m.doc, pages, color=r["color"], opacity=r["opacity"] / 100)

    def header_footer(self):
        m = self._require()
        r = D.ask(self, "Intestazione e piè di pagina", [
            ("label", "", "label", "Segnaposto: {n} pagina, {N} totale pagine, {data}, {ora}, {file}"),
            ("alto-sinistra", "Alto a sinistra", "str", ""), ("alto-centro", "Alto al centro", "str", ""),
            ("alto-destra", "Alto a destra", "str", ""), ("basso-sinistra", "Basso a sinistra", "str", ""),
            ("basso-centro", "Basso al centro", "str", "Pagina {n} di {N}"),
            ("basso-destra", "Basso a destra", "str", ""),
            ("font", "Carattere", "choice", "Helvetica", list(ST.BASE_FONTS)), ("size", "Corpo (pt)", "float", 9, (4, 72)),
            ("color", "Colore", "color", "#333333"), ("mx", "Margine laterale (mm)", "float", 15, (0, 200)),
            ("my", "Margine alto/basso (mm)", "float", 10, (0, 200)), ("start", "Numera da", "int", 1, (0, 100000)),
            self._pages_field()], width=520)
        if not r:
            return
        pages = parse_ranges(r["pages"], m.page_count)
        items = {k: r[k] for k in ST.POSITIONS}
        k = 72 / 25.4
        with m.edit("Intestazione e piè di pagina", pages):
            ST.header_footer(m.doc, pages, items, r["font"], r["size"], r["color"], r["mx"] * k, r["my"] * k,
                             r["start"], m.title)

    def page_numbers(self):
        m = self._require()
        r = D.ask(self, "Numeri di pagina", [
            ("template", "Formato", "choice", "Pagina {n} di {N}",
             ["Pagina {n} di {N}", "{n}", "{n} / {N}", "- {n} -", "Pag. {n}"]),
            ("position", "Posizione", "choice", "basso-centro", ST.POSITIONS),
            ("font", "Carattere", "choice", "Helvetica", list(ST.BASE_FONTS)), ("size", "Corpo (pt)", "float", 10, (4, 72)),
            ("color", "Colore", "color", "#000000"), ("start", "Primo numero", "int", 1, (0, 100000)),
            self._pages_field()])
        if not r:
            return
        pages = parse_ranges(r["pages"], m.page_count)
        with m.edit("Numeri di pagina", pages):
            ST.page_numbers(m.doc, pages, r["template"], r["position"], r["font"], r["size"], r["color"], r["start"])

    def bates(self):
        m = self._require()
        r = D.ask(self, "Numerazione Bates", [
            ("prefix", "Prefisso", "str", "DOC-"), ("suffix", "Suffisso", "str", ""),
            ("start", "Numero iniziale", "int", 1, (0, 10 ** 9)), ("digits", "Cifre", "int", 6, (1, 12)),
            ("position", "Posizione", "choice", "basso-destra", ST.POSITIONS),
            ("font", "Carattere", "choice", "Helvetica", list(ST.BASE_FONTS)), ("size", "Corpo (pt)", "float", 9, (4, 72)),
            ("color", "Colore", "color", "#000000"), self._pages_field()])
        if not r:
            return
        pages = parse_ranges(r["pages"], m.page_count)
        with m.edit("Numerazione Bates", pages):
            rng = ST.bates(m.doc, pages, r["prefix"], r["suffix"], r["start"], r["digits"], r["position"], r["font"],
                           r["size"], r["color"])
        self.status(f"Numerazione Bates applicata: {rng}")

    # ============================================================ commenti
    def annot_properties(self, idx: int, xref: int):
        m = self._require()
        page = m.page(idx)
        a = A.annot_by_xref(page, xref)
        if a is None:
            return
        p = A.annot_props(a)
        fields = [("label", "", "label", f"{p['type_name']} · pagina {idx + 1}"),
                  ("content", "Testo / commento", "text", p["content"]), ("author", "Autore", "str", p["author"]),
                  ("subject", "Oggetto", "str", p["subject"])]
        t = p["type"]
        if t not in (pymupdf.PDF_ANNOT_STAMP, pymupdf.PDF_ANNOT_FILE_ATTACHMENT):
            fields.append(("color", "Colore", "color", p["color"] or "#000000"))
        if t in (pymupdf.PDF_ANNOT_SQUARE, pymupdf.PDF_ANNOT_CIRCLE, pymupdf.PDF_ANNOT_POLYGON, pymupdf.PDF_ANNOT_FREE_TEXT):
            fields.append(("fill", "Riempimento", "color_none", p["fill"]))
        if t in (pymupdf.PDF_ANNOT_LINE, pymupdf.PDF_ANNOT_SQUARE, pymupdf.PDF_ANNOT_CIRCLE, pymupdf.PDF_ANNOT_POLYGON,
                 pymupdf.PDF_ANNOT_POLY_LINE, pymupdf.PDF_ANNOT_INK, pymupdf.PDF_ANNOT_FREE_TEXT):
            fields.append(("width", "Spessore (pt)", "float", p["width"], (0, 50)))
        fields.append(("opacity", "Opacità (%)", "slider", int(p["opacity"] * 100), (5, 100)))
        fields.append(("locked", "Blocca (non spostabile)", "bool", p["locked"]))
        r = D.ask(self, "Proprietà annotazione", fields)
        if not r:
            return
        r["opacity"] = r["opacity"] / 100
        if t == pymupdf.PDF_ANNOT_FREE_TEXT:
            r["text_color"] = r.get("color")
        with m.edit("Proprietà annotazione", [idx]):
            page = m.page(idx)  # la pagina deve restare in vita finché si usa l'annotazione
            a = A.annot_by_xref(page, xref)
            A.set_annot_props(a, r)

    def comments_summary(self):
        m = self._require()
        html = A.comments_summary_html(m.doc, m.title)
        D.ReportDialog(self, "Riepilogo commenti", html, Path(m.title).stem + "_commenti.html").exec()

    def delete_all_comments(self):
        m = self._require()
        if QMessageBox.question(self, "Commenti", "Eliminare tutti i commenti e le annotazioni del documento?") != QMessageBox.Yes:
            return
        with m.edit("Elimina commenti", pages=None):
            n = A.delete_all_annots(m.doc)
        self.status(f"Eliminate {n} annotazioni")

    def flatten_annots(self):
        m = self._require()
        if QMessageBox.question(self, "Appiattisci", "Rendere i commenti parte fissa delle pagine?\n"
                                                     "Non saranno più modificabili.") != QMessageBox.Yes:
            return
        with m.edit("Appiattisci commenti", pages=None):
            A.flatten(m.doc, annots=True, widgets=False)

    def choose_signature(self):
        d = D.SignaturePicker(self)
        if d.exec() == QDialog.Accepted and d.path():
            self.tools.signature_path = d.path()
            self.tools.persist()
            self.props._sig_preview()
            return True
        return False

    def place_signature(self, idx: int, rect):
        m = self._require()
        p = self.tools.signature_path
        if not (p and os.path.exists(p)):
            if not self.choose_signature():
                return
            p = self.tools.signature_path
        from PySide6.QtGui import QImageReader
        sz = QImageReader(p).size()
        ratio = sz.width() / max(1, sz.height())
        w = rect.width
        h = w / ratio
        if h > rect.height:
            h = rect.height
            w = h * ratio
        r = pymupdf.Rect(rect.x0, rect.y0, rect.x0 + w, rect.y0 + h)
        with m.edit("Firma autografa", [idx]):
            IM.insert_image(m.page(idx), r, path=p)
        self.view()._tool_done()
        self.status("Firma inserita. Con «Modifica oggetti» puoi spostarla o ridimensionarla.")

    # =============================================================== moduli
    def create_form_field(self, kind: str, idx: int, rect):
        m = self._require()
        base = {"text": "testo", "checkbox": "casella", "radio": "scelta", "combobox": "elenco",
                "listbox": "riepilogo", "signature": "firma", "button": "pulsante"}[kind]
        fields = [("name", "Nome del campo", "str", F.unique_name(m.doc, base)),
                  ("tooltip", "Descrizione (suggerimento)", "str", ""), ("required", "Obbligatorio", "bool", False)]
        if kind == "text":
            fields += [("value", "Valore iniziale", "str", ""), ("multiline", "Più righe", "bool", False),
                       ("maxlen", "Lunghezza massima (0 = nessuna)", "int", 0, (0, 10000)),
                       ("fontsize", "Corpo (0 = automatico)", "float", 0, (0, 72))]
        if kind in ("combobox", "listbox"):
            fields += [("choices", "Opzioni (una per riga)", "text", "Opzione 1\nOpzione 2\nOpzione 3")]
        if kind == "radio":
            fields[0] = ("name", "Nome del gruppo (uguale per le scelte alternative)", "str", base)
        if kind == "button":
            fields += [("value", "Etichetta", "str", "Pulsante")]
        r = D.ask(self, "Nuovo campo – " + F.FIELD_TYPES[kind][1], fields)
        if not r or not r["name"].strip():
            return
        with m.edit("Nuovo campo", [idx]):
            F.create_field(m.page(idx), kind, rect, r["name"].strip(), value=r.get("value", ""),
                           choices=[c for c in r.get("choices", "").splitlines() if c.strip()],
                           tooltip=r["tooltip"], required=r["required"], multiline=r.get("multiline", False),
                           fontsize=r.get("fontsize", 0), max_len=r.get("maxlen", 0))
        self.view()._tool_done()

    def form_detect(self):
        m = self._require()
        with m.edit("Riconosci campi", pages=None):
            n = F.auto_detect_fields(m.doc)
        QMessageBox.information(self, "Riconosci campi", f"Creati {n} campi di testo." if n else
                                "Non ho trovato righe o spazi da compilare.")

    def form_export(self):
        m = self._require()
        path, _ = QFileDialog.getSaveFileName(self, "Esporta dati modulo", Path(m.title).stem + "_dati.json", "JSON (*.json)")
        if path:
            n = F.export_data(m.doc, path)
            self.status(f"Esportati {n} campi")

    def form_import(self):
        m = self._require()
        path, _ = QFileDialog.getOpenFileName(self, "Importa dati modulo", "", "JSON (*.json)")
        if path:
            with m.edit("Importa dati modulo", pages=None):
                n = F.import_data(m.doc, path)
            self.status(f"Compilati {n} campi")

    def form_reset(self):
        m = self._require()
        if QMessageBox.question(self, "Svuota modulo", "Cancellare i valori di tutti i campi?") == QMessageBox.Yes:
            with m.edit("Svuota modulo", pages=None):
                F.reset_form(m.doc)

    def form_flatten(self):
        m = self._require()
        if QMessageBox.question(self, "Appiattisci modulo", "Trasformare i campi in testo fisso?\n"
                                                            "Non saranno più compilabili.") == QMessageBox.Yes:
            with m.edit("Appiattisci modulo", pages=None):
                A.flatten(m.doc, annots=False, widgets=True)

    def form_list(self):
        m = self._require()
        rows = F.all_fields(m.doc)
        import html
        body = "".join(f"<tr><td>{r['page'] + 1}</td><td>{html.escape(r['name'] or '')}</td><td>{r['type']}</td>"
                       f"<td>{html.escape(str(r['value']))}</td></tr>" for r in rows)
        D.ReportDialog(self, "Campi del modulo",
                       f"<h3>{len(rows)} campi</h3><table border='1' cellspacing='0' cellpadding='4' width='100%'>"
                       "<tr><th>Pag.</th><th>Nome</th><th>Tipo</th><th>Valore</th></tr>" + body + "</table>").exec()

    def toggle_fields(self):
        on = self.actions["highlight_fields"].isChecked()
        settings.put("highlight_fields", on)
        for t in self._tabs():
            t.view.highlight_fields = on
            t.view.viewport().update()

    # ============================================================ protezione
    def encrypt(self):
        m = self._require()
        d = D.EncryptDialog(self)
        if d.exec() != QDialog.Accepted:
            return
        m.encryption = d.result_options()
        m._set_modified(True)
        if m.has_signatures():
            QMessageBox.information(self, "Firme", "La protezione con password invaliderà le firme digitali esistenti.")
        if QMessageBox.question(self, "Proteggi", "Protezione pronta. Salvare ora il documento?") == QMessageBox.Yes:
            self.save()

    def decrypt(self):
        m = self._require()
        if not m.doc.is_encrypted and not m.doc.metadata.get("encryption"):
            QMessageBox.information(self, "Protezione", "Il documento non è protetto.")
            return
        if not (m.doc.permissions & pymupdf.PDF_PERM_MODIFY):
            pw, ok = QInputDialog.getText(self, "Rimuovi protezione", "Password dei permessi:", QLineEdit.Password)
            if not ok:
                return
            if m.doc.authenticate(pw) < 4 and not (m.doc.permissions & pymupdf.PDF_PERM_MODIFY):
                QMessageBox.warning(self, "Password errata", "La password non è corretta.")
                return
        m.encryption = {"remove": True}
        m._set_modified(True)
        if QMessageBox.question(self, "Protezione", "La protezione verrà rimossa al salvataggio. Salvare ora?") == QMessageBox.Yes:
            self.save()

    def redact_search(self):
        m = self._require()
        fields = [("text", "Parola o frase", "str", "")]
        for name in SEC.PATTERNS:
            fields.append(("p_" + name, name, "bool", False))
        fields += [("case", "Maiuscole/minuscole", "bool", False), ("overlay", "Testo sopra l'area oscurata", "str", ""),
                   ("fill", "Colore", "color", "#000000"), self._pages_field()]
        r = D.ask(self, "Cerca e redigi", fields, intro="Trova il testo da oscurare. Le aree vengono contrassegnate: "
                  "controllale e poi usa «Applica redazioni» per eliminarle definitivamente.", ok_text="Contrassegna")
        if not r:
            return
        pages = parse_ranges(r["pages"], m.page_count)
        hits = []
        if r["text"].strip():
            hits += SEC.find_pattern(m.doc, r["text"].strip(), pages, regex=False, match_case=r["case"])
        for name, pat in SEC.PATTERNS.items():
            if r["p_" + name]:
                hits += SEC.find_pattern(m.doc, pat, pages, regex=True)
        if not hits:
            QMessageBox.information(self, "Cerca e redigi", "Nessuna occorrenza trovata.")
            return
        with m.edit("Contrassegna redazioni", sorted({h[0] for h in hits})):
            SEC.mark_redactions(m.doc, hits, r["fill"], r["overlay"])
        QMessageBox.information(self, "Cerca e redigi", f"Contrassegnate {len(hits)} aree.\n"
                                "Controllale nel documento e poi scegli Proteggi › Applica redazioni.")

    def apply_redactions(self):
        m = self._require()
        n = SEC.pending_redactions(m.doc)
        if not n:
            QMessageBox.information(self, "Redazione", "Non ci sono aree contrassegnate.\nUsa lo strumento Redazione "
                                                       "o «Cerca e redigi».")
            return
        if QMessageBox.warning(self, "Applica redazioni", f"Il contenuto sotto {n} aree verrà eliminato "
                               "definitivamente (testo, immagini e grafica). Continuare?",
                               QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        with m.edit("Applica redazioni", pages=None):
            SEC.apply_redactions(m.doc)
        self.status(f"Applicate {n} redazioni")

    def sanitize(self):
        m = self._require()
        r = D.ask(self, "Rimuovi informazioni nascoste", [
            ("metadata", "Metadati (autore, titolo, programmi)", "bool", True),
            ("javascript", "JavaScript", "bool", True), ("embedded_files", "File allegati", "bool", True),
            ("hidden_text", "Testo nascosto", "bool", True), ("thumbnails", "Miniature incorporate", "bool", True),
            ("xml_metadata", "Metadati XMP", "bool", True), ("comments", "Commenti e annotazioni", "bool", False),
            ("links", "Collegamenti", "bool", False), ("reset_fields", "Valori dei moduli", "bool", False)],
            ok_text="Rimuovi")
        if not r:
            return
        with m.edit("Rimuovi informazioni nascoste", pages=None):
            SEC.sanitize(m.doc, **r)
        self.status("Informazioni nascoste rimosse")

    def sign_digital(self, idx: int | None, rect, field_name: str | None = None):
        from .ops import signatures as SG
        m = self._require()
        if m.doc.is_encrypted or m.encryption:
            QMessageBox.warning(self, "Firma digitale", "Rimuovi prima la protezione con password, poi firma.")
            return
        last = settings.get("last_pfx", "")
        r = D.ask(self, "Firma con certificato digitale", [
            ("pfx", "Certificato (.pfx / .p12)", "open", last, "Certificati (*.pfx *.p12)"),
            ("pw", "Password del certificato", "str", "", {"password": True}),
            ("reason", "Motivo", "str", "Approvo il documento"), ("location", "Luogo", "str", ""),
            ("contact", "Contatto", "str", ""), ("text", "Mostra nome e data nella firma", "bool", True),
            ("image", "Includi la firma autografa salvata", "bool", bool(self.tools.signature_path)),
            ("label", "", "label", "Non hai un certificato? Proteggi › Crea ID digitale. Per firme con valore legale "
                                   "serve un certificato qualificato rilasciato da un ente certificatore.")],
            ok_text="Firma")
        if not r:
            return
        if not os.path.exists(r["pfx"]):
            QMessageBox.warning(self, "Firma digitale", "Scegli il file del certificato.")
            return
        settings.put("last_pfx", r["pfx"])
        default = (m.path or m.title).replace(".pdf", "") + "_firmato.pdf"
        out, _ = QFileDialog.getSaveFileName(self, "Salva documento firmato", default, PDF_FILTER)
        if not out:
            return
        if m.has_signatures() and m.modified and not m.signatures_preserved_on_save():
            if QMessageBox.warning(self, "Firma", "Le modifiche fatte invalideranno le firme precedenti. Continuare?",
                                   QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
                return
        data = m.current_bytes()
        names = {w.field_name for p in m.doc for w in p.widgets()}
        name = field_name or next(f"Firma{i}" for i in range(1, 1000) if f"Firma{i}" not in names)
        page_h = m.page(idx).mediabox.height if idx is not None else 0
        img = self.tools.signature_path if r["image"] and self.tools.signature_path and os.path.exists(self.tools.signature_path) else None
        req = SG.SignRequest(r["pfx"], r["pw"], name, idx or 0, tuple(rect) if rect is not None else None,
                             r["reason"], r["location"], r["contact"], r["text"], img)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            signed = SG.sign_pdf(data, req, page_h, existing_field=field_name is not None)
        finally:
            QApplication.restoreOverrideCursor()
        with open(out, "wb") as f:
            f.write(signed)
        m.reload_from_bytes(signed, out)
        self._update_title(self.tab())
        self.tab().show_panel("signatures")
        self.tab().panels["signatures"].verify()
        settings.add_recent(out)
        self.set_tool("select")
        QMessageBox.information(self, "Firma digitale", f"Documento firmato e salvato:\n{out}")

    def sign_existing_field(self, name: str):
        from .ops import signatures as SG
        m = self._require()
        filled = {s.field for s in SG.verify_pdf(m.current_bytes())} if m.has_signatures() else set()
        if name in filled:
            self.tab().show_panel("signatures")
            return
        if QMessageBox.question(self, "Campo firma", f"Firmare digitalmente nel campo «{name}»?") == QMessageBox.Yes:
            self.sign_digital(None, None, field_name=name)

    def create_digital_id(self):
        from .ops import signatures as SG
        r = D.ask(self, "Crea ID digitale", [
            ("name", "Nome e cognome", "str", self.tools.author), ("email", "E-mail", "str", ""),
            ("org", "Organizzazione", "str", ""), ("country", "Paese (2 lettere)", "str", "IT"),
            ("years", "Validità (anni)", "int", 5, (1, 30)), ("pw", "Password", "str", "", {"password": True}),
            ("pw2", "Conferma password", "str", "", {"password": True}),
            ("path", "Salva in", "save", os.path.join(settings.app_data_dir("id_digitali"), "mio_id.pfx"),
             "Certificati (*.pfx)"),
            ("label", "", "label", "Un ID autofirmato va bene per uso personale o interno; chi riceve il file lo "
                                   "vedrà come 'identità non verificata' finché non lo considera attendibile.")])
        if not r:
            return
        if not r["name"].strip() or len(r["pw"]) < 4 or r["pw"] != r["pw2"]:
            QMessageBox.warning(self, "ID digitale", "Inserisci il nome e una password di almeno 4 caratteri, "
                                                     "uguale nei due campi.")
            return
        SG.create_self_signed_id(r["path"], r["pw"], r["name"].strip(), r["email"], r["org"], r["country"], r["years"])
        settings.put("last_pfx", r["path"])
        QMessageBox.information(self, "ID digitale", f"ID digitale creato:\n{r['path']}\n\nConserva la password: "
                                "senza non potrai firmare.")

    def show_trusted(self):
        from .ops import signatures as SG
        d = SG._trust_dir()
        files = os.listdir(d)
        QMessageBox.information(self, "Certificati attendibili",
                                (f"{len(files)} certificati scelti da te:\n" + "\n".join(files) if files else
                                 "Nessun certificato aggiunto.") +
                                "\n\nVengono considerati attendibili anche i certificati radice di Windows.\n"
                                f"Cartella: {d}")
        os.startfile(d)

    # ============================================================ strumenti
    def _ocr_on(self, m: PdfModel):
        from .ops import ocr as O
        if not O.available():
            QMessageBox.warning(self, "OCR", "Il riconoscimento del testo di Windows non è disponibile su questo PC.")
            return False
        langs = O.languages()
        if not langs:
            QMessageBox.warning(self, "OCR", "Nessuna lingua OCR installata in Windows.\n"
                                             "Impostazioni › Ora e lingua › Lingua: aggiungi una lingua.")
            return False
        r = D.ask(self, "Riconosci testo (OCR)", [
            ("lang", "Lingua", "choice", langs[0][0], [(n, t) for t, n in langs]),
            ("which", "Pagine", "choice", "needed", [("Solo le pagine senza testo", "needed"), ("Tutte", "all"),
                                                    ("Intervallo…", "range")]),
            ("range", "Intervallo", "str", "1-" + str(m.page_count)),
            ("dpi", "Risoluzione di lettura", "choice", 300, [("200 dpi (veloce)", 200), ("300 dpi", 300),
                                                             ("400 dpi (testi piccoli)", 400)])],
            intro="Il testo riconosciuto viene aggiunto invisibile sotto l'immagine: la pagina resta identica ma "
                  "diventa ricercabile e copiabile. Motore OCR di Windows, nessun dato lascia il PC.")
        if not r:
            return False
        if r["which"] == "range":
            pages = parse_ranges(r["range"], m.page_count)
        elif r["which"] == "all":
            pages = list(range(m.page_count))
        else:
            pages = [i for i in range(m.page_count) if not m.page(i).get_text().strip()]
            if not pages:
                QMessageBox.information(self, "OCR", "Tutte le pagine contengono già testo.")
                return False
        prog = self._progress("Riconoscimento del testo…", len(pages))
        words = 0
        try:
            with m.edit("OCR", pages):
                for k, p in enumerate(pages):
                    prog.setLabelText(f"Pagina {p + 1} ({k + 1} di {len(pages)})…")
                    prog.setValue(k)
                    QApplication.processEvents()
                    if prog.wasCanceled():
                        break
                    words += O.ocr_page(m.page(p), r["lang"], r["dpi"])
                m.fonts_inserted = True
        finally:
            prog.close()
        self.status(f"OCR completato: {words} parole riconosciute")
        return True

    def ocr(self):
        self._ocr_on(self._require())

    def ocr_file(self):
        self.open_dialog()
        if self.model():
            self.ocr()

    def compress(self):
        m = self._require()
        before = len(m.current_bytes())
        d = D.CompressDialog(self, before)
        if d.exec() != QDialog.Accepted:
            return
        opt = d.options()
        prog = self._progress("Compressione…", 0)
        prog.setCancelButton(None)
        QApplication.processEvents()
        try:
            data = CMP.compress(m.current_bytes(), opt, m.password,
                                progress=lambda t: (prog.setLabelText(t + "…"), QApplication.processEvents()))
        finally:
            prog.close()
        after = len(data)
        if after >= before:
            QMessageBox.information(self, "Riduci dimensione", f"Il file è già ottimizzato: {human_size(before)} → "
                                    f"{human_size(after)}. Nessuna modifica.")
            return
        m.replace_document(data, "Riduci dimensione")
        QMessageBox.information(self, "Riduci dimensione",
                                f"Da {human_size(before)} a {human_size(after)} (−{(1 - after / before) * 100:.0f}%).\n"
                                "Salva il documento per mantenere il risultato.")

    def compress_file(self):
        self.open_dialog()
        if self.model():
            self.compress()

    def compare(self):
        cur = self.model()
        a = cur.path if cur and cur.path else ""
        r = D.ask(self, "Confronta documenti", [
            ("a", "Documento A (vecchio)", "open", a, PDF_FILTER), ("b", "Documento B (nuovo)", "open", "", PDF_FILTER),
            ("annotate", "Apri le due versioni con le differenze evidenziate", "bool", True)], ok_text="Confronta")
        if not r:
            return
        if not (os.path.exists(r["a"]) and os.path.exists(r["b"])):
            QMessageBox.warning(self, "Confronta", "Scegli entrambi i file.")
            return
        from .ops import compare as CP
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            da, db = pymupdf.open(r["a"]), pymupdf.open(r["b"])
            diffs = CP.compare(da, db)
            html = CP.report_html(diffs, os.path.basename(r["a"]), os.path.basename(r["b"]))
            if r["annotate"]:
                CP.annotate(da, db, diffs)
        finally:
            QApplication.restoreOverrideCursor()
        if r["annotate"]:
            self.add_model(PdfModel(data=da.tobytes(), title="A - " + os.path.basename(r["a"])))
            self.add_model(PdfModel(data=db.tobytes(), title="B - " + os.path.basename(r["b"])))
        D.ReportDialog(self, "Confronto documenti", html, "confronto.html").exec()

    def extract_images(self):
        m = self._require()
        d = QFileDialog.getExistingDirectory(self, "Cartella in cui salvare le immagini")
        if not d:
            return
        paths = IM.extract_all_images(m.doc, d)
        QMessageBox.information(self, "Estrai immagini", f"Salvate {len(paths)} immagini in:\n{d}")

    def properties(self):
        m = self._require()
        d = D.PropertiesDialog(self, m)
        if d.exec() == QDialog.Accepted:
            vals = d.values()
            md = m.doc.metadata or {}
            if any((md.get(k) or "") != v for k, v in vals.items()):
                with m.edit("Proprietà documento", pages=[]):
                    SEC.set_metadata(m.doc, vals)

    # =============================================================== export
    def _export_path(self, ext: str, filt: str) -> str | None:
        m = self._require()
        base = os.path.splitext(m.path or m.title)[0] + "." + ext
        p, _ = QFileDialog.getSaveFileName(self, "Esporta", base, filt)
        return p or None

    def export_word(self):
        m = self._require()
        path = self._export_path("docx", "Documento Word (*.docx)")
        if not path:
            return
        data = m.current_bytes()
        prog = self._progress("Conversione in Word… (può richiedere qualche minuto)", 0)
        prog.setCancelButton(None)
        w = Worker(CV.to_word, data, path)

        def done(res, err):
            prog.close()
            if err:
                QMessageBox.warning(self, "Esporta in Word", f"Conversione non riuscita: {err}")
            elif QMessageBox.question(self, "Esporta in Word", f"Creato:\n{path}\n\nAprirlo?") == QMessageBox.Yes:
                os.startfile(path)
        w.done.connect(done)
        self._worker = w
        w.start()

    def export_excel(self):
        m = self._require()
        path = self._export_path("xlsx", "Cartella Excel (*.xlsx)")
        if not path:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            n = CV.to_excel(m.doc, path)
        finally:
            QApplication.restoreOverrideCursor()
        msg = f"Esportate {n} tabelle." if n else "Nessuna tabella riconosciuta: esportato il testo riga per riga."
        if QMessageBox.question(self, "Esporta in Excel", msg + f"\n{path}\n\nAprirlo?") == QMessageBox.Yes:
            os.startfile(path)

    def export_images(self, pages=None):
        m = self._require()
        r = D.ask(self, "Esporta come immagini", [
            ("fmt", "Formato", "choice", "png", [("PNG", "png"), ("JPEG", "jpg"), ("TIFF", "tiff"), ("WEBP", "webp"),
                                                 ("BMP", "bmp")]),
            ("dpi", "Risoluzione (dpi)", "int", 150, (36, 1200)),
            self._pages_field(format_ranges(pages) if pages else "tutte"),
            ("dir", "Cartella", "dir", os.path.dirname(m.path) if m.path else os.path.expanduser("~/Pictures"))])
        if not r:
            return
        pg = parse_ranges(r["pages"], m.page_count)
        prog = self._progress("Esportazione immagini…", len(pg))

        def step(k, n):
            prog.setValue(k)
            QApplication.processEvents()
            return not prog.wasCanceled()
        try:
            paths = CV.to_images(m.doc, pg, r["dir"], Path(m.title).stem, r["fmt"], r["dpi"], step)
        finally:
            prog.close()
        self.status(f"Esportate {len(paths)} immagini in {r['dir']}")

    def export_simple(self, kind: str):
        m = self._require()
        filt = {"txt": "Testo (*.txt)", "html": "Pagina web (*.html)", "md": "Markdown (*.md)"}[kind]
        path = self._export_path(kind, filt)
        if not path:
            return
        {"txt": CV.to_text, "html": CV.to_html, "md": CV.to_markdown}[kind](m.doc, path)
        self.status(f"Esportato: {path}")

    # ========================================================== visualizza
    def goto_page(self):
        m = self._require()
        n, ok = QInputDialog.getInt(self, "Vai alla pagina", f"Pagina (1–{m.page_count}):", self.view().current + 1,
                                    1, m.page_count)
        if ok:
            self.view().go_to_page(n - 1)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self._chrome(True)
        else:
            self._chrome(False)
            self.showFullScreen()
            self.status("Esc per uscire dallo schermo intero")

    def _chrome(self, visible: bool):
        self.menuBar().setVisible(visible)
        self.topbar.setVisible(visible)
        self.strip.setVisible(visible)
        self.statusBar().setVisible(visible)
        if not visible:
            self._props_was = self.props_dock.isVisible()
            self.props_dock.hide()
        elif getattr(self, "_props_was", True):
            self.props_dock.show()
        t = self.tab()
        if t:
            t.rail.setVisible(visible)
            if not visible:
                t.hide_panels()
        self.tabs.tabBar().setVisible(visible)

    def toggle_reading(self):
        self._chrome(not self.actions["reading"].isChecked())
        if self.view():
            QTimer.singleShot(50, lambda: self.view().set_fit(self.view().fit_mode or "width"))

    def presentation(self):
        v = self.view()
        if not v:
            return
        self._chrome(False)
        self.showFullScreen()
        v.set_layout("single")
        v.set_fit("page")
        self.status("Presentazione: frecce o spazio per avanzare, Esc per uscire")

    def toggle_night(self):
        v = self.view()
        if v:
            v.set_night(self.actions["night"].isChecked())

    def toggle_theme(self):
        mode = "dark" if self.actions["dark_theme"].isChecked() else "light"
        settings.put("theme", mode)
        self.apply_theme(mode)

    def apply_theme(self, mode: str):
        theme.apply(QApplication.instance(), mode)
        self.actions["dark_theme"].blockSignals(True)
        self.actions["dark_theme"].setChecked(theme.is_dark())
        self.actions["dark_theme"].blockSignals(False)
        # ricolora le icone
        for key, a in self.actions.items():
            name = None
            if key.startswith("tool_"):
                name = TOOL_ICONS.get(key[5:])
            if name:
                a.setIcon(icons.icon(name))
        self._recolor_icons()
        for b in self.findChildren(QToolButton):
            name = b.property("icon_name")
            if name:
                b.setIcon(icons.icon(name))
        self.search_box.actions()[0].setIcon(icons.icon("search")) if self.search_box.actions() else None
        self.strip.setStyleSheet(f"QFrame#strip {{ border-bottom: 1px solid {theme.current['border']}; }}")
        for t in self._tabs():
            t.view.viewport().update()

    def _recolor_icons(self):
        mapping = getattr(self, "_icon_names", None)
        if mapping is None:
            return
        for key, name in mapping.items():
            if key in self.actions:
                self.actions[key].setIcon(icons.icon(name))

    def toggle_panels(self):
        t = self.tab()
        if t:
            if t.side.isVisible():
                t.hide_panels()
            else:
                t.show_panel(t.current_panel or "thumbs")

    def read_aloud(self):
        m = self._require()
        try:
            from PySide6.QtCore import QLocale
            from PySide6.QtTextToSpeech import QTextToSpeech
        except ImportError:
            QMessageBox.warning(self, "Lettura", "Sintesi vocale non disponibile.")
            return
        if self._tts is None:
            self._tts = QTextToSpeech(self)
            self._tts.setLocale(QLocale(QLocale.Italian, QLocale.Italy))
        v = self.view()
        text = v.sel_text or m.page(v.current).get_text(sort=True)
        if not text.strip():
            self.status("Nessun testo da leggere su questa pagina (forse serve l'OCR)")
            return
        self._tts.say(text)
        self.status("Lettura in corso… (Interrompi lettura per fermarla)")

    def stop_reading(self):
        if self._tts is not None:
            self._tts.stop()

    def preferences(self):
        r = D.settings_dialog(self, self.tools)
        if not r:
            return
        settings.put("theme", r["theme"])
        settings.put("open_zoom", r["zoom"])
        settings.put("open_layout", r["layout"])
        settings.put("restore_session", r["restore"])
        settings.put("highlight_fields", r["highlight_fields"])
        self.tools.author = r["author"]
        self.tools.keep_tool = r["keep_tool"]
        settings.put("keep_tool", r["keep_tool"])
        self.tools.text_family = r["text_family"]
        self.tools.text_size = r["text_size"]
        self.tools.persist()
        self.props.author.setText(r["author"])
        self.props.keep.setChecked(r["keep_tool"])
        self.actions["highlight_fields"].setChecked(r["highlight_fields"])
        self.toggle_fields()
        self.apply_theme(r["theme"])

    def show_shortcuts(self):
        rows = [("Apri / Salva / Salva con nome", "Ctrl+O / Ctrl+S / Ctrl+Maiusc+S"), ("Stampa", "Ctrl+P"),
                ("Annulla / Ripeti", "Ctrl+Z / Ctrl+Y"), ("Cerca / Successivo", "Ctrl+F / F3"),
                ("Trova e sostituisci", "Ctrl+H"), ("Vai alla pagina", "Ctrl+G"),
                ("Zoom avanti / indietro", "Ctrl++ / Ctrl+-  ·  Ctrl+rotella"),
                ("Pagina intera / Larghezza / 100%", "Ctrl+1 / Ctrl+2 / Ctrl+0"),
                ("Pagina precedente / successiva", "← / →  ·  PagSu / PagGiù"), ("Prima / ultima pagina", "Home / Fine"),
                ("Schermo intero / Presentazione", "F11 / Ctrl+L"), ("Pannello laterale / proprietà", "F4 / F6"),
                ("Strumenti: Seleziona, Mano, Testo, Oggetti", "V, H, T, O"),
                ("Strumenti: Evidenzia, Nota, Penna, Rettangolo, Casella", "U, N, P, R, X"),
                ("Elimina elemento selezionato", "Canc"), ("Sposta annotazione", "Frecce (Maiusc = 10 pt)"),
                ("Conferma testo modificato", "Ctrl+Invio"), ("Annulla strumento / modifica", "Esc"),
                ("Ruota pagine a destra / sinistra", "Ctrl+Maiusc+R / Ctrl+Maiusc+L")]
        html = "<table cellpadding='5'>" + "".join(f"<tr><td>{a}</td><td><b>{b}</b></td></tr>" for a, b in rows) + "</table>"
        D.ReportDialog(self, "Scorciatoie da tastiera", html).exec()

    def about(self):
        QMessageBox.about(self, f"Informazioni su {APP_NAME}",
                          f"<h2>{APP_NAME}</h2><p>Versione {VERSION} · software libero, licenza GNU AGPL-3.0</p>"
                          "<p>Lettore ed editor PDF: modifica del testo, annotazioni, organizzazione pagine, moduli, "
                          "firme digitali, protezione, OCR, compressione e conversioni.</p>"
                          f"<p>Motore PDF: MuPDF {pymupdf.VersionFitz} (PyMuPDF {pymupdf.VersionBind}) · "
                          "Interfaccia: Qt · Firme: pyHanko · Word: pdf2docx.</p>")
