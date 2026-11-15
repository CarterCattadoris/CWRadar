"""Stage 1 routing: RF lines (TX, MON, LO pair, RX), RF-area grounding, +3V3_SYN_RF, via fences.

Usage: python3 route_rf.py <placed.kicad_pcb> <out.kicad_pcb>

Input is the output of place_layout.py (positions there are fixed: TX_X = 15.45, YP = 51.5, YL = 35.5,
DEMOD at (77.5, 51)). All RF bends are tangent arcs; other bends are 45-degree chamfers.
Widths: 50R CPWG 0.28 mm (0.20 mm pour gap), LO 100R coupled pair 0.19 / 0.20 mm.
"""
import math
import sys

import pcbnew

sys.path.insert(0, "/home/eon/Formula/CWRadar/.redraw-work")
from route_lib import Router, path_length  # noqa: E402

SRC, DST = sys.argv[1], sys.argv[2]
B = pcbnew.LoadBoard(SRC)
R = Router(B, 92.0, 66.0, 4.0)
W50, WLO, GLO = 0.28, 0.19, 0.20
PITCH = WLO + GLO
WPWR = 0.3
FENCE_OFF = W50 / 2 + 0.2 + 0.225 + 0.08      # CPWG: via edge just past the 0.2 mm pour gap
FENCE_LO = WLO / 2 + 0.2 + 0.225 + 0.08

P = R.pad
YL = 35.5
fence_jobs = []

# ------------------------------------------------------------------ TX: A_P -> C619 -> J601
a_p = P("PLL601", "12")
tx_x = P("C619", "1")[0]
pts = R.path("/Synthesizer/RFOUTA_P", [a_p, (tx_x, a_p[1]), P("C619", "1")], W50, r=0.5)
fence_jobs.append((pts, FENCE_OFF, (1, -1)))
r613 = P("R613", "2")
R.path("/Synthesizer/RFOUTA_P", [(tx_x, r613[1]), r613], W50)
j601 = P("J601", "1")
pts = R.path("/Synthesizer/TX_RF", [P("C619", "2"), (tx_x, j601[1] - 2.2)], W50)
fence_jobs.append((pts, FENCE_OFF, (1, -1)))

# ------------------------------------------------------------------ MON: A_N -> C618 -> J602 (R611 tee, R612 at the SMA)
a_n = P("PLL601", "13")
pts = R.path("/Synthesizer/RFOUTA_N", [a_n, P("C618", "1")], W50)
fence_jobs.append((pts, FENCE_OFF, (-1,)))      # north side; the south side is the TX turn / R613 / R611
r611 = P("R611", "2")
R.path("/Synthesizer/RFOUTA_N", [(r611[0], a_n[1]), r611], W50)
j602 = P("J602", "1")
pts = R.path("/Synthesizer/MON_RF", [P("C618", "2"), (j602[0], a_n[1]), (j602[0], j602[1] - 2.2)], W50, r=1.0)
fence_jobs.append((pts, FENCE_OFF, (1, -1)))
r612 = P("R612", "1")
R.path("/Synthesizer/MON_RF", [(j602[0], r612[1]), r612], W50)

# ------------------------------------------------------------------ B pair + LO pair (pin-to-pin phase matched)
b_n, b_p = P("PLL601", "15"), P("PLL601", "14")
c620, c621 = P("C620", "1"), P("C621", "1")
lo_n0, lo_p0 = P("C620", "2"), P("C621", "2")
pin9, pin10 = P("DEMOD701", "9"), P("DEMOD701", "10")     # LO_N -> LOIP (pin 9), LO_P -> LOIN (pin 10)
xd = (pin9[0] + pin10[0]) / 2
RC_LO = 1.2
h = PITCH / 2
yjog = lo_n0[1] - 0.3
xp = lo_p0[0]                    # LO_P runs straight north from C621
xn = xp - PITCH                  # LO_N jogs east to couple with it
bp_pts = [b_p, (c621[0], b_p[1]), c621]
rbp = 0.4


def bn_path(hb):
    """B_N with an eastward 45-degree bump of height hb on its vertical run (single-ended, before C620)."""
    x = c620[0]
    if hb <= 0:
        return [b_n, (x, b_n[1]), c620], 0.4
    y1, y2 = 49.55, 48.15
    return [b_n, (x, b_n[1]), (x, y1), (x + hb, y1 - hb), (x + hb, y2 + hb), (x, y2), c620], [0.4, 0.12, 0.12, 0.12, 0.12]


n = [lo_n0, (lo_n0[0], yjog), (xn, yjog - (xn - lo_n0[0])), (xn, YL - h), (xd + h, YL - h), (xd + h, pin9[1] - 0.75), pin9]
rn = [0.3, 0.3, RC_LO + h, RC_LO + h, 0.0]
p = [lo_p0, (xp, YL + h), (xd - h, YL + h), (xd - h, pin10[1] - 0.75), pin10]
rp = [RC_LO - h, RC_LO - h, 0.0]
LP = path_length(bp_pts, rbp) + path_length(p, rp)
LNlo = path_length(n, rn)


