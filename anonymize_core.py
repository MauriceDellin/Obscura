#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
anonymize_core.py — Kernlogik zum Schwaerzen von Patientendaten in
radiologischen Bild-Exporten (PNG/JPG/TIF).

Drei Erkennungswege, beliebig kombinierbar:
  1) AUTO    – findet das Header-Feld oben links (Name + Geburtsdatum) per
               Helligkeits-Zeilenerkennung und stoppt automatisch VOR der
               Bildkante (kein Hineinragen ins Bild).
  2) MANUELL – zusaetzliche, fest angegebene Rechtecke (z. B. eingebettete
               Patienten-Panels wie in Abb. 3).
  3) OCR     – sucht einen vorgegebenen Patientennamen im GANZEN Bild
               (benoetigt Tesseract + pytesseract; ist es nicht installiert,
               wird OCR stillschweigend uebersprungen).

Fuellfarbe je Feld: 'black', 'auto' (Hintergrund ringsum wird gesampelt und
gematcht – praktisch fuer farbige Panels) oder explizit "R,G,B".

Nur Abhaengigkeit fuer 1) + 2): Pillow.  Fuer 3) zusaetzlich pytesseract.

Dieses Modul ist GUI-frei und laesst sich auch direkt als CLI nutzen:
    python anonymize_core.py Rohdaten/ -o annonymisiert/ --ocr-name Mustermann
