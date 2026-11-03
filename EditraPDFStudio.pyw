"""Avvio di Editra PDF Studio (anche punto d'ingresso per PyInstaller)."""
import sys

from editra.app import main

if __name__ == "__main__":
    sys.exit(main())
