"""Final stage: GND stitching vias across the L1/L4 pours (and along the board edge), then a corner audit.

Usage: python3 stitch.py <in.kicad_pcb> <out.kicad_pcb> [pitch_mm]

Stitching is spaced generously (default 3 mm grid, 2.5 mm along the edge) since the two inner GND planes carry
the return currents; vias only go where they clear all copper by 0.25 mm and sit outside component courtyards.
"""
import math
import sys

import pcbnew

sys.path.insert(0, "/home/eon/Formula/CWRadar/.redraw-work")
from route_lib import Router  # noqa: E402

SRC, DST = sys.argv[1], sys.argv[2]
PITCH = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
B = pcbnew.LoadBoard(SRC)
R = Router(B, 92.0, 66.0, 4.0, load_existing=True)
n_grid = R.stitch_grid(1.5, 1.5, 90.5, 64.5, PITCH, d=0.45, drill=0.2, clr=0.25)
# perimeter ring, 1.2 mm in from the edge
n_edge = 0
W, H, RC, m = 92.0, 66.0, 4.0, 1.2
pts = []
x = RC
while x <= W - RC:
    pts += [(x, m), (x, H - m)]
    x += 2.5
y = RC
while y <= H - RC:
    pts += [(m, y), (W - m, y)]
    y += 2.5
for k in range(0, 90, 15):
    a = math.radians(k)
    for cx, cy, sx, sy in ((RC, RC, -1, -1), (W - RC, RC, 1, -1), (RC, H - RC, -1, 1), (W - RC, H - RC, 1, 1)):
        pts.append((cx + sx * (RC - m) * math.cos(a), cy + sy * (RC - m) * math.sin(a)))
for x, y in pts:
    if R.via_ok(x, y, 0.45, "GND", 0.25):
        R.via("GND", x, y, 0.45, 0.2)
        n_edge += 1
print(f"stitching vias: grid {n_grid}, edge {n_edge}")

# corner audit: consecutive same-net same-layer segments meeting at <= 90 degrees (true bends, not T-junctions)
ends = {}
for t in B.GetTracks():
    if t.GetClass() != "PCB_TRACK":
        continue
    for a, b in ((t.GetStart(), t.GetEnd()), (t.GetEnd(), t.GetStart())):
        key = (t.GetNetname(), t.GetLayer(), a.x, a.y)
        ends.setdefault(key, []).append((b.x - a.x, b.y - a.y))
sharp = 0
for key, vs in ends.items():
    if len(vs) != 2:
        continue
    (ax, ay), (bx, by) = vs
    la, lb = math.hypot(ax, ay), math.hypot(bx, by)
    if la == 0 or lb == 0:
        continue
    cos = (ax * bx + ay * by) / (la * lb)       # straight: -1, 45-degree bend: -0.71, 90-degree bend: 0
    if cos > -0.1:
        sharp += 1
        if sharp <= 10:
            print(f"   sharp bend {key[0]} layer {key[1]} at ({pcbnew.ToMM(key[2]) - 20:.2f}, {pcbnew.ToMM(key[3]) - 20:.2f})")
print(f"bends of 90 degrees or sharper: {sharp}")
B.Save(DST)
