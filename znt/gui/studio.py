#!/usr/bin/env python3
"""Visual editor for the VN framework (tkinter). Drives the real `VNRuntime`:
live stage with the engine, scene and step lists, property editing, Play, and
export to `.vn` + HTML player. The runtime does not import it (decoupled frontend)."""
import os, base64

from .. import vn
from ..vnstudio import VNRuntime, POS, ACTIONS
from ..engine import CURVES

STEP_OPS = ["bg", "show", "hide", "say", "animate", "bgm", "se", "choice", "goto", "end"]
AUDIO_EXTS = (".ogg", ".mp3", ".wav", ".m4a")
BG = "#0e1220"; PANEL = "#141a2c"; INK = "#dfe7f5"; MUT = "#8493b5"; ACC = "#e8b04b"


def _fresh():
    return {"title": "Nueva VN",
            "characters": {"narrator": {"name": "", "color": "#cccccc"}},
            "scenes": {"inicio": []}, "order": ["inicio"], "start": "inicio"}


def _default_step(op, model):
    chars = [c for c in model["characters"] if c != "narrator"] or ["narrator"]
    return {
        "bg": {"op": "bg", "spec": {"kind": "grad", "a": "#101828", "b": "#304060"}},
        "show": {"op": "show", "id": chars[0], "pos": "center"},
        "hide": {"op": "hide", "id": chars[0]},
        "say": {"op": "say", "who": chars[0], "text": "..."},
        "animate": {"op": "animate", "id": chars[0], "kind": "jump", "params": {"vib": 18, "cycle": 340}},
        "bgm": {"op": "bgm", "file": ""},
        "se": {"op": "se", "file": ""},
        "choice": {"op": "choice", "options": []},
        "goto": {"op": "goto", "target": model["order"][0]},
        "end": {"op": "end"},
    }[op]


