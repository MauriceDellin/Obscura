#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
anonymize_gui.py — grafische Oberflaeche zum Schwaerzen von Patientendaten
in radiologischen Bild-Exporten.

Die Vorschau ist ein kleiner Rechteck-Editor: jedes Feld (auch das automatisch
erkannte Header-Feld oben links) ist ein Objekt, das sich auswaehlen,
verschieben, in der Groesse aendern, umfaerben und loeschen laesst.

Nutzt die Logik aus anonymize_core.py (AUTO-Header, manuelle Felder, OCR).

Start:  python anonymize_gui.py
Benoetigt: Python mit tkinter und Pillow.
"""

import os
import sys
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser

from PIL import Image, ImageTk

import anonymize_core as ac

PREVIEW_MAX = (760, 620)   # Fallback-Vorschaugroesse vor Fenster-Realisierung
THUMB_MAX = (170, 140)     # Groesse der Galerie-Vorschaubilder
GALLERY_COLS = 2           # Spalten in der Galerie
HANDLE = 3                 # halbe Kantenlaenge der Resize-Griffe (Bildschirm-Px)
SEL_COLOR = "#ffd400"      # Farbe des ausgewaehlten Feldes
FIELD_COLOR = "#ff3030"    # Farbe der uebrigen Felder


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Obscura – Röntgenbild-Anonymisierung")
        self.minsize(1180, 700)
        self._set_window_icon()

        self.inputs = []
        self.out_var = tk.StringVar()
        self.lines_var = tk.IntVar(value=2)
        self.ocr_name_var = tk.StringVar()
        self.use_ocr_var = tk.BooleanVar(value=False)
        self.fill_var = tk.StringVar(value="black")   # Header-Fuellung
        self._msg_q = queue.Queue()
        self._preview_imgtk = None

        # Felder je Bild: dicts {x0,y0,x1,y1,fill,kind}; kind in {header,manual}
        self.fields = {}
        self.preview_base = None
        self.preview_scale = 1.0
        self._orig_size = (0, 0)
        self.zoom = 1.0
        self.draw_fill = "auto"        # Standard-Fuellfarbe NEUER Felder
        self.pan_var = tk.BooleanVar(value=False)  # Hand-/Verschiebemodus
        self.sel_index = None          # ausgewaehltes Feld im aktuellen Bild
        self._action = None            # ('new'|'move'|'resize', ...)
        self._press = (0, 0)           # Startpunkt (Originalkoord.) eines Drags
        self._orig_box = None          # Feldkoordinaten beim Drag-Start
        self._rubber = None            # Canvas-Item beim Aufziehen
        self._picking = False          # Pipette aktiv?

        # Galerie
        self.image_paths = []
        self.selected_path = None
        self.thumb_cells = {}
        self.thumb_labels = {}
        self._thumb_refs = {}
        self._last_canvas_size = (0, 0)

        self._build_ui()
        self._check_ocr()
        self.after(100, self._drain_queue)

    # --------------------------------------------------------------- UI ---
    def _build_ui(self):
        root = ttk.Frame(self, padding=10)
        root.pack(fill="both", expand=True)
        left = ttk.Frame(root); left.pack(side="left", fill="y")
        mid = ttk.Frame(root); mid.pack(side="left", fill="y", padx=(12, 0))
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

        # --- Galerie ---
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
        gcanvas.bind("<MouseWheel>", self._on_gallery_wheel)

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
        ttk.Button(opt, text="Auto-Felder neu erkennen",
                   command=self._on_options).pack(fill="x", pady=(6, 0))

        # Feldfarbe (auf ausgewaehltes Feld oder Standard fuer neue Felder)
        row = ttk.Frame(opt); row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="Feldfarbe:").pack(side="left")
        self.fill_swatch = tk.Label(row, width=7, text="auto", relief="solid",
                                    borderwidth=1)
        self.fill_swatch.pack(side="right")
        row = ttk.Frame(opt); row.pack(fill="x", pady=(2, 0))
        ttk.Button(row, text="auto", width=6,
                   command=lambda: self._apply_fill("auto")).pack(side="left")
        ttk.Button(row, text="Pipette", width=8,
                   command=self._start_pick).pack(side="left", padx=(4, 0))
        ttk.Button(row, text="Farbe…", width=8,
                   command=self._choose_color).pack(side="left", padx=(4, 0))
        ttk.Label(opt, text="(Feld auswählen → Farbe gilt für dieses Feld; "
                            "sonst für neue Felder)", foreground="#666",
                  wraplength=260).pack(anchor="w", pady=(2, 0))

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

        # --- Ausgabe + Start ---
        out = ttk.LabelFrame(left, text="3) Ausgabe", padding=8)
        out.pack(fill="x", pady=(10, 0))
        ttk.Entry(out, textvariable=self.out_var).pack(fill="x")
        ttk.Button(out, text="Ordner wählen…",
                   command=self._pick_outdir).pack(fill="x", pady=(4, 0))
        self.run_btn = ttk.Button(out, text="▶  Alle anonymisieren",
                                  command=self._run)
        self.run_btn.pack(fill="x", pady=(8, 0))

        # --- Vorschau (Editor) + Log ---
        pv = ttk.LabelFrame(
            right, text="Vorschau – ziehen = neues Feld · klicken = auswählen · "
                        "Griffe ziehen = Größe · Entf = löschen · Strg+Rad = Zoom",
            padding=8)
        pv.pack(fill="both", expand=True)
        bar = ttk.Frame(pv); bar.pack(fill="x")
        ttk.Button(bar, text="Alle Felder",
                   command=self._clear_fields).pack(side="right")
        ttk.Button(bar, text="Auswahl löschen",
                   command=self._delete_selected).pack(side="right", padx=(0, 4))
        ttk.Button(bar, text="Fit", width=4,
                   command=self._zoom_reset).pack(side="left")
        ttk.Button(bar, text="−", width=3,
                   command=self._zoom_out).pack(side="left", padx=(6, 0))
        self.zoom_lbl = ttk.Label(bar, text="×1.0", width=6, anchor="center")
        self.zoom_lbl.pack(side="left")
        ttk.Button(bar, text="+", width=3,
                   command=self._zoom_in).pack(side="left")
        ttk.Checkbutton(bar, text="✋ Verschieben", variable=self.pan_var,
                        command=self._toggle_pan).pack(side="left", padx=(12, 0))

        cwrap = ttk.Frame(pv); cwrap.pack(fill="both", expand=True, pady=(6, 0))
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
        self.canvas.bind("<Motion>", self._on_hover)
        # Bild verschieben (Pan): mittlere Maustaste (immer)
        self.canvas.bind("<ButtonPress-2>",
                         lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B2-Motion>",
                         lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        self.canvas.bind("<Button-3>", self._on_rightclick)
        self.canvas.bind("<Delete>", lambda e: self._delete_selected())
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<MouseWheel>", self._on_canvas_wheel)
        self.canvas.bind("<Shift-MouseWheel>", self._on_canvas_wheel_h)
        self.canvas.bind("<Control-MouseWheel>", self._on_ctrl_wheel)

        self.log = tk.Text(right, height=8, width=50, state="disabled")
        self.log.pack(fill="x", pady=(8, 0))

    # ------------------------------------------------------------ Helpers ---
    def _set_window_icon(self):
        base = getattr(sys, "_MEIPASS",
                       os.path.dirname(os.path.abspath(__file__)))
        ico = os.path.join(base, "app.ico")
        if not os.path.exists(ico):
            return
        # 1) als Default-Icon fuer alle Fenster (Titelleiste)
        try:
            self.iconbitmap(default=ico)
        except Exception:  # noqa: BLE001
            pass
        # 2) zusaetzlich per iconphoto (zuverlaessiger fuer die Taskleiste)
        try:
            self._icon_img = ImageTk.PhotoImage(Image.open(ico))
            self.iconphoto(True, self._icon_img)
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
                     "(Auto + manuelle Felder funktionieren weiter.)")

    def _log(self, text):
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    # -------------------------------------------------------- Feld-Modell ---
    def _seed_header(self, img):
        """Erkennt das Header-Feld und liefert ein Feld-dict (oder None)."""
        lines = self.lines_var.get()
        if lines <= 0:
            return None
        box = ac.header_box(img, lines=lines)
        if not box:
            return None
        return {"x0": box[0], "y0": box[1], "x1": box[2], "y1": box[3],
                "fill": self.fill_var.get(), "kind": "header"}

    def _ensure_seeded(self, base, img):
        """Legt beim ersten Sehen eines Bildes das Auto-Header-Feld an."""
        if base in self.fields:
            return
        hdr = self._seed_header(img)
        self.fields[base] = [hdr] if hdr else []

    def _reseed_headers(self):
        """Erkennt die Header-Felder aller Bilder neu (Zeilenzahl/Füllung)."""
        for p in self.image_paths:
            base = os.path.basename(p)
            try:
                img = Image.open(p)
            except Exception:  # noqa: BLE001
                continue
            rest = [f for f in self.fields.get(base, []) if f["kind"] != "header"]
            hdr = self._seed_header(img)
            self.fields[base] = ([hdr] if hdr else []) + rest
        self.sel_index = None

    def _cur_fields(self):
        return self.fields.setdefault(self.preview_base, []) \
            if self.preview_base else []

    def _fields_as_extra(self, base):
        return [(f["x0"], f["y0"], f["x1"], f["y1"], f["fill"])
                for f in self.fields.get(base, [])]

    # ----------------------------------------------------------- Galerie ---
    def _refresh_gallery(self):
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

    def _render_thumb(self, path):
        if path not in self.thumb_labels:
            return
        base = os.path.basename(path)
        try:
            img = Image.open(path)
            self._ensure_seeded(base, img)
            anon, _ = ac.anonymize_image(img, lines=0,
                                         extra=self._fields_as_extra(base))
        except Exception as e:  # noqa: BLE001
            self._log(f"Thumbnail-Fehler {base}: {e}")
            return
        anon.thumbnail(THUMB_MAX)
        ph = ImageTk.PhotoImage(anon)
        self._thumb_refs[path] = ph
        self.thumb_labels[path].config(image=ph)

    def _select_path(self, path):
        self.selected_path = path
        self.sel_index = None
        self._highlight_selected()
        self._update_preview()
        self._sync_swatch(self.draw_fill)

    def _rerender_all_thumbs(self):
        for p in list(self.image_paths):
            self._render_thumb(p)

    def _on_options(self):
        self._reseed_headers()
        self._rerender_all_thumbs()
        self._update_preview()

    def _highlight_selected(self):
        for p, cell in self.thumb_cells.items():
            cell.configure(highlightbackground=(
                "#1a73e8" if p == self.selected_path else "#2b2b2b"))

    def _on_gallery_wheel(self, e):
        self.gallery_canvas.yview_scroll(int(-e.delta / 120), "units")

    def _on_canvas_resize(self, e):
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

    def _sync_swatch(self, val):
        if isinstance(val, (tuple, list)):
            self.fill_swatch.config(text=self._rgb_hex(val),
                                    background=self._rgb_hex(val), foreground="#fff")
        else:
            self.fill_swatch.config(text="auto", background="SystemButtonFace",
                                    foreground="#000")

    def _apply_fill(self, val):
        """Setzt die Farbe: auf das ausgewaehlte Feld, sonst Standard fuer neue."""
        fields = self._cur_fields()
        if self.sel_index is not None and 0 <= self.sel_index < len(fields):
            fields[self.sel_index]["fill"] = val
            self._sync_swatch(val)
            self._update_preview()
        else:
            self.draw_fill = val
            self._sync_swatch(val)

    def _choose_color(self):
        cur = self.draw_fill
        fields = self._cur_fields()
        if self.sel_index is not None and 0 <= self.sel_index < len(fields):
            cur = fields[self.sel_index]["fill"]
        init = cur if isinstance(cur, (tuple, list)) else (0, 17, 40)
        res = colorchooser.askcolor(color=self._rgb_hex(init),
                                    title="Feldfarbe wählen")
        if res and res[0]:
            self._apply_fill(tuple(int(c) for c in res[0]))

    def _start_pick(self):
        if not self.selected_path:
            return
        self._picking = True
        try:
            self.canvas.config(cursor="dotbox")
        except tk.TclError:
            self.canvas.config(cursor="crosshair")
        self._log("Pipette: in die Vorschau klicken, um eine Farbe zu übernehmen.")

    def _pick_color_at(self, e):
        self._picking = False
        self.canvas.config(cursor="crosshair")
        if not self.selected_path:
            return
        ox, oy = self._oxy(e)
        try:
            img = Image.open(self.selected_path).convert("RGB")
            ox = max(0, min(int(ox), img.width - 1))
            oy = max(0, min(int(oy), img.height - 1))
            col = img.getpixel((ox, oy))
        except Exception as ex:  # noqa: BLE001
            self._log(f"Pipette-Fehler: {ex}")
            return
        self._log(f"Farbe übernommen: RGB {tuple(col)}")
        self._apply_fill(tuple(col))

    # ----------------------------------------------------- Koordinaten/Hit ---
    def _cxy(self, e):
        return self.canvas.canvasx(e.x), self.canvas.canvasy(e.y)

    def _oxy(self, e):
        """Maus -> Originalbild-Koordinaten (float)."""
        s = self.preview_scale or 1.0
        cx, cy = self._cxy(e)
        return cx / s, cy / s

    def _disp(self, ox, oy):
        s = self.preview_scale or 1.0
        return ox * s, oy * s

    @staticmethod
    def _handles(f):
        mx, my = (f["x0"] + f["x1"]) / 2, (f["y0"] + f["y1"]) / 2
        return {"nw": (f["x0"], f["y0"]), "n": (mx, f["y0"]), "ne": (f["x1"], f["y0"]),
                "e": (f["x1"], my), "se": (f["x1"], f["y1"]), "s": (mx, f["y1"]),
                "sw": (f["x0"], f["y1"]), "w": (f["x0"], my)}

    def _handle_at(self, f, ox, oy):
        tol = max((HANDLE + 3) / (self.preview_scale or 1.0), 5)
        for name, (hx, hy) in self._handles(f).items():
            if abs(ox - hx) <= tol and abs(oy - hy) <= tol:
                return name
        return None

    def _field_at(self, ox, oy):
        found = None
        for i, f in enumerate(self._cur_fields()):
            if f["x0"] <= ox <= f["x1"] and f["y0"] <= oy <= f["y1"]:
                found = i  # spaeteres Feld liegt oben
        return found

    # ----------------------------------------------------------- Rendering ---
    def _update_preview(self):
        if not self._render_image():
            return
        self._draw_overlays()
        if self.selected_path in self.thumb_labels:
            self._render_thumb(self.selected_path)

    def _render_image(self):
        path = self._selected_preview_path()
        if not path:
            return False
        base = os.path.basename(path)
        self.preview_base = base
        try:
            img = Image.open(path)
        except Exception as e:  # noqa: BLE001
            self._log(f"Vorschau-Fehler: {e}")
            return False
        self._ensure_seeded(base, img)
        ocr = self.ocr_name_var.get() if self.use_ocr_var.get() else None
        try:
            anon, applied = ac.anonymize_image(
                img, lines=0, extra=self._fields_as_extra(base), ocr_names=ocr)
        except Exception as e:  # noqa: BLE001
            self._log(f"Vorschau-Fehler: {e}")
            return False

        ow, oh = anon.size
        self._orig_size = (ow, oh)
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        cw = cw if cw > 50 else PREVIEW_MAX[0]
        ch = ch if ch > 50 else PREVIEW_MAX[1]
        self._last_canvas_size = (cw, ch)
        fit = min(cw / ow, ch / oh) if ow and oh else 1.0
        disp_scale = fit * self.zoom
        dw, dh = max(1, int(ow * disp_scale)), max(1, int(oh * disp_scale))
        self.preview_scale = disp_scale
        prev = anon.resize((dw, dh))
        self._preview_imgtk = ImageTk.PhotoImage(prev)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._preview_imgtk,
                                 tags="img")
        self.canvas.configure(scrollregion=(0, 0, dw, dh))
        return True

    def _draw_overlays(self):
        """Zeichnet Feld-Umrandungen + Griffe des ausgewaehlten Feldes."""
        self.canvas.delete("ov")
        s = self.preview_scale or 1.0
        fields = self._cur_fields()
        for i, f in enumerate(fields):
            sel = (i == self.sel_index)
            self.canvas.create_rectangle(
                f["x0"] * s, f["y0"] * s, f["x1"] * s, f["y1"] * s,
                outline=(SEL_COLOR if sel else FIELD_COLOR),
                width=(2 if sel else 1), tags="ov")
        if self.sel_index is not None and 0 <= self.sel_index < len(fields):
            for hx, hy in self._handles(fields[self.sel_index]).values():
                cx, cy = hx * s, hy * s
                self.canvas.create_rectangle(cx - HANDLE, cy - HANDLE,
                                             cx + HANDLE, cy + HANDLE,
                                             fill=SEL_COLOR, outline="#333", tags="ov")

    # --------------------------------------------------------- Maus-Editor ---
    def _on_press(self, e):
        self.canvas.focus_set()
        if self.pan_var.get():                 # Hand-Modus: Bild verschieben
            self.canvas.scan_mark(int(e.x), int(e.y))
            self._action = ("pan",)
            return
        if self._picking:
            self._pick_color_at(e)
            return
        if not self.preview_base:
            return
        ox, oy = self._oxy(e)
        fields = self._cur_fields()
        # 1) Griff des ausgewaehlten Feldes -> Groesse aendern
        if self.sel_index is not None and 0 <= self.sel_index < len(fields):
            h = self._handle_at(fields[self.sel_index], ox, oy)
            if h:
                f = fields[self.sel_index]
                self._action = ("resize", h)
                self._press = (ox, oy)
                self._orig_box = (f["x0"], f["y0"], f["x1"], f["y1"])
                return
        # 2) in einem Feld -> auswaehlen + verschieben
        idx = self._field_at(ox, oy)
        if idx is not None:
            self.sel_index = idx
            f = fields[idx]
            self._sync_swatch(f["fill"])
            self._action = ("move",)
            self._press = (ox, oy)
            self._orig_box = (f["x0"], f["y0"], f["x1"], f["y1"])
            self._draw_overlays()
            return
        # 3) leere Flaeche -> neues Feld aufziehen
        self.sel_index = None
        self._sync_swatch(self.draw_fill)
        self._action = ("new",)
        self._press = (ox, oy)
        dx, dy = self._disp(ox, oy)
        self._rubber = self.canvas.create_rectangle(
            dx, dy, dx, dy, outline=SEL_COLOR, width=2, dash=(3, 2))
        self._draw_overlays()

    def _on_drag(self, e):
        if not self._action:
            return
        if self._action[0] == "pan":
            self.canvas.scan_dragto(int(e.x), int(e.y), gain=1)
            return
        ow, oh = self._orig_size
        ox, oy = self._oxy(e)
        ox = max(0, min(ox, ow)); oy = max(0, min(oy, oh))
        kind = self._action[0]
        fields = self._cur_fields()
        if kind == "new":
            x0, y0 = self._press
            self.canvas.coords(self._rubber, *self._disp(min(x0, ox), min(y0, oy)),
                               *self._disp(max(x0, ox), max(y0, oy)))
        elif kind == "move" and self.sel_index is not None:
            x0, y0, x1, y1 = self._orig_box
            w, h = x1 - x0, y1 - y0
            nx0 = max(0, min(x0 + (ox - self._press[0]), ow - w))
            ny0 = max(0, min(y0 + (oy - self._press[1]), oh - h))
            f = fields[self.sel_index]
            f["x0"], f["y0"], f["x1"], f["y1"] = \
                int(nx0), int(ny0), int(nx0 + w), int(ny0 + h)
            self._draw_overlays()
        elif kind == "resize" and self.sel_index is not None:
            name = self._action[1]
            x0, y0, x1, y1 = self._orig_box
            if "w" in name:
                x0 = min(ox, x1 - 3)
            if "e" in name:
                x1 = max(ox, x0 + 3)
            if "n" in name:
                y0 = min(oy, y1 - 3)
            if "s" in name:
                y1 = max(oy, y0 + 3)
            f = fields[self.sel_index]
            f["x0"], f["y0"], f["x1"], f["y1"] = int(x0), int(y0), int(x1), int(y1)
            self._draw_overlays()

    def _on_release(self, e):
        act = self._action
        self._action = None
        if not act:
            return
        if act[0] == "pan":
            return                          # Pan veraendert keine Felder
        if act[0] == "new":
            if self._rubber:
                self.canvas.delete(self._rubber)
                self._rubber = None
            ow, oh = self._orig_size
            ox, oy = self._oxy(e)
            ox = max(0, min(ox, ow)); oy = max(0, min(oy, oh))
            x0, y0 = self._press
            xa, xb = sorted((x0, ox)); ya, yb = sorted((y0, oy))
            s = self.preview_scale or 1.0
            if (xb - xa) * s < 4 or (yb - ya) * s < 4:
                self._update_preview()      # zu klein -> nur Auswahl aufheben
                return
            fields = self._cur_fields()
            fields.append({"x0": int(xa), "y0": int(ya), "x1": int(xb),
                           "y1": int(yb), "fill": self.draw_fill, "kind": "manual"})
            self.sel_index = len(fields) - 1
            self._log(f"Feld hinzugefügt: ({int(xa)},{int(ya)},{int(xb)},{int(yb)})")
        self._update_preview()

    def _toggle_pan(self):
        try:
            self.canvas.config(
                cursor="fleur" if self.pan_var.get() else "crosshair")
        except tk.TclError:
            pass

    def _on_hover(self, e):
        """Cursor anpassen: Griff -> Resize, Feldinneres -> Move."""
        if self._action or self._picking or self.pan_var.get() \
                or not self.preview_base:
            return
        ox, oy = self._oxy(e)
        fields = self._cur_fields()
        cur = "crosshair"
        if self.sel_index is not None and 0 <= self.sel_index < len(fields):
            h = self._handle_at(fields[self.sel_index], ox, oy)
            if h:
                cur = {"n": "size_ns", "s": "size_ns",
                       "e": "size_we", "w": "size_we",
                       "nw": "size_nw_se", "se": "size_nw_se",
                       "ne": "size_ne_sw", "sw": "size_ne_sw"}.get(h, "fleur")
        if cur == "crosshair" and self._field_at(ox, oy) is not None:
            cur = "fleur"
        try:
            self.canvas.config(cursor=cur)
        except tk.TclError:
            self.canvas.config(cursor="")

    def _on_rightclick(self, e):
        if not self.preview_base:
            return
        ox, oy = self._oxy(e)
        idx = self._field_at(ox, oy)
        if idx is None:
            return
        f = self._cur_fields().pop(idx)
        if self.sel_index == idx:
            self.sel_index = None
        elif self.sel_index is not None and self.sel_index > idx:
            self.sel_index -= 1
        self._log(f"Feld entfernt: ({f['x0']},{f['y0']},{f['x1']},{f['y1']})")
        self._update_preview()

    def _delete_selected(self):
        fields = self._cur_fields()
        if self.sel_index is not None and 0 <= self.sel_index < len(fields):
            fields.pop(self.sel_index)
            self.sel_index = None
            self._sync_swatch(self.draw_fill)
            self._update_preview()

    def _clear_fields(self):
        if self.preview_base:
            self.fields[self.preview_base] = []
            self.sel_index = None
            self._update_preview()

    # ------------------------------------------------------------ Actions ---
    def _default_outdir(self):
        if not self.inputs:
            return
        first = self.inputs[0]
        base = first if os.path.isdir(first) else os.path.dirname(first)
        self.out_var.set(os.path.join(os.path.dirname(base.rstrip("/\\")) or base,
                                      "annonymisiert"))

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
        self.sel_index = None
        self.fields.clear()
        self._refresh_gallery()
        self.canvas.delete("all")

    def _selected_preview_path(self):
        if self.selected_path and os.path.exists(self.selected_path):
            return self.selected_path
        paths = list(ac.iter_image_paths(self.inputs))
        return paths[0] if paths else None

    # --------------------------------------------------------------- Run ---
    def _run(self):
        if not self.inputs:
            messagebox.showwarning("Keine Bilder", "Bitte zuerst Bilder wählen.")
            return
        out = self.out_var.get().strip()
        if not out:
            messagebox.showwarning("Kein Ausgabeordner",
                                   "Bitte einen Ausgabeordner wählen.")
            return
        # sicherstellen, dass jedes Bild Felder hat (Header erkannt)
        for p in self.image_paths:
            base = os.path.basename(p)
            if base not in self.fields:
                try:
                    self._ensure_seeded(base, Image.open(p))
                except Exception:  # noqa: BLE001
                    pass
        per_file = {os.path.basename(p): self._fields_as_extra(os.path.basename(p))
                    for p in self.image_paths}
        ocr = self.ocr_name_var.get() if self.use_ocr_var.get() else None
        kwargs = dict(lines=0, extra=[], ocr_names=ocr,
                      header_fill="black", extra_fill="auto", ocr_fill="auto")
        self.run_btn.state(["disabled"])
        self._log(f"--- Starte Anonymisierung nach: {out} ---")
        t = threading.Thread(target=self._worker, args=(out, kwargs, per_file),
                             daemon=True)
        t.start()

    def _worker(self, out, kwargs, per_file):
        def progress(path, applied, err):
            name = os.path.basename(path)
            self._msg_q.put(("log", f"  {name}: "
                             + (err if err else f"{len(applied)} Feld(er)")))
        try:
            res = ac.process(self.inputs, out, overwrite=True, progress=progress,
                             per_file_extra=per_file, **kwargs)
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
    """Macht den Prozess unter Windows DPI-aware -> scharfer Text."""
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:  # noqa: BLE001
        pass


def _set_app_user_model_id():
    """Eigene Taskleisten-Gruppe + eigenes Symbol statt des Tk-Standardsymbols."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Dellin.Obscura")
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    _enable_dpi_awareness()
    _set_app_user_model_id()
    App().mainloop()
