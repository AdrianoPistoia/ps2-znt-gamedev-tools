#!/usr/bin/env python3
"""Transpila el AST de Squirrel (`sqparse`) a Python que corre sobre el runtime
`sqrt`. Una unidad Squirrel -> Python que opera sobre un root table `R`
(globals, nativos, builtins).

Resolución de nombres (en codegen):
- local/param          -> variable Python
- miembro de la clase  -> `_get(_this,'x')` / `_set(_this,'x',v)`  (implicit this)
- lo demás             -> `R['x']`  (global / nativo / builtin)

Closures y clases: las funciones y lambdas se emiten como `def` anidados en el
mismo bloque donde se usan (hoisting de `_aux`), para que capturen los locales
que corresponden. Corrutinas: sin tratamiento especial; `suspend()` suspende el
SqThread actual vía runtime.

  python -m znt sqtranspile demo | check <dir/> | file <scene.nut>
"""
import sys, glob
from .sqparse import parse

CMP = {"==": "==", "!=": "!=", "<": "<", ">": ">", "<=": "<=", ">=": ">="}
BOOL = {"&&": "and", "||": "or"}
BITS = {"&": "&", "|": "|", "^": "^", "<<": "<<", ">>": ">>"}
HELPER = {"+": "_add", "-": "_sub", "*": "_mul", "/": "_div", "%": "_mod", "<=>": "_cmp"}
AUG = {"+=": "_add", "-=": "_sub", "*=": "_mul", "/=": "_div", "%=": "_mod"}


