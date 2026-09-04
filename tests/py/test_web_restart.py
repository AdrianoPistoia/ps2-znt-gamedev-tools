"""Reiniciar el server desde la CLI: encontrarlo, bajarlo y levantar otro."""
import os, sys, socket, subprocess, time, json, urllib.request, urllib.error, tempfile
from znt.web import server as ws

repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
d = tempfile.mkdtemp(); p = os.path.join(d, "h.vn")
open(p, "w", encoding="utf-8").write('title: T\ncharacter a "Ana"\nscene s\n  a: hola\n  end\n')

s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
env = dict(os.environ, PYTHONPATH=repo)
proc = subprocess.Popen([sys.executable, "-m", "znt", "web", p, "--port", str(port)],
                        cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

def up(t=8.0):
    fin = time.time() + t
    while time.time() < fin:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/model", timeout=.5).read()
            return True
        except Exception:
            time.sleep(.15)
    return False

assert up(), "el server no levantó: " + (proc.stdout.read(400).decode() if proc.poll() else "")

# 1) se lo puede encontrar (pidfile + barrido de procesos)
found = ws.running(port)
assert any(pid == proc.pid for pid, _ in found), (found, proc.pid)
assert ws.running(port + 1) == [], "no confunde puertos"

# 2) se lo baja y el puerto queda libre
killed = ws.stop(port)
assert proc.pid in killed, killed
proc.wait(timeout=5)
srv = ws.make_server(ws.Studio(p), "127.0.0.1", port)      # ahora sí entra ahí
assert srv.server_address[1] == port, "el puerto tiene que quedar libre"
srv.server_close()
assert ws.running(port) == [], "y el pidfile se limpia"
assert ws.stop(port) == [], "bajar lo que ya no está no rompe"
print("RESTART GREEN")
