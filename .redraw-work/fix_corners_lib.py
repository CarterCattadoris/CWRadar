"""Clearance helpers shared by fix_corners.py and gnd_tie.py."""
import math

import pcbnew

TO = pcbnew.ToMM
tracks, vias, pads = [], [], []


def init(B):
    tracks[:] = [t for t in B.GetTracks() if t.GetClass() == "PCB_TRACK"]
    vias[:] = [t for t in B.GetTracks() if t.GetClass() == "PCB_VIA"]
    pads[:] = [p for f in B.GetFootprints() for p in f.Pads()]


CLR = {"PWR_BATT": 0.25, "ANALOG_BB": 0.25, "Power": 0.2, "RF": 0.2, "USB_90": 0.2}


def clr(item):
    return CLR.get(item.GetNetClassName() if hasattr(item, "GetNetClassName") else "Default", 0.15)




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


