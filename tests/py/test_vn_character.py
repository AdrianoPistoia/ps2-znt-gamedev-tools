"""The `character` line accepts the color as color= or bare at the end."""
from znt import vn

m = vn.parse('title: T\n'
             'character a "Ana" color=#7cc4ff\n'
             'character b "Leo" #f0a92e\n'
             'character c "Cy"\n'
             'scene s\n  a: hola\n  end\n')
assert m["characters"]["a"] == {"name": "Ana", "color": "#7cc4ff"}, m["characters"]["a"]
assert m["characters"]["b"] == {"name": "Leo", "color": "#f0a92e"}, m["characters"]["b"]
assert m["characters"]["c"]["name"] == "Cy" and m["characters"]["c"]["color"] == "#cccccc"

# round-trip: what we write reads back the same
assert vn.parse(vn.to_text(m))["characters"] == m["characters"]
print("CHARACTER GREEN")
