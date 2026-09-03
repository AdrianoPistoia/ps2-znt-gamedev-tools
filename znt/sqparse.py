#!/usr/bin/env python3
"""Tokenizer + parser de Squirrel (2.x/3.x, el subconjunto que usa el juego).

Produce un AST de tuplas `(kind, ...)` que consume el transpilador. No es el
parser de referencia: cubre lo que aparece en el corpus de Zero no Tsukaima
(clases con extends, closures, foreach, switch, ternario, delegados, corrutinas).

  python -m znt sqparse demo
  python -m znt sqparse check scripts/       # parsea todo y reporta fallos
"""
import sys, glob

KEYWORDS = {
    "base", "break", "case", "catch", "class", "clone", "continue", "const",
    "default", "delete", "do", "else", "enum", "extends", "for", "foreach",
    "function", "if", "in", "instanceof", "local", "null", "resume", "return",
    "switch", "this", "throw", "try", "typeof", "while", "yield", "constructor",
    "static", "true", "false", "rawcall",
}
# operadores, del mas largo al mas corto para el maximal munch
OPS = ["<=>", "...", "<<", ">>", "<=", ">=", "==", "!=", "&&", "||", "+=", "-=",
       "*=", "/=", "%=", "++", "--", "<-", "::",
       "+", "-", "*", "/", "%", "=", "<", ">", "!", "~", "&", "|", "^",
       "(", ")", "{", "}", "[", "]", ",", ";", ".", ":", "?", "@"]


class Tok:
    __slots__ = ("k", "v", "ln")
    def __init__(self, k, v, ln): self.k, self.v, self.ln = k, v, ln
    def __repr__(self): return f"{self.k}:{self.v!r}"


def tokenize(src):
    toks = []
    i, n, ln = 0, len(src), 1
    while i < n:
        c = src[i]
        if c == "\n":
            ln += 1; i += 1; continue
        if c in " \t\r":
            i += 1; continue
        if c == "/" and i+1 < n and src[i+1] == "/":
            j = src.find("\n", i); i = n if j < 0 else j; continue
        if c == "/" and i+1 < n and src[i+1] == "*":
            j = src.find("*/", i); ln += src.count("\n", i, j if j>=0 else n)
            i = n if j < 0 else j+2; continue
        if c == '"' or (c == "@" and i+1 < n and src[i+1] == '"'):
            verb = c == "@"
            j = i + (2 if verb else 1); buf = []
            while j < n:
                if src[j] == '"' and not (verb and j+1 < n and src[j+1] == '"'):
                    break
                if not verb and src[j] == "\\":
                    esc = src[j+1]
                    buf.append({"n": "\n", "t": "\t", "r": "\r", '"': '"',
                                "\\": "\\", "0": "\0", "'": "'"}.get(esc, esc))
                    j += 2; continue
                if src[j] == "\n": ln += 1
                buf.append(src[j]); j += 1
            toks.append(Tok("str", "".join(buf), ln)); i = j + 1; continue
        if c == "'":
            j = i + 1
            if src[j] == "\\":
                ch = {"n": 10, "t": 9, "r": 13, "0": 0}.get(src[j+1], ord(src[j+1])); j += 2
            else:
                ch = ord(src[j]); j += 1
            toks.append(Tok("int", ch, ln)); i = j + 1; continue
        if c.isdigit() or (c == "." and i+1 < n and src[i+1].isdigit()):
            j = i
            if c == "0" and i+1 < n and src[i+1] in "xX":
                j = i + 2
                while j < n and src[j] in "0123456789abcdefABCDEF": j += 1
                toks.append(Tok("int", int(src[i:j], 16), ln)); i = j; continue
            isflt = False
            while j < n and (src[j].isdigit() or src[j] in ".eE" or
                             (src[j] in "+-" and src[j-1] in "eE")):
                if src[j] in ".eE": isflt = True
                j += 1
            num = src[i:j]
            toks.append(Tok("float" if isflt else "int",
                            float(num) if isflt else int(num), ln)); i = j; continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"): j += 1
            w = src[i:j]
            toks.append(Tok("kw" if w in KEYWORDS else "id", w, ln)); i = j; continue
        for op in OPS:
            if src.startswith(op, i):
                toks.append(Tok("op", op, ln)); i += len(op); break
        else:
            raise SyntaxError(f"linea {ln}: caracter inesperado {c!r}")
    toks.append(Tok("eof", None, ln))
    return toks


