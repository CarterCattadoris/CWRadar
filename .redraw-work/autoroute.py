"""Scripted grid router for the CWRadar board (stages 2 and 3: power/decoupling, then signals).

Usage: python3 autoroute.py <in.kicad_pcb> <drc.json> <out.kicad_pcb> [--nets power|signal|all] [--prep]

- Works on top (L1) and bottom (L4) only; the inner GND planes are never cut.
- Octilinear paths on a 0.1 mm grid; corners are chamfered (45 deg), never 90 deg.
- Clearance per net class (Default 0.15, Power 0.2, RF/USB 0.2, ANALOG_BB/PWR_BATT 0.25) and >= 0.2 to pads.
- Power tries wide first: Power 0.5 -> 0.2 mm, PWR_BATT 1.0 -> 0.3 mm; signals 0.2 mm.
- Edges to route are KiCad's own ratsnest (DRC unconnected items), shortest first.
--prep: thin the LO-lane fence to every other via and drop a GND via next to every SMD GND pad.
"""
import json
import math
import re
import sys

import numpy as np
import pcbnew

SRC, DRCJ, DST = sys.argv[1], sys.argv[2], sys.argv[3]
MODE = "all"
PREP = "--prep" in sys.argv
CHECK = "--check" in sys.argv
DEBUG = sys.argv[sys.argv.index("--debug") + 1] if "--debug" in sys.argv else None
for a in sys.argv[4:]:
    if a.startswith("--nets"):
        MODE = sys.argv[sys.argv.index(a) + 1]

OX, OY, W, H, RC = 20.0, 20.0, 92.0, 66.0, 4.0
G = 0.1
NX, NY = int(round(W / G)), int(round(H / G))
MARGIN = 0.02
mm = pcbnew.FromMM
B = pcbnew.LoadBoard(SRC)
NETS = {B.GetNetInfo().GetNetItem(i).GetNetname(): B.GetNetInfo().GetNetItem(i) for i in range(B.GetNetCount())}
NCODE = {n: ni.GetNetCode() for n, ni in NETS.items()}

# ------------------------------------------------------------------ net classes
PATTERNS = json.load(open(SRC.replace(".kicad_pcb", ".kicad_pro")))["net_settings"]["netclass_patterns"]
CLS_CLR = {"Default": 0.15, "ANALOG_BB": 0.25, "PWR_BATT": 0.25, "Power": 0.2, "RF": 0.2, "USB_90": 0.2, "SPI": 0.15,
           "GND": 0.15}


PRIO = {c["name"]: c.get("priority", 99) for c in
        json.load(open(SRC.replace(".kicad_pcb", ".kicad_pro")))["net_settings"]["classes"]}


def net_class(name):
    """KiCad semantics: of all matching patterns, the class with the best (lowest) priority wins."""
    import fnmatch
    hits = [p["netclass"] for p in PATTERNS if fnmatch.fnmatchcase(name, p["pattern"])]
    return min(hits, key=lambda c: PRIO.get(c, 99)) if hits else "Default"


CLS = {n: net_class(n) for n in NETS}


def clr_of(name):
    return CLS_CLR.get(CLS.get(name, "Default"), 0.15)


def widths_for(name):
    c = CLS[name]
    if c == "PWR_BATT":
        return [1.0, 0.8, 0.6, 0.4, 0.3, 0.25]
    if c == "Power":
        return [0.5, 0.4, 0.3, 0.25, 0.2]
    return [0.2]


def via_for(name):
    return (0.6, 0.3) if CLS[name] in ("Power", "PWR_BATT") else (0.45, 0.2)


# ------------------------------------------------------------------ raster of copper on L1 (0) / L4 (1)
owner = np.zeros((2, NY, NX), dtype=np.int32)          # net code + 1
OBJS = []   # exact copper shapes for clearance: (kind, layers, code, req, geom, bbox)
#   kind 'r': geom (x0, y0, x1, y1) rect;  'c': (cx, cy, r) disk;  's': (ax, ay, bx, by, r) capsule
creq = np.zeros((2, NY, NX), dtype=np.float32)          # clearance the occupant demands
XS = (np.arange(NX) + 0.5) * G
YS = (np.arange(NY) + 0.5) * G


def loc(v):
    return pcbnew.ToMM(v.x) - OX, pcbnew.ToMM(v.y) - OY


def win(x0, y0, x1, y1):
    i0, i1 = max(0, int(math.floor(x0 / G))), min(NX, int(math.ceil(x1 / G)) + 1)
    j0, j1 = max(0, int(math.floor(y0 / G))), min(NY, int(math.ceil(y1 / G)) + 1)
    return i0, i1, j0, j1


def paint(layer, mask_fn, x0, y0, x1, y1, code, req):
    i0, i1, j0, j1 = win(x0, y0, x1, y1)
    if i1 <= i0 or j1 <= j0:
        return
    X, Y = np.meshgrid(XS[i0:i1], YS[j0:j1])
    m = mask_fn(X, Y)
    for L in ((0, 1) if layer == "both" else (layer,)):
        sub = owner[L, j0:j1, i0:i1]
        sub[m] = code
        cr = creq[L, j0:j1, i0:i1]
        cr[m] = np.maximum(cr[m], req)


