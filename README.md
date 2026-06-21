# Röntgenbild-Anonymisierung

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
4. **Vorschau** (rechts) zeigt das fertige Ergebnis des gewählten Bildes
5. **Zusatzfelder mit der Maus aufziehen:** einfach im Vorschaubild ein Rechteck
   ziehen – es wird (in Hintergrundfarbe angeglichen) sofort in der Vorschau
   gefüllt und rot umrandet. **Rechtsklick** auf ein Feld löscht es; die Knöpfe
   „Letztes Feld" / „Felder löschen" helfen ebenfalls.
   Gezeichnete Felder gelten **nur für das jeweilige Bild** (pro Datei gemerkt).
6. **Zoom für präzises Zeichnen:** mit **Strg+Mausrad** (oder den Knöpfen
   `+` / `−` / `Fit`) in die Vorschau hineinzoomen; bei Vergrößerung mit den
   Scrollleisten bzw. Mausrad (horizontal: Umschalt+Mausrad) verschieben. So
   lassen sich auch kleine Felder pixelgenau aufziehen.
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

## Dateien

- `anonymize_core.py` – Kernlogik + Kommandozeile (nur Pillow nötig)
- `anonymize_gui.py`  – grafische Oberfläche (tkinter)
