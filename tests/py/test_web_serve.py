"""Levantar el server: puerto ocupado, versión de API y guardar sin ruta."""
import socket, tempfile, os
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write('title: T\ncharacter a "Ana"\nscene s\n  a: hola\n  end\n')
st = ws.Studio(p)

# 1) si el puerto está ocupado (otro VN Studio abierto), busca otro en vez de explotar
busy = socket.socket(); busy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
busy.bind(("127.0.0.1", 0)); busy.listen(1)
port = busy.getsockname()[1]
srv = ws.make_server(st, "127.0.0.1", port)
assert srv.server_address[1] != port, "tendría que haber elegido otro puerto"
srv.server_close(); busy.close()

# 2) la UI tiene que poder darse cuenta de que el server es viejo
assert isinstance(ws.API, int) and ws.API > 0
assert st.state()["api"] == ws.API, "el estado viaja con la versión de la API"

# 3) guardar un proyecto nuevo (sin ruta) no puede ser un no-op silencioso
st2 = ws.Studio(None)
r = st2.op({"op": "save"})
assert r.get("error"), "sin ruta hay que avisar, no tragarse el guardado"
r = st2.op({"op": "save", "path": os.path.join(d, "nuevo.vn")})
assert not r.get("error") and os.path.exists(os.path.join(d, "nuevo.vn"))
assert r["path"].endswith("nuevo.vn"), "y queda como ruta del proyecto"
print("SERVE GREEN")