class T:
    def __init__(self):
        self.scopes = [set()]
        self.members = None
        self.class_members = {}
        self.tmp = 0
        self.aux = []          # bloques de defs (líneas a indent 0) pendientes

    def push(self): self.scopes.append(set())
    def pop(self): self.scopes.pop()
    def declare(self, name): self.scopes[-1].add(name)
    def is_local(self, name): return any(name in s for s in self.scopes)
    def newtmp(self, p="_t"): self.tmp += 1; return f"{p}{self.tmp}"

    def take_aux(self, ind):
        """Vuelca los defs pendientes, indentados a `ind`, y limpia."""
        pad = " " * ind
        out = []
        for block in self.aux:
            out += [pad + ln if ln else ln for ln in block]
        self.aux = []
        return out

    # nombres ----------------------------------------------------------------
    def load(self, name):
        if self.is_local(name): return name
        if self.members is not None and name in self.members:
            return f"_get(_this,{name!r})"
        return f"R[{name!r}]"

    def store(self, name, v):
        if self.is_local(name): return f"{name} = {v}"
        if self.members is not None and name in self.members:
            return f"_set(_this,{name!r},{v})"
        return f"R[{name!r}] = {v}"

    # expresiones ------------------------------------------------------------
    def ex(self, n):
        k = n[0]
        if k == "num": return repr(n[1])
        if k == "str": return repr(n[1])
        if k == "null": return "None"
        if k == "this": return "_this"
        if k == "base": return "_cls.base"
        if k == "name": return self.load(n[1])
        if k == "array": return "[" + ", ".join(self.ex(e) for e in n[1]) + "]"
        if k == "table":
            return "Table({" + ", ".join(f"{self.ex(a)}: {self.ex(b)}" for a, b in n[1]) + "})"
        if k == "index": return f"_get({self.ex(n[1])}, {self.ex(n[2])})"
        if k == "field": return f"_get({self.ex(n[1])}, {n[2]!r})"
        if k == "call": return self.call(n[1], n[2])
        if k == "bin": return self.binop(n[1], n[2], n[3])
        if k == "unary": return self.unop(n[1], n[2])
        if k == "postop": return self.ex(n[2])
        if k == "ternary":
            return f"({self.ex(n[2])} if _truth({self.ex(n[1])}) else {self.ex(n[3])})"
        if k == "assign":
            return self.assign(n[1], n[2], n[3], as_expr=True)
        if k == "lambda":
            return self.emit_func(params=n[1], defs=n[2], varg=n[3], body=n[4], this=False)
        if k == "lambda_expr":
            return self.emit_func(params=n[1], defs=n[2], varg=n[3],
                                  body=("block", [("return", n[4])]), this=False)
        if k == "classexpr": return self.make_class(None, n[1], n[2])
        raise NotImplementedError(f"expr {k}")

    def binop(self, op, a, b):
        ea, eb = self.ex(a), self.ex(b)
        if op in CMP: return f"({ea} {CMP[op]} {eb})"
        if op in BOOL: return f"({ea} {BOOL[op]} {eb})"
        if op in BITS: return f"({ea} {BITS[op]} {eb})"
        if op == "in": return f"_in({ea}, {eb})"
        if op == "instanceof": return f"_instanceof({ea}, {eb})"
        if op in HELPER: return f"{HELPER[op]}({ea}, {eb})"
        raise NotImplementedError(f"binop {op}")

    def unop(self, op, e):
        if op in ("++", "--"): return self.ex(e)
        ex = self.ex(e)
        if op == "-": return f"(- {ex})"
        if op == "!": return f"(not _truth({ex}))"
        if op == "~": return f"(~ {ex})"
        if op == "typeof": return f"_typeof({ex})"
        if op == "clone": return f"_clone({ex})"
        if op == "resume": return f"_get({ex},'call')()"
        if op == "delete":
            if e[0] == "index": return f"_delete({self.ex(e[1])}, {self.ex(e[2])})"
            if e[0] == "field": return f"_delete({self.ex(e[1])}, {e[2]!r})"
        raise NotImplementedError(f"unop {op}")

    def call(self, callee, args):
        a = ", ".join(self.ex(x) for x in args)
        if callee[0] == "field" and callee[1] == ("base",):   # base.metodo(...)
            return f"_basecall(_this, _cls.base, {callee[2]!r}{', ' + a if a else ''})"
        return f"{self.ex(callee)}({a})"

    # funciones / lambdas: emiten un def en aux y devuelven su nombre ---------
    def emit_func(self, params, defs, varg, body, this):
        name = self.newtmp("_fn")
        head = (["_this", "_cls"] if this else []) + \
               [f"{p}=None" if p in defs else p for p in params] + \
               (["*vargv"] if varg else [])
        saved = self.aux; self.aux = []
        self.push()
        for p in params: self.declare(p)
        lines = [f"def {name}({', '.join(head)}):"]
        for p in params:
            if p in defs:
                lines.append(f"    if {p} is None: {p} = {self.ex(defs[p])}")
                lines += self.take_aux(4)
        lines += self.stmts(body[1], 4)
        self.pop()
        self.aux = saved + [lines]
        return name

    def make_class(self, name, base, members):
        base_ex = self.ex(base) if base else "None"
        mem = {m[1] for m in members}
        if base and base[0] == "name" and base[1] in self.class_members:
            mem |= self.class_members[base[1]]
        if name: self.class_members[name] = mem
        prev = self.members; self.members = mem
        fields, methods = [], []
        for m in members:
            if m[0] == "field":
                fields.append((m[1], self.ex(m[2])))
            else:
                _, mname, params, defs, varg, body = m
                methods.append((mname, self.emit_func(params, defs, varg, body, this=True)))
        self.members = prev
        fexpr = "{" + ", ".join(f"{k!r}: (lambda: {v})" for k, v in fields) + "}"
        mexpr = "{" + ", ".join(f"{k!r}: {v}" for k, v in methods) + "}"
        return f"_class({name!r}, {base_ex}, {fexpr}, {mexpr})"

    # statements -------------------------------------------------------------
    def stmts(self, body, ind):
        out = []
        for s in body:
            out += self.st(s, ind)
        return out or [" " * ind + "pass"]

    def line(self, ind, code):
        """Una línea de statement, precedida por sus defs auxiliares."""
        pre = self.take_aux(ind)
        return pre + [" " * ind + code]

    def st(self, n, ind):
        k = n[0]; pad = " " * ind
        if k == "block": return self.stmts(n[1], ind)
        if k == "nop": return []
        if k == "expr": return self.expr_stmt(n[1], ind)
        if k == "local":
            out = []
            for name, val in n[1]:
                v = self.ex(val); self.declare(name)
                out += self.line(ind, f"{name} = {v}")
            return out
        if k == "return":
            return self.line(ind, "return " + self.ex(n[1]) if n[1] else "return")
        if k == "yield_stmt":
            return self.line(ind, "R['suspend'](" + (self.ex(n[1]) if n[1] else "") + ")")
        if k == "break": return [pad + "break"]
        if k == "continue": return [pad + "continue"]
        if k == "throw": return self.line(ind, f"raise _SqError({self.ex(n[1])})")
        if k == "if":
            cond = self.ex(n[1]); pre = self.take_aux(ind)
            out = pre + [pad + f"if _truth({cond}):"] + self.st(n[2], ind+4)
            if n[3]:
                out += [pad + "else:"] + self.st(n[3], ind+4)
            return out
        if k == "while":
            cond = self.ex(n[1]); pre = self.take_aux(ind)
            return pre + [pad + f"while _truth({cond}):"] + self.st(n[2], ind+4)
        if k == "dowhile":
            body = self.st(n[2], ind+4)
            cond = self.ex(n[1]); pre = self.take_aux(ind+4)
            return [pad + "while True:"] + body + pre + [pad + f"    if not _truth({cond}): break"]
        if k == "for": return self.for_stmt(n, ind)
        if k == "foreach": return self.foreach_stmt(n, ind)
        if k == "switch": return self.switch_stmt(n, ind)
        if k == "funcdecl": return self.funcdecl(n, ind)
        if k == "classdecl":
            expr = self.make_class(n[1][-1], n[2], n[3])
            return self.line(ind, self.store(n[1][-1], expr))
        if k == "const":
            return self.line(ind, f"R[{n[1]!r}] = {self.ex(n[2])}")
        if k == "enum":
            out = self.line(ind, f"R[{n[1]!r}] = Table()")
            i = 0
            for key, val in n[2]:
                v = self.ex(val) if val else str(i)
                if not val: i += 1
                out += self.line(ind, f"R[{n[1]!r}][{key!r}] = {v}")
            return out
        if k == "try":
            out = [pad + "try:"] + self.st(n[1], ind+4)
            out += [pad + f"except Exception as {n[2]}:"] + self.st(n[3], ind+4)
            return out
        raise NotImplementedError(f"stmt {k}")

    def expr_stmt(self, e, ind):
        if e[0] == "assign":
            return self.assign(e[1], e[2], e[3], as_expr=False, ind=ind)
        if e[0] in ("postop", "unary") and len(e) > 2 and e[1] in ("++", "--"):
            return self.assign("+=", e[2], ("num", 1 if e[1] == "++" else -1),
                               as_expr=False, ind=ind)
        code = self.ex(e)
        return self.line(ind, code)

    def assign(self, op, target, val, as_expr, ind=0):
        v = self.ex(val)
        if op in AUG:
            v = f"{AUG[op]}({self.ex(target)}, {v})"
        if target[0] == "name":
            code = self.store(target[1], v)
        elif target[0] == "field":
            fn = "_newslot" if op == "<-" else "_set"
            code = f"{fn}({self.ex(target[1])}, {target[2]!r}, {v})"
        elif target[0] == "index":
            code = f"_set({self.ex(target[1])}, {self.ex(target[2])}, {v})"
        else:
            raise NotImplementedError("assign target")
        if as_expr:
            return code if target[0] != "name" else v   # aprox: como expr, valor
        return self.line(ind, code)

    def for_stmt(self, n, ind):
        pad = " " * ind; init, cond, step, body = n[1:]
        self.push()
        out = self.st(init, ind) if init else []
        c = self.ex(cond) if cond else "True"; pre = self.take_aux(ind)
        out += pre + [pad + f"while _truth({c}):"]
        out += self.st(body, ind+4)
        if step: out += self.expr_stmt(step, ind+4)
        self.pop()
        return out

    def foreach_stmt(self, n, ind):
        pad = " " * ind; key, val, it, body = n[1:]
        self.push()
        kv = self.newtmp("_kv")
        itx = self.ex(it); pre = self.take_aux(ind)
        if key: self.declare(key)
        self.declare(val)
        out = pre + [pad + f"for {kv} in _iter({itx}):"]
        out += [pad + f"    {key}, {val} = {kv}[0], {kv}[1]"] if key else \
               [pad + f"    {val} = {kv}[1]"]
        out += self.st(body, ind+4)
        self.pop()
        return out

    def switch_stmt(self, n, ind):
        pad = " " * ind; subj, cases = n[1], n[2]
        sv = self.newtmp("_sw")
        sx = self.ex(subj); pre = self.take_aux(ind)
        out = pre + [pad + f"{sv} = {sx}", pad + "while True:  # switch"]
        first = True; default = None
        for ce, body in cases:
            if ce is None: default = body; continue
            kw = "if" if first else "elif"; first = False
            cx = self.ex(ce); out += self.take_aux(ind+4)
            out += [pad + f"    {kw} {sv} == {cx}:"] + self.stmts(body, ind+8)
        if default is not None:
            out += [pad + ("    else:" if not first else "    if True:")]
            out += self.stmts(default, ind+8)
        out += [pad + "    break"]
        return out

    def funcdecl(self, n, ind):
        path, params, defs, varg, body = n[1:]
        fn = self.emit_func(params, defs, varg, body, this=False)
        if len(path) == 1:
            return self.line(ind, self.store(path[0], fn))
        tgt = self.load(path[0])
        for p in path[1:-1]:
            tgt = f"_get({tgt}, {p!r})"
        return self.line(ind, f"_set({tgt}, {path[-1]!r}, {fn})")

    def unit(self, ast):
        return "\n".join(self.stmts(ast[1], 0))