def skew(hb):
    pts, r = bn_path(hb)
    return LP - (path_length(pts, r) + LNlo)


hb = 0.0
if False and skew(0.0) > 0:   # bump removed by Carter in KiCad (2026-11-15); ~0.1 mm pin-to-pin skew is fine
    lo_, hi_ = 0.0, 0.5
    for _ in range(50):
        mid = (lo_ + hi_) / 2
        lo_, hi_ = (mid, hi_) if skew(mid) > 0 else (lo_, mid)
    hb = (lo_ + hi_) / 2
bn_pts, rbn = bn_path(hb)
R.path("/Synthesizer/RFOUTB_N", bn_pts, W50, r=rbn)
R.path("/Synthesizer/RFOUTB_P", bp_pts, W50, r=rbp)      # passes straight over R615 pad 2
r614 = P("R614", "2")
R.path("/Synthesizer/RFOUTB_N", [(r614[0], b_n[1]), r614], W50)
pts_n = R.path("/Receiver/LO_N", n, WLO, r=rn)
pts_p = R.path("/Receiver/LO_P", p, WLO, r=rp)
fence_jobs.append((pts_n[3:-2], FENCE_LO, (-1,)))   # outer side of each line, from the converged section
fence_jobs.append((pts_p[1:-2], FENCE_LO, (1,)))
xc = (xn + xp) / 2

# ------------------------------------------------------------------ RX: J701 -> balun -> DC blocks -> RFIP/RFIN
j701, t1 = P("J701", "1"), P("T701", "1")
pts = R.path("/Receiver/RX_RF", [(j701[0], j701[1] - 2.2), t1], W50)
fence_jobs.append((pts, FENCE_OFF, (1, -1)))
for bal, cap1, cap2, pin in (("3", "C702", "C702", "22"), ("4", "C703", "C703", "21")):
    tb, c1, c2, dp = P("T701", bal), P(cap1, "1"), P(cap2, "2"), P("DEMOD701", pin)
    netb = B.FindFootprintByReference(cap1).Pads()[0].GetNetname()
    for pd in B.FindFootprintByReference(cap1).Pads():
        if pd.GetNumber() == "1":
            netb = pd.GetNetname()
        else:
            netd = pd.GetNetname()
    jog = c1[0] - tb[0]
    R.path(netb, [tb, (c1[0], tb[1] - abs(jog)), c1], W50)
    jog2 = dp[0] - c2[0]
    R.path(netd, [c2, (c2[0], c2[1] - 0.35), (dp[0], c2[1] - 0.35 - abs(jog2)), dp], W50)

# ------------------------------------------------------------------ DEMOD GND pins -> exposed pad
dm = B.FindFootprintByReference("DEMOD701")
ep = [pd for pd in dm.Pads() if pd.GetNumber() == "25"][0]
ebb = ep.GetBoundingBox()
ex0, ey0 = pcbnew.ToMM(ebb.GetX()) - 20, pcbnew.ToMM(ebb.GetY()) - 20
ex1, ey1 = pcbnew.ToMM(ebb.GetRight()) - 20, pcbnew.ToMM(ebb.GetBottom()) - 20
for pd in dm.Pads():
    if pd.GetNetname() != "GND" or pd.GetNumber().startswith("25"):
        continue
    x, y = pcbnew.ToMM(pd.GetPosition().x) - 20, pcbnew.ToMM(pd.GetPosition().y) - 20
    tx, ty = min(max(x, ex0 + 0.15), ex1 - 0.15), min(max(y, ey0 + 0.15), ey1 - 0.15)
    R.path("GND", [(x, y), (tx, ty)], 0.2)

# ------------------------------------------------------------------ PLL right-side GND pins 9 / 11: own via each
p11 = P("PLL601", "11")
R.path("GND", [p11, (p11[0] + 0.86, p11[1]), (p11[0] + 1.16, p11[1] + 0.3)], 0.25)
R.via("GND", p11[0] + 1.16, p11[1] + 0.3, 0.45, 0.2)
p9 = P("PLL601", "9")
R.path("GND", [(p9[0] + 0.16, p9[1]), (p9[0] + 0.16, p9[1] + 1.15)], 0.25)
R.via("GND", p9[0] + 0.16, p9[1] + 1.15, 0.45, 0.2)

