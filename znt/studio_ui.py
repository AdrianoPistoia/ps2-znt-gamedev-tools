#!/usr/bin/env python3
"""Editor visual del framework de VN (tkinter). Maneja el `VNRuntime` real: stage
en vivo con el engine, lista de escenas y de pasos, edición de propiedades, Play,
y export a `.vn` + player HTML. No lo importa el runtime (frontend desacoplado)."""
import os, base64

from . import vn
from .vnstudio import VNRuntime, POS, ACTIONS
from .engine import CURVES

STEP_OPS = ["bg", "show", "hide", "say", "animate", "choice", "goto", "end"]
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
        "choice": {"op": "choice", "options": []},
        "goto": {"op": "goto", "target": model["order"][0]},
        "end": {"op": "end"},
    }[op]


def run_editor(path=None):
    import tkinter as tk
    from tkinter import ttk, filedialog, simpledialog, messagebox

    if path and os.path.exists(path):
        model = vn._link_choices(vn.parse(open(path, encoding="utf-8").read()))
        base = os.path.dirname(os.path.abspath(path)); cur = {"path": path}
    else:
        model = _fresh(); base = os.getcwd(); cur = {"path": None}
    rt = VNRuntime(model, base)
    st = {"scene": model["order"][0], "step": -1, "play": False}

    root = tk.Tk(); root.title("znt · VN Studio"); root.configure(bg=BG)
    tkimg = {}

    # ---- layout: stage a la izquierda, paneles a la derecha ---------------
    stagef = tk.Frame(root, bg=BG); stagef.grid(row=0, column=0, padx=8, pady=8, sticky="n")
    canvas = tk.Canvas(stagef, width=rt.W, height=rt.H, highlightthickness=1,
                       highlightbackground="#2a3350", bg="black")
    canvas.pack()
    item = canvas.create_image(0, 0, anchor="nw")
    # cuadro de diálogo (widgets reales -> soporta acentos)
    dbox = tk.Frame(stagef, bg=PANEL, height=90); dbox.pack(fill="x", pady=(6, 0))
    who_l = tk.Label(dbox, bg=PANEL, fg=ACC, font=("sans", 11, "bold"), anchor="w")
    who_l.pack(fill="x", padx=10, pady=(6, 0))
    text_l = tk.Label(dbox, bg=PANEL, fg=INK, font=("sans", 12), anchor="w",
                      justify="left", wraplength=rt.W - 24)
    text_l.pack(fill="x", padx=10, pady=(0, 8))
    choicef = tk.Frame(stagef, bg=BG); choicef.pack(fill="x")

    panel = tk.Frame(root, bg=BG); panel.grid(row=0, column=1, padx=8, pady=8, sticky="n")

    def lbl(parent, t, **kw):
        return tk.Label(parent, text=t, bg=kw.pop("bg", BG), fg=kw.pop("fg", MUT),
                        font=("sans", 9), **kw)

    def btn(parent, t, fn, **kw):
        return tk.Button(parent, text=t, command=fn, bg="#1b2440", fg=INK, relief="flat",
                         font=("sans", 9), activebackground="#26335c", **kw)

    # ---- toolbar ----------------------------------------------------------
    tb = tk.Frame(panel, bg=BG); tb.pack(fill="x")
    for t, fn in (("▶ Play", lambda: play()), ("＋ Personaje", lambda: add_char()),
                  ("Guardar .vn", lambda: save()), ("Exportar HTML", lambda: export())):
        btn(tb, t, fn).pack(side="left", padx=2)

    # ---- escenas ----------------------------------------------------------
    lbl(panel, "Escenas").pack(anchor="w", pady=(10, 0))
    scenes_lb = tk.Listbox(panel, height=6, width=34, bg=PANEL, fg=INK,
                           selectbackground="#26335c", highlightthickness=0, font=("mono", 9))
    scenes_lb.pack()
    sc_btns = tk.Frame(panel, bg=BG); sc_btns.pack(fill="x")
    btn(sc_btns, "＋ escena", lambda: add_scene()).pack(side="left", padx=2)
    btn(sc_btns, "renombrar", lambda: rename_scene()).pack(side="left", padx=2)

    # ---- pasos ------------------------------------------------------------
    lbl(panel, "Pasos de la escena").pack(anchor="w", pady=(10, 0))
    steps_lb = tk.Listbox(panel, height=12, width=44, bg=PANEL, fg=INK,
                          selectbackground="#26335c", highlightthickness=0, font=("mono", 9))
    steps_lb.pack()
    addf = tk.Frame(panel, bg=BG); addf.pack(fill="x", pady=2)
    add_op = tk.StringVar(value="say")
    ttk.Combobox(addf, textvariable=add_op, values=STEP_OPS, width=8, state="readonly").pack(side="left")
    btn(addf, "＋ agregar", lambda: add_step()).pack(side="left", padx=2)
    btn(addf, "↑", lambda: move_step(-1)).pack(side="left")
    btn(addf, "↓", lambda: move_step(1)).pack(side="left")
    btn(addf, "borrar", lambda: del_step()).pack(side="left", padx=2)

    # ---- propiedades del paso --------------------------------------------
    lbl(panel, "Propiedades").pack(anchor="w", pady=(10, 0))
    propf = tk.Frame(panel, bg=PANEL); propf.pack(fill="x")
    fields = {}   # nombre -> (widget, getter)

    # ------------------------------------------------------------------ helpers
    def steps():
        return model["scenes"][st["scene"]]

    def present():
        fb = rt.frame()
        tkimg["i"] = tk.PhotoImage(data=base64.b64encode(fb.png_bytes(1)))
        canvas.itemconfig(item, image=tkimg["i"])

    def show_dialogue():
        who = rt.speaker
        name = model["characters"].get(who, {}).get("name", who) if who else ""
        color = model["characters"].get(who, {}).get("color", ACC) if who else ACC
        who_l.config(text=name or "", fg=color)
        text_l.config(text=rt.text or "")
        for w in choicef.winfo_children():
            w.destroy()
        if rt.choices:
            for i, o in enumerate(rt.choices):
                tk.Button(choicef, text=o["label"], bg="#16244c", fg=INK, relief="flat",
                          font=("sans", 10), activebackground="#22357a",
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

    def refresh_all():
        refresh_scenes(); refresh_steps(); build_props(); refresh_preview()

    # ------------------------------------------------------------------ props
    def build_props():
        for w in propf.winfo_children():
            w.destroy()
        fields.clear()
        if not (0 <= st["step"] < len(steps())):
            lbl(propf, "(elegí un paso)", bg=PANEL).pack(anchor="w", padx=6, pady=6); return
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
        elif op in ("show", "hide"):
            w, g = combo(s["id"], chars); field("id", w, g)
            if op == "show":
                w2, g2 = combo(s.get("pos", "center"), list(POS)); field("pos", w2, g2)
        elif op == "say":
            w, g = combo(s.get("who", "narrator"), chars); field("quién", w, g)
            w2, g2 = entry(s.get("text", "")); field("texto", w2, g2)
        elif op == "animate":
            w, g = combo(s["id"], [c for c in chars if c != "narrator"]); field("id", w, g)
            w2, g2 = combo(s["kind"], list(CURVES) + list(ACTIONS) + ["move"]); field("tipo", w2, g2)
            kv = " ".join(f"{k}={v}" for k, v in s.get("params", {}).items())
            w3, g3 = entry(kv); field("params", w3, g3)
        elif op == "goto":
            w, g = combo(s.get("target", model["order"][0]), model["order"]); field("a", w, g)
        elif op == "choice":
            txt = tk.Text(propf, height=4, width=34, bg="#0f1525", fg=INK, insertbackground=INK,
                          relief="flat", font=("mono", 9))
            txt.insert("1.0", "\n".join(f"{o['label']} -> {o['target']}" for o in s.get("options", [])))
            txt.pack(fill="x", padx=6, pady=2)
            fields["opts"] = (txt, lambda: txt.get("1.0", "end"))
            lbl(propf, "etiqueta -> escena  (una por línea)", bg=PANEL).pack(anchor="w", padx=6)
        else:
            lbl(propf, "(sin propiedades)", bg=PANEL).pack(anchor="w", padx=6, pady=6)
        if op != "end":
            btn(propf, "Aplicar", apply_props).pack(pady=4)

    def apply_props():
        if not (0 <= st["step"] < len(steps())):
            return
        s = steps()[st["step"]]; op = s["op"]
        g = {k: getr() for k, (w, getr) in fields.items()}
        try:
            if op == "bg":
                s["spec"] = vn._bg(g["bg"].strip())
            elif op in ("show", "hide"):
                s["id"] = g["id"]
                if op == "show": s["pos"] = g["pos"]
            elif op == "say":
                s["who"] = g["quién"]; s["text"] = g["texto"]
            elif op == "animate":
                s["id"] = g["id"]; s["kind"] = g["tipo"]
                s["params"] = _parse_kv(g["params"])
            elif op == "goto":
                s["target"] = g["a"]
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

    # ------------------------------------------------------------------ acciones
    def add_scene():
        name = simpledialog.askstring("Escena", "id de la nueva escena:", parent=root)
        if name and name not in model["scenes"]:
            model["scenes"][name] = []; model["order"].append(name)
            st["scene"] = name; st["step"] = -1; refresh_all()

    def rename_scene():
        old = st["scene"]
        name = simpledialog.askstring("Renombrar", "nuevo id:", initialvalue=old, parent=root)
        if name and name != old and name not in model["scenes"]:
            model["scenes"][name] = model["scenes"].pop(old)
            model["order"][model["order"].index(old)] = name
            if model.get("start") == old: model["start"] = name
            for sid in model["scenes"]:                      # reapuntar gotos/choices
                for s in model["scenes"][sid]:
                    if s["op"] == "goto" and s["target"] == old: s["target"] = name
                    if s["op"] == "choice":
                        for o in s["options"]:
                            if o["target"] == old: o["target"] = name
            st["scene"] = name; refresh_all()

    def add_char():
        cid = simpledialog.askstring("Personaje", "id (ej: saito):", parent=root)
        if not cid: return
        name = simpledialog.askstring("Personaje", "nombre visible:", initialvalue=cid, parent=root) or cid
        color = simpledialog.askstring("Personaje", "color #hex:", initialvalue="#7cc4ff", parent=root) or "#7cc4ff"
        model["characters"][cid] = {"name": name, "color": color}
        build_props()

    def add_step():
        s = _default_step(add_op.get(), model)
        steps().insert(st["step"] + 1 if st["step"] >= 0 else len(steps()), s)
        st["step"] = st["step"] + 1 if st["step"] >= 0 else len(steps()) - 1
        refresh_all()

    def del_step():
        if 0 <= st["step"] < len(steps()):
            steps().pop(st["step"]); st["step"] = min(st["step"], len(steps()) - 1); refresh_all()

    def move_step(d):
        i = st["step"]; j = i + d
        if 0 <= i < len(steps()) and 0 <= j < len(steps()):
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
        messagebox.showinfo("Export", f"Player HTML escrito:\n{p}")

    # ------------------------------------------------------------------ play
    def play():
        st["play"] = True; rt.enter(st["scene"])
        for w in (scenes_lb, steps_lb):
            w.config(state="disabled")
        def click(_=None):
            if rt.text is not None and not rt.animating() and not rt.choices:
                rt.advance()
        canvas.bind("<Button-1>", click); root.bind("<space>", click)
        def loop():
            if not st["play"]: return
            rt.tick(33)
            present()
            show_dialogue()
            if rt.done and not rt.choices:
                stop_play(); return
            root.after(33, loop)
        loop()

    def sync_after_play():
        present(); show_dialogue()
        if rt.done and not rt.choices: stop_play()

    def stop_play():
        st["play"] = False
        canvas.unbind("<Button-1>"); root.unbind("<space>")
        for w in (scenes_lb, steps_lb):
            w.config(state="normal")
        refresh_all()

    # ------------------------------------------------------------------ eventos
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
    root.title(f"znt · VN Studio · {os.path.basename(cur['path']) if cur['path'] else 'nueva'}")
    refresh_all()
    root.mainloop()
