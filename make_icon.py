#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_icon.py — erzeugt das App-Icon (app.ico) und eine Vorschau (logo.png).

Motiv: eine weisse "Patientenkarte" auf medizinisch-blauem Grund, mit einem
schwarzen Redigier-Balken ueber der Namenszeile (Anonymisierung) und einer
kleinen Knochen-Silhouette (Radiologie/Osteoidosteom).

Aufruf:  python make_icon.py
"""

from PIL import Image, ImageDraw

# Farbpalette
BG_TOP = (18, 64, 105)      # dunkles Medizinblau
BG_BOT = (28, 110, 170)     # helleres Blau
CARD = (240, 244, 248)      # fast weiss
LINE = (176, 190, 205)      # graue Textzeilen
REDACT = (15, 15, 18)       # schwarzer Balken
BONE = (120, 140, 162)      # Knochen-Silhouette


def _gradient(size, top, bot):
    """Vertikaler Farbverlauf als RGBA-Bild."""
    w, h = size, size
    base = Image.new("RGB", (w, h), top)
    px = base.load()
    for y in range(h):
        t = y / (h - 1)
        px_row = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = px_row
    return base.convert("RGBA")


def _rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1],
                                        radius=radius, fill=255)
    return m


def draw_master(S=256):
    """Zeichnet das Icon in Aufloesung S x S (RGBA)."""
    img = _gradient(S, BG_TOP, BG_BOT)
    # abgerundete App-Ecken
    img.putalpha(_rounded_mask(S, int(S * 0.20)))
    d = ImageDraw.Draw(img)

    def sc(v):
        return int(v * S / 256)

    # weisse Karte
    card = [sc(52), sc(44), sc(204), sc(212)]
    d.rounded_rectangle(card, radius=sc(16), fill=CARD)

    # schwarzer Redigier-Balken (anonymisierte Namenszeile)
    d.rounded_rectangle([sc(68), sc(66), sc(170), sc(92)],
                        radius=sc(6), fill=REDACT)

    # graue "Textzeilen" darunter
    for i, y in enumerate((sc(106), sc(126), sc(146))):
        x2 = sc(184) if i != 2 else sc(150)
        d.rounded_rectangle([sc(68), y, x2, y + sc(10)],
                            radius=sc(5), fill=LINE)

    # Knochen-Silhouette (klassische Hantelform) unten auf der Karte
    ax, bx, cy = sc(84), sc(150), sc(186)   # Schaft horizontal
    d.line([(ax, cy), (bx, cy)], fill=BONE, width=sc(11))
    r, off = sc(9), sc(8)                    # Knoten-Radius / Versatz
    for cx in (ax, bx):
        d.ellipse([cx - r, cy - off - r, cx + r, cy - off + r], fill=BONE)
        d.ellipse([cx - r, cy + off - r, cx + r, cy + off + r], fill=BONE)

    return img


def main():
    master = draw_master(256)
    master.save("logo.png")
    # Mehrere Aufloesungen ins .ico (Windows waehlt die passende)
    master.save("app.ico",
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                       (64, 64), (128, 128), (256, 256)])
    print("geschrieben: logo.png, app.ico")


if __name__ == "__main__":
    main()
