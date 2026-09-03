"""La línea `character` acepta el color con color= o suelto al final."""
from znt import vn

m = vn.parse('title: T\n'
             'character a "Ana" color=#7cc4ff\n'
             'character b "Leo" #f0a92e\n'
             'character c "Cy"\n'
             'scene s\n  a: hola\n  end\n')
assert m["characters"]["a"] == {"name": "Ana", "color": "#7cc4ff"}, m["characters"]["a"]
assert m["characters"]["b"] == {"name": "Leo", "color": "#f0a92e"}, m["characters"]["b"]
assert m["characters"]["c"]["name"] == "Cy" and m["characters"]["c"]["color"] == "#cccccc"

# ida y vuelta: lo que escribimos se vuelve a leer igual
assert vn.parse(vn.to_text(m))["characters"] == m["characters"]
print("CHARACTER GREEN")