def run_editor(path=None):
    import tkinter as tk
    from tkinter import ttk, filedialog, simpledialog, messagebox, font as tkfont

    if path and os.path.exists(path):
        model = vn._link_choices(vn.parse(open(path, encoding="utf-8").read()))
        base = os.path.dirname(os.path.abspath(path)); cur = {"path": path}
    else:
        model = vn.blank_model(); base = os.getcwd(); cur = {"path": None}
    rt = VNRuntime(model, base)
    st = {"scene": model["order"][0], "step": -1, "play": False}
    drag = {"name": None, "ox": 0, "oy": 0, "step": None}
    import copy
    hist = {"undo": [], "redo": [], "max": 60}

    def _rel(p):
        try: return os.path.relpath(p, base)
        except ValueError: return p

    root = tk.Tk(); root.title("znt · VN Studio"); root.configure(bg=BG)

    # --- UI font size (named fonts -> live rescaling) ---------------------------
    _style = ttk.Style()

    def _pick_family(cands):
        """Pick a family that EXISTS in this Tk (do not assume 'sans'/'monospace')."""
        fams = set(tkfont.families())
        for c in cands:
            if c in fams:
                return c
        return tkfont.nametofont("TkDefaultFont").actual("family")

    SANS = _pick_family(("DejaVu Sans", "Liberation Sans", "Noto Sans", "Cantarell",
                         "Helvetica", "Arial", "sans-serif"))
    MONO = _pick_family(("DejaVu Sans Mono", "Liberation Mono", "Noto Sans Mono",
                         "Hack", "Courier New", "monospace"))
    _FBASE = {"ui": (9, "normal", SANS), "ui10": (10, "normal", SANS),
              "bold": (11, "bold", SANS), "big": (12, "normal", SANS),
              "mono": (9, "normal", MONO)}
    F = {k: tkfont.Font(family=fam, size=sz, weight=wt) for k, (sz, wt, fam) in _FBASE.items()}
    ui_scale = {"v": 1.0, "warned": False}

    def _fonts_scalable():
        """A Tk without Xft/fontconfig only sees the bitmap 'fixed' and IGNORES the size."""
        probe = tkfont.Font(family=SANS, size=9)
        a = probe.measure("Save"); probe.configure(size=18)
        return a != probe.measure("Save")

    FONTS_SCALABLE = _fonts_scalable()

    def apply_ui_scale():
        for k, (sz, wt, fam) in _FBASE.items():
            F[k].configure(size=max(6, round(sz * ui_scale["v"])))
        for nm in ("TkDefaultFont", "TkTextFont", "TkFixedFont", "TkMenuFont"):
            try: tkfont.nametofont(nm).configure(size=max(6, round(9 * ui_scale["v"])))
            except tk.TclError: pass
        _style.configure("TCombobox", font=F["ui"])
        root.option_add("*TCombobox*Listbox.font", F["ui"])

    def bump_ui(d):
        if not FONTS_SCALABLE:                 # warn instead of silently doing nothing
            if not ui_scale["warned"]:
                ui_scale["warned"] = True
                messagebox.showwarning(
                    "Fonts not scalable",
                    "This Tk has no scalable font support (Xft/fontconfig): it only sees "
                    f"the fixed-size family '{SANS}', so it ignores the requested size.\n\n"
                    "Fix: install Tcl/Tk with Xft and use a Python whose tkinter uses it.\n"
                    "On Arch:  sudo pacman -S tk   and run the editor with /usr/bin/python3")
            return
        ui_scale["v"] = min(2.5, max(0.7, round(ui_scale["v"] + d, 2))); apply_ui_scale()
    apply_ui_scale()
    root.bind("<Control-plus>", lambda e: bump_ui(0.1))
    root.bind("<Control-equal>", lambda e: bump_ui(0.1))
    root.bind("<Control-minus>", lambda e: bump_ui(-0.1))
    root.bind("<Control-0>", lambda e: (ui_scale.update(v=1.0), apply_ui_scale()))
    tkimg = {}

    # ---- layout: stage on the left (rescales), panels on the right ---------
    root.columnconfigure(0, weight=1); root.rowconfigure(0, weight=1)
    stagef = tk.Frame(root, bg=BG); stagef.grid(row=0, column=0, padx=8, pady=8, sticky="nsew")
    canvas = tk.Canvas(stagef, width=rt.W, height=rt.H, highlightthickness=1,
                       highlightbackground="#2a3350", bg="black")
    canvas.pack(fill="both", expand=True)
    item = canvas.create_image(0, 0, anchor="nw")
    disp = {"s": 1.0, "ox": 0, "oy": 0}      # stage scale and (letterbox) offset

    def fb_xy(e):                            # screen coords -> framebuffer coords
        return (e.x - disp["ox"]) / disp["s"], (e.y - disp["oy"]) / disp["s"]
    # dialogue box (real widgets -> supports accented characters)
    dbox = tk.Frame(stagef, bg=PANEL, height=90); dbox.pack(fill="x", pady=(6, 0))
    who_l = tk.Label(dbox, bg=PANEL, fg=ACC, font=F["bold"], anchor="w")
    who_l.pack(fill="x", padx=10, pady=(6, 0))
    text_l = tk.Label(dbox, bg=PANEL, fg=INK, font=F["big"], anchor="w",
                      justify="left", wraplength=rt.W - 24)
    text_l.pack(fill="x", padx=10, pady=(0, 8))
    choicef = tk.Frame(stagef, bg=BG); choicef.pack(fill="x")
    bgm_l = tk.Label(stagef, bg=BG, fg=MUT, font=F["mono"], anchor="w")
    bgm_l.pack(fill="x")

    panel = tk.Frame(root, bg=BG); panel.grid(row=0, column=1, padx=8, pady=8, sticky="n")

    def lbl(parent, t, **kw):
        return tk.Label(parent, text=t, bg=kw.pop("bg", BG), fg=kw.pop("fg", MUT),
                        font=F["ui"], **kw)

    def btn(parent, t, fn, **kw):
        return tk.Button(parent, text=t, command=fn, bg="#1b2440", fg=INK, relief="flat",
                         font=F["ui"], activebackground="#26335c", **kw)

    # ---- toolbar ----------------------------------------------------------
    tb = tk.Frame(panel, bg=BG); tb.pack(fill="x")
    for t, fn in (("New", lambda: new_project()), ("Open", lambda: open_project()),
                  ("▶ Play", lambda: play()), ("↶", lambda: undo()), ("↷", lambda: redo()),
                  ("＋ Character", lambda: add_char()), ("Validate", lambda: do_validate()),
                  ("Save .vn", lambda: save()), ("Export HTML", lambda: export()),
                  ("A−", lambda: bump_ui(-0.1)), ("A+", lambda: bump_ui(0.1))):
        btn(tb, t, fn).pack(side="left", padx=2)

    def _load_model(nm, path, nb):
        nonlocal base
        model.clear(); model.update(nm)
        base = nb; rt.base = nb; rt.invalidate()
        hist["undo"].clear(); hist["redo"].clear()
        cur["path"] = path
        st["scene"] = model["order"][0]; st["step"] = -1; st["play"] = False
        root.title(f"znt · VN Studio · {os.path.basename(path) if path else 'new'}")
        refresh_all()

    def new_project():
        if messagebox.askyesno("New", "Discard the current project?"):
            _load_model(vn.blank_model(), None, os.getcwd())

    def open_project():
        p = filedialog.askopenfilename(filetypes=[("VN", "*.vn")])
        if p:
            m2 = vn._link_choices(vn.parse(open(p, encoding="utf-8").read()))
            _load_model(m2, p, os.path.dirname(os.path.abspath(p)))

    def do_validate():
        probs = vn.validate(model, base)
        messagebox.showinfo("Validation",
                            "\n".join(probs) if probs else "No problems ✔")

    # ---- scenes -----------------------------------------------------------
    lbl(panel, "Scenes").pack(anchor="w", pady=(10, 0))
    scenes_lb = tk.Listbox(panel, height=6, width=34, bg=PANEL, fg=INK,
                           selectbackground="#26335c", highlightthickness=0, font=F["mono"])
    scenes_lb.pack()
    sc_btns = tk.Frame(panel, bg=BG); sc_btns.pack(fill="x")
    btn(sc_btns, "＋ scene", lambda: add_scene()).pack(side="left", padx=2)
    btn(sc_btns, "duplicate", lambda: dup_scene()).pack(side="left", padx=2)
    btn(sc_btns, "rename", lambda: rename_scene()).pack(side="left", padx=2)
    btn(sc_btns, "↑", lambda: move_scene_ui(-1)).pack(side="left")
    btn(sc_btns, "↓", lambda: move_scene_ui(1)).pack(side="left")

    # ---- steps ------------------------------------------------------------
    lbl(panel, "Scene steps").pack(anchor="w", pady=(10, 0))
    steps_lb = tk.Listbox(panel, height=12, width=44, bg=PANEL, fg=INK,
                          selectbackground="#26335c", highlightthickness=0, font=F["mono"])
    steps_lb.pack()
    addf = tk.Frame(panel, bg=BG); addf.pack(fill="x", pady=2)
    add_op = tk.StringVar(value="say")
    ttk.Combobox(addf, textvariable=add_op, values=STEP_OPS, width=8, state="readonly").pack(side="left")
    btn(addf, "＋ add", lambda: add_step()).pack(side="left", padx=2)
    btn(addf, "↑", lambda: move_step(-1)).pack(side="left")
    btn(addf, "↓", lambda: move_step(1)).pack(side="left")
    btn(addf, "dup", lambda: dup_step()).pack(side="left")
    btn(addf, "delete", lambda: del_step()).pack(side="left", padx=2)
    btn(addf, "▶ preview", lambda: preview_transition()).pack(side="left", padx=2)

    # ---- step properties --------------------------------------------------
    lbl(panel, "Properties").pack(anchor="w", pady=(10, 0))
    propf = tk.Frame(panel, bg=PANEL); propf.pack(fill="x")
    fields = {}   # name -> (widget, getter)

    lbl(panel, "Project assets (double-click: into the active show/bg)").pack(anchor="w", pady=(10, 0))
    assets_lb = tk.Listbox(panel, height=5, width=44, bg=PANEL, fg=INK,
                           selectbackground="#26335c", highlightthickness=0, font=F["mono"])
    assets_lb.pack()

    # ------------------------------------------------------------------ helpers
    def steps():
        return model["scenes"][st["scene"]]

    def present():
        fb = rt.frame()
        base = tk.PhotoImage(data=base64.b64encode(fb.png_bytes(1)))
        cw = max(canvas.winfo_width(), 1); ch = max(canvas.winfo_height(), 1)
        if cw <= 1 or ch <= 1: cw, ch = rt.W, rt.H          # not realized yet
        if cw >= rt.W and ch >= rt.H:                        # enlarge: integer zoom
            z = max(1, min(cw // rt.W, ch // rt.H)); img = base.zoom(z); disp["s"] = float(z)
        else:                                               # shrink: integer subsample
            sub = max((rt.W + cw - 1) // cw, (rt.H + ch - 1) // ch, 1)
            img = base.subsample(sub); disp["s"] = 1.0 / sub
        dw, dh = int(rt.W * disp["s"]), int(rt.H * disp["s"])
        disp["ox"], disp["oy"] = (cw - dw) // 2, (ch - dh) // 2
        tkimg["i"] = img                                    # keep the ref alive
        canvas.coords(item, disp["ox"], disp["oy"])
        canvas.itemconfig(item, image=img)

    def show_dialogue():
        who = rt.speaker
        name = model["characters"].get(who, {}).get("name", who) if who else ""
        color = model["characters"].get(who, {}).get("color", ACC) if who else ACC
        who_l.config(text=name or "", fg=color)
        text_l.config(text=rt.text or "")
        bgm_l.config(text=f"♪ {rt.bgm}" + (f"   se: {rt.last_se}" if rt.last_se else "") if rt.bgm else "")
        for w in choicef.winfo_children():
            w.destroy()
        if rt.choices:
            for i, o in enumerate(rt.choices):
                tk.Button(choicef, text=o["label"], bg="#16244c", fg=INK, relief="flat",
                          font=F["ui10"], activebackground="#22357a",
                          command=lambda i=i: (rt.choose(i), sync_after_play())
                          ).pack(fill="x", pady=2)

    def refresh_preview():
        if st["play"]:
            return
        rt.preview_upto(st["scene"], st["step"])
        present(); show_dialogue()

    def refresh_scenes():
        scenes_lb.delete(0, "end")
        for sid in model["order"]:
            scenes_lb.insert("end", f"{sid}  ({len(model['scenes'][sid])})")
        scenes_lb.selection_clear(0, "end")
        if st["scene"] in model["order"]:
            scenes_lb.selection_set(model["order"].index(st["scene"]))

    def refresh_steps():
        steps_lb.delete(0, "end")
        for s in steps():
            steps_lb.insert("end", vn._step_text(s).split("\n")[0])
        if 0 <= st["step"] < steps_lb.size():
            steps_lb.selection_set(st["step"])

    def refresh_assets():
        assets_lb.delete(0, "end")
        for f in vn.list_assets(base):
            assets_lb.insert("end", f)

    def assign_asset(_=None):
        sel = assets_lb.curselection()
        if not sel or not (0 <= st["step"] < len(steps())):
            return
        fname = assets_lb.get(sel[0]); s = steps()[st["step"]]
        if s["op"] == "show":
            snapshot(); model["characters"][s["id"]]["sprite"] = fname
        elif s["op"] == "bg":
            snapshot(); s["spec"] = {"kind": "img", "file": fname}
        else:
            return
        rt.invalidate(); refresh_all()

    def refresh_all():
        refresh_scenes(); refresh_steps(); build_props(); refresh_preview(); refresh_assets()

    # ------------------------------------------------------------------ undo/redo
    def snapshot():
        """Save the state before a mutation. Call BEFORE touching the model."""
        hist["undo"].append(copy.deepcopy(model)); hist["redo"].clear()
        if len(hist["undo"]) > hist["max"]:
            hist["undo"].pop(0)

    def _restore(saved):
        model.clear(); model.update(copy.deepcopy(saved))   # in-place: rt.model and the closures see the change
        rt.invalidate()
        if st["scene"] not in model["scenes"]:
            st["scene"] = model["order"][0]
        st["step"] = min(st["step"], len(model["scenes"][st["scene"]]) - 1)
        refresh_all()

    def undo(_=None):
        if st["play"] or not hist["undo"]:
            return
        hist["redo"].append(copy.deepcopy(model)); _restore(hist["undo"].pop())

    def redo(_=None):
        if st["play"] or not hist["redo"]:
            return
        hist["undo"].append(copy.deepcopy(model)); _restore(hist["redo"].pop())

    # ------------------------------------------------------------------ props
    def build_props():
        for w in propf.winfo_children():
            w.destroy()
        fields.clear()
        if not (0 <= st["step"] < len(steps())):
            lbl(propf, "(pick a step)", bg=PANEL).pack(anchor="w", padx=6, pady=6); return
        s = steps()[st["step"]]; op = s["op"]
        chars = list(model["characters"])
        def field(name, widget, getter):
            row = tk.Frame(propf, bg=PANEL); row.pack(fill="x", padx=6, pady=2)
            lbl(row, name, bg=PANEL, width=8, anchor="w").pack(side="left")
            widget.pack(in_=row, side="left", fill="x", expand=True)
            fields[name] = (widget, getter)
        def entry(val):
            e = tk.Entry(propf, bg="#0f1525", fg=INK, insertbackground=INK, relief="flat")
            e.insert(0, val); return e, (lambda e=e: e.get())
        def combo(val, values):
            v = tk.StringVar(value=val)
            c = ttk.Combobox(propf, textvariable=v, values=values, state="readonly")
            return c, (lambda v=v: v.get())

        if op == "bg":
            sp = s["spec"]
            cur_arg = (f"grad:{sp['a']},{sp['b']}" if sp["kind"] == "grad"
                       else sp.get("color") if sp["kind"] == "solid" else sp.get("file", ""))
            w, g = entry(cur_arg); field("bg", w, g)
            def pick_bg(s=s):
                p = filedialog.askopenfilename(filetypes=[("image", "*.png *.jpg *.jpeg *.webp *.gif")])
                if p:
                    snapshot()
                    s["spec"] = {"kind": "img", "file": _rel(p)}; rt.invalidate(); refresh_all()
            btn(propf, "background image…", pick_bg).pack(padx=6, pady=2, anchor="w")
        elif op in ("show", "hide"):
            w, g = combo(s["id"], chars); field("id", w, g)
            if op == "show":
                w2, g2 = combo(s.get("pos", "center"), list(POS)); field("pos", w2, g2)
                cur_z = rt.stage[s["id"]].level if s["id"] in rt.stage else s.get("z", 10)
                wz, gz = entry(str(cur_z)); field("z", wz, gz)
                def set_z(front, s=s):
                    snapshot()
                    others = [o.level for k, o in rt.stage.items()
                              if k not in (s["id"], "bg") and o.rows and o.show]
                    s["z"] = ((max(others) + 1) if others else 10) if front else \
                             (max(1, min(others) - 1) if others else 10)
                    refresh_all()
                zf = tk.Frame(propf, bg=PANEL); zf.pack(fill="x", padx=6, pady=1)
                btn(zf, "▲ to front", lambda: set_z(True)).pack(side="left", padx=2)
                btn(zf, "▼ to back", lambda: set_z(False)).pack(side="left", padx=2)
                cur_zoom = rt.stage[s["id"]].zoom if s["id"] in rt.stage else s.get("zoom", 100)
                wzm, gzm = entry(str(int(cur_zoom))); field("zoom%", wzm, gzm)
                cur_op = rt.stage[s["id"]].opacity if s["id"] in rt.stage else s.get("opacity", 100)
                wop, gop = entry(str(int(cur_op))); field("opac%", wop, gop)
                wtn, gtn = entry(s.get("tint", "")); field("tint", wtn, gtn)
                spr = model["characters"].get(s["id"], {}).get("sprite")
                lbl(propf, f"sprite: {spr or '(placeholder)'}", bg=PANEL).pack(anchor="w", padx=6)
                def pick_sprite(cid=s["id"]):
                    p = filedialog.askopenfilename(filetypes=[("image", "*.png *.jpg *.jpeg *.webp *.gif")])
                    if p:
                        snapshot()
                        model["characters"][cid]["sprite"] = _rel(p); rt.invalidate(); refresh_all()
                btn(propf, "assign sprite…", pick_sprite).pack(padx=6, pady=2, anchor="w")
                btn(propf, "rename character…", lambda cid=s["id"]: rename_char_ui(cid)).pack(padx=6, pady=2, anchor="w")
                lbl(propf, "drag the sprite on the stage to place it", bg=PANEL).pack(anchor="w", padx=6)
        elif op == "say":
            w, g = combo(s.get("who", "narrator"), chars); field("who", w, g)
            w2, g2 = entry(s.get("text", "")); field("text", w2, g2)
            if s.get("who", "narrator") != "narrator":
                btn(propf, "rename character…", lambda cid=s["who"]: rename_char_ui(cid)).pack(padx=6, pady=2, anchor="w")
        elif op == "animate":
            w, g = combo(s["id"], [c for c in chars if c != "narrator"]); field("id", w, g)
            w2, g2 = combo(s["kind"], list(CURVES) + list(ACTIONS) + ["move"]); field("type", w2, g2)
            kv = " ".join(f"{k}={v}" for k, v in s.get("params", {}).items())
            w3, g3 = entry(kv); field("params", w3, g3)
        elif op in ("bgm", "se"):
            w, g = entry(s.get("file", "")); field("file", w, g)
            def pick_audio(s=s):
                p = filedialog.askopenfilename(filetypes=[("audio", "*.ogg *.mp3 *.wav *.m4a")])
                if p:
                    snapshot(); s["file"] = _rel(p); s.pop("stop", None); refresh_all()
            btn(propf, "choose sound…", pick_audio).pack(padx=6, pady=2, anchor="w")
            if op == "bgm":
                sv = tk.BooleanVar(value=bool(s.get("stop")))
                tk.Checkbutton(propf, text="stop bgm", variable=sv, bg=PANEL, fg=MUT,
                               selectcolor="#0f1525", font=F["ui"]).pack(anchor="w", padx=6)
                fields["stop"] = (sv, lambda: sv.get())
        elif op == "goto":
            w, g = combo(s.get("target", model["order"][0]), model["order"]); field("to", w, g)
        elif op == "choice":
            txt = tk.Text(propf, height=4, width=34, bg="#0f1525", fg=INK, insertbackground=INK,
                          relief="flat", font=F["mono"])
            txt.insert("1.0", "\n".join(f"{o['label']} -> {o['target']}" for o in s.get("options", [])))
            txt.pack(fill="x", padx=6, pady=2)
            fields["opts"] = (txt, lambda: txt.get("1.0", "end"))
            lbl(propf, "label -> scene  (one per line)", bg=PANEL).pack(anchor="w", padx=6)
        else:
            lbl(propf, "(no properties)", bg=PANEL).pack(anchor="w", padx=6, pady=6)
        if op != "end":
            btn(propf, "Apply", apply_props).pack(pady=4)

    def apply_props():
        if not (0 <= st["step"] < len(steps())):
            return
        snapshot()
        s = steps()[st["step"]]; op = s["op"]
        g = {k: getr() for k, (w, getr) in fields.items()}
        try:
            if op == "bg":
                s["spec"] = vn._bg(g["bg"].strip())
            elif op in ("show", "hide"):
                s["id"] = g["id"]
                if op == "show":
                    s["pos"] = g["pos"]
                    if g.get("z", "").strip():
                        try: s["z"] = int(g["z"])
                        except ValueError: pass
                    if g.get("zoom%", "").strip():
                        try: s["zoom"] = int(g["zoom%"])
                        except ValueError: pass
                    if g.get("opac%", "").strip():
                        try: s["opacity"] = int(g["opac%"])
                        except ValueError: pass
                    tn = g.get("tint", "").strip()
                    if tn: s["tint"] = tn
                    else: s.pop("tint", None)
            elif op == "say":
                s["who"] = g["who"]; s["text"] = g["text"]
            elif op == "animate":
                s["id"] = g["id"]; s["kind"] = g["type"]
                s["params"] = _parse_kv(g["params"])
            elif op == "bgm":
                if g.get("stop"):
                    s.clear(); s["op"] = "bgm"; s["stop"] = True
                else:
                    s.pop("stop", None); s["file"] = g["file"].strip()
            elif op == "se":
                s["file"] = g["file"].strip()
            elif op == "goto":
                s["target"] = g["to"]
            elif op == "choice":
                s["options"] = [{"label": ln.split("->")[0].strip(),
                                 "target": ln.split("->")[1].strip()}
                                for ln in g["opts"].splitlines() if "->" in ln]
        except Exception as ex:
            messagebox.showerror("Error", str(ex)); return
        refresh_all()

    def _parse_kv(text):
        p = {}
        for kv in text.split():
            if "=" in kv:
                k, v = kv.split("=", 1)
                try: p[k] = int(v)
                except ValueError:
                    try: p[k] = float(v)
                    except ValueError: p[k] = v
        return p

    # ------------------------------------------------------------------ actions
    def add_scene():
        name = simpledialog.askstring("Scene", "id of the new scene:", parent=root)
        if name and name not in model["scenes"]:
            snapshot()
            model["scenes"][name] = []; model["order"].append(name)
            st["scene"] = name; st["step"] = -1; refresh_all()

    def rename_scene():
        old = st["scene"]
        name = simpledialog.askstring("Rename", "new id:", initialvalue=old, parent=root)
        if name and name != old and name not in model["scenes"]:
            snapshot()
            model["scenes"][name] = model["scenes"].pop(old)
            model["order"][model["order"].index(old)] = name
            if model.get("start") == old: model["start"] = name
            for sid in model["scenes"]:                      # repoint gotos/choices
                for s in model["scenes"][sid]:
                    if s["op"] == "goto" and s["target"] == old: s["target"] = name
                    if s["op"] == "choice":
                        for o in s["options"]:
                            if o["target"] == old: o["target"] = name
            st["scene"] = name; refresh_all()

    def rename_char_ui(cid):
        new = simpledialog.askstring("Rename character", f"new id for '{cid}':",
                                     initialvalue=cid, parent=root)
        if new and new != cid:
            snapshot()
            if vn.rename_character(model, cid, new):
                refresh_all()
            else:
                messagebox.showerror("Error", "id in use or does not exist")

    def add_char():
        cid = simpledialog.askstring("Character", "id (e.g. saito):", parent=root)
        if not cid: return
        name = simpledialog.askstring("Character", "display name:", initialvalue=cid, parent=root) or cid
        color = simpledialog.askstring("Character", "color #hex:", initialvalue="#7cc4ff", parent=root) or "#7cc4ff"
        snapshot()
        model["characters"][cid] = {"name": name, "color": color}
        build_props()

    def move_scene_ui(d):
        snapshot()
        if vn.move_scene(model, st["scene"], d):
            refresh_all()

    def dup_scene():
        snapshot()
        nid = vn.duplicate_scene(model, st["scene"])
        st["scene"] = nid; st["step"] = -1; refresh_all()

    def dup_step():
        if 0 <= st["step"] < len(steps()):
            snapshot()
            vn.duplicate_step(steps(), st["step"]); st["step"] += 1; refresh_all()

    def add_step():
        snapshot()
        s = _default_step(add_op.get(), model)
        steps().insert(st["step"] + 1 if st["step"] >= 0 else len(steps()), s)
        st["step"] = st["step"] + 1 if st["step"] >= 0 else len(steps()) - 1
        refresh_all()

    def del_step():
        if 0 <= st["step"] < len(steps()):
            snapshot()
            steps().pop(st["step"]); st["step"] = min(st["step"], len(steps()) - 1); refresh_all()

    def move_step(d):
        i = st["step"]; j = i + d
        if 0 <= i < len(steps()) and 0 <= j < len(steps()):
            snapshot()
            steps()[i], steps()[j] = steps()[j], steps()[i]; st["step"] = j; refresh_all()

    def save():
        p = cur["path"] or filedialog.asksaveasfilename(defaultextension=".vn",
                                                         filetypes=[("VN", "*.vn")])
        if not p: return
        open(p, "w", encoding="utf-8").write(vn.to_text(model))
        cur["path"] = p; root.title(f"znt · VN Studio · {os.path.basename(p)}")

    def export():
        p = filedialog.asksaveasfilename(defaultextension=".html",
                                         filetypes=[("HTML", "*.html")])
        if not p: return
        open(p, "w", encoding="utf-8").write(vn.render_html(vn._link_choices(model), base))
        messagebox.showinfo("Export", f"HTML player written:\n{p}")

    # ------------------------------------------------------------------ positioning (drag)
    def _hit(mx, my):
        best, bl = None, -1
        for name, l in rt.stage.items():
            if name == "bg" or not l.rows or not l.show:
                continue
            r = rt.layer_rect(name)
            if r and r[0] <= mx < r[0]+r[2] and r[1] <= my < r[1]+r[3] and l.level > bl:
                best, bl = name, l.level
        return best

    def _show_step_for(cid):
        end = st["step"] if st["step"] >= 0 else len(steps()) - 1
        for i in range(min(end, len(steps())-1), -1, -1):
            s = steps()[i]
            if s["op"] == "show" and s["id"] == cid:
                return s
        return None

    def play_advance(_=None):
        if st["play"] and rt.text is not None and not rt.animating() and not rt.choices:
            rt.advance(); present(); show_dialogue()
            if rt.done and not rt.choices: stop_play()

    def on_press(e):
        if st["play"]:                      # in Play, a click advances the dialogue
            play_advance(); return
        fx, fy = fb_xy(e)                    # while editing, drag the sprite (fb coords)
        name = _hit(fx, fy)
        if not name:
            return
        s = _show_step_for(name)
        if not s:
            return
        snapshot()                          # one undo per drag gesture
        r = rt.layer_rect(name)
        drag.update(name=name, ox=fx - r[0], oy=fy - r[1], step=s)

    SNAP = 12   # snap px

    def _nearest(v, targets):
        best, bd = None, SNAP + 1
        for t in targets:
            d = abs(v - t)
            if d < bd:
                best, bd = t, d
        return (best, True) if best is not None and bd <= SNAP else (v, False)

    def on_motion(e):
        if st["play"] or not drag["name"]:
            return
        name = drag["name"]; l = rt.stage[name]
        fx, fy = fb_xy(e)
        w, h = len(l.rows[0]) // 4, len(l.rows)
        raw_x = (fx - drag["ox"]) - (rt.W // 2 - w // 2)
        raw_y = (fy - drag["oy"]) - (rt.H - h)
        canvas.delete("guide")
        if e.state & 0x0001:                      # Shift = free drag (no snap)
            nx, ny = raw_x, raw_y
        else:
            others = [o for k, o in rt.stage.items()
                      if k not in (name, "bg") and o.rows and o.show]
            xt = [0.0, float(POS["left"]), float(POS["right"])] + [o.x for o in others]
            yt = [0.0] + [o.y for o in others]     # 0 = resting on the floor
            nx, sx = _nearest(raw_x, xt)
            ny, sy = _nearest(raw_y, yt)
            s, ox, oy = disp["s"], disp["ox"], disp["oy"]   # fb -> canvas
            if sx:                                 # vertical guide (centers aligned)
                gx = ox + (nx + rt.W / 2) * s
                canvas.create_line(gx, oy, gx, oy + rt.H * s, fill="#5fd0e0", dash=(4, 3), tags="guide")
            if sy:                                 # horizontal guide (same baseline)
                gy = oy + (ny + rt.H) * s
                canvas.create_line(ox, gy, ox + rt.W * s, gy, fill="#e8b04b", dash=(4, 3), tags="guide")
        l.x, l.y = float(nx), float(ny)
        drag["step"]["x"], drag["step"]["y"] = int(nx), int(ny)
        present()

    def on_release(_):
        if drag["name"]:
            drag["name"] = None; canvas.delete("guide"); refresh_steps(); build_props()

    canvas.bind("<Button-1>", on_press)
    canvas.bind("<B1-Motion>", on_motion)
    canvas.bind("<ButtonRelease-1>", on_release)
    canvas.bind("<Configure>", lambda e: present())   # rescale the stage with the window

    # ------------------------------------------------------------------ preview transition
    def preview_transition():
        if st["play"] or st["step"] < 0:
            return
        rt.preview_upto(st["scene"], st["step"], settle=False)   # live transition from t=0
        st["preview"] = [0]
        def loop():
            p = st.get("preview")
            if not p:
                return
            rt.tick(33); present(); p[0] += 1
            if not rt.animating() or p[0] > 90:                 # end, or ~3s cap (continuous actions)
                st["preview"] = None; refresh_preview(); return
            root.after(33, loop)
        loop()

    # ------------------------------------------------------------------ play
    def play():
        st["play"] = True; rt.enter(st["scene"])
        for w in (scenes_lb, steps_lb):
            w.config(state="disabled")
        root.bind("<space>", play_advance)
        def loop():
            if not st["play"]:
                return
            rt.tick(33); present(); show_dialogue()
            if rt.done and not rt.choices:
                stop_play(); return
            root.after(33, loop)
        loop()

    def sync_after_play():
        present(); show_dialogue()
        if rt.done and not rt.choices: stop_play()

    def stop_play():
        st["play"] = False
        root.unbind("<space>")
        for w in (scenes_lb, steps_lb):
            w.config(state="normal")
        refresh_all()

    # ------------------------------------------------------------------ events
    def on_scene(_=None):
        sel = scenes_lb.curselection()
        if sel:
            st["scene"] = model["order"][sel[0]]; st["step"] = -1; refresh_steps(); build_props(); refresh_preview()

    def on_step(_=None):
        sel = steps_lb.curselection()
        if sel:
            st["step"] = sel[0]; build_props(); refresh_preview()

    scenes_lb.bind("<<ListboxSelect>>", on_scene)
    steps_lb.bind("<<ListboxSelect>>", on_step)
    assets_lb.bind("<Double-Button-1>", assign_asset)
    root.bind("<Control-z>", undo)
    root.bind("<Control-y>", redo)
    root.bind("<Control-Z>", redo)          # Ctrl+Shift+Z
    root.title(f"znt · VN Studio · {os.path.basename(cur['path']) if cur['path'] else 'new'}")
    refresh_all()
    root.mainloop()