def _lay(layer):
    return (0, 1) if layer == "both" else (layer,)


def paint_capsule(layer, a, b, w, code, req):
    (ax, ay), (bx, by) = a, b
    r = w / 2
    OBJS.append(("s", _lay(layer), code, req, (ax, ay, bx, by, r),
                 (min(ax, bx) - r, min(ay, by) - r, max(ax, bx) + r, max(ay, by) + r)))

    def f(X, Y):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = np.clip(((X - ax) * dx + (Y - ay) * dy) / L2, 0, 1) if L2 > 0 else 0
        return np.hypot(X - ax - t * dx, Y - ay - t * dy) <= r
    paint(layer, f, min(ax, bx) - r, min(ay, by) - r, max(ax, bx) + r, max(ay, by) + r, code, req)


def paint_disk(layer, c, d, code, req):
    OBJS.append(("c", _lay(layer), code, req, (c[0], c[1], d / 2), (c[0] - d / 2, c[1] - d / 2, c[0] + d / 2, c[1] + d / 2)))
    paint(layer, lambda X, Y: np.hypot(X - c[0], Y - c[1]) <= d / 2, c[0] - d / 2, c[1] - d / 2, c[0] + d / 2,
          c[1] + d / 2, code, req)


PADS = []   # (ref, num, net, layer, poly-ish data for source/target masks)
HOLES = []  # (x, y, drill, netcode) of every drilled hole (vias, PTH/NPTH pads)


def pad_layers(p):
    ls = p.GetLayerSet()
    a = ls.Contains(pcbnew.F_Cu)
    b = ls.Contains(pcbnew.B_Cu)
    return "both" if a and b else (0 if a else (1 if b else None))


def paint_pad(p, ref):
    L = pad_layers(p)
    if L is None:
        return
    net = p.GetNetname()
    code = NCODE.get(net, 0) + 1 if net else 999999
    req = max(0.2, clr_of(net)) if net else 0.2
    c = loc(p.GetPosition())
    if p.GetShape() == pcbnew.PAD_SHAPE_CIRCLE:
        paint_disk(L, c, pcbnew.ToMM(p.GetSize().x), code, req)
    else:
        bb = p.GetBoundingBox()
        x0, y0 = loc(bb.GetPosition())
        x1, y1 = x0 + pcbnew.ToMM(bb.GetWidth()), y0 + pcbnew.ToMM(bb.GetHeight())
        paint(L, lambda X, Y: (X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1), x0, y0, x1, y1, code, req)
        OBJS.append(("r", _lay(L), code, req, (x0, y0, x1, y1), (x0, y0, x1, y1)))
    if p.GetDrillSize().x > 0:
        HOLES.append((c[0], c[1], pcbnew.ToMM(p.GetDrillSize().x), code))
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:      # DRC 'PTH to track': 0.35 mm from the hole edge
            hr = pcbnew.ToMM(p.GetDrillSize().x) / 2
            OBJS.append(("c", (0, 1), code, -0.35, (c[0], c[1], hr), (c[0] - hr, c[1] - hr, c[0] + hr, c[1] + hr)))
    if p.GetDrillSize().x > 0 and p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
        paint_disk("both", c, pcbnew.ToMM(p.GetDrillSize().x) + 0.2, 999999, 0.25)
    PADS.append((ref, p.GetNumber(), net, L, p))


for f in B.GetFootprints():
    for p in f.Pads():
        paint_pad(p, f.GetReference())


def paint_item(t):
    net = t.GetNetname()
    code = NCODE[net] + 1
    req = clr_of(net)
    if t.GetClass() == "PCB_VIA":
        paint_disk("both", loc(t.GetPosition()), pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)), code, req)
        HOLES.append((*loc(t.GetPosition()), pcbnew.ToMM(t.GetDrill()), code))
        return
    L = {pcbnew.F_Cu: 0, pcbnew.B_Cu: 1}.get(t.GetLayer())
    if L is None:
        return
    w = pcbnew.ToMM(t.GetWidth())
    if t.GetClass() == "PCB_ARC":
        c = loc(t.GetCenter())
        r = pcbnew.ToMM(t.GetRadius())
        a0 = math.atan2(loc(t.GetStart())[1] - c[1], loc(t.GetStart())[0] - c[0])
        am = math.atan2(loc(t.GetMid())[1] - c[1], loc(t.GetMid())[0] - c[0])
        a1 = math.atan2(loc(t.GetEnd())[1] - c[1], loc(t.GetEnd())[0] - c[0])
        def nrm(x):
            return (x + 2 * math.pi) % (2 * math.pi)
        s1, sm = nrm(a1 - a0), nrm(am - a0)
        sw = s1 if sm <= s1 else s1 - 2 * math.pi
        n = max(2, int(abs(sw) * r / 0.05))
        pts = [(c[0] + r * math.cos(a0 + sw * i / n), c[1] + r * math.sin(a0 + sw * i / n)) for i in range(n + 1)]
        for a, b in zip(pts[:-1], pts[1:]):
            paint_capsule(L, a, b, w, code, req)
    else:
        paint_capsule(L, loc(t.GetStart()), loc(t.GetEnd()), w, code, req)


for t in B.GetTracks():
    paint_item(t)

