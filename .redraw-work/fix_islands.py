"""Stitch isolated GND pour fragments on L1/L4: any filled island without a GND via or PTH GND pad gets a via.

Usage: python3 fix_islands.py <filled.kicad_pcb> <out.kicad_pcb>   (input must have refilled zones)
"""
import sys

import pcbnew

sys.path.insert(0, "/home/eon/Formula/CWRadar/.redraw-work")
from route_lib import Router, OX, OY  # noqa: E402

SRC, DST = sys.argv[1], sys.argv[2]
B = pcbnew.LoadBoard(SRC)
anchors = [t.GetPosition() for t in B.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]
anchors += [p.GetPosition() for f in B.GetFootprints() for p in f.Pads()
            if p.GetNetname() == "GND" and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
islands = []
for z in B.Zones():
    if z.GetIsRuleArea() or z.GetNetname() != "GND" or z.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu):
        continue
    polys = z.GetFilledPolysList(z.GetLayer())
    for k in range(polys.OutlineCount()):
        ol = polys.Outline(k)
        if any(ol.PointInside(a) for a in anchors):
            continue
        bb = ol.BBox()
        islands.append((z.GetLayer(), ol, bb))
R = Router(B, 92.0, 66.0, 4.0, load_existing=True)
fixed = 0
for layer, ol, bb in islands:
    x0, y0 = pcbnew.ToMM(bb.GetX()) - OX, pcbnew.ToMM(bb.GetY()) - OY
    x1, y1 = x0 + pcbnew.ToMM(bb.GetWidth()), y0 + pcbnew.ToMM(bb.GetHeight())
    done = False
    steps = 12
    for i in range(steps + 1):
        for j in range(steps + 1):
            x = x0 + (x1 - x0) * i / steps
            y = y0 + (y1 - y0) * j / steps
            q = pcbnew.VECTOR2I(pcbnew.FromMM(x + OX), pcbnew.FromMM(y + OY))
            if ol.PointInside(q) and R.via_ok(x, y, 0.45, "GND", 0.2, courtyards=False):
                R.via("GND", x, y, 0.45, 0.2)
                fixed += 1
                done = True
                break
        if done:
            break
    if not done:
        print(f"   island on {B.GetLayerName(layer)} near ({(x0 + x1) / 2:.1f}, {(y0 + y1) / 2:.1f}) "
              f"size {x1 - x0:.1f} x {y1 - y0:.1f} mm: no via site (will be removed as an island)")
print(f"GND islands: {len(islands)}, stitched: {fixed}")
B.Save(DST)
