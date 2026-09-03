#!/usr/bin/env python3
"""Escaner heuristico del corpus Squirrel para mapear la API del engine.

No es un parser de Squirrel: quita comentarios y literales de string, y despues
reconoce con regex las *definiciones* (class/function/local/enum/const/slots) y
las *llamadas* (`nombre(` global vs `.metodo(`). Un identificador llamado como
funcion global y nunca definido en el corpus es, casi seguro, un nativo que el
engine expone via SqPlus. Cruzarlo con los strings del ELF lo confirma.

  python -m znt scan scripts/                 # catalogo a stdout
  python -m znt scan scripts/ --elf SLPS_257.09 [--json api.json]

ponytail: heuristico por regex. Falla en casos raros (nombres en macros, llamadas
por variable). Suficiente para el catalogo; un parser real solo si hace falta.
"""
import os, re, sys, glob, json, collections

# Palabras reservadas de Squirrel 2.x/3.x: nunca son nativos del engine.
KEYWORDS = {
    "base", "break", "case", "catch", "class", "clone", "continue", "const",
    "default", "delete", "delegate", "do", "else", "enum", "extends", "for",
    "foreach", "function", "if", "in", "instanceof", "local", "null", "resume",
    "return", "switch", "this", "throw", "try", "typeof", "while", "yield",
    "constructor", "static", "rawcall", "true", "false", "vargc", "vargv",
}
# Builtins del propio lenguaje (funciones globales de la stdlib de Squirrel).
SQ_BUILTINS = {
    "print", "error", "compilestring", "collectgarbage", "getroottable",
    "setroottable", "getconsttable", "setconsttable", "assert", "format",
    "array", "type", "callee", "dummy", "getstackinfos", "newthread",
    "suspend", "sin", "cos", "tan", "atan", "atan2", "sqrt", "pow", "exp",
    "log", "log10", "floor", "ceil", "abs", "fabs", "rand", "srand", "min", "max",
}

_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)
_STRING = re.compile(r'@"[^"]*"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', re.S)
_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"

_DEF_CLASS = re.compile(r"\bclass\s+(" + _IDENT + r")")
_DEF_FUNC = re.compile(r"\bfunction\s+(" + _IDENT + r")")
_DEF_LOCAL = re.compile(r"\blocal\s+(" + _IDENT + r")")
_DEF_ENUM = re.compile(r"\b(?:enum|const)\s+(" + _IDENT + r")")
_DEF_SLOT = re.compile(r"(" + _IDENT + r")\s*<-")           # nombre <- valor
_DEF_MEMBER = re.compile(r"^\s*(" + _IDENT + r")\s*=", re.M)  # miembro/asignacion
_CALL = re.compile(r"(\.?)(" + _IDENT + r")\s*\(")


def strip(src):
    """Quita comentarios y literales para no confundir identificadores."""
    src = _COMMENT.sub(" ", src)
    src = _STRING.sub('""', src)
    return src


def scan_text(src, defined, gcalls, mcalls, params):
    src = strip(src)
    for rx, bucket in ((_DEF_CLASS, defined), (_DEF_FUNC, defined),
                       (_DEF_LOCAL, defined), (_DEF_ENUM, defined),
                       (_DEF_SLOT, defined), (_DEF_MEMBER, defined)):
        bucket.update(rx.findall(src))
    # parametros de funcion: no son nativos aunque se los llame
    for m in re.finditer(r"\bfunction\b[^(]*\(([^)]*)\)", src):
        params.update(p.strip().split("=")[0].strip()
                      for p in m.group(1).split(",") if p.strip())
    for dot, name in _CALL.findall(src):
        (mcalls if dot else gcalls)[name] += 1


def scan(paths):
    defined, params = set(), set()
    gcalls, mcalls = collections.Counter(), collections.Counter()
    files = [p for pat in paths for p in (glob.glob(f"{pat}/*.nut") if os.path.isdir(pat) else [pat])]
    for p in sorted(files):
        raw = open(p, "rb").read()
        try:
            src = raw.decode("cp932")
        except UnicodeDecodeError:
            src = raw.decode("latin1")
        scan_text(src, defined, gcalls, mcalls, params)
    known = defined | params | KEYWORDS | SQ_BUILTINS
    natives = {n: c for n, c in gcalls.items() if n not in known}
    return dict(files=len(files), defined=defined, params=params,
                gcalls=gcalls, mcalls=mcalls, natives=natives)


def elf_strings(path, minlen=3):
    data = open(path, "rb").read()
    return set(re.findall(rb"[!-~]{%d,}" % minlen, data))


def report(res, elf=None):
    natives = res["natives"]
    in_elf = set()
    if elf:
        strs = elf_strings(elf)
        in_elf = {n for n in natives if n.encode() in strs}
    print(f"# API del engine (heuristico) — {res['files']} escenas")
    print(f"# definidos en corpus: {len(res['defined'])} | "
          f"nativos candidatos: {len(natives)} | metodos distintos: {len(res['mcalls'])}")
    print()
    print("## Nativos candidatos (llamada global, no definida en el corpus)")
    if elf:
        print("## [E] = el nombre aparece como string en el ELF (binding SqPlus confirmado)")
    for n, c in sorted(natives.items(), key=lambda kv: -kv[1]):
        tag = " [E]" if n in in_elf else ""
        print(f"  {c:5d}  {n}{tag}")
    print()
    print("## Metodos mas llamados (.metodo(), sobre objetos del engine o propios)")
    for n, c in res["mcalls"].most_common(40):
        print(f"  {c:5d}  .{n}")


def cli(argv):
    if not argv or argv[0] == "demo":
        return demo()
    paths, elf, jsonout = [], None, None
    it = iter(argv)
    for a in it:
        if a == "--elf":
            elf = next(it)
        elif a == "--json":
            jsonout = next(it)
        else:
            paths.append(a)
    res = scan(paths)
    if jsonout:
        out = {k: (sorted(v) if isinstance(v, set) else v) for k, v in res.items()}
        json.dump(out, open(jsonout, "w"), ensure_ascii=False, indent=1)
        print(f"escrito {jsonout}")
    report(res, elf)


def demo():
    src = """
    class Foo { function bar(x) { return baz(x); } }
    function helper(a, b) { return a + drawSprite(b); }
    reset();
    local q = 1;
    obj.play();
    // comment drawSprite(fake)
    local s = "string with call(inside)";
    """
    d, p = set(), set()
    g, m = collections.Counter(), collections.Counter()
    scan_text(src, d, g, m, p)
    assert "Foo" in d and "bar" in d and "helper" in d and "q" in d, d
    assert "baz" in g and "drawSprite" in g and "reset" in g, dict(g)
    assert "call" not in g, "no debe contar llamadas dentro de strings"
    assert "play" in m and "drawSprite" not in m, dict(m)
    # 'bar'/'helper' definidas, 'x'/'a'/'b' son params -> no nativos
    known = d | p | KEYWORDS | SQ_BUILTINS
    natives = {n for n in g if n not in known}
    assert natives == {"baz", "drawSprite", "reset"}, natives
    assert "print" not in natives  # builtin de Squirrel
    print("demo OK")


if __name__ == "__main__":
    cli(sys.argv[1:])
