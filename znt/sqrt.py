#!/usr/bin/env python3
"""Runtime for Squirrel code transpiled to Python.

The transpiler (`sqtranspile`) emits Python that calls these helpers. Squirrel's
object system (tables, classes, instances) is modelled at runtime instead of
mapping onto native Python classes, because Squirrel resolves free identifiers
against `this` and inherits fields+constructor in a way that does not fit
Python's MRO. Coroutines are stackful (they suspend through nested calls), so
they are implemented with `threading`, not generators.

Conventions of the generated code:
- Squirrel tables  -> `Table` (ordered dict with slot access)
- arrays           -> Python list
- classes          -> `SqClass`; instances -> `SqInstance`
- member access    -> `_get(o,k)` / `_set(o,k,v)` / `_newslot(o,k,v)`
- `k in cont`      -> `_in(k,cont)`
- call             -> plain Python; methods come already bound to `this`
"""
import math, threading


class Table(dict):
    """Squirrel table: ordered dict with attribute-style repr."""
    def __repr__(self): return "{" + ", ".join(f"{k}={v!r}" for k, v in self.items()) + "}"


class SqClass:
    def __init__(self, name, base, fields, methods):
        self.name, self.base, self.fields, self.methods = name, base, fields, methods

    def method(self, key):
        """Return (fn, defining_class) or None. The defining class is what gets
        passed as _cls to the method, so `base` makes the right super-call."""
        c = self
        while c is not None:
            if key in c.methods:
                return c.methods[key], c
            c = c.base
        return None

    def __call__(self, *args):
        return _new(self, args)

    def all_fields(self):
        chain = []
        c = self
        while c is not None:
            chain.append(c.fields); c = c.base
        out = {}
        for f in reversed(chain):        # base first, derived overrides
            out.update(f)
        return out


class SqInstance:
    def __init__(self, cls):
        self.cls = cls
        self.slots = {}
    def __repr__(self): return f"<{self.cls.name} {self.slots!r}>"


class BoundMethod:
    __slots__ = ("this", "fn", "cls")
    def __init__(self, this, fn, cls): self.this, self.fn, self.cls = this, fn, cls
    def __call__(self, *a): return self.fn(self.this, self.cls, *a)


def _class(name, base, fields, methods):
    return SqClass(name, base, fields, methods)


class _SqError(Exception):
    def __init__(self, val): super().__init__(str(val)); self.val = val


def _truth(x):
    """Falsy in Squirrel: null, false, 0, 0.0. The empty string is TRUE."""
    if x is None or x is False: return False
    if isinstance(x, (int, float)) and x == 0: return False
    return True


def _tostr(x):
    if x is None: return "null"
    if x is True: return "true"
    if x is False: return "false"
    return str(x)


def _add(a, b):
    if isinstance(a, str) or isinstance(b, str):
        return _tostr(a) + _tostr(b)
    return a + b


def _sub(a, b): return a - b
def _mul(a, b): return a * b


def _div(a, b):
    if isinstance(a, int) and isinstance(b, int):
        q = abs(a) // abs(b)
        return q if (a < 0) == (b < 0) else -q      # truncates toward zero (C)
    return a / b


def _mod(a, b):
    r = math.fmod(a, b)
    return int(r) if isinstance(a, int) and isinstance(b, int) else r


def _cmp(a, b): return -1 if a < b else (1 if a > b else 0)


def _clone(x):
    if isinstance(x, list): return list(x)
    if isinstance(x, Table): return Table(x)
    if isinstance(x, SqInstance):
        o = SqInstance(x.cls); o.slots = dict(x.slots); return o
    return x


def _basecall(this, base_cls, name, *args):
    """base.method(...): look up `name` from the base class with the current `this`."""
    m = base_cls.method(name)
    if m is None:
        raise AttributeError(f"base has no '{name}'")
    fn, defcls = m
    return fn(this, defcls, *args)


def _instanceof(o, cls):
    if not isinstance(o, SqInstance): return False
    c = o.cls
    while c is not None:
        if c is cls: return True
        c = c.base
    return False


def _new(cls, args):
    inst = SqInstance(cls)
    for k, thunk in cls.all_fields().items():
        inst.slots[k] = thunk()
    ctor = cls.method("constructor")
    if ctor is not None:
        fn, defcls = ctor
        fn(inst, defcls, *args)
    return inst


