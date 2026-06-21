# Projektdokumentation – Röntgenbild-Anonymisierung

Entwickler-/Übergabedokument zum Weiterarbeiten. Die **Bedien-Anleitung** steht
in `README.md`; dieses Dokument beschreibt **Stand, Aufbau und Ideen**.

- **Repo:** `MauriceDellin/roentgen-anonymisierung` (privat), Branch `main`
- **Zweck:** Patientendaten (Name + Geburtsdatum) in radiologischen Bild-Exporten
  (PNG/JPG/TIF) durch schwarze/farbige Felder überschreiben – per Auto-Erkennung,
  manuellen Feldern und optionaler OCR. Auflösung/Größe/Format bleiben erhalten.

> ⚠️ **Wichtigste Regel:** Es kommen **keine Patientenbilder** ins Repo oder an
> externe Dienste (DSGVO/Patientengeheimnis). Das Repo enthält nur Code; eine
> `.gitignore` schließt alle Bildtypen und die Ordner `Rohdaten/`,
> `annonymisiert/` aus. Vor jedem Commit `git status` prüfen.

## Status (funktioniert)

- **Kernlogik** (`anonymize_core.py`): Auto-Header-Erkennung oben links
  (Name+Geburtsdatum), manuelle Zusatzfelder, optionale OCR (Tesseract),
  Stapelverarbeitung, CLI.