# board edge distance (rounded rectangle) and via keep-outs
X, Y = np.meshgrid(XS, YS)
dx = np.minimum(X, W - X)
dy = np.minimum(Y, H - Y)
EDGE = np.minimum(dx, dy)
cx = np.clip(X, RC, W - RC)
cy = np.clip(Y, RC, H - RC)
corner = (np.abs(X - cx) > 0) & (np.abs(Y - cy) > 0)
EDGE = np.where(corner, RC - np.hypot(X - cx, Y - cy), EDGE)
VIA_KEEP = np.zeros((NY, NX), dtype=bool)
for z in B.Zones():
    if z.GetIsRuleArea() and z.GetDoNotAllowVias():
        bb = z.GetBoundingBox()
        x0, y0 = loc(bb.GetPosition())
        x1, y1 = x0 + pcbnew.ToMM(bb.GetWidth()), y0 + pcbnew.ToMM(bb.GetHeight())
        VIA_KEEP |= (X >= x0 - 0.3) & (X <= x1 + 0.3) & (Y >= y0 - 0.3) & (Y <= y1 + 0.3)
FINE = []    # courtyard rects where the DRC allows 0.15 mm (fine-pitch escape rules)
for f in B.GetFootprints():
    if f.GetReference() in ("PLL601", "DEMOD701", "USB201", "CHG201", "BUCK301", "BUCK302"):
        cy_ = f.GetCourtyard(pcbnew.F_CrtYd)
        bb = cy_.BBox()
        x0_, y0_ = loc(bb.GetPosition())
        FINE.append((x0_, y0_, x0_ + pcbnew.ToMM(bb.GetWidth()), y0_ + pcbnew.ToMM(bb.GetHeight())))


def in_fine(bb):
    for r in FINE:
        if bb[0] <= r[2] and bb[2] >= r[0] and bb[1] <= r[3] and bb[3] >= r[1]:
            return True
    return False


COURT_IC = np.zeros((NY, NX), dtype=bool)     # no signal vias under IC bodies
for f in B.GetFootprints():
    if f.GetReference()[:2] in ("MC", "PL", "DE", "LD", "CH", "BU", "AD", "OP", "IN", "US", "J5", "SW"):
        cy_ = f.GetCourtyard(pcbnew.F_CrtYd)
        if cy_.OutlineCount():
            bb = cy_.BBox()
            x0, y0 = loc(bb.GetPosition())
            x1, y1 = x0 + pcbnew.ToMM(bb.GetWidth()), y0 + pcbnew.ToMM(bb.GetHeight())
            if f.GetReference() == "MCU401":
                y0 = max(y0, 0)
            COURT_IC |= (X > x0 + 0.3) & (X < x1 - 0.3) & (Y > y0 + 0.3) & (Y < y1 - 0.3)
del X, Y, dx, dy, cx, cy, corner

# ------------------------------------------------------------------ board item creation
def V(x, y):
    return pcbnew.VECTOR2I(mm(float(OX + x)), mm(float(OY + y)))


EMIT = []
CUR = [-1]


def add_track(net, a, b, w, L):
    if math.dist(a, b) < 1e-4:
        return
    EMIT.append(("t", net, a, b, w, L, CUR[0]))
    t = pcbnew.PCB_TRACK(B)
    t.SetStart(V(*a))
    t.SetEnd(V(*b))
    t.SetWidth(mm(w))
    t.SetLayer(pcbnew.F_Cu if L == 0 else pcbnew.B_Cu)
    t.SetNet(NETS[net])
    B.Add(t)
    paint_capsule(L, a, b, w, NCODE[net] + 1, clr_of(net))


def add_via(net, c, d, drill):
    EMIT.append(("v", net, c, d, CUR[0]))
    v = pcbnew.PCB_VIA(B)
    v.SetPosition(V(*c))
    v.SetDrill(mm(drill))
    v.SetWidth(mm(d))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetNet(NETS[net])
    B.Add(v)
    paint_disk("both", c, d, NCODE[net] + 1, clr_of(net))
    HOLES.append((c[0], c[1], drill, NCODE[net] + 1))


def hole_block(net, drill, i0, i1, j0, j1):
    """Cells where a new hole of this drill would break hole-to-hole (0.55 other nets, 0.3 same net)."""
    code = NCODE[net] + 1
    m = np.zeros((j1 - j0, i1 - i0), dtype=bool)
    Xw, Yw = np.meshgrid(XS[i0:i1], YS[j0:j1])
    x0, x1 = (i0) * G - 1.5, (i1) * G + 1.5
    y0, y1 = (j0) * G - 1.5, (j1) * G + 1.5
    for hx, hy, hd, hc in HOLES:
        if not (x0 < hx < x1 and y0 < hy < y1):
            continue
        need = (0.3 if hc == code else 0.55) + hd / 2 + drill / 2 + 0.03
        if hc == code:
            need = max(need, 0.7)
        m |= np.hypot(Xw - hx, Yw - hy) < need
    return m


# ------------------------------------------------------------------ free-space masks
_DISK = {}


def disk_offsets(rc):
    if rc not in _DISK:
        R = int(math.ceil(rc))
        _DISK[rc] = [(di, dj) for di in range(-R, R + 1) for dj in range(-R, R + 1) if math.hypot(di, dj) <= rc]
    return _DISK[rc]