# --- delegates builtin ------------------------------------------------------
def _arr_delegate(a, key):
    d = {
        "len": lambda: len(a), "append": lambda v: (a.append(v), a)[1],
        "push": lambda v: (a.append(v), a)[1], "pop": a.pop,
        "top": lambda: a[-1], "insert": lambda i, v: a.insert(i, v),
        "remove": lambda i: a.pop(i), "clear": a.clear,
        "resize": lambda n, f=None: _resize(a, n, f), "reverse": lambda: (a.reverse(), a)[1],
        "slice": lambda i, j=None: a[i:(j if j is not None else len(a))],
        "find": lambda v: (a.index(v) if v in a else None),
        "sort": lambda f=None: (a.sort(key=_cmp_key(f)) if f else a.sort(), a)[1],
        "extend": lambda o: (a.extend(o), a)[1],
        "map": lambda f: [f(x) for x in a], "apply": lambda f: [f(x) for x in a],
        "tostring": lambda: str(a),
    }
    return d.get(key)


def _resize(a, n, fill):
    while len(a) < n: a.append(fill)
    del a[n:]
    return a


def _cmp_key(f):
    import functools
    return functools.cmp_to_key(f)


def _str_delegate(s, key):
    d = {
        "len": lambda: len(s), "tointeger": lambda: int(s), "tofloat": lambda: float(s),
        "tostring": lambda: s, "slice": lambda i, j=None: s[i:(j if j is not None else len(s))],
        "find": lambda sub, st=0: (s.find(sub, st) if s.find(sub, st) >= 0 else None),
        "toupper": s.upper, "tolower": s.lower,
    }
    return d.get(key)


def _num_delegate(x, key):
    d = {"tointeger": lambda: int(x), "tofloat": lambda: float(x),
         "tostring": lambda: str(x), "tochar": lambda: chr(int(x))}
    return d.get(key)


def _get(o, key):
    if isinstance(o, SqInstance):
        if key in o.slots:
            return o.slots[key]
        m = o.cls.method(key)
        if m is not None:
            return BoundMethod(o, m[0], m[1])
        raise AttributeError(f"{o.cls.name} has no '{key}'")
    if isinstance(o, SqClass):
        m = o.method(key)
        return BoundMethod(None, m[0], m[1]) if m else None
    if isinstance(o, Table):
        if key in o: return o[key]
        raise KeyError(f"table has no slot '{key}'")
    if isinstance(o, list):
        if isinstance(key, int): return o[key]
        d = _arr_delegate(o, key)
        if d: return d
    if isinstance(o, str):
        if isinstance(key, int): return o[key]
        d = _str_delegate(o, key)
        if d: return d
    if isinstance(o, (int, float)):
        d = _num_delegate(o, key)
        if d: return d
    # native host object (Layer, MessageWindow, disc...): Python attribute
    return getattr(o, key)


def _set(o, key, val):
    if isinstance(o, SqInstance): o.slots[key] = val
    elif isinstance(o, Table): o[key] = val
    elif isinstance(o, list): o[key] = val
    else: setattr(o, key, val)
    return val


def _newslot(o, key, val):
    if isinstance(o, SqInstance): o.slots[key] = val
    elif isinstance(o, Table): o[key] = val
    else: setattr(o, key, val)
    return val


def _delete(o, key):
    if isinstance(o, (Table, dict)): return o.pop(key, None)
    if isinstance(o, SqInstance): return o.slots.pop(key, None)
    if isinstance(o, list): return o.pop(key)
    return None


def _in(key, cont):
    if isinstance(cont, (Table, dict, SqInstance)):
        keys = cont.slots if isinstance(cont, SqInstance) else cont
        return key in keys
    if isinstance(cont, (list, str)):
        return key in cont
    return False


def _iter(cont):
    """foreach: return (key, value) pairs."""
    if isinstance(cont, SqInstance): cont = cont.slots
    if isinstance(cont, (Table, dict)): return list(cont.items())
    if isinstance(cont, (list, tuple)): return list(enumerate(cont))
    if isinstance(cont, str): return list(enumerate(cont))
    return []


def _typeof(x):
    if isinstance(x, bool): return "bool"
    if isinstance(x, int): return "integer"
    if isinstance(x, float): return "float"
    if isinstance(x, str): return "string"
    if isinstance(x, list): return "array"
    if isinstance(x, (Table, dict)): return "table"
    if isinstance(x, SqInstance): return "instance"
    if isinstance(x, SqClass): return "class"
    if x is None: return "null"
    if callable(x): return "function"
    return "instance"


