"""Bringing up the server: busy port, API version and saving without a path."""
import socket, tempfile, os
from znt.web import server as ws

d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write('title: T\ncharacter a "Ana"\nscene s\n  a: hello\n  end\n')
st = ws.Studio(p)

# 1) if the port is busy (another VN Studio open), it picks another instead of blowing up
busy = socket.socket(); busy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
busy.bind(("127.0.0.1", 0)); busy.listen(1)
port = busy.getsockname()[1]
srv = ws.make_server(st, "127.0.0.1", port)
assert srv.server_address[1] != port, "should have picked another port"
srv.server_close(); busy.close()

# 2) the UI must be able to tell the server is old
assert isinstance(ws.API, int) and ws.API > 0
assert st.state()["api"] == ws.API, "the state carries the API version"

# 3) saving a new project (no path) must not be a silent no-op
st2 = ws.Studio(None)
r = st2.op({"op": "save"})
assert r.get("error"), "without a path it must warn, not swallow the save"
r = st2.op({"op": "save", "path": os.path.join(d, "new.vn")})
assert not r.get("error") and os.path.exists(os.path.join(d, "new.vn"))
assert r["path"].endswith("new.vn"), "and it becomes the project path"
print("SERVE GREEN")