def dilate(mask, rcells):
    out = np.zeros_like(mask)
    ny, nx = mask.shape
    for di, dj in disk_offsets(rcells):
        ys0, ys1 = max(0, dj), ny + min(0, dj)
        xs0, xs1 = max(0, di), nx + min(0, di)
        out[ys0:ys1, xs0:xs1] |= mask[ys0 - dj:ys1 - dj, xs0 - di:xs1 - di]
    return out


def free_mask(net, w, i0, i1, j0, j1, own_extra=None):
    """True where a track of width w centred on the cell clears all foreign copper (exact shapes) and the edge."""
    code = NCODE[net] + 1
    cn = clr_of(net)
    ny, nx = j1 - j0, i1 - i0
    blocked = np.zeros((2, ny, nx), dtype=bool)
    wx0, wy0, wx1, wy1 = i0 * G, j0 * G, i1 * G, j1 * G
    for kind, lays, oc, req, g, bb in OBJS:
        if oc == code:
            continue
        R = w / 2 + (-req if req < 0 else (0.15 if in_fine(bb) else max(cn, req))) + MARGIN
        if bb[2] + R < wx0 or bb[0] - R > wx1 or bb[3] + R < wy0 or bb[1] - R > wy1:
            continue
        a0_ = max(0, int(math.floor((bb[0] - R) / G)) - i0)
        a1_ = min(nx, int(math.ceil((bb[2] + R) / G)) - i0 + 1)
        b0_ = max(0, int(math.floor((bb[1] - R) / G)) - j0)
        b1_ = min(ny, int(math.ceil((bb[3] + R) / G)) - j0 + 1)
        if a1_ <= a0_ or b1_ <= b0_:
            continue
        Xs = XS[i0 + a0_:i0 + a1_][None, :]
        Ys = YS[j0 + b0_:j0 + b1_][:, None]
        if kind == "r":
            dx = np.maximum(np.maximum(g[0] - Xs, 0), Xs - g[2])
            dy = np.maximum(np.maximum(g[1] - Ys, 0), Ys - g[3])
            dist = np.hypot(dx, dy)
        elif kind == "c":
            dist = np.hypot(Xs - g[0], Ys - g[1]) - g[2]
        else:
            ax, ay, bx, by, r = g
            ddx, ddy = bx - ax, by - ay
            L2 = ddx * ddx + ddy * ddy
            t = np.clip(((Xs - ax) * ddx + (Ys - ay) * ddy) / L2, 0, 1) if L2 > 0 else 0.0
            dist = np.hypot(Xs - ax - t * ddx, Ys - ay - t * ddy) - r
        m = dist < R
        for L in lays:
            blocked[L, b0_:b1_, a0_:a1_] |= m
    ok = EDGE[j0:j1, i0:i1] >= 0.3 + w / 2
    return ~blocked & ok[None, :, :]


# ------------------------------------------------------------------ search
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
SQ2 = math.sqrt(2)


def shift(a, di, dj, fill):
    out = np.full_like(a, fill)
    ny, nx = a.shape
    ys0, ys1 = max(0, dj), ny + min(0, dj)
    xs0, xs1 = max(0, di), nx + min(0, di)
    out[ys0:ys1, xs0:xs1] = a[ys0 - dj:ys1 - dj, xs0 - di:xs1 - di]
    return out


def distance_field(free, viaok, target, vcost, maxit, src=None):
    INF = 1e9
    d = np.where(target & free, 0.0, INF)
    stable = 0
    last = INF
    for it in range(maxit):
        old = d
        for L in (0, 1):
            dl = d[L]
            for di, dj in DIRS:
                c = G * (SQ2 if di and dj else 1.0)
                dl = np.minimum(dl, shift(dl, di, dj, INF) + c)
            d[L] = np.where(free[L], dl, INF)
        both = np.minimum(d[0], d[1] + vcost)
        d[0] = np.where(viaok & free[0], np.minimum(d[0], d[1] + vcost), d[0])
        d[1] = np.where(viaok & free[1], np.minimum(d[1], d[0] + vcost), d[1])
        if src is not None:
            m = float(np.min(np.where(src, d, INF)))
            if m < INF:
                stable = stable + 1 if abs(m - last) < 1e-9 else 0
                last = m
                if stable > 12:
                    break
    return d


def backtrace(d, free, viaok, start, vcost):
    INF = 1e9
    L, j, i = start
    path = [(L, j, i)]
    pdir = None
    ny, nx = d.shape[1:]
    guard = 0
    while d[L, j, i] > 1e-9 and guard < 100000:
        guard += 1
        best = None
        for k, (di, dj) in enumerate(DIRS):
            jj, ii = j + dj, i + di
            if not (0 <= jj < ny and 0 <= ii < nx) or not free[L, jj, ii]:
                continue
            c = G * (SQ2 if di and dj else 1.0)
            if d[L, jj, ii] + c > d[L, j, i] + 1e-6 or d[L, jj, ii] >= d[L, j, i]:
                continue
            turn = 0 if pdir is None else min((k - pdir) % 8, (pdir - k) % 8)
            pen = {0: 0.0, 1: 0.05, 2: 0.3, 3: 5.0, 4: 50.0}[turn]
            score = d[L, jj, ii] + c + pen * G * 10
            if best is None or score < best[0]:
                best = (score, L, jj, ii, k)
        if viaok[j, i]:
            Lo = 1 - L
            if free[Lo, j, i] and d[Lo, j, i] + vcost <= d[L, j, i] + 1e-6 and d[Lo, j, i] < d[L, j, i]:
                score = d[Lo, j, i] + vcost + 0.5
                if best is None or score < best[0]:
                    best = (score, Lo, j, i, pdir)
        if best is None:
            return None
        _, L, j, i, pdir = best
        path.append((L, j, i))
    return path


