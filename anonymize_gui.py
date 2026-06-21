#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
anonymize_gui.py — kleine grafische Oberflaeche zum Schwaerzen von
Patientendaten in radiologischen Bild-Exporten.

Nutzt die Logik aus anonymize_core.py:
  * AUTO    – Header oben links (Name + Geburtsdatum) automatisch.
  * MANUELL – optionale Zusatzfelder (z. B. eingebettetes Panel in Abb. 3).
  * OCR     – optionale Namenssuche im ganzen Bild (falls Tesseract installiert).

Start:  python anonymize_gui.py
Benoetigt: Python mit tkinter (Standard bei Windows-/Mac-Python; unter
Linux/WSL ggf.  sudo apt install python3-tk) und Pillow.
"""

import os
import sys
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser

from PIL import Image, ImageTk

import anonymize_core as ac

PREVIEW_MAX = (760, 620)   # groesser = feineres Ziehen von Hand
THUMB_MAX = (170, 140)     # Groesse der Galerie-Vorschaubilder
GALLERY_COLS = 2           # Spalten in der Galerie


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Röntgenbild-Anonymisierung")
        self.minsize(1180, 700)
        self._set_window_icon()

        self.inputs = []                       # gewaehlte Dateien/Ordner
        self.out_var = tk.StringVar()
        self.lines_var = tk.IntVar(value=2)
        self.ocr_name_var = tk.StringVar()
        self.use_ocr_var = tk.BooleanVar(value=False)
        self.extra_var = tk.StringVar()        # "x0,y0,x1,y1[:R,G,B]"
        self.fill_var = tk.StringVar(value="black")
        self._msg_q = queue.Queue()
        self._preview_imgtk = None

        # Per Maus gezogene Zusatzfelder, je Bild (Originalkoordinaten):
        self.drawn = {}                # {Dateiname: [(x0, y0, x1, y1), ...]}
        self.preview_base = None       # Dateiname des aktuell gezeigten Bildes
        self.preview_scale = 1.0       # Anzeige / Original
        self.preview_disp = (0, 0)     # Groesse des angezeigten (skalierten) Bildes
        self._drag = None              # (startx, starty, canvas-rect-id)
        self.zoom = 1.0                # 1.0 = einpassen (Fit); >1 = hineingezoomt
        self.draw_fill = "auto"        # Fuellfarbe NEUER gezeichneter Felder
        self._picking = False          # Pipette aktiv?

        # Galerie-Zustand
        self.image_paths = []          # alle (aufgeloesten) Bildpfade
        self.selected_path = None      # aktuell gewaehltes Bild (gross)
        self.thumb_cells = {}          # pfad -> Rahmen-Widget
        self.thumb_labels = {}         # pfad -> Bild-Label
        self._thumb_refs = {}          # pfad -> PhotoImage (Referenz halten)

        self._build_ui()
        self._check_ocr()
        self.after(100, self._drain_queue)

    # --------------------------------------------------------------- UI ---
    def _build_ui(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)
        left = ttk.Frame(root)
        left.pack(side="left", fill="y")
        mid = ttk.Frame(root)
        mid.pack(side="left", fill="y", padx=(12, 0))
        right = ttk.Frame(root)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))

        # --- Eingabe ---
        box = ttk.LabelFrame(left, text="1) Bilder", padding=8)
        box.pack(fill="x")
        ttk.Button(box, text="Dateien wählen…",
                   command=self._pick_files).pack(fill="x")
        ttk.Button(box, text="Ordner wählen…",
                   command=self._pick_folder).pack(fill="x", pady=(4, 0))
        ttk.Button(box, text="Liste leeren",
                   command=self._clear_inputs).pack(fill="x", pady=(4, 0))

        # --- Galerie (alle Bilder als Vorschau) ---
        gal = ttk.LabelFrame(mid, text="Galerie – Bild anklicken", padding=6)
        gal.pack(fill="both", expand=True)
        gcanvas = tk.Canvas(gal, width=GALLERY_COLS * (THUMB_MAX[0] + 14),
                            highlightthickness=0, background="#2b2b2b")
        vsb = ttk.Scrollbar(gal, orient="vertical", command=gcanvas.yview)
        gcanvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        gcanvas.pack(side="left", fill="both", expand=True)
        self.gallery_inner = ttk.Frame(gcanvas)
        self._gal_window = gcanvas.create_window((0, 0), window=self.gallery_inner,
                                                 anchor="nw")
        self.gallery_inner.bind(
            "<Configure>",
            lambda e: gcanvas.configure(scrollregion=gcanvas.bbox("all")))
        gcanvas.bind(
            "<Configure>",
            lambda e: gcanvas.itemconfig(self._gal_window, width=e.width))
        self.gallery_canvas = gcanvas
        gcanvas.bind("<MouseWheel>", self._on_gallery_wheel)        # Mausrad

        # --- Optionen ---
        opt = ttk.LabelFrame(left, text="2) Optionen", padding=8)
        opt.pack(fill="x", pady=(10, 0))
        row = ttk.Frame(opt); row.pack(fill="x")
        ttk.Label(row, text="Header-Zeilen (Name+Geb.=2):").pack(side="left")
        ttk.Spinbox(row, from_=0, to=6, width=4, textvariable=self.lines_var,
                    command=self._on_options).pack(side="right")

        row = ttk.Frame(opt); row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text="Header-Füllung:").pack(side="left")
        fill_cb = ttk.Combobox(row, width=10, state="readonly",
                               textvariable=self.fill_var, values=["black", "auto"])
        fill_cb.pack(side="right")
        fill_cb.bind("<<ComboboxSelected>>", lambda e: self._on_options())

        # Füllfarbe für per Maus gezogene Felder (auto / Pipette / Farbwähler)
        row = ttk.Frame(opt); row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text="Feldfarbe (Maus):").pack(side="left")
        self.fill_swatch = tk.Label(row, width=6, text="auto", relief="solid",
                                    borderwidth=1)
        self.fill_swatch.pack(side="right")
        row = ttk.Frame(opt); row.pack(fill="x", pady=(2, 0))
        ttk.Button(row, text="auto", width=6,
                   command=lambda: self._set_draw_fill("auto")).pack(side="left")
        ttk.Button(row, text="Pipette", width=8,
                   command=self._start_pick).pack(side="left", padx=(4, 0))
        ttk.Button(row, text="Farbe…", width=8,
                   command=self._choose_color).pack(side="left", padx=(4, 0))

        self.ocr_chk = ttk.Checkbutton(opt, text="OCR-Namenssuche nutzen",
                                       variable=self.use_ocr_var,
                                       command=self._update_preview)
        self.ocr_chk.pack(anchor="w", pady=(8, 0))
        row = ttk.Frame(opt); row.pack(fill="x")
        ttk.Label(row, text="Patientenname:").pack(side="left")
        ttk.Entry(row, textvariable=self.ocr_name_var, width=20).pack(
            side="right", fill="x", expand=True)
        self.ocr_hint = ttk.Label(opt, text="", foreground="#a00")
        self.ocr_hint.pack(anchor="w")

        row = ttk.Frame(opt); row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="Zusatzfeld x0,y0,x1,y1[:R,G,B]:").pack(anchor="w")
        ttk.Entry(opt, textvariable=self.extra_var).pack(fill="x")
        ttk.Label(opt, text="(leer lassen, wenn nicht benötigt – gilt für alle "
                            "gewählten Bilder)", foreground="#666",
                  wraplength=260).pack(anchor="w")
        ttk.Button(opt, text="Vorschau aktualisieren",
                   command=self._on_options).pack(fill="x", pady=(8, 0))

        # --- Ausgabe + Start ---
        out = ttk.LabelFrame(left, text="3) Ausgabe", padding=8)
        out.pack(fill="x", pady=(10, 0))
        ttk.Entry(out, textvariable=self.out_var).pack(fill="x")
        ttk.Button(out, text="Ordner wählen…",
                   command=self._pick_outdir).pack(fill="x", pady=(4, 0))
        self.run_btn = ttk.Button(out, text="▶  Alle anonymisieren",
                                  command=self._run)
        self.run_btn.pack(fill="x", pady=(8, 0))

        # --- Vorschau (interaktiv, zoombar) + Log ---
        pv = ttk.LabelFrame(
            right, text="Vorschau – ziehen = Feld · Rechtsklick = löschen · "
                        "Strg+Mausrad = Zoom", padding=8)
        pv.pack(fill="both", expand=True)
        bar = ttk.Frame(pv)
        bar.pack(fill="x")
        ttk.Button(bar, text="Felder löschen",
                   command=self._clear_drawn).pack(side="right")
        ttk.Button(bar, text="Letztes Feld",
                   command=self._undo_drawn).pack(side="right", padx=(0, 4))
        # Zoom-Steuerung
        ttk.Button(bar, text="Fit", width=4,
                   command=self._zoom_reset).pack(side="left")
        ttk.Button(bar, text="−", width=3,
                   command=self._zoom_out).pack(side="left", padx=(6, 0))
        self.zoom_lbl = ttk.Label(bar, text="×1.0", width=6, anchor="center")
        self.zoom_lbl.pack(side="left")
        ttk.Button(bar, text="+", width=3,
                   command=self._zoom_in).pack(side="left")

        cwrap = ttk.Frame(pv)
        cwrap.pack(fill="both", expand=True, pady=(6, 0))
        self.canvas = tk.Canvas(cwrap, background="#222", highlightthickness=0,
                                cursor="crosshair")
        hsb = ttk.Scrollbar(cwrap, orient="horizontal", command=self.canvas.xview)
        vsb = ttk.Scrollbar(cwrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hsb.set, yscrollcommand=vsb.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        cwrap.rowconfigure(0, weight=1)
        cwrap.columnconfigure(0, weight=1)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._on_rightclick)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<MouseWheel>", self._on_canvas_wheel)          # scrollen
        self.canvas.bind("<Shift-MouseWheel>", self._on_canvas_wheel_h)  # horizontal
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_wheel)    # zoomen
        self._last_canvas_size = (0, 0)

        self.log = tk.Text(right, height=8, width=50, state="disabled")
        self.log.pack(fill="x", pady=(8, 0))

    # ------------------------------------------------------------ Helpers ---
    def _set_window_icon(self):
        """Setzt das Fenster-/Taskleisten-Symbol (app.ico), wenn vorhanden.
        Funktioniert aus dem Quellcode wie auch im PyInstaller-Bundle."""
        base = getattr(sys, "_MEIPASS",
                       os.path.dirname(os.path.abspath(__file__)))
        ico = os.path.join(base, "app.ico")
        try:
            if os.path.exists(ico):
                self.iconbitmap(ico)
        except Exception:  # noqa: BLE001
            pass

    def _check_ocr(self):
        if ac.ocr_available():
            self.ocr_hint.config(text="Tesseract gefunden – OCR verfügbar.",
                                 foreground="#070")
        else:
            self.use_ocr_var.set(False)
            self.ocr_chk.state(["disabled"])
            self.ocr_hint.config(
                text="Tesseract nicht gefunden – OCR deaktiviert.\n"
                     "(Auto + Zusatzfelder funktionieren weiter.)")

    def _log(self, text):
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # ----------------------------------------------------------- Galerie ---
    def _refresh_gallery(self):
        """Baut die Thumbnail-Galerie aus allen gewaehlten Bildern neu auf."""
        for w in self.gallery_inner.winfo_children():
            w.destroy()
        self.thumb_cells.clear()
        self.thumb_labels.clear()
        self._thumb_refs.clear()
        self.image_paths = list(ac.iter_image_paths(self.inputs))
        for i, p in enumerate(self.image_paths):
            self._make_cell(p, i // GALLERY_COLS, i % GALLERY_COLS)
        if self.image_paths and self.selected_path not in self.image_paths:
            self.selected_path = self.image_paths[0]
        self._highlight_selected()

    def _make_cell(self, path, row, col):
        cell = tk.Frame(self.gallery_inner, bg="#2b2b2b",
                        highlightthickness=2, highlightbackground="#2b2b2b")
        cell.grid(row=row, column=col, padx=3, pady=3)
        img_lbl = tk.Label(cell, bg="#222")
        img_lbl.pack()
        txt_lbl = tk.Label(cell, text=os.path.basename(path), fg="#ddd",
                           bg="#2b2b2b", wraplength=THUMB_MAX[0], font=("", 8))
        txt_lbl.pack()
        for w in (cell, img_lbl, txt_lbl):
            w.bind("<Button-1>", lambda e, p=path: self._select_path(p))
            w.bind("<MouseWheel>", self._on_gallery_wheel)
        self.thumb_cells[path] = cell
        self.thumb_labels[path] = img_lbl
        self._render_thumb(path)

    def _on_gallery_wheel(self, e):
        self.gallery_canvas.yview_scroll(int(-e.delta / 120), "units")

    def _on_canvas_resize(self, e):
        # Vorschau neu einpassen, wenn sich die Canvas-Groesse spuerbar aendert
        lw, lh = self._last_canvas_size
        if abs(e.width - lw) > 4 or abs(e.height - lh) > 4:
            if self.selected_path:
                self._update_preview()

    # ------------------------------------------------------------- Zoom ---
    def _set_zoom(self, z):
        self.zoom = max(0.2, min(8.0, z))
        self.zoom_lbl.config(text=f"×{self.zoom:.1f}")
        if self.selected_path:
            self._update_preview()

    def _zoom_in(self):
        self._set_zoom(self.zoom * 1.25)

    def _zoom_out(self):
        self._set_zoom(self.zoom / 1.25)

    def _zoom_reset(self):
        self._set_zoom(1.0)

    def _on_ctrl_wheel(self, e):
        self._set_zoom(self.zoom * (1.25 if e.delta > 0 else 0.8))
        return "break"

    def _on_canvas_wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def _on_canvas_wheel_h(self, e):
        self.canvas.xview_scroll(int(-e.delta / 120), "units")

    # ------------------------------------------------- Feldfarbe / Pipette ---
    @staticmethod
    def _rgb_hex(c):
        return "#%02x%02x%02x" % (int(c[0]), int(c[1]), int(c[2]))

    def _set_draw_fill(self, val):
        """Setzt die Füllfarbe für NEU gezogene Felder ('auto' oder (r,g,b))."""
        self.draw_fill = val
        if isinstance(val, (tuple, list)):
            self.fill_swatch.config(text=self._rgb_hex(val),
                                    background=self._rgb_hex(val), foreground="#fff")
        else:
            self.fill_swatch.config(text="auto", background="SystemButtonFace",
                                    foreground="#000")

    def _choose_color(self):
        init = self.draw_fill if isinstance(self.draw_fill, (tuple, list)) else (0, 17, 40)
        res = colorchooser.askcolor(color=self._rgb_hex(init),
                                    title="Feldfarbe wählen")
        if res and res[0]:
            self._set_draw_fill(tuple(int(c) for c in res[0]))
            self._log(f"Feldfarbe gesetzt: RGB {self.draw_fill}")

    def _start_pick(self):
        if not self.selected_path:
            return
        self._picking = True
        self.canvas.config(cursor="dotbox")
        self._log("Pipette aktiv: in die Vorschau klicken, um eine Farbe zu übernehmen.")

    def _pick_color_at(self, e):
        self._picking = False
        self.canvas.config(cursor="crosshair")
        if not self.selected_path:
            return
        s = self.preview_scale or 1.0
        cx, cy = self._cxy(e)
        ox, oy = int(cx / s), int(cy / s)
        try:
            img = Image.open(self.selected_path).convert("RGB")
            ox = max(0, min(ox, img.width - 1))
            oy = max(0, min(oy, img.height - 1))
            col = img.getpixel((ox, oy))
        except Exception as ex:  # noqa: BLE001
            self._log(f"Pipette-Fehler: {ex}")
            return
        self._set_draw_fill(tuple(col))
        self._log(f"Farbe übernommen: RGB {tuple(col)} bei ({ox},{oy})")

    def _render_thumb(self, path):
        """Rendert ein (anonymisiertes) Galerie-Vorschaubild – ohne OCR (schnell)."""
        if path not in self.thumb_labels:
            return
        base = os.path.basename(path)
        try:
            anon, _ = ac.anonymize_image(
                Image.open(path), lines=self.lines_var.get(),
                extra=list(self.drawn.get(base, [])),
                header_fill=self.fill_var.get())
        except Exception as e:  # noqa: BLE001
            self._log(f"Thumbnail-Fehler {base}: {e}")
            return
        anon.thumbnail(THUMB_MAX)
        ph = ImageTk.PhotoImage(anon)
        self._thumb_refs[path] = ph
        self.thumb_labels[path].config(image=ph)

    def _select_path(self, path):
        self.selected_path = path
        self._highlight_selected()
        self._update_preview()

    def _rerender_all_thumbs(self):
        for p in list(self.image_paths):
            self._render_thumb(p)

    def _on_options(self):
        """Optionen (Zeilen/Füllfarbe) wirken auf Galerie UND grosse Vorschau."""
        self._rerender_all_thumbs()
        self._update_preview()

    def _highlight_selected(self):
        for p, cell in self.thumb_cells.items():
            cell.configure(highlightbackground=(
                "#1a73e8" if p == self.selected_path else "#2b2b2b"))

    def _default_outdir(self):
        if not self.inputs:
            return
        first = self.inputs[0]
        base = first if os.path.isdir(first) else os.path.dirname(first)
        self.out_var.set(os.path.join(os.path.dirname(base.rstrip("/\\")) or base,
                                      "annonymisiert"))

    def _parse_extra(self):
        v = self.extra_var.get().strip()
        if not v:
            return []
        try:
            return ac._parse_extra([v])
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Zusatzfeld ungültig", str(e))
            return []

    # ------------------------------------------------------------ Actions ---
    def _pick_files(self):
        paths = filedialog.askopenfilenames(
            title="Bilder wählen",
            filetypes=[("Bilder", "*.png *.jpg *.jpeg *.tif *.tiff *.bmp"),
                       ("Alle Dateien", "*.*")])
        if paths:
            self.inputs.extend(paths)
            self._refresh_gallery()
            if not self.out_var.get():
                self._default_outdir()
            self._update_preview()

    def _pick_folder(self):
        d = filedialog.askdirectory(title="Ordner mit Bildern wählen")
        if d:
            self.inputs.append(d)
            self._refresh_gallery()
            if not self.out_var.get():
                self._default_outdir()
            self._update_preview()

    def _pick_outdir(self):
        d = filedialog.askdirectory(title="Ausgabeordner wählen")
        if d:
            self.out_var.set(d)

    def _clear_inputs(self):
        self.inputs = []
        self.selected_path = None
        self.preview_base = None
        self._refresh_gallery()
        self.canvas.delete("all")

    def _selected_preview_path(self):
        """Pfad des aktuell gewaehlten Galerie-Bildes (oder erstes)."""
        if self.selected_path and os.path.exists(self.selected_path):
            return self.selected_path
        paths = list(ac.iter_image_paths(self.inputs))
        return paths[0] if paths else None

    def _common_kwargs(self):
        return dict(
            lines=self.lines_var.get(),
            extra=self._parse_extra(),
            ocr_names=self.ocr_name_var.get() if self.use_ocr_var.get() else None,
            header_fill=self.fill_var.get(),
            extra_fill="auto",
            ocr_fill="auto",
        )

    def _update_preview(self):
        path = self._selected_preview_path()
        if not path:
            return
        base = os.path.basename(path)
        self.preview_base = base
        kwargs = self._common_kwargs()
        # globale (Text-)Zusatzfelder + die per Maus gezeichneten dieses Bildes
        kwargs["extra"] = list(kwargs.get("extra") or []) + \
            list(self.drawn.get(base, []))
        try:
            img = Image.open(path)
            anon, applied = ac.anonymize_image(img, **kwargs)
        except Exception as e:  # noqa: BLE001
            self._log(f"Vorschau-Fehler: {e}")
            return

        # Anzeigegroesse = an Canvas einpassen (Fit) * Zoomfaktor. Direkt aus dem
        # Originalbild skalieren (auch beim Hineinzoomen scharf). Vor der
        # Realisierung des Fensters auf PREVIEW_MAX zurueckfallen.
        ow, oh = anon.size
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        cw = cw if cw > 50 else PREVIEW_MAX[0]
        ch = ch if ch > 50 else PREVIEW_MAX[1]
        self._last_canvas_size = (cw, ch)
        fit = min(cw / ow, ch / oh) if ow and oh else 1.0
        disp_scale = fit * self.zoom
        dw, dh = max(1, int(ow * disp_scale)), max(1, int(oh * disp_scale))
        prev = anon.resize((dw, dh))
        self.preview_disp = (dw, dh)
        self.preview_scale = disp_scale
        self._preview_imgtk = ImageTk.PhotoImage(prev)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._preview_imgtk)
        self.canvas.configure(scrollregion=(0, 0, dw, dh))
        # gezeichnete Felder zusaetzlich rot umranden (zum Erkennen/Loeschen)
        s = self.preview_scale
        for box in self.drawn.get(base, []):
            x0, y0, x1, y1 = box[:4]
            self.canvas.create_rectangle(x0 * s, y0 * s, x1 * s, y1 * s,
                                         outline="#ff3030", width=2)
        # Galerie-Thumbnail des aktuellen Bildes mitziehen
        if self.selected_path in self.thumb_labels:
            self._render_thumb(self.selected_path)
        self._log(f"Vorschau {base}: {len(applied)} Feld(er)")

    # ------------------------------------------------- Maus: Felder ziehen ---
    def _cxy(self, e):
        """Widget- in Canvas-(Inhalts-)Koordinaten umrechnen (beruecksichtigt Scroll)."""
        return self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)

    def _on_press(self, e):
        if self._picking:                  # Pipette: Farbe aus Bild aufnehmen
            self._pick_color_at(e)
            return
        x, y = self._cxy(e)
        rid = self.canvas.create_rectangle(x, y, x, y,
                                           outline="#ff3030", width=2, dash=(3, 2))
        self._drag = (x, y, rid)

    def _on_drag(self, e):
        if self._drag:
            x0, y0, rid = self._drag
            x, y = self._cxy(e)
            self.canvas.coords(rid, x0, y0, x, y)

    def _on_release(self, e):
        if not self._drag or not self.preview_base:
            self._drag = None
            return
        x0, y0, rid = self._drag
        self._drag = None
        self.canvas.delete(rid)
        x, y = self._cxy(e)
        dw, dh = self.preview_disp
        xa, xb = sorted((x0, x))
        ya, yb = sorted((y0, y))
        # auf Bildflaeche begrenzen
        xa, xb = max(0, min(xa, dw)), max(0, min(xb, dw))
        ya, yb = max(0, min(ya, dh)), max(0, min(yb, dh))
        if xb - xa < 4 or yb - ya < 4:
            return  # zu kleiner Klick -> ignorieren
        s = self.preview_scale or 1.0
        box = (int(xa / s), int(ya / s), int(xb / s), int(yb / s), self.draw_fill)
        self.drawn.setdefault(self.preview_base, []).append(box)
        self._log(f"Feld hinzugefügt ({self.preview_base}): {box}")
        self._update_preview()

    def _on_rightclick(self, e):
        base = self.preview_base
        boxes = self.drawn.get(base or "", [])
        if not boxes:
            return
        s = self.preview_scale or 1.0
        cx, cy = self._cxy(e)
        ox, oy = cx / s, cy / s
        for i, box in enumerate(boxes):
            x0, y0, x1, y1 = box[:4]
            if x0 <= ox <= x1 and y0 <= oy <= y1:
                removed = boxes.pop(i)
                self._log(f"Feld entfernt ({base}): {removed}")
                self._update_preview()
                return

    def _undo_drawn(self):
        boxes = self.drawn.get(self.preview_base or "", [])
        if boxes:
            boxes.pop()
            self._update_preview()

    def _clear_drawn(self):
        if self.drawn.get(self.preview_base or ""):
            self.drawn[self.preview_base] = []
            self._update_preview()

    def _run(self):
        if not self.inputs:
            messagebox.showwarning("Keine Bilder", "Bitte zuerst Bilder wählen.")
            return
        out = self.out_var.get().strip()
        if not out:
            messagebox.showwarning("Kein Ausgabeordner",
                                   "Bitte einen Ausgabeordner wählen.")
            return
        self.run_btn.state(["disabled"])
        self._log(f"--- Starte Anonymisierung nach: {out} ---")
        kwargs = self._common_kwargs()
        t = threading.Thread(target=self._worker, args=(out, kwargs), daemon=True)
        t.start()

    def _worker(self, out, kwargs):
        def progress(path, applied, err):
            name = os.path.basename(path)
            self._msg_q.put(("log", f"  {name}: "
                             + (err if err else f"{len(applied)} Feld(er)")))
        try:
            res = ac.process(self.inputs, out, overwrite=True,
                             progress=progress,
                             per_file_extra={k: list(v) for k, v in self.drawn.items()},
                             **kwargs)
            self._msg_q.put(("log", f"Fertig: {len(res)} Bild(er) geschrieben."))
            self._msg_q.put(("done", out))
        except Exception as e:  # noqa: BLE001
            self._msg_q.put(("log", f"FEHLER: {e}"))
            self._msg_q.put(("done", None))

    def _drain_queue(self):
        try:
            while True:
                kind, payload = self._msg_q.get_nowait()
                if kind == "log":
                    self._log(payload)
                elif kind == "done":
                    self.run_btn.state(["!disabled"])
                    if payload:
                        messagebox.showinfo(
                            "Fertig", "Anonymisierung abgeschlossen.\n\n"
                            "Bitte die Ergebnisse visuell prüfen!\n" + payload)
        except queue.Empty:
            pass
        self.after(150, self._drain_queue)


def _enable_dpi_awareness():
    """Macht den Prozess unter Windows DPI-aware -> scharfer Text bei
    Skalierung >100 %. Muss VOR dem Erzeugen des Fensters laufen."""
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # System-DPI-aware
        except Exception:  # noqa: BLE001
            ctypes.windll.user32.SetProcessDPIAware()        # aelterer Fallback
    except Exception:  # noqa: BLE001 (nicht-Windows o. nicht verfuegbar)
        pass


if __name__ == "__main__":
    _enable_dpi_awareness()
    App().mainloop()
