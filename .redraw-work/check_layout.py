"""Placement checks before routing: aggressor/victim spacing and ratsnest routability.

Usage: python3 check_layout.py <board.kicad_pcb>
"""
import collections
import math
import re
import sys

import pcbnew

B = pcbnew.LoadBoard(sys.argv[1])
bb = B.GetBoardEdgesBoundingBox()
OX, OY = pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY())
W, H = pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())
FP = {f.GetReference(): f for f in B.GetFootprints()}


def rect(ref):
    f = FP[ref]
    cy = f.GetCourtyard(pcbnew.B_CrtYd if f.IsFlipped() else pcbnew.F_CrtYd)
    b = cy.BBox() if cy.OutlineCount() else f.GetBoundingBox(False)
    r = [pcbnew.ToMM(v) for v in (b.GetX(), b.GetY(), b.GetRight(), b.GetBottom())]
    if ref == "MCU401":   # module body only (the courtyard includes the antenna keep-out past the edge)
        c = f.GetPosition()
        r = [pcbnew.ToMM(c.x) - 9.0, max(pcbnew.ToMM(c.y) - 12.75, OY), pcbnew.ToMM(c.x) + 9.0, pcbnew.ToMM(c.y) + 12.75]
    return r


def gap(a, b):
    dx = max(a[0] - b[2], b[0] - a[2], 0)
    dy = max(a[1] - b[3], b[1] - a[3], 0)
    return math.hypot(dx, dy)


# ------------------------------------------------------------------ aggressors vs victims
AGG = {
    "BUCK1 (+VPRE) SW loop": ["BUCK301", "L301", "C304", "C301", "C302"],
    "BUCK2 (+3V3_D) SW loop": ["BUCK302", "L302", "C310", "C307", "C308"],
    "Charger SW loop": ["CHG201", "L201", "C202", "C203"],
    "ESP32 module": ["MCU401"],
    "USB-C": ["USB201"],
}
VIC = {
    "PLL + loop filter": ["PLL601", "C622", "R616", "C623", "R617", "C624", "R619"],
    "TCXO / REF": ["Y601", "C617", "R604", "C604", "C605", "C606"],
    "+3V3_SYN LDO (LDO305)": ["LDO305", "C325", "C326", "C327"],
    "DEMOD + RX": ["DEMOD701", "T701", "C702", "C703", "J701"],
    "+5V_RF LDO (LDO303)": ["LDO303", "C315", "C316", "C317"],
    "I in-amp + inputs": ["INA801", "C801", "C802", "R801", "R802", "R803", "R804", "C803", "C804", "C805"],
    "Q in-amp + inputs": ["INA901", "C901", "C902", "R901", "R902", "R903", "R904", "C903", "C904", "C905"],
    "I/Q op-amps": ["OPA801", "OPA901"],
    "ADC analog side": ["ADC1001", "C812", "C912", "C1005", "C1006"],
    "+5V_A LDO (LDO304)": ["LDO304", "C320", "C321", "C322"],
}
print(f"board {W:.1f} x {H:.1f} mm\n")
print("min courtyard gap, aggressor -> victim (mm):")
hdr = "".join(f"{k[:14]:>15}" for k in AGG)
print(f"{'':28}{hdr}")
worst = []
for vn, vl in VIC.items():
    row = []
    for an, al in AGG.items():
        g = min(gap(rect(a), rect(v)) for a in al for v in vl if a in FP and v in FP)
        row.append(g)
        worst.append((g, an, vn))
    print(f"{vn:28}" + "".join(f"{g:15.1f}" for g in row))
print("\ntightest pairs:", ", ".join(f"{a} -> {v} {g:.1f}" for g, a, v in sorted(worst)[:6]))

# ------------------------------------------------------------------ ratsnest
pads = collections.defaultdict(list)
for f in B.GetFootprints():
    for p in f.Pads():
        n = p.GetNetname()
        if n and not n.startswith("unconnected"):
            pads[n].append((pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y), f.GetReference()))


