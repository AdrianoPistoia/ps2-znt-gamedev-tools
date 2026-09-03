#!/usr/bin/env python3
"""Servidor del editor web (stdlib). `Studio` es el estado del editor (modelo,
selección, historial) sin ninguna UI; el handler HTTP lo expone como API JSON.
"""
import json, os, copy, mimetypes, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .. import vn, frontends
from ..vnstudio import VNRuntime

UI = os.path.join(os.path.dirname(__file__), "ui.html")
HIST_MAX = 60


class Studio:
    """Estado del editor, agnóstico de UI (lo usa el server; testeable solo)."""

    def __init__(self, path=None):
        if path and os.path.exists(path):
            self.model = vn._link_choices(vn.parse(open(path, encoding="utf-8").read()))
            self.base = os.path.dirname(os.path.abspath(path))
            self.path = path
        else:
            self.model = vn.blank_model()
            self.base = os.getcwd()
            self.path = None
        self.rt = VNRuntime(self.model, self.base)   # render/animación reales
        self.scene = self.model["order"][0]
        self.step = -1
        self.undo, self.redo = [], []
        self.problems = []

    # --- helpers -----------------------------------------------------------
    def steps(self):
        return self.model["scenes"][self.scene]

    def _snapshot(self):
        self.undo.append(copy.deepcopy(self.model)); self.redo.clear()
        if len(self.undo) > HIST_MAX:
            self.undo.pop(0)

    def _restore(self, saved):
        self.model.clear(); self.model.update(copy.deepcopy(saved))   # in-place: rt lo ve
        self.rt.invalidate()
        if self.scene not in self.model["scenes"]:
            self.scene = self.model["order"][0]
        self.step = min(self.step, len(self.steps()) - 1)

    def state(self):
        return {"model": self.model, "scene": self.scene, "step": self.step,
                "path": self.path, "base": self.base, "problems": self.problems,
                "step_ops": vn.STEP_OPS,
                "can_undo": bool(self.undo), "can_redo": bool(self.redo)}

    # --- operaciones -------------------------------------------------------
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
            i = self.step + 1 if self.step >= 0 else len(self.steps())
            self.steps().insert(i, s); self.step = i
        elif o == "del_step":
            if 0 <= self.step < len(self.steps()):
                self._snapshot(); self.steps().pop(self.step)
                self.step = min(self.step, len(self.steps()) - 1)
        elif o == "dup_step":
            if 0 <= self.step < len(self.steps()):
                self._snapshot(); vn.duplicate_step(self.steps(), self.step); self.step += 1
        elif o == "move_step":
            d = int(r.get("delta", 0)); i, j = self.step, self.step + d
            if 0 <= i < len(self.steps()) and 0 <= j < len(self.steps()):
                self._snapshot()
                self.steps()[i], self.steps()[j] = self.steps()[j], self.steps()[i]
                self.step = j
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
        elif o == "add_char":
            cid = (r.get("id") or "").strip()
            if cid and cid not in self.model["characters"]:
                self._snapshot()
                self.model["characters"][cid] = {"name": r.get("name") or cid,
                                                 "color": r.get("color") or "#7cc4ff"}
        elif o == "set_sprite":
            cid, f = r.get("id"), (r.get("file") or "").strip()
            c = self.model["characters"].get(cid)
            if c is not None:
                self._snapshot()
                if f: c["sprite"] = f
                else: c.pop("sprite", None)      # sin archivo -> vuelve al placeholder
        elif o == "rename_char":
            self._snapshot(); vn.rename_character(self.model, r.get("old"), r.get("new"))
        elif o == "set_layer_pos":
            # el drag mueve una CAPA: escribe x/y en el último `show` de ese
            # personaje en o antes del paso seleccionado.
            cid, steps = r.get("id"), self.steps()
            end = self.step if self.step >= 0 else len(steps) - 1
            tgt = None
            for i in range(min(end, len(steps) - 1), -1, -1):
                if steps[i]["op"] == "show" and steps[i].get("id") == cid:
                    tgt = steps[i]; break
            if tgt is not None:
                self._snapshot()
                tgt["x"] = int(round(float(r.get("x", tgt.get("x", 0)))))
                tgt["y"] = int(round(float(r.get("y", tgt.get("y", 0)))))
        elif o == "undo":
            if self.undo:
                self.redo.append(copy.deepcopy(self.model)); self._restore(self.undo.pop())
        elif o == "redo":
            if self.redo:
                self.undo.append(copy.deepcopy(self.model)); self._restore(self.redo.pop())
        elif o == "validate":
            self.problems = vn.validate(self.model, self.base)
        elif o == "save":
            p = r.get("path") or self.path
            if p:
                open(p, "w", encoding="utf-8").write(vn.to_text(self.model)); self.path = p
        elif o == "export":
            p = r.get("path") or os.path.join(self.base, "player.html")
            open(p, "w", encoding="utf-8").write(vn.render_html(self.model, self.base))
        if o not in ("select", "validate", "save", "export"):
            self.rt.invalidate()
        return self.state()

    def anim(self, scene, step, ms=1200, fps=15, shrink=2):
        """Preview AUTORITATIVO: renderiza la transición con el engine real
        (curvas y acciones de Python) y la empaqueta como APNG para que el
        browser la reproduzca nativamente."""
        import tempfile
        if scene not in self.model["scenes"]:
            scene = self.model["order"][0]
        ms = max(200, min(int(ms), 3000))
        dt = max(1, 1000 // int(fps))
        self.rt.preview_upto(scene, int(step), settle=False)   # animación viva desde t=0
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

    # --- stage para que el browser componga con CSS ------------------------
    def stage(self, scene, step):
        """Layout de las capas tras aplicar los pasos 0..step (el render real lo
        hace el runtime; acá sólo describimos qué dibujar y dónde)."""
        if scene not in self.model["scenes"]:
            scene = self.model["order"][0]
        step = int(step)
        self.rt.preview_upto(scene, step)
        url = lambda f: "/api/asset?f=" + urllib.parse.quote(f)
        bg = {"kind": "solid", "color": "#000000"}
        for st_ in self.model["scenes"][scene][:step + 1]:
            if st_["op"] == "bg":
                sp = st_["spec"]
                bg = {"kind": "img", "url": url(sp["file"])} if sp.get("kind") == "img" else dict(sp)
        layers = []
        for name, l in self.rt.stage.items():
            if name == "bg" or not l.rows or not l.show:
                continue
            c = self.model["characters"].get(name, {})
            spr = c.get("sprite")
            layers.append({"id": name, "name": c.get("name", name), "color": c.get("color", "#888888"),
                           "x": l.x, "y": l.y, "z": l.level, "zoom": l.zoom,
                           "opacity": l.opacity, "tint": l.tint,
                           "w": len(l.rows[0]) // 4, "h": len(l.rows),
                           "url": url(spr) if spr else None})
        say = None
        if self.rt.text is not None:
            cc = self.model["characters"].get(self.rt.speaker, {})
            say = {"who": self.rt.speaker, "name": cc.get("name", self.rt.speaker or ""),
                   "color": cc.get("color", "#cccccc"), "text": self.rt.text}
        return {"w": self.rt.W, "h": self.rt.H, "bg": bg, "layers": layers,
                "say": say, "choices": self.rt.choices, "bgm": self.rt.bgm}

    def _set_props(self, s, props):
        for k, v in props.items():
            if k == "bg":                       # el cliente manda el arg tal cual
                s["spec"] = vn._bg(str(v).strip())
            elif k == "options":                # choice: lista de {label,target}
                s["options"] = v
            elif k == "params":
                s["params"] = v
            elif v == "" and k in ("tint", "file"):
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
        pass                                     # silencio

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
                body = b"<html><body>falta ui.html</body></html>"
            return self._send(200, "text/html; charset=utf-8", body)
        if path.startswith("/static/"):
            f = os.path.join(os.path.dirname(__file__), "static", os.path.basename(path))
            if not os.path.isfile(f):
                return self._json({"error": "no existe"}, 404)
            ctype = mimetypes.guess_type(f)[0] or "application/octet-stream"
            return self._send(200, ctype, open(f, "rb").read())
        if path == "/api/model":
            return self._json(self.studio.state())
        q = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
        if path == "/api/stage":
            sc = (q.get("scene") or [self.studio.scene])[0]
            sp = (q.get("step") or ["-1"])[0]
            return self._json(self.studio.stage(sc, sp))
        if path == "/api/assets":
            return self._json({"assets": vn.list_assets(self.studio.base)})
        if path == "/api/anim":
            sc = (q.get("scene") or [self.studio.scene])[0]
            sp = (q.get("step") or ["-1"])[0]
            ms = (q.get("ms") or ["1200"])[0]
            return self._send(200, "image/apng", self.studio.anim(sc, sp, ms))
        if path == "/api/asset":
            return self._asset((q.get("f") or [""])[0])
        self._json({"error": "not found"}, 404)

    def _asset(self, f):
        """Sirve un archivo del proyecto. Bloquea salir del directorio base."""
        base = os.path.realpath(self.studio.base)
        full = os.path.realpath(os.path.join(base, f))
        if full != base and not full.startswith(base + os.sep):
            return self._json({"error": "prohibido"}, 403)
        if not os.path.isfile(full):
            return self._json({"error": "no existe"}, 404)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        self._send(200, ctype, open(full, "rb").read())

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        n = int(self.headers.get("Content-Length") or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._json({"error": "json inválido"}, 400)
        if path == "/api/op":
            try:
                return self._json(self.studio.op(req))
            except Exception as e:                # no tirar el server por un op malo
                return self._json({"error": f"{type(e).__name__}: {e}"}, 400)
        self._json({"error": "not found"}, 404)


def make_server(studio, host="127.0.0.1", port=8765):
    handler = type("Handler", (_Handler,), {"studio": studio})
    return ThreadingHTTPServer((host, port), handler)


def serve(path=None, host="127.0.0.1", port=8765, open_browser=True):
    st = Studio(path)
    httpd = make_server(st, host, port)
    url = f"http://{host}:{httpd.server_address[1]}/"
    print(f"VN Studio (web) en {url}   — Ctrl+C para salir")
    if open_browser:
        try:
            import webbrowser; webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nchau")


def demo():
    """Self-check: ops del Studio en proceso + una vuelta por la capa HTTP."""
    import tempfile, threading, urllib.request
    d = tempfile.mkdtemp(); p = os.path.join(d, "d.vn")
    open(p, "w", encoding="utf-8").write('title: T\ncharacter a "Ana"\nscene s\n  a: hola\n  end\n')
    st = Studio(p)
    assert st.state()["model"]["title"] == "T" and st.scene == "s" and st.step == -1
    n = len(st.steps())
    st.op({"op": "add_step", "kind": "say"}); assert len(st.steps()) == n + 1
    st.op({"op": "undo"});                    assert len(st.steps()) == n
    st.op({"op": "redo"});                    assert len(st.steps()) == n + 1
    st.op({"op": "undo"})
    st.op({"op": "select", "scene": "s", "step": 0})
    st.op({"op": "set_props", "props": {"text": "chau"}})
    assert st.steps()[0]["text"] == "chau", st.steps()[0]
    assert st.op({"op": "validate"})["problems"] == []
    st.op({"op": "save"}); assert "chau" in open(p, encoding="utf-8").read()
    # escena nueva + rename reapunta gotos
    st.op({"op": "add_scene", "name": "dos"}); assert "dos" in st.model["scenes"]
    st.op({"op": "rename_scene", "name": "final"}); assert "final" in st.model["scenes"]
    # stage: layout de capas para que el browser componga
    p2 = os.path.join(d, "s.vn")
    open(p2, "w", encoding="utf-8").write(
        'title: T2\ncharacter z "Zoe" color=#88ffdd\nscene s\n  bg grad:#101828,#304060\n'
        '  show z left\n  z: hola\n  end\n')
    sg = Studio(p2).stage("s", 2)
    assert (sg["w"], sg["h"]) == (640, 448)
    assert sg["bg"]["kind"] == "grad" and sg["bg"]["a"] == "#101828"
    L = {l["id"]: l for l in sg["layers"]}
    assert L["z"]["x"] == -180 and L["z"]["url"] is None and L["z"]["color"] == "#88ffdd", L["z"]
    assert (L["z"]["w"], L["z"]["h"]) == (200, 300)          # placeholder
    assert sg["say"]["name"] == "Zoe" and sg["say"]["text"] == "hola"

    # drag: set_layer_pos escribe x/y en el último `show` de ese personaje
    p3 = os.path.join(d, "g.vn")
    open(p3, "w", encoding="utf-8").write(
        'title: T3\ncharacter z "Zoe"\nscene s\n  show z left\n  z: hola\n  end\n')
    s3 = Studio(p3)
    s3.op({"op": "select", "scene": "s", "step": 1})
    s3.op({"op": "set_layer_pos", "id": "z", "x": 42.4, "y": -7.6})
    sh = s3.model["scenes"]["s"][0]
    assert sh["op"] == "show" and sh["x"] == 42 and sh["y"] == -8, sh
    assert s3.state()["can_undo"], "el drag debe entrar en el historial"

    # sprite del personaje: asignar y quitar (vuelve al placeholder)
    s4 = Studio(p2)
    s4.op({"op": "set_sprite", "id": "z", "file": "zoe.png"})
    assert s4.model["characters"]["z"]["sprite"] == "zoe.png"
    s4.op({"op": "set_sprite", "id": "z", "file": ""})
    assert "sprite" not in s4.model["characters"]["z"]

    # preview autoritativo: APNG renderizado con el engine real
    ap = Studio(p2).anim("s", 2, ms=200)
    assert ap[:8] == b"\x89PNG\r\n\x1a\n" and b"acTL" in ap, "el preview debe ser un APNG"

    # capa HTTP
    httpd = make_server(st, "127.0.0.1", 0)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    got = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/model"))
    assert got["model"]["scenes"]["s"][0]["text"] == "chau"
    httpd.shutdown(); httpd.server_close()
    print("demo OK")


if __name__ == "__main__":
    demo()
