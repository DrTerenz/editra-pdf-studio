# Third-party components

Editra PDF Studio is built on these open-source projects. Their licenses apply to the
corresponding parts of the distributed program.

| Component | Use | License |
|---|---|---|
| [MuPDF](https://mupdf.com) / [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | PDF rendering and editing engine | AGPL-3.0 (or Artifex commercial license) |
| [Qt](https://www.qt.io) / [PySide6](https://doc.qt.io/qtforpython-6/) | User interface | LGPL-3.0 |
| [pyHanko](https://github.com/MatthiasValvekens/pyHanko) | Digital signatures (signing and validation) | MIT |
| [pdf2docx](https://github.com/ArtifexSoftware/pdf2docx) | PDF to Word conversion | MIT |
| [OpenCV](https://opencv.org) | Used by pdf2docx | Apache-2.0 |
| [cryptography](https://github.com/pyca/cryptography) | Certificates and keys | Apache-2.0 or BSD-3-Clause |
| [openpyxl](https://openpyxl.readthedocs.io) | Excel export | MIT |
| [Pillow](https://python-pillow.org) | Image processing | MIT-CMU |
| [NumPy](https://numpy.org) | Used by pdf2docx and OpenCV | BSD-3-Clause |
| [PyWinRT](https://github.com/pywinrt/pywinrt) | Access to the Windows OCR engine | MIT |
| [PyInstaller](https://pyinstaller.org) | Packaging (build only) | GPL-2.0 with bootloader exception |
| [Inno Setup](https://jrsoftware.org/isinfo.php) | Installer (build only) | Inno Setup license |

Because MuPDF is licensed under the AGPL, Editra PDF Studio is distributed under the
GNU Affero General Public License v3.0 or later (see `LICENSE`).

Icons are drawn at runtime from the Segoe Fluent Icons / Segoe MDL2 Assets fonts that ship
with Windows; no icon files are redistributed.