"""

from __future__ import annotations
import os
import sys
import argparse
from PIL import Image, ImageDraw

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp")


# --------------------------------------------------------------------------- #
# Hilfsfunktionen: Texterkennung per Helligkeit
# --------------------------------------------------------------------------- #
def _row_bands(px, x0, x1, y0, y1, th):
    """Liefert (start, ende)-Zeilenbaender, in denen helle (Text-)Pixel liegen."""
    bands = []
    in_band = False
    start = 0
    for y in range(y0, y1):
        bright = False
        for x in range(x0, x1):
            if px[x, y] > th:
                bright = True
                break
        if bright and not in_band:
            start = y
            in_band = True
        elif not bright and in_band:
            bands.append((start, y - 1))
            in_band = False
    if in_band:
        bands.append((start, y1 - 1))
    return bands


def header_box(img, lines=2, region_w=620, region_h=280, text_th=120,
               pad_right=12, pad_bottom=6, panel_margin=3, faint_th=6,
               left_anchor=60, word_gap=30, min_band_h=8):
    """
    Ermittelt das Schwaerzungs-Rechteck fuer den Header oben links.

    lines        – Anzahl der zu schwaerzenden Textzeilen (Name + Geburtsdatum = 2).
    text_th      – Helligkeitsschwelle, ab der ein Pixel als Text gilt.
    pad_right    – Zusatzbreite rechts neben dem laengsten Text.
    panel_margin – Sicherheitsabstand zur erkannten Bildkante.
    faint_th     – niedrige Schwelle, um auch dunkelgraue Bildpanels als
                   "Bild" zu erkennen (verhindert Hineinragen, vgl. Abb. 5b/5c).
    left_anchor  – nur Zeilen beruecksichtigen, deren Text nahe am linken Rand
                   beginnt (ignoriert Toolbar-/Bildbeschriftungen weiter rechts).
    word_gap     – ab dieser Lueckenbreite (Pixel) endet der linke Textblock
                   (trennt Header-Text von rechts danebenliegendem Bildinhalt,
                   vgl. "15KP Belastung" in Abb. 1a).

    Rueckgabe: (x0, y0, x1, y1) inklusive, oder None wenn kein Text gefunden.
    """
    gray = img.convert("L")
    W, H = img.size
    rw, rh = min(region_w, W), min(region_h, H)
    px = gray.load()

    bands = _row_bands(px, 0, rw, 0, rh, text_th)
    # Mini-Baender herausfiltern (z. B. der hochstehende "*" des Geburtsdatums),
    # damit die Zeilenzaehlung stabil bleibt. Echte Textzeilen sind ~20 px hoch.
    bands = [b for b in bands if b[1] - b[0] + 1 >= min_band_h]
    if not bands:
        return None

    n = min(lines, len(bands))
    covered = bands[:n]

    # Unterkante: zwischen letzter gewuenschter Zeile und der naechsten Zeile
    # stoppen, damit z. B. die Modalitaets-/Bild-Zeile sichtbar bleibt.
    if len(bands) > n:
        bottom = (covered[-1][1] + bands[n][0]) // 2
    else:
        bottom = min(rh - 1, covered[-1][1] + pad_bottom)
    top = 0  # ab Bildoberkante schwaerzen (darueber ist ohnehin nur Rand)

    # Rechte Textkante: nur der LINKS verankerte, zusammenhaengende Textblock.
    # Pro Zeile bis zur ersten groesseren Luecke laufen; weiter rechts liegender
    # Bildinhalt (Beschriftung, Toolbar) wird so nicht mitgezaehlt.
    text_right = 0
    for (a, b) in covered:
        for y in range(a, b + 1):
            first = next((x for x in range(rw) if px[x, y] > text_th), None)
            if first is None or first > left_anchor:
                continue  # Zeile beginnt nicht links -> kein Header-Text
            end, gap = first, 0
            for x in range(first, rw):
                if px[x, y] > text_th:
                    end, gap = x, 0
                else:
                    gap += 1
                    if gap >= word_gap:
                        break
            text_right = max(text_right, end)
    if text_right == 0:
        return None
    box_right = text_right + pad_right

    # Bild-/Panelkante ueber die TEXTFREIEN Zwischenzeilen finden (dort stoert
    # kein Anti-Aliasing des Textes) und das Feld mit Abstand davor stoppen.
    # Auch sehr dunkle Graupanels werden so erkannt (vgl. Abb. 5b/5c).
    covered_rows = set()
    for (a, b) in covered:
        covered_rows.update(range(a, b + 1))
    panel_left = None
    for y in range(top, bottom + 1):
        if y in covered_rows:
            continue
        for x in range(rw):
            if px[x, y] > faint_th:
                panel_left = x if panel_left is None else min(panel_left, x)
                break
    if panel_left is not None and panel_left - panel_margin > text_right:
        box_right = min(box_right, panel_left - panel_margin)

    box_right = max(box_right, text_right)  # Name immer vollstaendig abdecken
    return (0, top, box_right, bottom)


# --------------------------------------------------------------------------- #
# OCR (optional)
# --------------------------------------------------------------------------- #
# Gaengige Windows-Installationspfade von Tesseract (UB-Mannheim-Build),
# damit OCR auch ohne PATH-Eintrag gefunden wird.
_TESSERACT_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
]


def _configure_tesseract():
    """Importiert pytesseract und stellt sicher, dass tesseract.exe gefunden wird.
    Rueckgabe: das pytesseract-Modul oder None, wenn nicht installiert."""
    try:
        import pytesseract
        import shutil
    except Exception:
        return None
    cmd = pytesseract.pytesseract.tesseract_cmd
    if shutil.which(cmd):           # bereits ueber PATH auffindbar
        return pytesseract
    for cand in _TESSERACT_CANDIDATES:
        if cand and os.path.exists(cand):
            pytesseract.pytesseract.tesseract_cmd = cand
            break
    return pytesseract


def ocr_available():
    try:
        pt = _configure_tesseract()
        if pt is None:
            return False
        pt.get_tesseract_version()
        return True
    except Exception:
        return False


def ocr_boxes(img, names, conf_min=40, pad=5, extra_lines_below=0, min_token=3):
    """
    Sucht die Woerter aus `names` (Leerzeichen/Komma-getrennt) im ganzen Bild
    und liefert Rechtecke um jede Fundstelle. Leere Liste, wenn OCR fehlt.

    extra_lines_below – zusaetzlich n Textzeilenhoehen nach unten mitnehmen
                        (praktisch, um ein direkt darunter stehendes
                        Geburtsdatum gleich mit abzudecken).
    """
    pytesseract = _configure_tesseract()
    if pytesseract is None:
        return []
    from pytesseract import Output

    tokens = [t.strip(" ,.:;-").lower()
              for t in names.replace(",", " ").split()]
    tokens = [t for t in tokens if len(t) >= min_token]
    if not tokens:
        return []

    try:
        data = pytesseract.image_to_data(img, output_type=Output.DICT)
    except Exception:
        return []

    boxes = []
    for i in range(len(data["text"])):
        word = data["text"][i].strip(" ,.:;-").lower()
        if not word:
            continue
        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1.0
        if conf < conf_min:
            continue
        if any(tok in word for tok in tokens):
            x, y = data["left"][i], data["top"][i]
            w, h = data["width"][i], data["height"][i]
            boxes.append((max(0, x - pad), max(0, y - pad),
                          x + w + pad, y + h + pad + extra_lines_below * h))
    return boxes


# --------------------------------------------------------------------------- #
# Fuellfarbe
# --------------------------------------------------------------------------- #
def sample_bg(img, box, ring=8):
    """Median-Farbe eines Rahmens rund um `box` (zum Angleichen an den Hintergrund)."""
    rgb = img.convert("RGB")
    px = rgb.load()
    W, H = rgb.size
    x0, y0, x1, y1 = box
    rs, gs, bs = [], [], []
    xa, xb = max(0, x0 - ring), min(W, x1 + ring + 1)
    for x in range(xa, xb):
        for y in list(range(max(0, y0 - ring), y0)) + \
                 list(range(y1 + 1, min(H, y1 + ring + 1))):
            r, g, b = px[x, y][:3]
            rs.append(r); gs.append(g); bs.append(b)
    if not rs:
        return (0, 0, 0)
    med = lambda v: sorted(v)[len(v) // 2]
    return (med(rs), med(gs), med(bs))


def resolve_fill(img, box, fill):
    if isinstance(fill, (tuple, list)):
        return tuple(fill[:3])
    if fill == "auto":
        return sample_bg(img, box)
    if fill == "black":
        return (0, 0, 0)
    # Format "R,G,B"
    try:
        parts = tuple(int(p) for p in str(fill).split(","))
        if len(parts) == 3:
            return parts
    except ValueError:
        pass
    return (0, 0, 0)


# --------------------------------------------------------------------------- #
# Hauptfunktion: ein Bild anonymisieren
# --------------------------------------------------------------------------- #
def anonymize_image(img, lines=2, extra=None, ocr_names=None,
                    header_fill="black", extra_fill="auto", ocr_fill="auto",
                    detector_kwargs=None):
    """
    Liefert (anonymisiertes_Bild, Liste_der_angewandten_Rechtecke).
    `extra` ist eine Liste von (x0,y0,x1,y1) oder (x0,y0,x1,y1,fill).
    """
    img = img.convert("RGB")
    detector_kwargs = detector_kwargs or {}
    planned = []  # (box, fill)

    if lines and lines > 0:
        hb = header_box(img, lines=lines, **detector_kwargs)
        if hb:
            planned.append((hb, header_fill))

    for b in (extra or []):
        if len(b) >= 5:
            planned.append((tuple(b[:4]), b[4]))
        else:
            planned.append((tuple(b[:4]), extra_fill))

    if ocr_names:
        for b in ocr_boxes(img, ocr_names):
            planned.append((b, ocr_fill))

    draw = ImageDraw.Draw(img)
    applied = []
    for box, fill in planned:
        draw.rectangle(box, fill=resolve_fill(img, box, fill))
        applied.append(tuple(box))
    return img, applied


# --------------------------------------------------------------------------- #
# Stapelverarbeitung
# --------------------------------------------------------------------------- #
def iter_image_paths(inputs):
    """Akzeptiert Dateien und/oder Ordner und liefert alle Bildpfade."""
    for p in inputs:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                if name.lower().endswith(IMAGE_EXTS):
                    yield os.path.join(p, name)
        elif os.path.isfile(p) and p.lower().endswith(IMAGE_EXTS):
            yield p


def process(inputs, out_dir, suffix="_anon", overwrite=False,
            progress=None, extra=None, per_file_extra=None, **kwargs):
    """
    Verarbeitet alle Bilder. `progress(pfad, applied, fehler)` wird je Bild
    aufgerufen (fuer GUI/CLI-Status). Rueckgabe: Liste (pfad, out_pfad, n_boxes).

    extra          – Zusatzfelder, die fuer ALLE Bilder gelten.
    per_file_extra – dict {Dateiname: [Felder]} fuer Felder, die nur auf ein
                     bestimmtes Bild angewendet werden (z. B. per Maus gezogen).
    """
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for path in iter_image_paths(inputs):
        base = os.path.basename(path)
        stem, ext = os.path.splitext(base)
        out_path = os.path.join(out_dir, f"{stem}{suffix}{ext}")
        if os.path.exists(out_path) and not overwrite:
            if progress:
                progress(path, [], "uebersprungen (existiert)")
            continue
        combined = list(extra or [])
        if per_file_extra:
            combined += list(per_file_extra.get(base, []))
        try:
            img = Image.open(path)
            anon, applied = anonymize_image(img, extra=combined, **kwargs)
            anon.save(out_path)
            results.append((path, out_path, len(applied)))
            if progress:
                progress(path, applied, None)
        except Exception as e:  # noqa: BLE001
            if progress:
                progress(path, [], str(e))
    return results


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _parse_extra(values):
    """--extra "x0,y0,x1,y1" oder "x0,y0,x1,y1:R,G,B" (mehrfach erlaubt)."""
    out = []
    for v in values or []:
        coords, _, fill = v.partition(":")
        nums = [int(n) for n in coords.split(",")]
        if len(nums) != 4:
            raise ValueError(f"--extra erwartet 4 Zahlen: {v}")
        if fill:
            out.append((*nums, tuple(int(p) for p in fill.split(","))))
        else:
            out.append(tuple(nums))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Schwaerzt Patientendaten (Name/Geburtsdatum) in radiologischen Bild-Exporten.")
    ap.add_argument("inputs", nargs="+", help="Bilddateien und/oder Ordner")
    ap.add_argument("-o", "--out", default="annonymisiert", help="Ausgabeordner")
    ap.add_argument("--suffix", default="_anon", help="Dateinamen-Suffix")
    ap.add_argument("--lines", type=int, default=2,
                    help="Anzahl Header-Zeilen oben links (Name+Geburtsdatum=2; 0=aus)")
    ap.add_argument("--extra", action="append",
                    help='Zusatzfeld "x0,y0,x1,y1" oder "x0,y0,x1,y1:R,G,B"')
    ap.add_argument("--ocr-name", help="Patientenname fuer OCR-Suche im ganzen Bild")
    ap.add_argument("--header-fill", default="black", help="black | auto | R,G,B")
    ap.add_argument("--extra-fill", default="auto", help="black | auto | R,G,B")
    ap.add_argument("--ocr-fill", default="auto", help="black | auto | R,G,B")
    ap.add_argument("--overwrite", action="store_true", help="vorhandene Ausgaben ueberschreiben")
    args = ap.parse_args(argv)

    if args.ocr_name and not ocr_available():
        print("! Hinweis: OCR angefordert, aber Tesseract/pytesseract nicht "
              "verfuegbar – OCR wird uebersprungen.", file=sys.stderr)

    def progress(path, applied, err):
        if err:
            print(f"  {os.path.basename(path):24s} -> {err}")
        else:
            print(f"  {os.path.basename(path):24s} -> {len(applied)} Feld(er): {applied}")

    print(f"Anonymisiere nach: {args.out}")
    results = process(
        args.inputs, args.out, suffix=args.suffix, overwrite=args.overwrite,
        progress=progress, lines=args.lines,
        extra=_parse_extra(args.extra), ocr_names=args.ocr_name,
        header_fill=args.header_fill, extra_fill=args.extra_fill,
        ocr_fill=args.ocr_fill,
    )
    print(f"Fertig: {len(results)} Bild(er) geschrieben.")


if __name__ == "__main__":
    main()
