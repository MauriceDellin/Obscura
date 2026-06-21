# CLAUDE.md – Hinweise für Claude-Sessions in diesem Repo

Tool zum Anonymisieren radiologischer Bild-Exporte (Name + Geburtsdatum
schwärzen). Dies ist der aktive Arbeitsordner (vom früheren Sciebo-Ordner
hierher umgezogen).

## ⚠️ Wichtigste Regel: keine Patientendaten ins Git
Die Beispielbilder unter `Beispielbilder/` enthalten **echte Patientendaten**
(PHI) und sind per `.gitignore` ausgeschlossen. **Niemals** Bilder committen oder
an externe Dienste senden. Vor jedem Commit `git status` prüfen, dass keine
Bilddateien (`*.png` etc.) gestaged sind.

## Orientierung
- **Bedien-Anleitung:** `README.md`
- **Stand, Architektur, Projektstruktur, Roadmap:** `PROJEKT.md` (hier zuerst lesen)
- **Code:** `anonymize_core.py` (Logik + CLI), `anonymize_gui.py` (GUI/Feld-Editor)
- **Packaging:** `make_icon.py`, `anonymize.spec`, `installer.iss`, `build.bat`
- **Beispielbilder (gitignored):** `Beispielbilder/Rohdaten` (Originale),
  `Beispielbilder/annonymisiert` (geschwärzt) – zum lokalen Testen.

## Entwicklungsumgebung
- Läuft unter Windows mit **`py -3.13`** (Python Install Manager). Pakete:
  `pillow`, optional `pytesseract` (+ Tesseract-OCR fürs OCR-Feature).
- Unter WSL ist oft **kein tkinter** vorhanden → die GUI dort nicht startbar.
  Daher: **Kernlogik headless testen** (gegen `Beispielbilder/Rohdaten`), GUI auf
  Windows starten/prüfen.
- Start GUI:  `py -3.13 anonymize_gui.py`
- Paketieren: `.\build.bat`  → `dist\…exe` (portabel) + `Output\…Setup.exe`

## Git / Release
- Remote: `MauriceDellin/roentgen-anonymisierung` (privat), Branch `main`.
- Commits: Nutzer pusht auf Wunsch; Commit-Messages mit Co-Authored-By-Trailer.
- Releases: EXE/Installer per `gh release create vX.Y.Z … dist\…exe Output\…exe`
  (Binaries vorher mit `build.bat` neu bauen). Aktuell: `v1.0.0`.

## Arbeitsweise
- Änderungen klein halten, Stil des umgebenden Codes treffen.
- Nach Logik-Änderungen headless gegen die Beispielbilder gegenprüfen.
- Roadmap-Ideen stehen in `PROJEKT.md` (Sitzung speichern/laden,
  Gerätevoreinstellungen, Export-Sicherheitscheck, DICOM, Code-Signatur …).
