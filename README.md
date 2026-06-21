# Obscura — Röntgenbild-Anonymisierung

Kleines Tool zum **Schwärzen von Patientendaten** (Name + Geburtsdatum) in
radiologischen Bild-Exporten (PNG/JPG/TIF). Auflösung, Größe und Format bleiben
unverändert – nur die markierten Felder werden überschrieben.

## Drei Erkennungswege (beliebig kombinierbar)

1. **AUTO** – findet das Header-Feld oben links (Name + Geburtsdatum) automatisch
   per Helligkeits-Zeilenerkennung und stoppt zuverlässig **vor der Bildkante**
   (auch vor sehr dunklen Graupanels – kein Hineinragen ins Bild).
2. **MANUELL** – zusätzliche, fest angegebene Rechtecke für Sonderfälle wie ein
   eingebettetes Patienten-Panel (z. B. „Abb. 3").
3. **OCR** – sucht einen vorgegebenen Patientennamen im **ganzen** Bild
   (optional, benötigt Tesseract). Ist Tesseract nicht installiert, wird OCR
   stillschweigend übersprungen; Auto + Manuell laufen weiter.

## Voraussetzungen

- **Python 3** mit **Pillow**:  `pip install pillow`
- Für die GUI: **tkinter** (bei Windows-/Mac-Python bereits dabei;
  unter Linux/WSL: `sudo apt install python3-tk`)
- Nur für OCR (optional):
  - `pip install pytesseract`
  - Tesseract-Programm:
    - Windows: Installer von <https://github.com/UB-Mannheim/tesseract/wiki>
    - Linux/WSL: `sudo apt install tesseract-ocr tesseract-ocr-deu`

## GUI starten

```
python anonymize_gui.py
```

1. Bilder oder einen Ordner wählen
2. In der **Galerie** (mittlere Spalte) erscheinen alle Bilder als kleine,
   bereits anonymisierte Vorschaubilder. Ein **Klick** lädt ein Bild groß in den
   interaktiven Bereich rechts. So siehst du auf einen Blick, dass jedes Bild
   abgedeckt ist.
3. Optionen prüfen (Header-Zeilen = 2 für Name + Geburtsdatum), ggf. Name für
   OCR eintragen
4. **Vorschau = Feld-Editor** (rechts): Das automatisch erkannte Header-Feld wird
   bereits angezeigt. **Jedes** Feld (auch das automatische) ist bearbeitbar:
   - **Neues Feld:** auf leerer Fläche ein Rechteck aufziehen.
   - **Auswählen:** Feld anklicken (gelb umrandet, mit Griffen).
   - **Verschieben:** in ein ausgewähltes Feld hineinziehen.
   - **Größe ändern:** an einem der 8 Griffe ziehen.
   - **Löschen:** **Entf**-Taste oder **Rechtsklick** auf das Feld
     (oder Knopf „Auswahl löschen" / „Alle Felder").
   - Felder gelten **nur für das jeweilige Bild** (pro Datei gemerkt).
   - **Feldfarbe:** Ein Feld auswählen → die Farbeinstellung wirkt **auf dieses
     Feld**; ohne Auswahl gilt sie als Standard für neue Felder. Standard ist
     `auto` (Hintergrund gemittelt). Für einen exakten Treffer auf farbigen Panels
     die **Pipette** nutzen: anklicken, dann in der Vorschau auf die gewünschte
     Farbe klicken – sie wird pixelgenau übernommen. Alternativ **„Farbe…"** für
     einen Farbwähler.
   - „**Auto-Felder neu erkennen**" setzt die Header-Felder anhand der aktuellen
     Zeilenzahl/Füllung neu (manuelle Felder bleiben erhalten).
6. **Zoom für präzises Zeichnen:** mit **Strg+Mausrad** (oder den Knöpfen
   `+` / `−` / `Fit`) in die Vorschau hineinzoomen. So lassen sich auch kleine
   Felder pixelgenau bearbeiten.
   - **Bild verschieben (Pan):** mit der **mittleren Maustaste** ziehen, oder den
     Schalter **„✋ Verschieben"** aktivieren und mit links ziehen. Alternativ
     Scrollleisten bzw. Mausrad (vertikal) / Umschalt+Mausrad (horizontal).
7. Ausgabeordner wählen → **„Alle anonymisieren"**

> Tipp: Für sehr präzise Felder vor dem Ziehen hineinzoomen (z. B. ×4 → unter
> einem Originalpixel pro Anzeige-Pixel). Alternativ die CLI-Option `--extra`
> mit exakten Koordinaten nutzen. Die Füllung `auto` gleicht die Farbe an den
> Hintergrund an, sodass kleine Ungenauigkeiten auf farbigen Panels kaum
> auffallen.

## Kommandozeile (CLI)

```bash
# Ganzen Ordner anonymisieren (nur Auto-Header)
python anonymize_core.py Rohdaten/ -o annonymisiert/

# Mit OCR-Namenssuche
python anonymize_core.py Rohdaten/ -o annonymisiert/ --ocr-name Mustermann

# Sonderfall mit Zusatzfeld (eingebettetes Panel, in Hintergrundfarbe gefüllt)
python anonymize_core.py "Abb. 3.png" -o annonymisiert/ \
    --extra "575,33,658,61:0,17,40"
```

Wichtige Optionen:

| Option           | Bedeutung                                                        |
|------------------|------------------------------------------------------------------|
| `--lines N`      | Anzahl Header-Zeilen oben links (Name+Geburtsdatum = `2`, `0` = aus) |
| `--extra ...`    | Zusatzfeld `x0,y0,x1,y1` oder `x0,y0,x1,y1:R,G,B` (mehrfach möglich) |
| `--ocr-name`     | Patientenname für die OCR-Suche im ganzen Bild                   |
| `--header-fill`  | `black` (Standard), `auto` (Hintergrund angleichen) oder `R,G,B` |
| `--overwrite`    | vorhandene Ausgaben überschreiben                                |

**Füllfarbe `auto`** sampelt den Hintergrund rund um das Feld und gleicht die
Farbe an – praktisch für farbige Panels (z. B. das dunkelblaue Panel in Abb. 3).

## Wichtige Hinweise / Grenzen

- ⚠️ **Ergebnisse immer visuell prüfen.** Die Erkennung ist heuristisch.
- Die **AUTO**-Erkennung ist auf den typischen Geräte-Export ausgelegt
  (weißer Header oben links: Name / Geburtsdatum / Modalität / Bild).
  Bei stark abweichendem Layout ggf. `--lines` anpassen oder `--extra` nutzen.
- **Eingebettete Panels** (Name mitten im Bild) findet AUTO nicht – dafür ist
  das Zusatzfeld (`--extra`) bzw. OCR gedacht.
- Dies ist eine **Pixel-Schwärzung**, kein DICOM-Anonymisierer: Lagen die
  Bilder ursprünglich als DICOM vor, müssen für eine echte Anonymisierung
  zusätzlich die DICOM-Metadaten entfernt werden. Für reine PNG/JPG-Exporte
  (wie hier) reicht die Pixel-Schwärzung.

## Als Windows-App verpacken (Installer + Icon)

Damit Kolleg:innen die App **ohne Python** nutzen können, lässt sie sich zu
einer `.exe` und einem Installer bündeln. Der Build läuft auf **Windows**.

**In einem Schritt** (installiert Build-Tools, erzeugt Icon, EXE und – falls
Inno Setup vorhanden – den Installer):

```powershell
.\build.bat
```

Ergebnisse:
- `dist\Obscura.exe` – portable App (eine Datei, kein Python nötig)
- `Output\Obscura-Setup.exe` – Installer (Startmenü, Desktop-
  Verknüpfung, Deinstaller), nur wenn **Inno Setup** installiert ist
  (<https://jrsoftware.org/isdl.php>)

Einzelschritte (falls gewünscht):
```powershell
py -3.13 -m pip install pyinstaller pillow pytesseract
py -3.13 make_icon.py                       # erzeugt app.ico + logo.png
py -3.13 -m PyInstaller --noconfirm anonymize.spec
```

Hinweise:
- **OCR in der App:** `pytesseract` wird mitgebündelt; das Tesseract-Programm
  selbst nicht (zu groß). Auf dem Zielrechner muss Tesseract installiert sein
  (Standardpfad `C:\Program Files\Tesseract-OCR`) – die App findet es dort.
- Das **Icon** wird per `make_icon.py` aus Code erzeugt (reproduzierbar); zum
  Anpassen einfach die Farben/Formen dort ändern und neu bauen.

## Dateien

- `anonymize_core.py` – Kernlogik + Kommandozeile (nur Pillow nötig)
- `anonymize_gui.py`  – grafische Oberfläche (tkinter)
- `make_icon.py`      – erzeugt das App-Icon (`app.ico`)
- `anonymize.spec`    – PyInstaller-Konfiguration (→ `.exe`)
- `version_info.txt`  – Versions-Metadaten der `.exe`
- `installer.iss`     – Inno-Setup-Skript (→ Installer)
- `build.bat`         – baut Icon, EXE und Installer in einem Rutsch

## Lizenz

[MIT](LICENSE) © 2026 Maurice Dellin. Nutzung auf eigene Verantwortung – die
Pixel-Schwärzung ersetzt keine zertifizierte/DICOM-konforme Anonymisierung;
Ergebnisse immer prüfen.