# --- stackful coroutines (threading) ----------------------------------------
class SqThread:
    """Stackful coroutine: runs the body in a thread and syncs with events.
    Models Squirrel's newthread/call/wakeup/suspend/getstatus."""
    def __init__(self, fn):
        self.fn = fn
        self._resume = threading.Event()
        self._yielded = threading.Event()
        self._val = None          # value carried across each handoff
        self._status = "idle"
        self._thread = None

    def _run(self, args):
        _thread_local.current = self
        try:
            self._val = self.fn(*args)
        except _ThreadKill:
            pass
        finally:
            self._status = "dead"
            self._yielded.set()

    def call(self, *args):
        self._status = "running"
        self._thread = threading.Thread(target=self._run, args=(args,), daemon=True)
        self._yielded.clear()
        self._thread.start()
        self._yielded.wait()
        return self._val

    def wakeup(self, val=None):
        if self._status == "dead":
            return None
        self._val = val
        self._status = "running"
        self._yielded.clear()
        self._resume.set()
        self._yielded.wait()
        return self._val

    def getstatus(self):
        return self._status

    def _suspend(self, val=None):
        self._val = val
        self._status = "suspended"
        self._resume.clear()
        self._yielded.set()
        self._resume.wait()
        return self._val


class _ThreadKill(Exception): pass
_thread_local = threading.local()


def _suspend(val=None):
    cur = getattr(_thread_local, "current", None)
    if cur is None:
        raise RuntimeError("suspend outside a coroutine")
    return cur._suspend(val)


# --- standard Squirrel / SqPlus builtins ------------------------------------
def _format(fmt, *args):
    return fmt % args if args else fmt


def _array(n, fill=None):
    return [fill] * int(n)


ROOT = {
    "print": lambda s="": print(s, end=""),
    "error": lambda s="": print(s, end=""),
    "format": _format,
    "array": _array,
    "type": _typeof,
    "newthread": lambda fn: SqThread(fn),
    "suspend": _suspend,
    "rand": lambda: __import__("random").randint(0, 32767),
    "srand": lambda s: __import__("random").seed(s),
    "abs": abs, "fabs": abs, "floor": lambda x: int(math.floor(x)),
    "ceil": lambda x: int(math.ceil(x)), "sqrt": math.sqrt, "pow": pow,
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "atan": math.atan,
    "atan2": math.atan2, "exp": math.exp, "log": math.log, "log10": math.log10,
    "min": min, "max": max, "PI": math.pi,
}


def new_root():
    """A fresh root table (Table) with the builtins."""
    t = Table()
    t.update(ROOT)
    return t


def demo():
    # class with inheritance + implicit this + delegates + foreach
    Base = SqClass("Base", None, {"hp": lambda: 10}, {})
    def ctor(this, cls, n): this.slots["name"] = n
    def hit(this, cls, d): this.slots["hp"] = _get(this, "hp") - d; return _get(this, "hp") <= 0
    Foo = SqClass("Foo", Base, {"tag": lambda: "x"},
                  {"constructor": ctor, "hit": hit})
    o = _new(Foo, ("goblin",))
    assert _get(o, "hp") == 10 and _get(o, "name") == "goblin" and _get(o, "tag") == "x"
    assert _get(o, "hit")(3) is False and _get(o, "hp") == 7
    assert _get(o, "hit")(10) is True
    # delegates
    a = [1, 2, 3]
    assert _get(a, "len")() == 3
    _get(a, "append")(4); assert a == [1, 2, 3, 4]
    assert _get("hola", "toupper")() == "HOLA"
    assert _in("hp", o) and not _in("zzz", o)
    assert [v for _, v in _iter([9, 8])] == [9, 8]
    # stackful coroutine: suspends inside a nested function
    log = []
    def inner(t): log.append("a"); _suspend(1); log.append("b"); _suspend(2); return 3
    th = SqThread(lambda: inner(0))
    assert th.call() == 1 and log == ["a"]
    assert th.wakeup() == 2 and log == ["a", "b"]
    assert th.wakeup() == 3 and th.getstatus() == "dead"
    print("demo OK")


if __name__ == "__main__":
    demo()
