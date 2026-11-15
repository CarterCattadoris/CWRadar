"""Routing helpers for the CWRadar scripted layout (KiCad 10 pcbnew).

Coordinates are board-local mm (origin at the board's top-left corner, page offset OX/OY), y down.
- path(): polyline with filleted (arc) corners for RF, or 45-degree chamfers for everything else; never 90.
- via(), fence(): GND vias; fence() walks a routed path and drops vias on both sides wherever they clear
  every pad, track, via, keep-out and the board edge (rounded corners included).
- Lengths per net are accumulated in R.length for skew checks.
"""
import math

import pcbnew

OX, OY = 20.0, 20.0
mm = pcbnew.FromMM


def V(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


def unit(v):
    L = math.hypot(*v)
    return (v[0] / L, v[1] / L)


class Router:
    def __init__(self, board, W, H, RC, load_existing=False):
        self.B, self.W, self.H, self.RC = board, W, H, RC
        self.nets = {board.GetNetInfo().GetNetItem(i).GetNetname(): board.GetNetInfo().GetNetItem(i)
                     for i in range(board.GetNetCount())}
        self.length = {}
        self.segs = []     # (ax, ay, bx, by, w, net, layer) incl. arcs as polylines
        self.vias = []     # (x, y, d, net)
        self.keepout = []  # (x0, y0, x1, y1) no vias
        self.pads = []     # (x0, y0, x1, y1, net, ref)
        self.court = []    # (x0, y0, x1, y1, ref) courtyards: no stitching vias inside
        self.holes = []    # (x, y, drill, net) existing drilled holes (for hole-to-hole)
        for f in board.GetFootprints():
            ref = f.GetReference()
            for p in f.Pads():
                bb = p.GetBoundingBox()
                self.pads.append((pcbnew.ToMM(bb.GetX()) - OX, pcbnew.ToMM(bb.GetY()) - OY,
                                  pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY,
                                  p.GetNetname(), ref))
            if ref.startswith(("MH", "FID")):
                continue
            cy = f.GetCourtyard(pcbnew.F_CrtYd)
            if cy.OutlineCount():
                bb = cy.BBox()
                r = [pcbnew.ToMM(bb.GetX()) - OX, pcbnew.ToMM(bb.GetY()) - OY,
                     pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY]
                if ref == "MCU401":
                    r[1] = max(r[1], 0.0)
                    c = f.GetPosition()
                    r = [pcbnew.ToMM(c.x) - OX - 9.0, 0.0, pcbnew.ToMM(c.x) - OX + 9.0, pcbnew.ToMM(c.y) - OY + 12.75]
                self.court.append((*r, ref))
        if load_existing:
            for t in board.GetTracks():
                n = t.GetNetname()
                if t.GetClass() == "PCB_VIA":
                    q = t.GetPosition()
                    self.vias.append((pcbnew.ToMM(q.x) - OX, pcbnew.ToMM(q.y) - OY, pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)), n))
                else:
                    a, b = t.GetStart(), t.GetEnd()
                    self.segs.append((pcbnew.ToMM(a.x) - OX, pcbnew.ToMM(a.y) - OY, pcbnew.ToMM(b.x) - OX,
                                      pcbnew.ToMM(b.y) - OY, pcbnew.ToMM(t.GetWidth()), n, t.GetLayer()))
            for f in board.GetFootprints():
                for p in f.Pads():
                    if p.GetDrillSize().x > 0:
                        q = p.GetPosition()
                        self.holes.append((pcbnew.ToMM(q.x) - OX, pcbnew.ToMM(q.y) - OY, pcbnew.ToMM(p.GetDrillSize().x), p.GetNetname()))
        for z in board.Zones():
            if z.GetIsRuleArea() and z.GetDoNotAllowVias():
                bb = z.GetBoundingBox()
                self.keepout.append((pcbnew.ToMM(bb.GetX()) - OX, pcbnew.ToMM(bb.GetY()) - OY,
                                     pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY))

    # -------------------------------------------------------------- primitives
    def net(self, name):
        return self.nets[name]

    def pad(self, ref, num):
        f = self.B.FindFootprintByReference(ref)
        for p in f.Pads():
            if p.GetNumber() == num:
                q = p.GetPosition()
                return (pcbnew.ToMM(q.x) - OX, pcbnew.ToMM(q.y) - OY)
        raise KeyError((ref, num))

    def _add_len(self, net, L):
        self.length[net] = self.length.get(net, 0.0) + L

    def seg(self, net, a, b, w, layer=pcbnew.F_Cu):
        if math.dist(a, b) < 1e-4:
            return
        t = pcbnew.PCB_TRACK(self.B)
        t.SetStart(V(*a))
        t.SetEnd(V(*b))
        t.SetWidth(mm(w))
        t.SetLayer(layer)
        t.SetNet(self.net(net))
        self.B.Add(t)
        self.segs.append((*a, *b, w, net, layer))
        self._add_len(net, math.dist(a, b))

    def arc(self, net, a, m, b, w, center, r, layer=pcbnew.F_Cu):
        t = pcbnew.PCB_ARC(self.B)
        t.SetStart(V(*a))
        t.SetMid(V(*m))
        t.SetEnd(V(*b))
        t.SetWidth(mm(w))
        t.SetLayer(layer)
        t.SetNet(self.net(net))
        self.B.Add(t)
        a0 = math.atan2(a[1] - center[1], a[0] - center[0])
        a1 = math.atan2(b[1] - center[1], b[0] - center[0])
        am = math.atan2(m[1] - center[1], m[0] - center[0])
        # sweep through the mid point
        def norm(x):
            return (x + 2 * math.pi) % (2 * math.pi)
        s1, sm = norm(a1 - a0), norm(am - a0)
        sweep = s1 if sm <= s1 else s1 - 2 * math.pi
        n = max(2, int(abs(sweep) * r / 0.1))
        prev = a
        for i in range(1, n + 1):
            ang = a0 + sweep * i / n
            pt = (center[0] + r * math.cos(ang), center[1] + r * math.sin(ang))
            self.segs.append((*prev, *pt, w, net, layer))
            prev = pt
        self._add_len(net, abs(sweep) * r)

    def path(self, net, pts, w, r=0.0, chamfer=0.0, layer=pcbnew.F_Cu):
        """Polyline through pts. r > 0: tangent arcs of radius r at corners (RF). chamfer > 0: 45-degree cuts.
        Returns the list of sampled centre points (for fences)."""
        pts = [tuple(p) for p in pts]
        out = [pts[0]]
        cur = pts[0]
        rlist = r if isinstance(r, (list, tuple)) else None
        for i in range(1, len(pts) - 1):
            if rlist is not None:
                r = rlist[i - 1]
            P, Pn = pts[i], pts[i + 1]
            d1, d2 = unit((P[0] - pts[i - 1][0], P[1] - pts[i - 1][1])), unit((Pn[0] - P[0], Pn[1] - P[1]))
            dot = max(-1.0, min(1.0, d1[0] * d2[0] + d1[1] * d2[1]))
            th = math.acos(dot)
            if th < 1e-6:
                continue
            l1, l2 = math.dist(cur, P), math.dist(P, Pn)
            if r > 0:
                t = r * math.tan(th / 2)
                lim = min(l1, l2 / 2 if i < len(pts) - 2 else l2)
                rr = r
                if t > lim:
                    t = lim
                    rr = t / math.tan(th / 2)
                A = (P[0] - d1[0] * t, P[1] - d1[1] * t)
                Bp = (P[0] + d2[0] * t, P[1] + d2[1] * t)
                n1 = (-d1[1], d1[0])
                C1 = (A[0] + n1[0] * rr, A[1] + n1[1] * rr)
                C2 = (A[0] - n1[0] * rr, A[1] - n1[1] * rr)
                C = C1 if abs(math.dist(C1, Bp) - rr) < abs(math.dist(C2, Bp) - rr) else C2
                u = unit((P[0] - C[0], P[1] - C[1]))
                M = (C[0] + u[0] * rr, C[1] + u[1] * rr)
                self.seg(net, cur, A, w, layer)
                self.arc(net, A, M, Bp, w, C, rr, layer)
                out += [A, M, Bp]
                cur = Bp
            else:
                c = min(chamfer if chamfer > 0 else 0.0, l1 * 0.5, l2 * 0.5)
                if abs(th - math.pi / 2) < 1e-3 and c <= 0:
                    raise ValueError(f"90-degree corner without chamfer on {net} at {P}")
                if c > 0:
                    A = (P[0] - d1[0] * c, P[1] - d1[1] * c)
                    Bp = (P[0] + d2[0] * c, P[1] + d2[1] * c)
                    self.seg(net, cur, A, w, layer)
                    self.seg(net, A, Bp, w, layer)
                    out += [A, Bp]
                    cur = Bp
                else:
                    self.seg(net, cur, P, w, layer)
                    out.append(P)
                    cur = P
        self.seg(net, cur, pts[-1], w, layer)
        out.append(pts[-1])
        return out

    def via(self, net, x, y, d=0.6, drill=0.3, check=False, clr=0.2):
        if check and not self.via_ok(x, y, d, net, clr):
            return False
        v = pcbnew.PCB_VIA(self.B)
        v.SetPosition(V(x, y))
        v.SetDrill(mm(drill))
        v.SetWidth(mm(d))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetNet(self.net(net))
        self.B.Add(v)
        self.vias.append((x, y, d, net))
        return True

    # -------------------------------------------------------------- clearance checks
    def inside_board(self, x, y, m):
        W, H, RC = self.W, self.H, self.RC
        if not (m <= x <= W - m and m <= y <= H - m):
            return False
        for cx, cy in ((RC, RC), (W - RC, RC), (RC, H - RC), (W - RC, H - RC)):
            if (x < RC and cx == RC or x > W - RC and cx == W - RC) and \
               (y < RC and cy == RC or y > H - RC and cy == H - RC):
                if math.hypot(x - cx, y - cy) > RC - m:
                    return False
        return True

    @staticmethod
    def _pt_seg(px, py, ax, ay, bx, by):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = 0 if L2 == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L2))
        return math.hypot(px - ax - t * dx, py - ay - t * dy)

    @staticmethod
    def _pt_rect(px, py, r):
        dx = max(r[0] - px, 0, px - r[2])
        dy = max(r[1] - py, 0, py - r[3])
        return math.hypot(dx, dy)

    def via_ok(self, x, y, d, net, clr=0.2, courtyards=True):
        rad = d / 2
        if not self.inside_board(x, y, rad + 0.35):
            return False
        for k in self.keepout:
            if self._pt_rect(x, y, k) < rad + 0.05:
                return False
        if courtyards:
            for c in self.court:
                if c[0] < x < c[2] and c[1] < y < c[3]:
                    return False
        for p in self.pads:
            need = rad + (0.1 if p[4] == net else clr)
            if self._pt_rect(x, y, p) < need:
                return False
        for s in self.segs:
            if s[5] == net:
                continue
            if self._pt_seg(x, y, *s[:4]) < rad + s[4] / 2 + clr:
                return False
        for v in self.vias:
            if math.hypot(x - v[0], y - v[1]) < max(rad + v[2] / 2 + (0.15 if v[3] == net else clr), 0.85):
                return False
        for hx, hy, hd, hn in self.holes:
            if math.hypot(x - hx, y - hy) < (0.3 if hn == net else 0.55) + hd / 2 + 0.15:
                return False
        return True

    # -------------------------------------------------------------- fences
    def fence(self, pts, offset, pitch=0.9, d=0.45, drill=0.2, net="GND", sides=(1, -1), start=0.0, end=0.0):
        """Vias at +/-offset from the centre polyline pts, every `pitch` mm of arc length."""
        segs = list(zip(pts[:-1], pts[1:]))
        total = sum(math.dist(a, b) for a, b in segs)
        placed = 0
        s = start
        while s <= total - end + 1e-9:
            acc = 0.0
            for a, b in segs:
                L = math.dist(a, b)
                if L < 1e-9:
                    continue
                if acc + L >= s:
                    t = (s - acc) / L
                    x, y = a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])
                    dx, dy = unit((b[0] - a[0], b[1] - a[1]))
                    for sd in sides:
                        vx, vy = x - dy * offset * sd, y + dx * offset * sd
                        if self.via_ok(vx, vy, d, net):
                            self.via(net, vx, vy, d, drill)
                            placed += 1
                    break
                acc += L
            s += pitch
        return placed

    def stitch_grid(self, x0, y0, x1, y1, pitch, d=0.6, drill=0.3, net="GND", clr=0.25):
        n = 0
        y = y0
        while y <= y1:
            x = x0
            while x <= x1:
                if self.via_ok(x, y, d, net, clr):
                    self.via(net, x, y, d, drill)
                    n += 1
                x += pitch
            y += pitch
        return n


def path_length(pts, r=0.0):
    """Length of path() through pts with fillet radius r (float or per-corner list), without drawing."""
    pts = [tuple(p) for p in pts]
    L = sum(math.dist(a, b) for a, b in zip(pts[:-1], pts[1:]))
    cur = pts[0]
    for i in range(1, len(pts) - 1):
        rr = r[i - 1] if isinstance(r, (list, tuple)) else r
        if rr <= 0:
            cur = pts[i]
            continue
        P, Pn = pts[i], pts[i + 1]
        d1 = unit((P[0] - pts[i - 1][0], P[1] - pts[i - 1][1]))
        d2 = unit((Pn[0] - P[0], Pn[1] - P[1]))
        th = math.acos(max(-1.0, min(1.0, d1[0] * d2[0] + d1[1] * d2[1])))
        if th < 1e-6:
            continue
        t = rr * math.tan(th / 2)
        lim = min(math.dist(cur, P), math.dist(P, Pn) / 2 if i < len(pts) - 2 else math.dist(P, Pn))
        if t > lim:
            t = lim
            rr = t / math.tan(th / 2)
        L -= 2 * t - rr * th
        cur = (P[0] + d2[0] * t, P[1] + d2[1] * t)
    return L