# --- Pratt parser -----------------------------------------------------------
# precedencias de operadores binarios
BINPREC = {
    "||": 3, "&&": 4, "|": 5, "^": 6, "&": 7,
    "==": 8, "!=": 8, "<=>": 8, "<": 9, ">": 9, "<=": 9, ">=": 9,
    "in": 9, "instanceof": 9,
    "<<": 10, ">>": 10, "+": 11, "-": 11, "*": 12, "/": 12, "%": 12,
}
ASSIGN = {"=", "<-", "+=", "-=", "*=", "/=", "%="}


class Parser:
    def __init__(self, toks):
        self.t = toks; self.p = 0

    def cur(self): return self.t[self.p]
    def nx(self): tok = self.t[self.p]; self.p += 1; return tok

    def is_(self, k, v=None):
        tk = self.t[self.p]
        return tk.k == k and (v is None or tk.v == v)

    def eat(self, k, v=None):
        tk = self.t[self.p]
        if tk.k != k or (v is not None and tk.v != v):
            raise SyntaxError(f"linea {tk.ln}: esperaba {k} {v}, vino {tk.k} {tk.v!r}")
        self.p += 1; return tk

    def opt(self, k, v=None):
        if self.is_(k, v): self.p += 1; return True
        return False

    # statements ------------------------------------------------------------
    def parse(self):
        body = []
        while not self.is_("eof"):
            body.append(self.stmt())
        return ("block", body)

    def block(self):
        self.eat("op", "{"); body = []
        while not self.is_("op", "}"):
            body.append(self.stmt())
        self.eat("op", "}")
        return ("block", body)

    def stmt(self):
        tk = self.cur()
        if tk.k == "op" and tk.v == "{": return self.block()
        if tk.k == "op" and tk.v == ";": self.nx(); return ("nop",)
        if tk.k == "kw":
            m = getattr(self, "st_" + tk.v, None)
            if m: return m()
        e = self.expr()
        self.opt("op", ";")
        return ("expr", e)

    def st_local(self):
        self.nx(); decls = []
        while True:
            name = self.eat("id").v
            val = self.expr() if self.opt("op", "=") else ("null",)
            decls.append((name, val))
            if not self.opt("op", ","): break
        self.opt("op", ";")
        return ("local", decls)

    def st_return(self):
        self.nx()
        e = None if self.is_("op", ";") or self.is_("op", "}") else self.expr()
        self.opt("op", ";"); return ("return", e)

    def st_yield(self):
        self.nx()
        e = None if self.is_("op", ";") or self.is_("op", "}") else self.expr()
        self.opt("op", ";"); return ("yield_stmt", e)

    def st_break(self): self.nx(); self.opt("op", ";"); return ("break",)
    def st_continue(self): self.nx(); self.opt("op", ";"); return ("continue",)

    def st_if(self):
        self.nx(); self.eat("op", "("); cond = self.expr(); self.eat("op", ")")
        then = self.stmt()
        els = self.stmt() if self.opt("kw", "else") else None
        return ("if", cond, then, els)

    def st_while(self):
        self.nx(); self.eat("op", "("); cond = self.expr(); self.eat("op", ")")
        return ("while", cond, self.stmt())

    def st_do(self):
        self.nx(); body = self.stmt(); self.eat("kw", "while")
        self.eat("op", "("); cond = self.expr(); self.eat("op", ")"); self.opt("op", ";")
        return ("dowhile", cond, body)

    def st_for(self):
        self.nx(); self.eat("op", "(")
        init = None if self.is_("op", ";") else (self.st_local() if self.is_("kw", "local")
                                                 else ("expr", self.expr()))
        self.opt("op", ";")
        cond = None if self.is_("op", ";") else self.expr(); self.eat("op", ";")
        step = None if self.is_("op", ")") else self.expr(); self.eat("op", ")")
        return ("for", init, cond, step, self.stmt())

    def st_foreach(self):
        self.nx(); self.eat("op", "(")
        a = self.eat("id").v; b = None
        if self.opt("op", ","): b = self.eat("id").v
        self.eat("kw", "in"); it = self.expr(); self.eat("op", ")")
        key, val = (a, b) if b else (None, a)
        return ("foreach", key, val, it, self.stmt())

    def st_switch(self):
        self.nx(); self.eat("op", "("); subj = self.expr(); self.eat("op", ")")
        self.eat("op", "{"); cases = []
        while not self.is_("op", "}"):
            if self.opt("kw", "case"):
                ce = self.expr(); self.eat("op", ":")
            else:
                self.eat("kw", "default"); self.eat("op", ":"); ce = None
            body = []
            while not (self.is_("kw", "case") or self.is_("kw", "default") or self.is_("op", "}")):
                body.append(self.stmt())
            cases.append((ce, body))
        self.eat("op", "}")
        return ("switch", subj, cases)

    def st_function(self):
        self.nx(); name = self.eat("id").v
        # funcion con nombre calificado a.b.c
        path = [name]
        while self.opt("op", "."): path.append(self.eat("id").v)
        params, defs, varg = self.params()
        return ("funcdecl", path, params, defs, varg, self.block())

    def st_class(self):
        self.nx(); path = [self.eat("id").v]
        while self.opt("op", "."): path.append(self.eat("id").v)
        base = self.expr() if self.opt("kw", "extends") else None
        return ("classdecl", path, base, self.class_body())

    def st_const(self):
        self.nx(); name = self.eat("id").v; self.opt("op", "="); v = self.expr()
        self.opt("op", ";"); return ("const", name, v)

    def st_enum(self):
        self.nx(); name = self.eat("id").v; self.eat("op", "{"); items = []
        while not self.is_("op", "}"):
            k = self.eat("id").v
            v = self.expr() if self.opt("op", "=") else None
            items.append((k, v)); self.opt("op", ",")
        self.eat("op", "}"); return ("enum", name, items)

    def st_try(self):
        self.nx(); body = self.block(); self.eat("kw", "catch")
        self.eat("op", "("); var = self.eat("id").v; self.eat("op", ")")
        return ("try", body, var, self.block())

    def st_throw(self):
        self.nx(); e = self.expr(); self.opt("op", ";"); return ("throw", e)

    # class body ------------------------------------------------------------
    def class_body(self):
        self.eat("op", "{"); members = []
        while not self.is_("op", "}"):
            if self.opt("op", ";"): continue
            static = self.opt("kw", "static")
            if self.is_("kw", "constructor"):
                self.nx(); params, defs, varg = self.params()
                members.append(("method", "constructor", params, defs, varg, self.block()))
            elif self.opt("kw", "function"):
                name = self.nx().v; params, defs, varg = self.params()   # id o kw
                members.append(("method", name, params, defs, varg, self.block()))
            else:
                name = self.eat("id").v
                val = self.expr() if (self.opt("op", "=") or self.opt("op", "<-")) else ("null",)
                self.opt("op", ";")
                members.append(("field", name, val, static))
        self.eat("op", "}")
        return members

    def params(self):
        self.eat("op", "("); names, defs, varg = [], {}, False
        while not self.is_("op", ")"):
            if self.opt("op", "..."): varg = True; break
            pn = self.eat("id").v; names.append(pn)
            if self.opt("op", "="): defs[pn] = self.expr()
            if not self.opt("op", ","): break
        self.eat("op", ")")
        return names, defs, varg

    # expressions (Pratt) ---------------------------------------------------
    def expr(self): return self.assign()

    def assign(self):
        left = self.ternary()
        if self.cur().k == "op" and self.cur().v in ASSIGN:
            op = self.nx().v; right = self.assign()
            return ("assign", op, left, right)
        return left

    def ternary(self):
        c = self.binary(0)
        if self.opt("op", "?"):
            a = self.assign(); self.eat("op", ":"); b = self.assign()
            return ("ternary", c, a, b)
        return c

    def binary(self, minp):
        left = self.unary()
        while True:
            tk = self.cur()
            op = tk.v if (tk.k == "op" or (tk.k == "kw" and tk.v in ("in", "instanceof"))) else None
            if op not in BINPREC or BINPREC[op] < minp: break
            self.nx()
            right = self.binary(BINPREC[op] + 1)
            left = ("bin", op, left, right)
        return left

    def unary(self):
        tk = self.cur()
        if tk.k == "op" and tk.v in ("-", "!", "~", "++", "--"):
            self.nx(); return ("unary", tk.v, self.unary())
        if tk.k == "kw" and tk.v in ("typeof", "clone", "resume", "delete"):
            self.nx(); return ("unary", tk.v, self.unary())
        return self.postfix()

    def postfix(self):
        e = self.primary()
        while True:
            tk = self.cur()
            if tk.k == "op" and tk.v == ".":
                self.nx(); nm = self.nx()          # id o keyword (.constructor, .len...)
                if nm.k not in ("id", "kw"):
                    raise SyntaxError(f"linea {nm.ln}: esperaba nombre de campo, vino {nm.k}")
                e = ("field", e, nm.v)
            elif tk.k == "op" and tk.v == "[":
                self.nx(); idx = self.expr(); self.eat("op", "]"); e = ("index", e, idx)
            elif tk.k == "op" and tk.v == "(":
                e = ("call", e, self.args())
            elif tk.k == "op" and tk.v in ("++", "--"):
                self.nx(); e = ("postop", tk.v, e)
            else:
                break
        return e

    def args(self):
        self.eat("op", "("); a = []
        while not self.is_("op", ")"):
            a.append(self.assign())
            if not self.opt("op", ","): break
        self.eat("op", ")")
        return a

    def primary(self):
        tk = self.cur()
        if tk.k == "int" or tk.k == "float": self.nx(); return ("num", tk.v)
        if tk.k == "str": self.nx(); return ("str", tk.v)
        if tk.k == "id": self.nx(); return ("name", tk.v)
        if tk.k == "kw":
            if tk.v == "true": self.nx(); return ("num", True)
            if tk.v == "false": self.nx(); return ("num", False)
            if tk.v == "null": self.nx(); return ("null",)
            if tk.v == "this": self.nx(); return ("this",)
            if tk.v == "base": self.nx(); return ("base",)
            if tk.v == "function": return self.lambda_()
            if tk.v == "class":
                self.nx(); base = self.expr() if self.opt("kw", "extends") else None
                return ("classexpr", base, self.class_body())
        if tk.k == "op":
            if tk.v == "(":
                self.nx(); e = self.expr(); self.eat("op", ")"); return e
            if tk.v == "[":
                return self.array()
            if tk.v == "{":
                return self.table()
            if tk.v == "::":
                self.nx(); return ("name", self.eat("id").v)   # root: tratamos como global
            if tk.v == "@":
                self.nx(); return self.lambda_short()
        raise SyntaxError(f"linea {tk.ln}: expresion inesperada {tk.k} {tk.v!r}")

    def lambda_(self):
        self.eat("kw", "function")
        params, defs, varg = self.params()
        return ("lambda", params, defs, varg, self.block())

    def lambda_short(self):
        # @(a,b) expr   (lambda de expresion de Squirrel 3)
        params, defs, varg = self.params()
        return ("lambda_expr", params, defs, varg, self.assign())

    def array(self):
        self.eat("op", "["); items = []
        while not self.is_("op", "]"):
            items.append(self.assign())
            if not self.opt("op", ","): break
        self.eat("op", "]")
        return ("array", items)

    def table(self):
        self.eat("op", "{"); pairs = []
        while not self.is_("op", "}"):
            if self.opt("op", "["):
                k = self.expr(); self.eat("op", "]"); self.opt("op", "=")
            elif self.is_("kw", "function"):
                self.nx(); name = self.eat("id").v
                params, defs, varg = self.params()
                pairs.append((("str", name), ("lambda", params, defs, varg, self.block())))
                self.opt("op", ","); self.opt("op", ";"); continue
            else:
                nm = self.nx()
                k = ("str", nm.v)
                self.opt("op", "=") or self.opt("op", "<-") or self.eat("op", ":")
            v = self.assign(); pairs.append((k, v))
            self.opt("op", ",") or self.opt("op", ";")
        self.eat("op", "}")
        return ("table", pairs)