- **GUI** (`anonymize_gui.py`):
  - Galerie aller Bilder (Thumbnails, anklickbar).
  - **Feld-Editor**: jedes Feld (auch das automatische Header-Feld) ist
    auswählbar, verschiebbar, in der Größe änderbar (8 Griffe), umfärbbar,
    löschbar (Entf/Rechtsklick). Felder werden **pro Bild** gehalten.
  - **Feldfarbe** je Feld: `auto`, Pipette (Farbe pixelgenau aus dem Bild),
    Farbwähler.
  - **Zoom** (Strg+Mausrad) + **Pan** (mittlere Maustaste / „✋ Verschieben").
  - Scharfer Text (DPI-aware), eigenes Fenster-/Taskleisten-Icon.
- **Packaging**: eigenes Icon (`make_icon.py`), portable `.exe` (PyInstaller),
  Windows-Installer (Inno Setup), Build per `build.bat`.

## Projektstruktur

```
anonymisierung/
├─ anonymize_core.py     Kernlogik + CLI (nur Pillow nötig)
├─ anonymize_gui.py      GUI / Feld-Editor (tkinter + Pillow)
├─ make_icon.py          erzeugt app.ico / logo.png aus Code
├─ anonymize.spec        PyInstaller-Konfiguration (→ .exe)
├─ version_info.txt      Windows-Versionsmetadaten der .exe
├─ installer.iss         Inno-Setup-Skript (→ Installer)
├─ build.bat             baut Icon + EXE + Installer in einem Schritt
├─ README.md             Bedien-Anleitung
├─ PROJEKT.md            dieses Dokument
└─ .gitignore            schließt Bilder + Build-Artefakte aus

# nicht im Repo (erzeugt/ignored): app.ico, logo.png, build/, dist/, Output/
```

## Architektur / Funktionsweise

### Kern (`anonymize_core.py`)
- `header_box(img, lines=2, ...)` – findet das Header-Rechteck oben links:
  Textzeilen per Helligkeits-**Zeilenbändern** (`_row_bands`), filtert Mini-Bänder
  (z. B. den hochstehenden `*` des Geburtsdatums), nimmt die ersten `lines` Zeilen
  und stoppt die **rechte Kante vor dem Bild/Panel** (auch vor dunkelgrauen
  Panels, über `faint_th` in den textfreien Zwischenzeilen → verhindert
  Hineinragen ins Bild). Wichtige Parameter: `text_th`, `faint_th`, `word_gap`,
  `left_anchor`, `min_band_h`, `panel_margin`.
- `ocr_boxes(img, names)` – sucht Namen per Tesseract; `_configure_tesseract()`
  findet `tesseract.exe` auch am Windows-Standardpfad.
- `anonymize_image(img, lines, extra, ocr_names, ...)` – füllt Header (falls
  `lines>0`) + `extra`-Felder + OCR-Funde; `extra` sind 4- oder 5-Tupel
  `(x0,y0,x1,y1[,fill])`, `fill` = `'auto'` | `'black'` | `(r,g,b)`.
  `resolve_fill`/`sample_bg` setzen `auto` = Median des Rahmens ringsum.
- `process(...)` – Stapel; `per_file_extra={Dateiname: [Felder]}` für
  bildspezifische Felder.

### GUI (`anonymize_gui.py`)
- **Feld-Modell:** `self.fields = {Dateiname: [ {x0,y0,x1,y1,fill,kind}, … ]}`,
  `kind ∈ {header, manual}`. Beim ersten Sehen eines Bildes wird das Header-Feld
  aus `header_box` **materialisiert** (`_ensure_seeded`); der Core wird danach mit
  `lines=0` aufgerufen, d. h. die Felder (inkl. Header) kommen als `extra`.
  „Auto-Felder neu erkennen" re-seedet die Header neu (manuelle Felder bleiben).
- **Rendering:** `_render_image` (teuer: skalieren/zeichnen) getrennt von
  `_draw_overlays` (billig: Umrandungen + Griffe). Beim Ziehen werden nur Overlays
  aktualisiert, der gefüllte Re-Render passiert beim Loslassen.
- **Koordinaten:** Felder in **Originalpixeln**; Anzeige = `fit_an_canvas * zoom`;
  Maus → Original via `_oxy` (berücksichtigt Scroll/Zoom). Mapping ist zoom-/
  scroll-fest (verifiziert).

### Packaging
- `make_icon.py` zeichnet das Icon (Patientenkarte + Redigier-Balken + Knochen).
- `anonymize.spec`: onefile-EXE, `console=False`, `icon=app.ico`,
  `datas=[('app.ico','.')]`, `version_info.txt`.
- `installer.iss`: Inno Setup, Startmenü/Desktop/Deinstaller, pro-Benutzer.
- Start-Hooks: DPI-Awareness + AppUserModelID (Taskleisten-Icon).

## Build & Start

```powershell
# Entwicklung
py -3.13 -m pip install pillow pytesseract
py -3.13 anonymize_gui.py

# Paketieren (Windows; Inno Setup optional für den Installer)
.\build.bat
#  -> dist\Roentgen-Anonymisierung.exe         (portabel)
#  -> Output\Roentgen-Anonymisierung-Setup.exe (Installer)
```

OCR braucht zusätzlich **Tesseract-OCR** (UB-Mannheim-Build) auf dem Zielrechner.

## Ideen / Roadmap

- [ ] **Sitzung speichern/laden** – gesetzte Felder je Bild als JSON sichern, um
      später weiterzuarbeiten (z. B. `<ausgabe>/felder.json`).
- [ ] **Voreinstellungen je Gerätetyp** (CT/MRT-Export) mit hinterlegten
      Standard-Zusatzfeldern.
- [ ] **Export-Sicherheitscheck** – Warnung, wenn ein Bild **kein** Feld hat
      (Schutz vor versehentlich nicht-anonymisierten Bildern).
- [ ] **OCR-Felder editierbar** machen (aktuell nur Overlay zur Laufzeit).
- [ ] **DICOM-Unterstützung** inkl. Entfernen der Metadaten (echte
      Anonymisierung statt reiner Pixel-Schwärzung).
- [ ] **Code-Signatur** der EXE gegen SmartScreen-Warnung.
- [ ] Fortschrittsbalken bei großen Stapeln; Galerie-Thumbnails im Hintergrund.

## Bekannte Punkte / Gotchas

- Pixel-Schwärzung ≠ DICOM-Anonymisierung (Metadaten!). Für PNG/JPG-Exporte ok.
- Erkennung ist heuristisch → **Ergebnisse immer visuell prüfen** (Galerie hilft).
- `auto`-Füllung mittelt den Rand und trifft farbige Panels evtl. nicht exakt →
  dafür die **Pipette**.
- Eingebettete Panels (z. B. Name mitten im Bild, „Abb. 3") findet die
  Auto-Erkennung nicht → manuelles Feld oder OCR.
- Entwicklung lief unter WSL ohne tkinter → GUI dort nicht startbar; Kernlogik
  wird headless getestet, GUI auf Windows (`py -3.13`).