def simplify(cells, i0, j0):
    """cells -> list of runs [(layer, [(x,y),...])] with collinear points merged."""
    runs = []
    cur = None
    for L, j, i in cells:
        p = ((i0 + i + 0.5) * G, (j0 + j + 0.5) * G)
        if cur is None or cur[0] != L:
            if cur is not None:
                runs.append(cur)
                cur = (L, [cur[1][-1], p]) if cur[1][-1] == p else (L, [p])
            else:
                cur = (L, [p])
        else:
            cur[1].append(p)
    runs.append(cur)
    out = []
    for L, pts in runs:
        q = [pts[0]]
        for k in range(1, len(pts) - 1):
            a, b, c = q[-1], pts[k], pts[k + 1]
            cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            if abs(cr) > 1e-9:
                q.append(b)
        if len(pts) > 1:
            q.append(pts[-1])
        out.append((L, q))
    return out


def _objs_near(x0, y0, x1, y1, R):
    for o in OBJS:
        bb = o[5]
        if bb[2] + R >= x0 and bb[0] - R <= x1 and bb[3] + R >= y0 and bb[1] - R <= y1:
            yield o


def seg_clear(net, w, L, a, b):
    """Exact clearance check of a track segment a-b (width w, layer L) against all foreign copper."""
    code = NCODE[net] + 1
    cn = clr_of(net)
    Rmax = w / 2 + 0.25 + MARGIN
    near = [o for o in _objs_near(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]), Rmax)
            if o[2] != code and L in o[1]]
    n = max(2, int(math.dist(a, b) / 0.025))
    for k in range(n + 1):
        x = a[0] + (b[0] - a[0]) * k / n
        y = a[1] + (b[1] - a[1]) * k / n
        if EDGE[min(NY - 1, max(0, int(y / G))), min(NX - 1, max(0, int(x / G)))] < 0.3 + w / 2 - 0.07:
            return False
        for kind, lays, oc, req, g, bb in near:
            R = w / 2 + (-req if req < 0 else (0.15 if in_fine(bb) else max(cn, req))) + MARGIN - 1e-6
            if kind == "r":
                dd = math.hypot(max(g[0] - x, 0, x - g[2]), max(g[1] - y, 0, y - g[3]))
            elif kind == "c":
                dd = math.hypot(x - g[0], y - g[1]) - g[2]
            else:
                ax, ay, bx, by, r = g
                ddx, ddy = bx - ax, by - ay
                L2 = ddx * ddx + ddy * ddy
                t = max(0.0, min(1.0, ((x - ax) * ddx + (y - ay) * ddy) / L2)) if L2 > 0 else 0.0
                dd = math.hypot(x - ax - t * ddx, y - ay - t * ddy) - r
            if dd < R:
                return False
    return True


def seg_free(free, L, a, b, i0, j0):
    n = max(2, int(math.dist(a, b) / 0.04))
    for k in range(n + 1):
        x = a[0] + (b[0] - a[0]) * k / n
        y = a[1] + (b[1] - a[1]) * k / n
        i, j = int(x / G) - i0, int(y / G) - j0
        if not (0 <= j < free.shape[1] and 0 <= i < free.shape[2]) or not free[L, j, i]:
            return False
    return True


def chamfer(pts, free, L, i0, j0, net=None, w=None):
    """Replace corners of 90 deg or sharper with 45-degree cuts."""
    dd = [pts[0]]
    for q in pts[1:]:
        if math.dist(q, dd[-1]) > 1e-6:
            dd.append(q)
    pts = dd
    if len(pts) < 3:
        return pts
    out = [pts[0]]
    for k in range(1, len(pts) - 1):
        a, P, c = out[-1], pts[k], pts[k + 1]
        u = ((P[0] - a[0]), (P[1] - a[1]))
        v = ((c[0] - P[0]), (c[1] - P[1]))
        lu, lv = math.hypot(*u), math.hypot(*v)
        if lu < 1e-6 or lv < 1e-6:
            continue
        cos = (u[0] * v[0] + u[1] * v[1]) / (lu * lv)
        if cos > 0.01:      # turn < 90 deg: keep
            out.append(P)
            continue
        done = False
        for cl in (0.3, 0.2, 0.12, 0.07):
            cl = min(cl, lu * 0.5, lv * 0.5)
            A = (P[0] - u[0] / lu * cl, P[1] - u[1] / lu * cl)
            Bq = (P[0] + v[0] / lv * cl, P[1] + v[1] / lv * cl)
            if (seg_clear(net, w, L, A, Bq) if net else seg_free(free, L, A, Bq, i0, j0)):
                out += [A, Bq]
                done = True
                break
        if not done:
            out.append(P)
    out.append(pts[-1])
    return out