# ------------------------------------------------------------------ +3V3_SYN_RF: west island on L1, L4 link to the east islands
RF = "+3V3_SYN_RF"
p16, r614a, c610, c611, r601 = P("PLL601", "16"), P("R614", "1"), P("C610", "1"), P("C611", "1"), P("R601", "2")
xw = 13.95
R.path(RF, [p16, (xw, p16[1]), (xw, r614a[1])], 0.25, chamfer=0.1)
R.path(RF, [(xw, r614a[1]), r614a], WPWR)
R.path(RF, [r614a, (14.4, r614a[1] - 0.4), (14.4, c611[1]), c611], WPWR, chamfer=0.15)
R.path(RF, [(14.4, c610[1]), c610], WPWR)
R.path(RF, [(14.4, c611[1]), (14.4, r601[1] + 0.35), r601], WPWR, chamfer=0.15)
vW = (14.4, 44.35)
R.via(RF, *vW, 0.45, 0.2)
c602 = P("C602", "1")
vC = (c602[0], c602[1] + 0.75)
R.path(RF, [c602, vC], WPWR)
R.via(RF, *vC, 0.45, 0.2)
r615a, c627 = P("R615", "1"), P("C627", "1")
R.path(RF, [r615a, c627], WPWR)
vE1 = (c627[0], c627[1] + 0.75)
R.path(RF, [c627, vE1], WPWR)
R.via(RF, *vE1, 0.45, 0.2)
r613a, r611a, c626 = P("R613", "1"), P("R611", "1"), P("C626", "1")
R.path(RF, [r613a, (r611a[0] - 0.4, r613a[1]), r611a], WPWR)
R.path(RF, [r611a, c626], WPWR)
vE2 = (c626[0] + 0.75, r613a[1] + 0.05)
R.path(RF, [(r611a[0], r613a[1] + 0.05), vE2], WPWR)
R.via(RF, *vE2, 0.45, 0.2)
xb = 19.4
L4 = pcbnew.B_Cu
R.path(RF, [vW, (vC[0], vW[1]), vC], WPWR, chamfer=0.2, layer=L4)
R.path(RF, [(vC[0], vW[1]), (xb, vW[1] + xb - vC[0]), (xb, vE2[1] - 0.6), vE2], WPWR, chamfer=0.2, layer=L4)
R.path(RF, [(xb, vE1[1]), vE1], WPWR, layer=L4)


# ------------------------------------------------------------------ GND vias at RF-area decaps / terminations
def gnd_via(ref, num="2", d=0.45, drill=0.2, reach=(0.55, 0.7, 0.85)):
    f = B.FindFootprintByReference(ref)
    pd = [q for q in f.Pads() if q.GetNumber() == num][0]
    x, y = pcbnew.ToMM(pd.GetPosition().x) - 20, pcbnew.ToMM(pd.GetPosition().y) - 20
    c = f.GetPosition()
    cx, cy = pcbnew.ToMM(c.x) - 20, pcbnew.ToMM(c.y) - 20
    ux, uy = x - cx, y - cy
    L = math.hypot(ux, uy) or 1.0
    ux, uy = ux / L, uy / L
    dirs = [(ux, uy), (-uy, ux), (uy, -ux), (ux * 0.707 - uy * 0.707, uy * 0.707 + ux * 0.707),
            (ux * 0.707 + uy * 0.707, uy * 0.707 - ux * 0.707)]
    for rch in reach:
        for dx, dy in dirs:
            vx, vy = x + dx * rch, y + dy * rch
            if R.via_ok(vx, vy, d, "GND", 0.2, courtyards=False):
                R.via("GND", vx, vy, d, drill)
                R.path("GND", [(x, y), (vx, vy)], 0.3)
                return True
    print("   no GND via for", ref, num)
    return False


for ref in ("C610", "C611", "C626", "C627", "C602", "C704", "C705", "C706", "C707", "C708", "C709"):
    gnd_via(ref)
gnd_via("R612")
gnd_via("R702")
gnd_via("T701", "2")
gnd_via("T701", "5")

# ------------------------------------------------------------------ fences
nf = 0
for pts, off, sides in fence_jobs:
    nf += R.fence(pts, off, pitch=0.9, sides=sides)
print(f"fence vias: {nf}")
for k in sorted(R.length):
    if any(t in k for t in ("RFOUT", "TX_RF", "MON_RF", "LO_", "RX_", "DEMOD_RF")):
        print(f"  {k:28s} {R.length[k]:6.2f} mm")
tn = R.length["/Synthesizer/RFOUTB_N"] + R.length["/Receiver/LO_N"]
tp = R.length["/Synthesizer/RFOUTB_P"] + R.length["/Receiver/LO_P"]
stub = math.dist((P("R614", "2")[0], P("PLL601", "15")[1]), P("R614", "2"))
print(f"  B_N bump height {hb:.3f} mm")
print(f"  LO pin-to-pin (R614 stub {stub:.2f} excluded)  N {tn - stub:.3f}  P {tp:.3f}  skew {tp - tn + stub:+.3f} mm"
      f"  (pair centre after jog x = {xc:.3f})")
B.Save(DST)
