"""Find true 90-degree-or-sharper bends (two same-net segments meeting off any pad or via) and chamfer them.

Usage: python3 fix_corners.py <in.kicad_pcb> <out.kicad_pcb>
A bend at P between P->a and P->b is replaced by a 45-degree cut of length c (0.3 -> 0.08 mm), checked
against every other-net pad, track and via with the net-class clearance (+0.02 mm).
"""
import math
import sys

import pcbnew

SRC, DST = sys.argv[1], sys.argv[2]
B = pcbnew.LoadBoard(SRC)
mm = pcbnew.FromMM
TO = pcbnew.ToMM
CLR = {"PWR_BATT": 0.25, "ANALOG_BB": 0.25, "Power": 0.2, "RF": 0.2, "USB_90": 0.2}


def clr(item):
    return CLR.get(item.GetNetClassName() if hasattr(item, "GetNetClassName") else "Default", 0.15)


tracks = [t for t in B.GetTracks() if t.GetClass() == "PCB_TRACK"]
vias = [t for t in B.GetTracks() if t.GetClass() == "PCB_VIA"]
pads = [p for f in B.GetFootprints() for p in f.Pads()]


def on_pad_or_via(net, layer, x, y):
    for v in vias:
        if v.GetNetname() == net and math.hypot(TO(v.GetPosition().x) - x, TO(v.GetPosition().y) - y) < TO(v.GetWidth(pcbnew.F_Cu)) / 2:
            return True
    for p in pads:
        if p.GetNetname() != net or not p.IsOnLayer(layer):
            continue
        bb = p.GetBoundingBox()
        if TO(bb.GetX()) - 0.01 <= x <= TO(bb.GetRight()) + 0.01 and TO(bb.GetY()) - 0.01 <= y <= TO(bb.GetBottom()) + 0.01:
            return True
    return False


def d_seg_seg(a, b, c, d):
    def dps(p, q, r):
        dx, dy = r[0] - q[0], r[1] - q[1]
        L2 = dx * dx + dy * dy
        t = max(0, min(1, ((p[0] - q[0]) * dx + (p[1] - q[1]) * dy) / L2)) if L2 else 0
        return math.hypot(p[0] - q[0] - t * dx, p[1] - q[1] - t * dy)
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    if a != b and c != d:
        o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
        if o1 * o2 < 0 and o3 * o4 < 0:
            return 0.0       # proper crossing
    return min(dps(a, c, d), dps(b, c, d), dps(c, a, b), dps(d, a, b))


def seg_ok(net, layer, a, b, w, ncls):
    for t in tracks:
        if t.GetNetname() == net or t.GetLayer() != layer:
            continue
        need = max(ncls, clr(t)) + w / 2 + TO(t.GetWidth()) / 2 + 0.02
        if d_seg_seg(a, b, (TO(t.GetStart().x), TO(t.GetStart().y)), (TO(t.GetEnd().x), TO(t.GetEnd().y))) < need:
            return False
    for v in vias:
        if v.GetNetname() == net:
            continue
        c = (TO(v.GetPosition().x), TO(v.GetPosition().y))
        need = max(ncls, clr(v)) + w / 2 + TO(v.GetWidth(pcbnew.F_Cu)) / 2 + 0.02
        if d_seg_seg(a, b, c, c) < need:
            return False
    for p in pads:
        if p.GetNetname() == net or not p.IsOnLayer(layer):
            continue
        bb = p.GetBoundingBox()
        r = (TO(bb.GetX()), TO(bb.GetY()), TO(bb.GetRight()), TO(bb.GetBottom()))
        need = max(0.2, ncls, clr(p)) + w / 2 + 0.02
        for k in range(11):
            x = a[0] + (b[0] - a[0]) * k / 10
            y = a[1] + (b[1] - a[1]) * k / 10
            if math.hypot(max(r[0] - x, 0, x - r[2]), max(r[1] - y, 0, y - r[3])) < need:
                return False
    return True


ends = {}
for t in tracks:
    for which in ("s", "e"):
        p = t.GetStart() if which == "s" else t.GetEnd()
        ends.setdefault((t.GetNetname(), t.GetLayer(), p.x, p.y), []).append((t, which))
found = fixed = 0
for (net, layer, px, py), lst in ends.items():
    if len(lst) != 2:
        continue
    P = (TO(px), TO(py))
    if on_pad_or_via(net, layer, *P):
        continue
    (t1, w1), (t2, w2) = lst
    o1 = t1.GetEnd() if w1 == "s" else t1.GetStart()
    o2 = t2.GetEnd() if w2 == "s" else t2.GetStart()
    A, Bp = (TO(o1.x), TO(o1.y)), (TO(o2.x), TO(o2.y))
    u = (A[0] - P[0], A[1] - P[1])
    v = (Bp[0] - P[0], Bp[1] - P[1])
    lu, lv = math.hypot(*u), math.hypot(*v)
    if lu < 1e-6 or lv < 1e-6:
        continue
    if (u[0] * v[0] + u[1] * v[1]) / (lu * lv) <= -0.1:
        continue
    found += 1
    w = min(TO(t1.GetWidth()), TO(t2.GetWidth()))
    ncls = max(clr(t1), clr(t2))
    for c in (0.3, 0.2, 0.12, 0.08):
        c = min(c, lu * 0.45, lv * 0.45)
        Q1 = (P[0] + u[0] / lu * c, P[1] + u[1] / lu * c)
        Q2 = (P[0] + v[0] / lv * c, P[1] + v[1] / lv * c)
        if seg_ok(net, layer, Q1, Q2, w, ncls):
            for t, wh, Q in ((t1, w1, Q1), (t2, w2, Q2)):
                q = pcbnew.VECTOR2I(mm(Q[0]), mm(Q[1]))
                if wh == "s":
                    t.SetStart(q)
                else:
                    t.SetEnd(q)
            n = pcbnew.PCB_TRACK(B)
            n.SetStart(pcbnew.VECTOR2I(mm(Q1[0]), mm(Q1[1])))
            n.SetEnd(pcbnew.VECTOR2I(mm(Q2[0]), mm(Q2[1])))
            n.SetWidth(mm(w))
            n.SetLayer(layer)
            n.SetNet(t1.GetNet())
            B.Add(n)
            tracks.append(n)
            fixed += 1
            break
    else:
        print(f"   could not chamfer {net} on {B.GetLayerName(layer)} at ({P[0] - 20:.2f}, {P[1] - 20:.2f})")
print(f"true sharp bends: {found}, chamfered: {fixed}")
B.Save(DST)
