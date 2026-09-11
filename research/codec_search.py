import struct, os, sys
sys.setrecursionlimit(200000)
def load(hd,bn):
    sz=list(struct.unpack('<%dI'%(os.path.getsize(hd)//4),open(hd,'rb').read()))
    f=open(bn,'rb'); off=0; e=[]
    for s in sz:
        f.seek(off); e.append(f.read(s)); off+=(s+2047)//2048*2048
    return e
def copy(out, dist, ln):
    if dist <= 0: return None
    r = bytearray()
    for _ in range(ln):
        i = len(out) + len(r) - dist
        r.append(out[i] if 0 <= i < len(out) else (r[i-len(out)] if i >= len(out) else 0))
    return bytes(r)
M = {}
for b in (1,2,3):
    M[f'Z{b}']    = (0, lambda T,x,o,b=b: b"\0"*((T&0x1F)+b))
    M[f'R{b}']    = (1, lambda T,x,o,b=b: bytes([x[0]])*((T&0x1F)+b))
    M[f'M8_{b}']  = (1, lambda T,x,o,b=b: copy(o, x[0]+1, (T&0x1F)+b))
    M[f'M16_{b}'] = (2, lambda T,x,o,b=b: copy(o, (x[0]|(x[1]<<8))+1, (T&0x1F)+b))
    M[f'MW_{b}']  = (1, lambda T,x,o,b=b: copy(o, (((T&0x1F)<<8)|x[0])+1, b+2))
    M[f'DL_{b}']  = (1, lambda T,x,o,b=b: copy(o, (T&0x1F)+1, x[0]+b))
    M[f'MO_{b}']  = (2, lambda T,x,o,b=b: copy(o, (((T&0x1F)<<8)|x[0])+1, x[1]+b))
NAMES = list(M)

def solve(cases, budget=8_000_000):
    n=[0]
    def run(assign, ci):
        if ci == len(cases): return dict(assign)
        d, usize, pre, tail = cases[ci]
        def step(i, out, assign):
            n[0]+=1
            if n[0] > budget: raise TimeoutError
            L=len(out)
            if L == usize and i == len(d): return run(assign, ci+1)
            if L > usize or i >= len(d): return None
            T = d[i]; cls = T >> 5
            if cls == 7:
                c=(T&0x1F)+1
                if i+1+c > len(d) or L+c > usize: return None
                nx = out + d[i+1:i+1+c]
            else:
                for nm in ([assign[cls]] if cls in assign else NAMES):
                    ex, fn = M[nm]
                    if i+1+ex > len(d): continue
                    emit = fn(T, d[i+1:i+1+ex], out)
                    if not emit or L+len(emit) > usize: continue
                    cand = out + emit
                    if cand[:len(pre)] != pre[:len(cand)]: continue
                    if len(cand) >= 20 and tail and cand[16:20] != tail: continue
                    r = step(i+1+ex, cand, assign if cls in assign else {**assign, cls: nm})
                    if r: return r
                return None
            if nx[:len(pre)] != pre[:len(nx)]: return None
            if len(nx) >= 20 and tail and nx[16:20] != tail: return None
            return step(i+1+c, nx, assign)
        return step(0, b"", assign)
    try: return run({}, 0)
    except TimeoutError: return None

iso = os.path.expanduser("~/Downloads/znt-work/iso")
sd = load(f"{iso}/SCENEDAT.HD", f"{iso}/SCENEDAT.BIN")
cand=[]
for e in sd:
    if len(e) < 40 or e[8:12] != b'\xe6TIM': continue
    u,c = struct.unpack('<II', e[:8])
    cand.append((e[8:], u, b'TIM2\x04\x00\x01\x00'+b'\x00'*8, struct.pack('<I', u-16), len(e)))
cand.sort(key=lambda t: t[4])
print("TIM2 candidates (comp, usize):", [(t[4], t[1]) for t in cand[:5]])
cases = [(d,u,p,t) for d,u,p,t,_ in cand[:3]]
r = solve(cases)
print("\nopcode table:", r)
