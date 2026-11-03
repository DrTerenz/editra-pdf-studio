# Editra PDF Studio

Lettore ed editor PDF gratuito e open source per Windows 10/11 (licenza AGPL-3.0).

## Installazione

- **Installer:** `installer\EditraPDFStudio_Setup_1.0.0.exe`. Non servono permessi di amministratore.
  Durante l'installazione puoi scegliere il collegamento sul desktop e l'apertura automatica dei file `.pdf` e `.p7m`.
  Su Windows 11 la prima volta che apri un PDF il sistema può chiedere con quale app aprirlo: scegli Editra PDF Studio.
- **Versione portatile:** `installer\EditraPDFStudio_portatile_1.0.0.zip`. La estrai dove vuoi (anche su una chiavetta)
  e avvii `EditraPDFStudio.exe`, senza installare nulla.

Una volta installato il programma è indipendente da questa cartella. La cartella `PDF` serve solo per modificarlo
e ricostruirlo: puoi cancellarla senza conseguenze, ma ti conviene tenerla se vuoi aggiunte o correzioni.
L'installer e lo zip si possono dare ad altre persone.

Impostazioni, firme autografe salvate e certificati considerati attendibili stanno in `%APPDATA%\EditraPDFStudio`.

## Funzioni

| Area | Cosa fa |
|---|---|
| Visualizzazione | Schede multiple, zoom (anche Ctrl+rotella, zoom su un'area), pagina singola/continua/due pagine, schermo intero, presentazione, lettura notturna, tema chiaro/scuro, miniature, segnalibri, livelli, ricerca con evidenziazione, lettura ad alta voce |
| Modifica testo | Clic su un blocco di testo per cambiarlo: font di Windows, corpo, grassetto, corsivo, sottolineato, colore, allineamento. Se possibile riusa il font originale del PDF. Testo nuovo ovunque, trova e sostituisci, spostamento ed eliminazione di blocchi |
| Oggetti | Immagini: inserisci, sposta, ridimensiona, ruota, sostituisci, estrai, elimina. Incolla immagini e testo dagli appunti |
| Commenti | Evidenzia, sottolinea, barrato, ondulata, note, caselle di testo, richiami, timbri (anche personalizzati), penna, linee, frecce, rettangoli, ellissi, poligoni, misure di distanza e area in scala, allegati, gomma, riepilogo commenti, appiattimento |
| Pagine | Inserisci, elimina, estrai, dividi (per pagine, intervalli, segnalibri, dimensione), combina file, ruota, riordina trascinando le miniature, duplica, sostituisci, ritaglia, cambia formato, più pagine per foglio, unisci fronte/retro, rimuovi pagine vuote, etichette di pagina |
| Modifica documento | Filigrana (testo o immagine), sfondo, intestazioni e piè di pagina, numeri di pagina, numerazione Bates, collegamenti, link automatici agli indirizzi web, proprietà e metadati |
| Moduli | Compilazione; creazione di campi di testo, caselle, scelte, elenchi, pulsanti, campi firma; riconoscimento automatico dei campi; esporta/importa dati; svuota; appiattisci |
| Firma e protezione | Firma autografa (disegnata, scritta o da immagine); firma digitale con certificato .pfx/.p12; verifica delle firme dei PDF (PAdES) e dei file .p7m (CAdES); creazione di un ID digitale; password e permessi (AES 256); redazione con ricerca automatica (e-mail, telefoni, codice fiscale, IBAN...); rimozione di informazioni nascoste |
| Conversioni | Da PDF a Word, Excel, immagini, testo, HTML, Markdown. Da Word, Excel, PowerPoint (serve Office o LibreOffice), immagini, testo, HTML, XPS, EPUB a PDF |
| Strumenti | OCR con il motore di Windows (rende ricercabili le scansioni), riduzione delle dimensioni, confronto tra due versioni, istantanea, stampa con anteprima |

Premi **F1** nel programma per l'elenco delle scorciatoie da tastiera.

## Limiti noti

- **Modifica del testo:** il testo modificato viene riscritto con il font scelto; le singole lettere non vengono
  avvicinate (crenatura) come nell'originale, quindi la riga può risultare leggermente più larga o più stretta.
  I blocchi di testo ruotati di angoli diversi da 90° non si possono modificare.
- **Firme digitali:** la verifica controlla integrità e certificato, ma non interroga online la revoca dei certificati.
  Le firme con smart card o token (CNS, firma remota) non sono supportate: servono file .pfx/.p12.
  Un ID creato con il programma è autofirmato e non ha valore legale.
- **Conversione in Word:** buona per testi e tabelle semplici; impaginazioni complesse possono richiedere ritocchi.
- **OCR:** usa le lingue installate in Windows (Impostazioni › Ora e lingua).
- **PDF/A** e accessibilità (tag) non sono gestiti.

## Sviluppo

Struttura:
- `editra\ops\`: le operazioni sui PDF, senza interfaccia (testo, pagine, annotazioni, immagini, moduli, sicurezza,
  firme, OCR, conversioni, confronto, compressione);
- `editra\view.py`: area di visualizzazione e strumenti col mouse;
- `editra\editors.py`: editor in linea;
- `editra\panels.py`: pannelli laterali;
- `editra\mainwindow.py`: finestra, menu e comandi;
- `editra\dialogs.py`: dialoghi.

Avvio dal codice: `.venv\Scripts\python.exe EditraPDFStudio.pyw`

Ricostruzione completa (collaudi, eseguibile, installer, zip):

```
powershell -ExecutionPolicy Bypass -File build\build.ps1
```

Collaudi: `tests\test_ops.py` (operazioni, 118 verifiche) e `tests\test_gui.py` (interfaccia con mouse e tastiera
simulati, 122 verifiche). Lo script di ricostruzione li esegue in una cartella temporanea.

Componenti: PyMuPDF/MuPDF (AGPL), Qt/PySide6 (LGPL), pyHanko, pdf2docx, openpyxl, cryptography.
Poiché MuPDF è AGPL, l'intero programma è distribuito con licenza AGPL-3.0 (vedi `LICENSE` e `THIRD_PARTY_NOTICES.md`).