# ------------------------------------------------------------------ endpoints
def pad_at(net, x, y):
    best = None
    for ref, num, n, L, p in PADS:
        if n != net:
            continue
        c = loc(p.GetPosition())
        dd = math.dist(c, (x, y))
        if best is None or dd < best[0]:
            best = (dd, p, L, c)
    return best


def endpoint_mask(net, pos, desc, i0, i1, j0, j1):
    """Cells (per layer) belonging to the endpoint item."""
    m = np.zeros((2, j1 - j0, i1 - i0), dtype=bool)
    Xw, Yw = np.meshgrid(XS[i0:i1], YS[j0:j1])
    if desc.startswith("Pad") or "pad" in desc.split(" of ")[0].lower():
        b = pad_at(net, *pos)
        if b and b[0] < 0.05:
            p, L = b[1], b[2]
            bb = p.GetBoundingBox()
            x0, y0 = loc(bb.GetPosition())
            x1, y1 = x0 + pcbnew.ToMM(bb.GetWidth()), y0 + pcbnew.ToMM(bb.GetHeight())
            inside = (Xw >= x0) & (Xw <= x1) & (Yw >= y0) & (Yw <= y1)
            for LL in ((0, 1) if L == "both" else (L,)):
                m[LL] |= inside
            return m, b[3], L
    # track / via end: cells of this net's copper within 0.3 mm of the point
    code = NCODE[net] + 1
    near = np.hypot(Xw - pos[0], Yw - pos[1]) <= 0.3
    for LL in (0, 1):
        m[LL] = near & (owner[LL, j0:j1, i0:i1] == code)
    lay = "both" if desc.startswith("Via") else (0 if "F.Cu" in desc else 1)
    return m, pos, lay


# ------------------------------------------------------------------ route one edge
def route_edge(net, a, b, verbose=False):
    (pa, da), (pb, db) = a, b
    for w in widths_for(net):
        for margin in (2.5, 6.0, 14.0):
            x0, x1 = min(pa[0], pb[0]) - margin, max(pa[0], pb[0]) + margin
            y0, y1 = min(pa[1], pb[1]) - margin, max(pa[1], pb[1]) + margin
            i0, i1, j0, j1 = win(x0, y0, x1, y1)
            free = free_mask(net, w, i0, i1, j0, j1)
            vd, vdr = via_for(net)
            vfree = free_mask(net, vd, i0, i1, j0, j1)
            viaok = vfree[0] & vfree[1] & ~VIA_KEEP[j0:j1, i0:i1] & ~hole_block(net, vdr, i0, i1, j0, j1)
            if CLS[net] not in ("Power", "PWR_BATT"):
                viaok &= ~COURT_IC[j0:j1, i0:i1]
            sm, sc, sl = endpoint_mask(net, pa, da, i0, i1, j0, j1)
            tm, tc, tl = endpoint_mask(net, pb, db, i0, i1, j0, j1)
            if DEBUG and net == DEBUG:
                print(f"   dbg {net} w{w} m{margin} src cells {int(sm.sum())} free {int((sm & free).sum())} | "
                      f"tgt cells {int(tm.sum())} free {int((tm & free).sum())} | free frac L1 {free[0].mean():.2f} L4 {free[1].mean():.2f} via {viaok.mean():.3f}")
            if not (sm & free).any() or not (tm & free).any():
                break     # endpoint itself cannot take this width: try narrower
            vcost = 1.0
            maxit = int(2.5 * (abs(i1 - i0) + abs(j1 - j0)))
            d = distance_field(free, viaok, tm, vcost, maxit, src=sm & free)
            cand = np.where(sm & free, d, 1e9)
            k = int(np.argmin(cand))
            if cand.flat[k] >= 1e9:
                if DEBUG and net == DEBUG:
                    reach = (d < 1e9)
                    print(f"   dbg no path: reachable cells from target L1 {int(reach[0].sum())} L4 {int(reach[1].sum())}")
                    np.save("/tmp/claude-1000/-home-eon-Formula-CWRadar-Frontend/2f7d572a-b22c-4ad1-a4c0-d7b3a43be794/scratchpad/dbg.npy",
                            np.stack([free[0], free[1], reach[0], reach[1], sm[0] | sm[1], tm[0] | tm[1], viaok]).astype(np.uint8))
                    print(f"   dbg window i{i0}-{i1} j{j0}-{j1}")
                continue
            L, j, i = np.unravel_index(k, cand.shape)
            cells = backtrace(d, free, viaok, (L, j, i), vcost)
            if cells is None:
                continue
            runs = simplify(cells, i0, j0)
            # attach the true endpoint centres
            def cell_free(pt, L):
                i, j = int(pt[0] / G) - i0, int(pt[1] / G) - j0
                return 0 <= j < free.shape[1] and 0 <= i < free.shape[2] and free[L, j, i]
            if runs[0][1][0] != sc and seg_clear(net, w, runs[0][0], sc, runs[0][1][0]):
                runs[0][1].insert(0, sc)
            if runs[-1][1][-1] != tc and seg_clear(net, w, runs[-1][0], runs[-1][1][-1], tc):
                runs[-1][1].append(tc)
            emitted = []
            for idx, (L, pts) in enumerate(runs):
                pts = chamfer(pts, free, L, i0, j0, net, w)
                for p, q in zip(pts[:-1], pts[1:]):
                    emitted.append(("t", net, p, q, w, L))
                if idx < len(runs) - 1:
                    emitted.append(("v", net, pts[-1], vd, vdr))
            if CHECK:
                for e in emitted:
                    if e[0] == "t" and not seg_clear(e[1], e[4], e[5], e[2], e[3]):
                        print(f"   CHECK track {e[1]} w{e[4]} L{e[5]} {e[2]}->{e[3]} fails")
                    if e[0] == "v" and not (seg_clear(e[1], e[3], 0, e[2], e[2]) and seg_clear(e[1], e[3], 1, e[2], e[2])):
                        print(f"   CHECK via {e[1]} at {e[2]} fails")
            for e in emitted:
                if e[0] == "t":
                    add_track(*e[1:])
                else:
                    add_via(*e[1:])
            return w
    return None


