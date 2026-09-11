#!/usr/bin/env python3
"""Web editor server (stdlib). `Studio` is the editor state (model, selection,
history) with no UI at all; the HTTP handler exposes it as a JSON API.
"""
import json, os, sys, copy, base64, errno, signal, time, mimetypes, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import vn, frontends
from ..vnstudio import VNRuntime

UI = os.path.join(os.path.dirname(__file__), "ui.html")
HIST_MAX = 60


API = 4          # bump it when the ops change; the UI warns on a mismatch

_NUM = ("x", "y", "z", "zoom", "opacity")


class Studio:
    """Editor state, UI-agnostic (the server uses it; testable on its own)."""

    def __init__(self, path=None):
        self.problems = []
        self.dirty = False
        if path and not os.path.exists(path):        # typo in the path: say so
            self.problems.append(f"{path} does not exist: starting a new project")
            sys.stderr.write(f"⚠ {path} does not exist: starting a new project\n")
        if path and os.path.exists(path):
            self.model = vn._link_choices(vn.parse(open(path, encoding="utf-8").read()))
            self.base = os.path.dirname(os.path.abspath(path))
            self.path = path
        else:
            self.model = vn.blank_model()
            self.base = os.getcwd()
            self.path = None
        self._autosave_notice()
        self.rt = VNRuntime(self.model, self.base)   # real render/animation
        self.scene = self.model["order"][0]
        self.step = -1
        self.prt = None                              # playback runtime (Play)
        self.play_stepwise = True                    # Play: step by step (editor) or as the player
        self.undo, self.redo = [], []

    # --- helpers -----------------------------------------------------------
    def steps(self):
        return self.model["scenes"][self.scene]

    def _autosave_notice(self):
        """If an autosave newer than the .vn was left behind (closed without saving), warn."""
        a = autosave_path(self.path) if self.path else None
        try:
            if a and os.path.getmtime(a) > os.path.getmtime(self.path):
                self.problems.append(f"there is an autosave newer than the project: {a} "
                                     f"(open it if you lost changes)")
        except OSError:
            pass

    def _autosave(self):
        if self.path and self.dirty:
            try:
                open(autosave_path(self.path), "w", encoding="utf-8").write(vn.to_text(self.model))
            except OSError:
                pass

    def _snapshot(self):
        self.dirty = True
        self.undo.append(copy.deepcopy(self.model)); self.redo.clear()
        if len(self.undo) > HIST_MAX:
            self.undo.pop(0)

    def _restore(self, saved):
        self.model.clear(); self.model.update(copy.deepcopy(saved))   # in-place: rt sees it
        self.rt.invalidate()
        if self.scene not in self.model["scenes"]:
            self.scene = self.model["order"][0]
        self.step = min(self.step, len(self.steps()) - 1)

    def state(self):
        return {"api": API,
                "model": self.model, "scene": self.scene, "step": self.step,
                "play": self.play_state() if self.prt else None,
                "path": self.path, "base": os.path.abspath(self.base or "."),
                "dirty": self.dirty,
                "problems": self.problems,
                "step_ops": vn.STEP_OPS,
                "can_undo": bool(self.undo), "can_redo": bool(self.redo)}

    # --- operations -------------------------------------------------------
    def op(self, r):
        o = r.get("op")
        if o == "select":
            sc = r.get("scene", self.scene)
            if sc in self.model["scenes"]:
                self.scene = sc
            self.step = int(r.get("step", -1))
            self.step = min(self.step, len(self.steps()) - 1)
        elif o == "add_step":
            self._snapshot()
            s = vn.default_step(r.get("kind", "say"), self.model)
            s.update(r.get("props") or {})           # e.g. the quick dialogue
            i = self.step + 1 if self.step >= 0 else len(self.steps())
            self.steps().insert(i, s); self.step = i
        elif o == "del_step":
            if 0 <= self.step < len(self.steps()):
                self._snapshot(); self.steps().pop(self.step)
                self.step = min(self.step, len(self.steps()) - 1)
        elif o == "paste_steps":
            # client clipboard (step JSON): independent copies, a single undo
            new = copy.deepcopy(r.get("steps") or [])
            if not new or any(not isinstance(x, dict) or x.get("op") not in vn.STEP_OPS for x in new):
                st = self.state(); st["error"] = "no valid steps to paste"; return st
            self._snapshot()
            steps = self.steps()
            i = self.step + 1 if 0 <= self.step < len(steps) else len(steps)
            steps[i:i] = new; self.step = i + len(new) - 1
        elif o == "set_group":
            steps = self.steps()
            name = (r.get("name") or "").strip().replace(" ", "_")
            idx = [int(i) for i in (r.get("indices") or []) if 0 <= int(i) < len(steps)]
            if idx:
                self._snapshot()
                for i in idx:
                    if name: steps[i]["group"] = name
                    else: steps[i].pop("group", None)
        elif o == "del_steps":
            steps = self.steps()
            idx = sorted({int(i) for i in (r.get("indices") or []) if 0 <= int(i) < len(steps)}, reverse=True)
            if idx:
                self._snapshot()
                for i in idx: steps.pop(i)
                self.step = max(-1, min(idx[-1], len(steps) - 1))
        elif o == "dup_step":
            if 0 <= self.step < len(self.steps()):
                self._snapshot(); vn.duplicate_step(self.steps(), self.step); self.step += 1
        elif o == "move_step":
            d = int(r.get("delta", 0)); i, j = self.step, self.step + d
            if 0 <= i < len(self.steps()) and 0 <= j < len(self.steps()):
                self._snapshot()
                self.steps()[i], self.steps()[j] = self.steps()[j], self.steps()[i]
                self.step = j
        elif o == "move_step_to":
            # the timeline drag moves to any position (not a swap)
            steps, to = self.steps(), int(r.get("to", -1))
            if 0 <= self.step < len(steps) and 0 <= to < len(steps):
                self._snapshot()
                steps.insert(to, steps.pop(self.step)); self.step = to
        elif o == "set_props":
            if 0 <= self.step < len(self.steps()):
                self._snapshot(); self._set_props(self.steps()[self.step], r.get("props", {}))
        elif o == "add_scene":
            name = (r.get("name") or "").strip()
            if name and name not in self.model["scenes"]:
                self._snapshot()
                self.model["scenes"][name] = [{"op": "end"}]
                self.model["order"].append(name)
                self.scene, self.step = name, -1
        elif o == "dup_scene":
            self._snapshot(); self.scene = vn.duplicate_scene(self.model, self.scene); self.step = -1
        elif o == "move_scene":
            self._snapshot(); vn.move_scene(self.model, self.scene, int(r.get("delta", 0)))
        elif o == "rename_scene":
            name = (r.get("name") or "").strip()
            if name and name not in self.model["scenes"]:
                self._snapshot(); self._rename_scene(self.scene, name); self.scene = name
        elif o == "del_scene":
            if len(self.model["order"]) <= 1:
                st = self.state(); st["error"] = "the last scene cannot be deleted"; return st
            self._snapshot()
            del self.model["scenes"][self.scene]; self.model["order"].remove(self.scene)
            self.scene = self.model["order"][0]; self.step = -1
        elif o == "del_char":
            cid = r.get("id")
            if cid == "narrator" or cid not in self.model["characters"]:
                st = self.state(); st["error"] = f"{cid} cannot be deleted"; return st
            uses = sum(1 for steps in self.model["scenes"].values() for x in steps
                       if x.get("id") == cid or x.get("who") == cid)
            if uses:
                st = self.state()
                st["error"] = f"{cid} is used in {uses} step(s): remove it from them before deleting"
                return st
            self._snapshot(); del self.model["characters"][cid]
        elif o == "add_char":
            cid = (r.get("id") or "").strip()
            if cid and cid not in self.model["characters"]:
                self._snapshot()
                self.model["characters"][cid] = {"name": r.get("name") or cid,
                                                 "color": r.get("color") or "#7cc4ff"}
        elif o == "set_sprite":
            c = self.model["characters"].get(r.get("id"))
            if c is not None:
                self._snapshot()
                self._assign_sprite(c, (r.get("file") or "").strip(), r.get("expr"))
        elif o == "set_char":
            c = self.model["characters"].get(r.get("id"))
            if c is not None:
                self._snapshot()
                for k in ("name", "color"):
                    if r.get(k): c[k] = r[k]
                self.rt.invalidate()
        elif o == "rename_char":
            self._snapshot(); vn.rename_character(self.model, r.get("old"), r.get("new"))
        elif o == "import_asset":
            # copy a file from anywhere on disk next to the .vn
            src = os.path.expanduser(r.get("path") or "")
            if not os.path.isfile(src):
                st = self.state(); st["error"] = f"file does not exist: {src}"
                return st
            name = os.path.basename(src)
            dst = os.path.join(self.base or ".", name)
            if os.path.abspath(src) != os.path.abspath(dst):
                with open(src, "rb") as fi, open(dst, "wb") as fo:
                    fo.write(fi.read())
            self._snapshot()
            c = self.model["characters"].get(r.get("id"))
            steps, ap = self.steps(), r.get("apply")
            if c is not None:
                self._assign_sprite(c, name, r.get("expr"))
            elif ap and 0 <= self.step < len(steps):
                self._set_props(steps[self.step], {ap: name})
            self.rt.invalidate()
        elif o == "upload_sprite":
            # the browser cannot see the server's disk: it sends the chosen image as base64.
            c = self.model["characters"].get(r.get("id"))
            name = self._save_upload(r)
            if c is not None and name:
                self._snapshot(); self._assign_sprite(c, name, r.get("expr"))
                self.rt.invalidate()
        elif o == "upload":
            # uploads a file and (optionally) applies it to a prop of the selected step.
            name, steps = self._save_upload(r), self.steps()
            ap = r.get("apply")
            if name and ap and 0 <= self.step < len(steps):
                self._snapshot(); self._set_props(steps[self.step], {ap: name})
                self.rt.invalidate()
        elif o == "set_z":
            # ▲/▼: the Z order lives in the `show`, like x/y.
            tgt = self._show_of(r.get("id"))
            if tgt is not None:
                others = [l.level for k, l in self.rt.stage.items()
                          if k not in ("bg", tgt["id"])]
                self._snapshot()
                tgt["z"] = ((max(others) + 1) if others else 10) if r.get("front") \
                    else (max(1, min(others) - 1) if others else 10)
        elif o in ("set_layer", "set_layer_pos"):
            # editing a LAYER (drag, handles, tint) writes to its `show`,
            # even if the selected step is a later one.
            tgt = self._show_of(r.get("id"))
            props = r.get("props") or {k: r[k] for k in ("x", "y") if k in r}
            if tgt is not None and props:
                self._snapshot()
                self._set_props(tgt, {k: int(round(float(v))) if k in _NUM else v
                                      for k, v in props.items()})
                self.rt.invalidate()
        elif o == "play":
            # starts at the selected step (or the one the client sends), not at 0.
            # stepwise=false runs as the player would: up to the next dialogue or choice.
            self.prt = VNRuntime(self.model, self.base)
            self.play_stepwise = bool(r.get("stepwise", True))
            k = r.get("step", self.step if r.get("scene", self.scene) == self.scene else 0)
            self.prt.enter_at(r.get("scene") or self.scene, k if k is not None else 0,
                              stepwise=self.play_stepwise)
        elif o == "play_advance":
            if self.prt:
                if self.play_stepwise: self.prt.step_once()   # one step (what the timeline follows)
                else: self.prt.advance()                      # up to the next dialogue
        elif o == "play_choose":
            if self.prt: self.prt.choose(int(r.get("i", 0)), stepwise=self.play_stepwise)
        elif o == "play_stop":
            self.prt = None
        elif o == "open_project" and not os.path.exists(os.path.expanduser(r.get("path") or "")):
            st = self.state(); st["error"] = f"file does not exist: {r.get('path')}"
            return st
        elif o == "open_project":
            path = r.get("path")
            if path and os.path.exists(path):
                m = vn._link_choices(vn.parse(open(path, encoding="utf-8").read()))
                self._load(m, path, os.path.dirname(os.path.abspath(path)))
        elif o == "new_project":
            self._load(vn.blank_model(), None, self.base)
        elif o == "undo" and self.undo:
            self.dirty = True
            self.redo.append(copy.deepcopy(self.model)); self._restore(self.undo.pop())
        elif o == "undo":
            if self.undo:
                self.redo.append(copy.deepcopy(self.model)); self._restore(self.undo.pop())
        elif o == "redo":
            if self.redo:
                self.dirty = True
                self.undo.append(copy.deepcopy(self.model)); self._restore(self.redo.pop())
        elif o == "validate":
            self.problems = vn.validate(self.model, self.base)
        elif o == "save":
            p = r.get("path") or self.path
            if not p:
                st = self.state(); st["error"] = "the project has no path yet: choose where to save it"
                return st
            open(p, "w", encoding="utf-8").write(vn.to_text(self.model))
            self.path = p; self.dirty = False
            try:
                os.remove(autosave_path(p))
            except OSError:
                pass
            self.base = os.path.dirname(os.path.abspath(p)) or "."
            self.rt.base = self.base
        elif o == "export":
            p = r.get("path") or os.path.join(self.base, "player.html")
            open(p, "w", encoding="utf-8").write(vn.render_html(self.model, self.base))
            st = self.state(); st["notice"] = f"HTML player written: {p}"; return st
        elif o == "export_ps2":
            # .vnp blob of the IN-MEMORY project (not the .vn on disk); .iso if there is an ELF
            from .. import vniso, psf
            p = r.get("path") or os.path.join(self.base, "game.vnp")
            try:
                blob = vniso.compile_blob(self.model, base=self.base, font=psf.find_default())
            except Exception as e:
                st = self.state(); st["error"] = f"could not compile the blob: {e}"; return st
            if p.lower().endswith(".iso"):
                elf = os.path.expanduser(r.get("elf") or "")
                if not os.path.isfile(elf):
                    st = self.state(); st["error"] = "an ISO needs the player ELF (ps2/ZNTVN.ELF): choose it"; return st
                import shutil
                if not shutil.which("genisoimage"):
                    st = self.state(); st["error"] = "genisoimage is missing (it masters the ISO): install it"; return st
                bp = p[:-4] + ".vnp"
                open(bp, "wb").write(blob)
                try:
                    vniso.build_iso(elf, bp, p, name=r.get("name") or "ZNTVN")
                except Exception as e:
                    st = self.state(); st["error"] = f"genisoimage failed: {e}"; return st
                st = self.state(); st["notice"] = f"ISO written: {p} (and the blob {bp})"; return st
            open(p, "wb").write(blob)
            st = self.state(); st["notice"] = f"PS2 blob written: {p}"; return st
        else:
            st = self.state(); st["error"] = f"unknown op: {o}"
            return st
        if o not in ("select", "validate", "save", "export", "export_ps2"):
            self.rt.invalidate()
            self._autosave()
        return self.state()

    def anim(self, scene, step, ms=1200, fps=15, shrink=2):
        """AUTHORITATIVE preview: renders the transition with the real engine
        (Python curves and actions) and packs it as an APNG so the browser
        plays it natively."""
        import tempfile
        if scene not in self.model["scenes"]:
            scene = self.model["order"][0]
        ms = max(200, min(int(ms), 3000))
        dt = max(1, 1000 // int(fps))
        self.rt.preview_upto(scene, int(step), settle=False)   # live animation from t=0
        frames = []
        for _ in range(max(2, ms // dt)):
            frames.append(bytes(self.rt.frame().buf))
            self.rt.tick(dt)
        w, h = self.rt.W, self.rt.H
        sh = [frontends._shrink(f, w, h, int(shrink)) for f in frames]
        tmp = tempfile.mktemp(suffix=".apng")
        try:
            frontends.write_apng([x[0] for x in sh], sh[0][1], sh[0][2], tmp, delay_ms=dt)
            return open(tmp, "rb").read()
        finally:
            try: os.remove(tmp)
            except OSError: pass

    # --- stage for the browser to compose with CSS ------------------------
    def stage(self, scene, step):
        """Layout after applying steps 0..step (for the editor)."""
        if scene not in self.model["scenes"]:
            scene = self.model["order"][0]
        self.rt.preview_upto(scene, int(step))
        return self._stage_from(self.rt)

    def play_state(self):
        st = self._stage_from(self.prt)
        st["playing"] = True; st["done"] = self.prt.done
        st["scene"], st["step"] = self.prt.scene_id, self.prt.cursor   # for the timeline
        st["se"], st["se_seq"] = self.prt.last_se, self.prt.se_seq     # audio
        st["stepwise"] = self.play_stepwise
        return st

    def _stage_from(self, rt):
        """Describes what to draw and where; the browser composes it with CSS."""
        url = lambda f: "/api/asset?f=" + urllib.parse.quote(f)
        sp = rt.bg_spec or {"kind": "solid", "color": "#000000"}
        bg = {"kind": "img", "url": url(sp["file"])} if sp.get("kind") == "img" else dict(sp)
        layers = []
        for name, l in rt.stage.items():
            if name in ("bg", "bg_prev") or not l.rows or not l.show:
                continue
            c = self.model["characters"].get(name, {})
            spr = vn.sprite_file(c, getattr(l, "expr", None))
            layers.append({"id": name, "name": c.get("name", name), "color": c.get("color", "#888888"),
                           "expr": getattr(l, "expr", None),
                           "x": l.x, "y": l.y, "z": l.level, "zoom": l.zoom,
                           "opacity": l.opacity, "tint": l.tint,
                           "w": len(l.rows[0]) // 4, "h": len(l.rows),
                           "url": url(spr) if spr else None})
        say = None
        if rt.text is not None:
            cc = self.model["characters"].get(rt.speaker, {})
            say = {"who": rt.speaker, "name": cc.get("name", rt.speaker or ""),
                   "color": cc.get("color", "#cccccc"), "text": rt.text}
        return {"w": rt.W, "h": rt.H, "bg": bg, "layers": layers,
                "say": say, "choices": rt.choices, "bgm": rt.bgm,
                "warnings": rt.warnings()}


    def browse(self, path, kind="any"):
        """Lists a folder on disk for the editor's file browser.
        (The server is local and the editor already writes wherever you tell it:
        this opens nothing a hand-typed path would not open anyway.)"""
        home = os.path.expanduser("~")
        path = os.path.abspath(os.path.expanduser(path or home))
        pick = None
        if os.path.isfile(path):
            path, pick = os.path.dirname(path), os.path.basename(path)
        if not os.path.isdir(path):
            path = home
        exts = {"img": vn._IMG_EXTS, "audio": vn._SND_EXTS, "vn": {".vn"}}.get(kind)
        dirs, files = [], []
        try:
            for name in sorted(os.listdir(path), key=str.lower):
                if name.startswith("."):
                    continue
                full = os.path.join(path, name)
                if os.path.isdir(full):
                    dirs.append(name)
                elif exts is None or os.path.splitext(name)[1].lower() in exts:
                    files.append(name)
        except OSError as e:
            return {"path": path, "parent": os.path.dirname(path), "dirs": [], "files": [],
                    "home": home, "pick": None, "error": str(e)}
        parent = os.path.dirname(path)
        return {"path": path, "parent": parent if parent != path else None,
                "dirs": dirs, "files": files, "home": home, "pick": pick}

    def assets(self, kind="img"):
        return vn.list_assets(self.base, kind)

    def _save_upload(self, r):
        """Saves the file the browser sent next to the .vn. Returns the name."""
        name = os.path.basename(r.get("name") or "")
        if name:
            open(os.path.join(self.base or ".", name), "wb").write(
                base64.b64decode(r.get("data") or ""))
        return name

    @staticmethod
    def _assign_sprite(c, f, expr=None):
        """Base sprite (empty expr) or an expression's; no file = remove it."""
        expr = (expr or "").strip()
        if expr:
            ex = c.setdefault("expr", {})
            if f: ex[expr] = f
            else: ex.pop(expr, None)
            if not ex: c.pop("expr", None)
        elif f:
            c["sprite"] = f
        else:
            c.pop("sprite", None)                 # back to the placeholder

    def _show_of(self, cid):
        """The last `show` of that character at or before the selected step."""
        steps = self.steps()
        end = self.step if self.step >= 0 else len(steps) - 1
        for i in range(min(end, len(steps) - 1), -1, -1):
            if steps[i]["op"] == "show" and steps[i].get("id") == cid:
                return steps[i]
        return None

    def _load(self, m, path, base):
        """Replaces the project IN-PLACE (the runtime shares the reference)."""
        self.model.clear(); self.model.update(m)
        self.path, self.base = path, base
        self.rt.base = base; self.rt.invalidate()
        self.undo.clear(); self.redo.clear()
        self.scene = self.model["order"][0]; self.step = -1
        self.problems = []; self.dirty = False
        self._autosave_notice()

    def _set_props(self, s, props):
        for k, v in props.items():
            if k == "bg":                       # the client sends the arg as-is
                s["spec"] = vn._bg(str(v).strip())
            elif k == "options":                # choice: list of {label,target}
                s["options"] = v
            elif k == "params":
                s["params"] = v
            elif v in ("", 0, None) and k in ("tint", "file", "expr", "pos", "fade"):
                s.pop(k, None)
            else:
                s[k] = v

    def _rename_scene(self, old, new):
        m = self.model
        m["scenes"][new] = m["scenes"].pop(old)
        m["order"][m["order"].index(old)] = new
        if m.get("start") == old:
            m["start"] = new
        for steps in m["scenes"].values():
            for s in steps:
                if s["op"] == "goto" and s.get("target") == old:
                    s["target"] = new
                if s["op"] == "choice":
                    for o in s.get("options", []):
                        if o["target"] == old:
                            o["target"] = new


# --- HTTP -------------------------------------------------------------------
class _Handler(BaseHTTPRequestHandler):
    studio = None
    server_version = "znt-web"

    def log_message(self, *a):
        pass                                     # quiet

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, "application/json; charset=utf-8",
                   json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            try:
                body = open(UI, "rb").read()
            except OSError:
                body = b"<html><body>ui.html is missing</body></html>"
            return self._send(200, "text/html; charset=utf-8", body)
        if path.startswith("/static/"):
            f = os.path.join(os.path.dirname(__file__), "static", os.path.basename(path))
            if not os.path.isfile(f):
                return self._json({"error": "does not exist"}, 404)
            ctype = mimetypes.guess_type(f)[0] or "application/octet-stream"
            return self._send(200, ctype, open(f, "rb").read())
        if path == "/api/model":
            return self._json(self.studio.state())
        q = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
        if path == "/api/stage":
            sc = (q.get("scene") or [self.studio.scene])[0]
            sp = (q.get("step") or ["-1"])[0]
            return self._json(self.studio.stage(sc, sp))
        if path == "/api/browse":
            return self._json(self.studio.browse((q.get("path") or [""])[0],
                                                 (q.get("kind") or ["any"])[0]))
        if path == "/api/assets":
            return self._json({"assets": self.studio.assets(),
                               "audio": self.studio.assets("audio")})
        if path == "/api/anim":
            sc = (q.get("scene") or [self.studio.scene])[0]
            sp = (q.get("step") or ["-1"])[0]
            ms = (q.get("ms") or ["1200"])[0]
            return self._send(200, "image/apng", self.studio.anim(sc, sp, ms))
        if path == "/api/asset":
            return self._asset((q.get("f") or [""])[0])
        self._json({"error": "not found"}, 404)

    def _asset(self, f):
        """Serves a project file. Blocks escaping the base directory."""
        base = os.path.realpath(self.studio.base)
        full = os.path.realpath(os.path.join(base, f))
        if full != base and not full.startswith(base + os.sep):
            return self._json({"error": "forbidden"}, 403)
        if not os.path.isfile(full):
            return self._json({"error": "does not exist"}, 404)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        self._send(200, ctype, open(full, "rb").read())

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        n = int(self.headers.get("Content-Length") or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._json({"error": "invalid json"}, 400)
        if path == "/api/op":
            try:
                return self._json(self.studio.op(req))
            except Exception as e:                # do not bring the server down over a bad op
                return self._json({"error": f"{type(e).__name__}: {e}"}, 400)
        self._json({"error": "not found"}, 404)


def make_server(studio, host="127.0.0.1", port=8765):
    """If the port is busy (typically another VN Studio left open), grabs the
    next free one instead of dying with a traceback."""
    handler = type("Handler", (_Handler,), {"studio": studio})
    for p in list(range(port, port + 10)) + [0]:
        try:
            return ThreadingHTTPServer((host, p), handler)
        except OSError as e:
            if e.errno != errno.EADDRINUSE:
                raise
    raise OSError("no free ports")


def autosave_path(path):
    """h.vn -> h.autosave.vn (visible and with .vn: it can be opened from the file browser)."""
    root, ext = os.path.splitext(path)
    return f"{root}.autosave{ext or '.vn'}"


# --- processes: find / stop the running server -----------------

PIDDIR = os.path.join(os.environ.get("XDG_RUNTIME_DIR")
                      or os.path.join(os.path.expanduser("~"), ".cache"), "znt")


def _pidfile(port):
    return os.path.join(PIDDIR, f"web-{port}.pid")


def _alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _write_pid(port):
    try:
        os.makedirs(PIDDIR, exist_ok=True)
        open(_pidfile(port), "w").write(str(os.getpid()))
    except OSError:
        pass


def _scan_proc(port):
    """Sweep of /proc: finds `python -m znt web` even if it left no pidfile
    (e.g. an old server). Linux only; other OSes just get the pidfile."""
    out = []
    try:
        pids = [int(x) for x in os.listdir("/proc") if x.isdigit()]
    except OSError:
        return out
    for pid in pids:
        if pid == os.getpid():
            continue
        try:
            argv = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")
        except OSError:
            continue
        argv = [a.decode("utf-8", "replace") for a in argv if a]
        if "web" in argv and "znt" in argv:            # exact tokens, not substrings
            got = 8765
            if "--port" in argv:
                try:
                    got = int(argv[argv.index("--port") + 1])
                except (IndexError, ValueError):
                    pass
            out.append((pid, got))
    return out


def running(port=8765):
    """[(pid, port)] of the VN Studio web servers running on that port."""
    found = {}
    f = _pidfile(port)
    try:
        pid = int(open(f).read().strip())
        if _alive(pid):
            found[pid] = port
        else:
            os.remove(f)                                # stale pidfile
    except (OSError, ValueError):
        pass
    for pid, p in _scan_proc(port):
        if p == port:
            found[pid] = p
    return sorted(found.items())


def stop(port=8765, timeout=5.0):
    """Stops the server on that port. Returns the pids it stopped."""
    killed = []
    for pid, _ in running(port):
        try:
            os.kill(pid, signal.SIGTERM); killed.append(pid)
        except OSError:
            pass
    fin = time.time() + timeout
    for pid in killed:
        while _alive(pid) and time.time() < fin:
            time.sleep(0.05)
        if _alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)            # did not go quietly
            except OSError:
                pass
    try:
        os.remove(_pidfile(port))
    except OSError:
        pass
    return killed


def serve(path=None, host="127.0.0.1", port=8765, open_browser=True, restart=False):
    if restart:
        gone = stop(port)
        print(f"stopped the previous server (pid {', '.join(map(str, gone))})" if gone
              else "no server was running on that port")
    st = Studio(path)
    httpd = make_server(st, host, port)
    got = httpd.server_address[1]
    _write_pid(got)
    if port and got != port:
        print(f"⚠ port {port} was already in use (another VN Studio open?): "
              f"using {got}. Close the old one if you do not want it.")
    url = f"http://{host}:{got}/"
    print(f"VN Studio (web) at {url}   — Ctrl+C to quit", flush=True)
    if open_browser:
        try:
            import webbrowser; webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        try:
            os.remove(_pidfile(got))
        except OSError:
            pass


def demo():
    """Self-check: in-process Studio ops + one round trip through the HTTP layer."""
    import tempfile, threading, urllib.request
    d = tempfile.mkdtemp(); p = os.path.join(d, "d.vn")
    open(p, "w", encoding="utf-8").write('title: T\ncharacter a "Ana"\nscene s\n  a: hello\n  end\n')
    st = Studio(p)
    assert st.state()["model"]["title"] == "T" and st.scene == "s" and st.step == -1
    n = len(st.steps())
    st.op({"op": "add_step", "kind": "say"}); assert len(st.steps()) == n + 1
    st.op({"op": "undo"});                    assert len(st.steps()) == n
    st.op({"op": "redo"});                    assert len(st.steps()) == n + 1
    st.op({"op": "undo"})
    st.op({"op": "select", "scene": "s", "step": 0})
    st.op({"op": "set_props", "props": {"text": "bye"}})
    assert st.steps()[0]["text"] == "bye", st.steps()[0]
    assert st.op({"op": "validate"})["problems"] == []
    st.op({"op": "save"}); assert "bye" in open(p, encoding="utf-8").read()
    # new scene + rename re-points gotos
    st.op({"op": "add_scene", "name": "dos"}); assert "dos" in st.model["scenes"]
    st.op({"op": "rename_scene", "name": "final"}); assert "final" in st.model["scenes"]
    # stage: layer layout for the browser to compose
    p2 = os.path.join(d, "s.vn")
    open(p2, "w", encoding="utf-8").write(
        'title: T2\ncharacter z "Zoe" color=#88ffdd\nscene s\n  bg grad:#101828,#304060\n'
        '  show z left\n  z: hello\n  end\n')
    sg = Studio(p2).stage("s", 2)
    assert (sg["w"], sg["h"]) == (640, 448)
    assert sg["bg"]["kind"] == "grad" and sg["bg"]["a"] == "#101828"
    L = {l["id"]: l for l in sg["layers"]}
    assert L["z"]["x"] == -180 and L["z"]["url"] is None and L["z"]["color"] == "#88ffdd", L["z"]
    assert (L["z"]["w"], L["z"]["h"]) == (200, 300)          # placeholder
    assert sg["say"]["name"] == "Zoe" and sg["say"]["text"] == "hello"

    # drag: set_layer_pos writes x/y to that character's last `show`
    p3 = os.path.join(d, "g.vn")
    open(p3, "w", encoding="utf-8").write(
        'title: T3\ncharacter z "Zoe"\nscene s\n  show z left\n  z: hello\n  end\n')
    s3 = Studio(p3)
    s3.op({"op": "select", "scene": "s", "step": 1})
    s3.op({"op": "set_layer_pos", "id": "z", "x": 42.4, "y": -7.6})
    sh = s3.model["scenes"]["s"][0]
    assert sh["op"] == "show" and sh["x"] == 42 and sh["y"] == -8, sh
    assert s3.state()["can_undo"], "the drag must go into the history"

    # character sprite: assign and remove (back to the placeholder)
    s4 = Studio(p2)
    s4.op({"op": "set_sprite", "id": "z", "file": "zoe.png"})
    assert s4.model["characters"]["z"]["sprite"] == "zoe.png"
    s4.op({"op": "set_sprite", "id": "z", "file": ""})
    assert "sprite" not in s4.model["characters"]["z"]

    # authoritative preview: APNG rendered with the real engine
    ap = Studio(p2).anim("s", 2, ms=200)
    assert ap[:8] == b"\x89PNG\r\n\x1a\n" and b"acTL" in ap, "the preview must be an APNG"

    # HTTP layer
    httpd = make_server(st, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    got = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/model"))
    assert got["model"]["scenes"]["s"][0]["text"] == "bye"
    httpd.shutdown(); httpd.server_close()
    print("demo OK")


if __name__ == "__main__":
    demo()


def cli(args):
    """znt web [project.vn] [--port N] [--restart] [--stop] [--no-browser]"""
    port, path, restart, browser, do_stop = 8765, None, False, True, False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--port" and i + 1 < len(args):
            i += 1; port = int(args[i])
        elif a in ("--restart", "-r"):
            restart = True
        elif a == "--stop":
            do_stop = True
        elif a in ("--no-browser", "-n"):
            browser = False
        elif not a.startswith("-"):
            path = a
        i += 1
    if do_stop:
        gone = stop(port)
        print(f"stopped the server (pid {', '.join(map(str, gone))})" if gone
              else f"no VN Studio was running on port {port}")
        return
    serve(path, port=port, open_browser=browser, restart=restart)