def parse(src):
    return Parser(tokenize(src)).parse()


def check(dirpath):
    files = sorted(glob.glob(f"{dirpath}/*.nut"))
    ok = fail = 0; errs = []
    for p in files:
        b = open(p, "rb").read()
        try: s = b.decode("cp932")
        except UnicodeDecodeError: s = b.decode("latin1")
        try:
            parse(s); ok += 1
        except Exception as e:
            fail += 1; errs.append((p.split("/")[-1], str(e)[:90]))
    print(f"parse: {ok}/{len(files)} OK, {fail} fallan")
    for name, e in errs[:25]:
        print(f"  {name}: {e}")
    return fail


def demo():
    ast = parse("""
    class Enemy extends Actor {
        hp = 100;
        constructor(n) { name = n; }
        function hit(dmg) { hp -= dmg; return hp <= 0; }
    }
    local xs = [1, 2, 3];
    foreach (i, x in xs) { print(x + i); }
    local t = { a = 1, ["b"] = 2 };
    local f = @(n) n * 2;
    for (local i = 0; i < 3; i += 1) { if (i == 1) continue; }
    """)
    kinds = [s[0] for s in ast[1]]
    assert kinds == ["classdecl", "local", "foreach", "local", "local", "for"], kinds
    cls = ast[1][0]
    assert cls[1] == ["Enemy"] and cls[2] == ("name", "Actor"), cls[:3]
    assert cls[3][0][0] == "field" and cls[3][1][0] == "method", cls[3]
    print("demo OK")


def cli(argv):
    if not argv or argv[0] == "demo": return demo()
    if argv[0] == "check": return check(argv[1])
    print(parse(open(argv[0], "rb").read().decode("cp932")))


if __name__ == "__main__":
    cli(sys.argv[1:])