# ------------------------------------------------------------------ prep: LO fence thinning + GND vias at SMD GND pads
def prep():
    lo = [t for t in B.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"
          and abs(loc(t.GetPosition())[1] - 35.5) < 1.0 and 14.0 < loc(t.GetPosition())[0] < 80.0]
    lo.sort(key=lambda t: (round(loc(t.GetPosition())[1], 1), loc(t.GetPosition())[0]))
    rows = {}
    for t in lo:
        rows.setdefault(round(loc(t.GetPosition())[1], 1), []).append(t)
    removed = 0
    for row in rows.values():
        for k, t in enumerate(row):
            if k % 2 == 1:
                B.Remove(t)
                removed += 1
    # rebuild the raster for vias after removal
    owner[:] = 0
    creq[:] = 0
    PADS.clear()
    HOLES.clear()
    OBJS.clear()
    for f in B.GetFootprints():
        for p in f.Pads():
            paint_pad(p, f.GetReference())
    for t in B.GetTracks():
        paint_item(t)
    print(f"LO fence thinned: removed {removed} vias")
    # GND vias next to SMD GND pads that are not already stitched
    placed = 0
    have = [loc(t.GetPosition()) for t in B.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]
    for f in B.GetFootprints():
        ref = f.GetReference()
        if ref.startswith(("MH", "FID", "J60", "J70", "MCU", "USB")):
            continue
        fc = loc(f.GetPosition())
        for p in f.Pads():
            if p.GetNetname() != "GND" or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            c = loc(p.GetPosition())
            sz = max(pcbnew.ToMM(p.GetSize().x), pcbnew.ToMM(p.GetSize().y))
            if sz > 1.6:      # exposed pads carry their own thermal vias
                continue
            if any(math.dist(c, h) < 0.9 for h in have):
                continue
            ux, uy = c[0] - fc[0], c[1] - fc[1]
            Lr = math.hypot(ux, uy) or 1
            ux, uy = ux / Lr, uy / Lr
            dirs = [(ux, uy), (-uy, ux), (uy, -ux), (0.707 * (ux - uy), 0.707 * (uy + ux)), (0.707 * (ux + uy), 0.707 * (uy - ux)),
                    (-ux, -uy)]
            ok = False
            for rch in (0.55, 0.7, 0.85, 1.0):
                for ddx, ddy in dirs:
                    v = (c[0] + ddx * rch, c[1] + ddy * rch)
                    i, j = int(v[0] / G), int(v[1] / G)
                    if not (0 < i < NX - 1 and 0 < j < NY - 1) or VIA_KEEP[j, i]:
                        continue
                    i0, i1, j0, j1 = win(v[0] - 1.5, v[1] - 1.5, v[0] + 1.5, v[1] + 1.5)
                    fm = free_mask("GND", 0.45, i0, i1, j0, j1)
                    tm = free_mask("GND", 0.3, i0, i1, j0, j1)
                    hb = hole_block("GND", 0.2, i0, i1, j0, j1)
                    if fm[0, j - j0, i - i0] and fm[1, j - j0, i - i0] and not hb[j - j0, i - i0] and \
                            seg_free(tm, 0, c, v, i0, j0):
                        add_track("GND", c, v, 0.3, 0)
                        add_via("GND", v, 0.45, 0.2)
                        have.append(v)
                        placed += 1
                        ok = True
                        break
                if ok:
                    break
    print(f"GND pad vias placed: {placed}")
    fanout()


FANOUT_REFS = ("MCU401", "CHG201", "USB201")