def transpile(src):
    return T().unit(parse(src))


def check(dirpath):
    files = sorted(glob.glob(f"{dirpath}/*.nut"))
    ok = fail = 0; errs = []
    for p in files:
        b = open(p, "rb").read()
        try: s = b.decode("cp932")
        except UnicodeDecodeError: s = b.decode("latin1")
        try:
            py = transpile(s)
            compile(py, p, "exec")          # además: Python válido
            ok += 1
        except Exception as e:
            fail += 1; errs.append((p.split("/")[-1], f"{type(e).__name__}: {e}"[:100]))
    print(f"transpile+compile: {ok}/{len(files)} OK, {fail} fallan")
    for name, e in errs[:25]: print(f"  {name}: {e}")
    return fail


def demo():
    from . import sqrt
    src = """
    class Enemy extends Actor {
        hp = 100;
        constructor(n) { name = n; }
        function hit(dmg) { hp = hp - dmg; return hp <= 0; }
    }
    """
    py = transpile(src)
    assert "_class('Enemy'" in py and "_get(_this,'hp')" in py, py
    # ejecución end-to-end de un programa que no depende del juego
    prog = """
    total <- 0;
    function add(a, b) { return a + b; }
    for (local i = 1; i <= 5; i += 1) { total = total + i; }
    local xs = [10, 20, 30];
    foreach (i, x in xs) { total = add(total, x); }
    local msg = "suma=" + total;
    """
    ns = sqrt_ns()
    exec(compile(transpile(prog), "<demo>", "exec"), ns)
    assert ns["R"]["total"] == 75, ns["R"]["total"]
    assert ns["R"]["add"](2, 3) == 5
    # clase con implicit-this corriendo de verdad
    prog2 = """
    class Counter { n = 0; function inc() { n = n + 1; return n; } }
    local c = Counter();
    r <- c.inc() + c.inc();
    """
    ns = sqrt_ns()
    exec(compile(transpile(prog2), "<demo2>", "exec"), ns)
    assert ns["R"]["r"] == 3, ns["R"]["r"]
    print("demo OK")


def sqrt_ns():
    """Namespace de ejecución: helpers de sqrt + un root table fresco."""
    from . import sqrt
    ns = {k: getattr(sqrt, k) for k in dir(sqrt) if not k.startswith("__")}
    ns["R"] = sqrt.new_root()
    return ns


def cli(argv):
    if not argv or argv[0] == "demo": return demo()
    if argv[0] == "check": return check(argv[1])
    if argv[0] == "file":
        b = open(argv[1], "rb").read()
        try: s = b.decode("cp932")
        except UnicodeDecodeError: s = b.decode("latin1")
        print(transpile(s))


if __name__ == "__main__":
    cli(sys.argv[1:])