def mst(pts):
    if len(pts) < 2:
        return []
    inn, edges = {0}, []
    d = {i: (math.dist(pts[0][:2], pts[i][:2]), 0) for i in range(1, len(pts))}
    while d:
        j = min(d, key=lambda k: d[k][0])
        L, i = d.pop(j)
        edges.append((pts[i], pts[j], L))
        inn.add(j)
        for k in d:
            nd = math.dist(pts[j][:2], pts[k][:2])
            if nd < d[k][0]:
                d[k] = (nd, j)
    return edges


SKIP = {"GND"}
POWER = re.compile(r"^\+")
rows, edges_all = [], []
for n, pts in pads.items():
    if n in SKIP:
        continue
    # merge pads of the same footprint that share the net (internally connected)
    e = mst(pts)
    L = sum(x[2] for x in e)
    longest = max((x[2] for x in e), default=0)
    rows.append((longest, L, n, len(pts)))
    for a, b, l in e:
        edges_all.append((n, a, b, l))

print("\nlongest single ratsnest links (signals; power rails listed separately):")
sig = [r for r in rows if not POWER.match(r[2])]
for longest, L, n, k in sorted(sig, reverse=True)[:22]:
    print(f"  {longest:6.1f} mm  (net total {L:6.1f}, {k} pads)  {n}")
print("\npower rails, total MST length:")
for longest, L, n, k in sorted((r for r in rows if POWER.match(r[2])), key=lambda r: -r[1])[:14]:
    print(f"  {L:6.1f} mm  longest link {longest:5.1f}  {k:3d} pads  {n}")

# nets that must cross the LO lane (y band between PLL B pins and DEMOD top), i.e. go on L4
# LO guard lane: place_layout.py puts it 16 mm above the PLL centre (YL = YP - 16)
lane_y = pcbnew.ToMM(FP["PLL601"].GetPosition().y) - 16.0
x0 = pcbnew.ToMM(FP["C620"].GetPosition().x)
x1 = pcbnew.ToMM(FP["DEMOD701"].GetPosition().x)
cross = collections.Counter()
for n, a, b, l in edges_all:
    if n.startswith("/Receiver/LO") or n.startswith("/Synthesizer/RFOUTB"):
        continue
    (ax, ay, _), (bx, by, _) = a, b
    if (ay - lane_y) * (by - lane_y) < 0:
        t = (lane_y - ay) / (by - ay)
        xc = ax + t * (bx - ax)
        if x0 < xc < x1:
            cross[n] += 1
print(f"\nratsnest links crossing the LO lane (y = {lane_y - OY:.1f}, x {x0 - OX:.0f}..{x1 - OX:.0f}): {sum(cross.values())}")
for n, c in cross.most_common():
    print(f"  {c}x {n}")

# congestion: ratsnest length per 5 mm cell (all non-GND links), crude routing-demand map
CELL = 5.0
nx, ny = int(math.ceil(W / CELL)), int(math.ceil(H / CELL))
dem = [[0.0] * nx for _ in range(ny)]
for n, a, b, l in edges_all:
    steps = max(1, int(l / 0.5))
    for s in range(steps):
        t = (s + 0.5) / steps
        x = a[0] + t * (b[0] - a[0]) - OX
        y = a[1] + t * (b[1] - a[1]) - OY
        i, j = min(nx - 1, max(0, int(x / CELL))), min(ny - 1, max(0, int(y / CELL)))
        dem[j][i] += l / steps
print("\nrouting demand (mm of ratsnest per 5 mm cell; L1+L4 capacity is roughly 2 x 5 mm / 0.35 mm pitch x 5 mm ~ 140):")
for j in range(ny):
    print(f"  y{j * CELL:4.0f} " + " ".join(f"{dem[j][i]:4.0f}" for i in range(nx)))