def fanout():
    """Stub + via straight out of every signal pin of the dense parts, so later routes cannot seal the exits."""
    n = 0
    for f in B.GetFootprints():
        ref = f.GetReference()
        if ref not in FANOUT_REFS:
            continue
        fc = loc(f.GetPosition())
        pads = sorted(f.Pads(), key=lambda p: p.GetNumber())
        for k, p in enumerate(pads):
            net = p.GetNetname()
            if not net or net == "GND" or net.startswith("unconnected") or CLS.get(net) in ("Power", "PWR_BATT"):
                continue
            if p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            c = loc(p.GetPosition())
            bb = p.GetBoundingBox()
            bw, bh = pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())
            if bw >= bh:
                ax = (1.0 if c[0] > fc[0] else -1.0, 0.0)
                half, side = bw / 2, (0.0, 1.0)
            else:
                ax = (0.0, 1.0 if c[1] > fc[1] else -1.0)
                half, side = bh / 2, (1.0, 0.0)
            if ref == "USB201":
                ax = (0.0, 1.0)          # pins face into the board (receptacle opening at the top edge)
                half = bh / 2
            ok = False
            for dist in (half + 0.45, half + 0.75, half + 1.05, half + 1.35, half + 1.65):
                for lat in (0.0, 0.35, -0.35, 0.6, -0.6):
                    v = (c[0] + ax[0] * dist + side[0] * lat, c[1] + ax[1] * dist + side[1] * lat)
                    i, j = int(v[0] / G), int(v[1] / G)
                    if not (2 < i < NX - 2 and 2 < j < NY - 2) or VIA_KEEP[j, i] or COURT_IC[j, i]:
                        continue
                    i0, i1, j0, j1 = win(v[0] - 1.2, v[1] - 1.2, v[0] + 1.2, v[1] + 1.2)
                    fm = free_mask(net, 0.45, i0, i1, j0, j1)
                    if not (fm[0, j - j0, i - i0] and fm[1, j - j0, i - i0]):
                        continue
                    if hole_block(net, 0.2, i0, i1, j0, j1)[j - j0, i - i0]:
                        continue
                    # stub: straight out of the pad end, then (if offset) 45 degrees to the via
                    e = (c[0] + ax[0] * (half + 0.15), c[1] + ax[1] * (half + 0.15))
                    pts = [c, e]
                    if abs(lat) > 1e-6:
                        k1 = (e[0] + ax[0] * (dist - half - 0.15 - abs(lat)), e[1] + ax[1] * (dist - half - 0.15 - abs(lat)))
                        if (dist - half - 0.15 - abs(lat)) < 0:
                            continue
                        pts += [k1, v]
                    else:
                        pts += [v]
                    if all(seg_clear(net, 0.2, 0, a, b) for a, b in zip(pts[:-1], pts[1:])):
                        for a, b in zip(pts[:-1], pts[1:]):
                            add_track(net, a, b, 0.2, 0)
                        add_via(net, v, 0.45, 0.2)
                        n += 1
                        ok = True
                        break
                if ok:
                    break
    print(f"fan-out vias placed: {n}")


if PREP:
    prep()

# ------------------------------------------------------------------ main
d = json.load(open(DRCJ))
edges = []
for u in d["unconnected_items"]:
    it = u["items"]
    m = re.search(r"\[([^\]]+)\]", it[0]["description"])
    if not m:
        continue
    net = m.group(1)
    if net == "GND":
        continue
    isp = net.startswith("+")
    if (MODE == "power" and not isp) or (MODE == "signal" and isp):
        continue
    pa = (it[0]["pos"]["x"] - OX, it[0]["pos"]["y"] - OY)
    pb = (it[1]["pos"]["x"] - OX, it[1]["pos"]["y"] - OY)
    edges.append((math.dist(pa, pb), net, (pa, it[0]["description"]), (pb, it[1]["description"])))
HARD = ("MCU401", "CHG201", "USB201", "ADC1001", "OPA801", "OPA901", "ESD20", "PLL601")
PRIORITY = set(sys.argv[sys.argv.index("--first") + 1].split(",")) if "--first" in sys.argv else set()


def hardness(e):
    L, net, a, b = e
    first = 0 if net in PRIORITY else 1
    hard = 0 if any(h in a[1] or h in b[1] for h in HARD) else 1
    return (first, hard, L)


edges.sort(key=hardness)
ok, fail = 0, []
for k, (L, net, a, b) in enumerate(edges):
    CUR[0] = k
    if DEBUG and net != DEBUG:
        continue
    w = route_edge(net, a, b)
    if w:
        ok += 1
    else:
        fail.append((net, round(L, 1), a[1][:40], b[1][:40]))
print(f"routed {ok}/{len(edges)} edges")
print("FAILNETS " + ",".join(sorted({f_[0] for f_ in fail})))
for f_ in fail:
    print("  FAILED", f_)
if CHECK:
    import itertools
    def d_ps(p, a, b):
        ddx, ddy = b[0] - a[0], b[1] - a[1]
        L2 = ddx * ddx + ddy * ddy
        t = max(0, min(1, ((p[0] - a[0]) * ddx + (p[1] - a[1]) * ddy) / L2)) if L2 else 0
        return math.hypot(p[0] - a[0] - t * ddx, p[1] - a[1] - t * ddy)
    vs = [e for e in EMIT if e[0] == "v"]
    ts = [e for e in EMIT if e[0] == "t"]
    for v in vs:
        for t in ts:
            if t[1] == v[1]:
                continue
            need = max(clr_of(t[1]), clr_of(v[1]))
            gap = d_ps(v[2], t[2], t[3]) - v[3] / 2 - t[4] / 2
            if gap < need - 0.001:
                print(f"   PAIR via {v[1]}@{v[2]} (edge {v[4]}) vs track {t[1]} {t[2]}->{t[3]} w{t[4]} (edge {t[6]}): gap {gap:.3f} < {need}")
B.Save(DST)
