"""Tie isolated SMD GND pads to the nearest GND via with a short checked trace (straight or one 45-degree bend).

Usage: python3 gnd_tie.py <in.kicad_pcb> <out.kicad_pcb> REF:PAD [REF:PAD ...]
"""
import math
import sys

import pcbnew

sys.path.insert(0, "/home/eon/Formula/CWRadar/.redraw-work")
import fix_corners_lib as fc  # noqa: E402

SRC, DST = sys.argv[1], sys.argv[2]
B = pcbnew.LoadBoard(SRC)
fc.init(B)
TO, mm = pcbnew.ToMM, pcbnew.FromMM
gvias = [(TO(t.GetPosition().x), TO(t.GetPosition().y)) for t in B.GetTracks() if t.GetClass() == "PCB_VIA" and t.GetNetname() == "GND"]
gnd = B.FindNet("GND")
for spec in sys.argv[3:]:
    ref, num = spec.split(":")
    f = B.FindFootprintByReference(ref)
    p = [q for q in f.Pads() if q.GetNumber() == num][0]
    P = (TO(p.GetPosition().x), TO(p.GetPosition().y))
    done = False
    for vx, vy in sorted(gvias, key=lambda v: math.dist(v, P))[:12]:
        dx, dy = vx - P[0], vy - P[1]
        cands = [[P, (vx, vy)]]
        m = min(abs(dx), abs(dy))
        cands.append([P, (P[0] + math.copysign(m, dx), P[1] + math.copysign(m, dy)), (vx, vy)])   # 45 first
        cands.append([P, (vx - math.copysign(m, dx), vy - math.copysign(m, dy)), (vx, vy)])       # 45 last
        for pts in cands:
            for layer in (pcbnew.F_Cu,):
                if all(fc.seg_ok("GND", layer, a, b, 0.25, 0.15) for a, b in zip(pts[:-1], pts[1:])):
                    for a, b in zip(pts[:-1], pts[1:]):
                        if math.dist(a, b) < 1e-4:
                            continue
                        t = pcbnew.PCB_TRACK(B)
                        t.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1])))
                        t.SetEnd(pcbnew.VECTOR2I(mm(b[0]), mm(b[1])))
                        t.SetWidth(mm(0.25))
                        t.SetLayer(layer)
                        t.SetNet(gnd)
                        B.Add(t)
                        fc.tracks.append(t)
                    print(f"{spec}: tied to GND via at ({vx - 20:.2f}, {vy - 20:.2f}), {sum(math.dist(a, b) for a, b in zip(pts[:-1], pts[1:])):.2f} mm")
                    done = True
                    break
            if done:
                break
        if done:
            break
    if not done:
        print(f"{spec}: no clear path to a nearby GND via")
B.Save(DST)
