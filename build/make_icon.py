"""Genera l'icona .ico dell'applicazione e dei documenti PDF associati."""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication

app = QApplication([])
from editra.icons import app_icon_pixmap

out = sys.argv[1]
pm = app_icon_pixmap(256)
buf = QBuffer()
buf.open(QIODevice.WriteOnly)
pm.save(buf, "PNG")
img = Image.open(io.BytesIO(bytes(buf.data())))
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("icona:", out)
