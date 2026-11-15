"""Hand routes at the MAX2871's 0.5 mm-pitch supply / ground pins that the grid router cannot fit.

Usage: python3 fix_pll.py <in.kicad_pcb> <out.kicad_pcb>

- VCC_PLL (pin 10): 45-degree escape down the slot between the PLL and the TX turn to C609 (pad 1 on top).
- VCC_DIG (pin 28): west, then north into C608 pad 1; C617 moves 0.55 mm down so REF_IN enters it with a 45-degree jog.
- GND_DIG / GND_SD (pins 27 / 31): own via each just off the pin (Fine-pitch IC escape rule, 0.15 mm in the courtyard).
- LD / RFOUT_EN (pins 25 / 26): short escapes north; the router finishes them.
"""
import math
import sys

import pcbnew

sys.path.insert(0, "/home/eon/Formula/CWRadar/.redraw-work")
from route_lib import Router, V  # noqa: E402

SRC, DST = sys.argv[1], sys.argv[2]
B = pcbnew.LoadBoard(SRC)


def loc(v):
    return pcbnew.ToMM(v.x) - 20, pcbnew.ToMM(v.y) - 20


# C617 down so REF_IN jogs into it and VCC_DIG can run west at y = 51.25
c617 = B.FindFootprintByReference("C617")
c617.SetPosition(V(6.95, 52.0))
# vias to drop (TX west-fence vias in the slot, redundant second pin-9 via); removed last, because
# BOARD.Remove() in KiCad 10.0.7 Python leaves later SWIG lookups returning bare pointers
kill = [(14.805, 54.472), (14.805, 53.572), (13.884, 53.571)]
doomed = [t for t in B.GetTracks()
          if t.GetClass() == "PCB_VIA" and any(math.dist(loc(t.GetPosition()), k) < 0.05 for k in kill)]
R = Router(B, 92.0, 66.0, 4.0)
P = R.pad
# VCC_PLL
p10 = P("PLL601", "10")
c609 = P("C609", "1")
R.path("+3V3_SYN_PLL", [p10, (14.0, p10[1]), (14.4, p10[1] + 0.4), (14.4, c609[1] - 0.27), (14.13, c609[1]), c609], 0.2)
# VCC_DIG
p28, c608 = P("PLL601", "28"), P("C608", "1")
R.path("+3V3_SYN_DIG", [p28, (7.3, p28[1]), (7.05, p28[1] - 0.25), (7.05, c608[1] + 0.1), c608], 0.2)
# REF_IN -> C617 pad 2, C617 pad 1 -> TCXO OUT (pin 3)
p29, c617b, c617a, y3 = P("PLL601", "29"), P("C617", "2"), P("C617", "1"), P("Y601", "3")
R.path("/Synthesizer/REF_IN", [p29, (c617b[0] + (c617b[1] - p29[1]), p29[1]), c617b], 0.2)
d = c617a[1] - y3[1]
R.path("/Synthesizer/REF_25M", [c617a, (c617a[0] - d, y3[1]), y3], 0.2)
# GND_DIG (27) / GND_SD (31)
for pin in ("27", "31"):
    q = P("PLL601", pin)
    R.path("GND", [q, (7.75, q[1])], 0.2)
    R.via("GND", 7.75, q[1], 0.45, 0.2)
# LD (25), RFOUT_EN (26) escapes north
p25, p26 = P("PLL601", "25"), P("PLL601", "26")
R.path("/Synthesizer/SYN_LD", [p25, (8.1, p25[1]), (8.1, 48.4)], 0.2, chamfer=0.15)
R.path("/Synthesizer/SYN_RFOUT_EN", [p26, (7.95, p26[1]), (7.65, p26[1] - 0.3), (7.65, 48.4)], 0.2)
for t in doomed:
    B.Remove(t)
B.Save(DST)
print("ok, removed", len(doomed))
