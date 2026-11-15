"""Placement for the CWRadar front-end board (no routing).

Usage: python3 place_layout.py <in.kicad_pcb> <out.kicad_pcb>

Board 92 x 66 mm (4 mm corner radii), 4 layers (JLC04161H-7628), sig/GND/GND/sig: L2 + L3 solid GND,
L1 + L4 GND-poured. Bottom long edge: TX (J601, left end), MON (J602), RX (J701, right end). Top long edge: USB-C.

Floorplan: the LO pair runs along a guard lane at y = YL (16 mm above the PLL) and splits the board.
- Dirty half (above YL): ESP32 top-left (antenna past the top edge, short SPI down to the PLL), J501 under it,
  USB-C + charger + both bucks top-centre, J201/J203/J301 on the top edge, LDO306, buttons, SW301 on the right edge.
- Clean half (below YL): PLL + TCXO + LDO305 left, Q chain + ADC + LDO304 + I filter op-amp centre,
  DEMOD + LDO303 + I in-amp right. Only +VPRE, +3V3_D and the I2S lines cross the lane (on L4, under L2/L3).
- zone_of() keeps every auto-placed passive in its own half. check_layout.py reports the aggressor/victim gaps.

RF core
- PLL601 (MAX2871) rot 90: its RF side faces +x. Right side, top to bottom: VCC_RF, B_N, B_P, A_N, A_P.
  A_P -> C619 -> straight down to TX (turn at x = TX_X). A_N -> C618 -> MON (to the right, under the LO pair).
  B pair -> C620/C621 -> up, then east along y ~57.5 to DEMOD701. No crossings with the existing nets.
- DEMOD701 (ADL5380) rot 180: RF pins face the RX SMA (balun T701 directly below), LO pins on top,
  I outputs on the right side (I chain above-right), Q outputs on the left (Q chain bottom-middle).
  LO_N (from B_N) lands on LOIP pin 9, LO_P on LOIN pin 10 with no crossing, as in the schematic.
- Loop filter: CP-node parts (C622, R616, C623) near CP_OUT (bottom side), R617/C624 at TUNE (top side).
  The CP node runs on L4 under the PLL (L2 shields it from the RF lines).

Everything that is not hand-placed is packed by `autoplace`: the part goes as close as possible to the
pad it connects to (decaps to their IC supply pin first), on a 0.1 mm occupancy grid using courtyards.
"""
import math
import sys

import numpy as np
import pcbnew

SRC, DST = sys.argv[1], sys.argv[2]
OX, OY = 20.0, 20.0           # board origin on the page (mm)
W, H = 92.0, 66.0
RC = 4.0                      # corner radius, concentric with the M3 holes at (4, 4) from each corner
XS = W - 100.0                # right-side anchors are written for W = 100 and shifted by XS
YM = H - 74.0                 # middle-band anchors are written for H = 74 and shifted by YM
YB = H - 80.0                 # bottom-band coordinates below are written for H = 80 and shifted by YB
EDGE_KEEP = 0.4               # courtyard to board edge


def strip_board_items(src):
    """Copy of `src` without board-level zones and Edge.Cuts graphics. Removing zones through the
    KiCad 10.0.7 Python API (BOARD.Remove) corrupts the SWIG type table, so it is done on the text."""
    import tempfile
    t = open(src, encoding="utf-8").read()
    out, i, n = [], 0, len(t)
    while i < n:
        j = t.find("\n\t(", i)
        if j < 0:
            out.append(t[i:])
            break
        out.append(t[i:j + 1])
        k, depth = j + 2, 0          # k at the "(" of a top-level item
        m = k
        while True:
            c = t[m]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            elif c == '"':
                m += 1
                while t[m] != '"':
                    m += 2 if t[m] == "\\" else 1
            m += 1
        item = t[k:m + 1]
        head = item[:40]
        drop = head.startswith("(zone") or (head.startswith(("(gr_rect", "(gr_line", "(gr_arc", "(gr_poly"))
                                             and '(layer "Edge.Cuts")' in item)
        if not drop:
            out.append("\t" + item)
        i = m + 1
    fd, tmp = tempfile.mkstemp(suffix=".kicad_pcb")
    with open(fd, "w", encoding="utf-8") as fh:
        fh.write("".join(out))
    return tmp


B = pcbnew.LoadBoard(strip_board_items(SRC))
GND_NET = B.FindNet("GND")    # look up before any zone removal (SWIG loses the type afterwards)
mm = pcbnew.FromMM


def fp(ref):
    f = B.FindFootprintByReference(ref)
    assert f is not None, ref
    return f


def V(x, y):
    return pcbnew.VECTOR2I(mm(OX + x), mm(OY + y))


def loc(v):
    return pcbnew.ToMM(v.x) - OX, pcbnew.ToMM(v.y) - OY


# ------------------------------------------------------------------ Y601 (new TCXO footprint)
def ensure_y601():
    if B.FindFootprintByReference("Y601"):
        return
    f = pcbnew.FootprintLoad("/usr/share/kicad/footprints/Crystal.pretty", "Crystal_SMD_3225-4Pin_3.2x2.5mm")
    f.SetReference("Y601")
    f.SetValue("25MHz")
    f.SetPath(pcbnew.KIID_PATH("/6d1c5a0e-3f7b-4c2a-9a51-5b0f2e8c6006/4a7b60af-a36e-533f-ba73-0ec2bbbb6563"))
    f.SetSheetname("/Synthesizer/")
    f.SetSheetfile("synthesizer.kicad_sch")
    f.SetFPIDAsString("Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm")
    nets = {"1": "unconnected-(Y601-NC-Pad1)", "2": "GND", "3": "/Synthesizer/REF_25M", "4": "+3V3_SYN_REF"}
    for k, v in {"Datasheet": "https://www.ctscorp.com/Files/DataSheets/Passives/FCP/TCXO/TCXO-525-datasheet.pdf",
                 "Description": "25 MHz TCXO, +/-1 ppm, 3.3 V, clipped sine, 3.2x2.5 mm (pin 1 VC/NC, 2 GND, 3 OUT, 4 VCC)",
                 "Manufacturer": "CTS-Frequency Controls", "Mfg Part #": "525L25010ITR",
                 "Distributor Link 1": "https://www.digikey.com/en/products/detail/cts-frequency-controls/525L25010ITR/16365180",
                 "Distributor Link 2": "", "LCSC": ""}.items():
        if f.HasField(k):
            f.GetField(k).SetText(v)
        else:
            fld = pcbnew.PCB_FIELD(f, f.GetNextFieldOrdinal(), k)
            fld.SetText(v)
            fld.SetVisible(False)
            fld.SetLayer(pcbnew.F_Fab)
            f.Add(fld)
    B.Add(f)
    for p in f.Pads():
        name = nets[p.GetNumber()]
        ni = B.FindNet(name)
        if ni is None:
            ni = pcbnew.NETINFO_ITEM(B, name)
            B.Add(ni)
        p.SetNet(ni)


ensure_y601()
# start every footprint on the top side (frames are measured on F.CrtYd; put(back=True) flips explicitly)
for _f in B.GetFootprints():
    if _f.IsFlipped():
        _f.Flip(_f.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)

# ------------------------------------------------------------------ outline
def edge_seg(a, b, mid=None):
    sh = pcbnew.PCB_SHAPE(B)
    sh.SetLayer(pcbnew.Edge_Cuts)
    sh.SetWidth(mm(0.1))
    if mid is None:
        sh.SetShape(pcbnew.SHAPE_T_SEGMENT)
        sh.SetStart(V(*a))
        sh.SetEnd(V(*b))
    else:
        sh.SetShape(pcbnew.SHAPE_T_ARC)
        sh.SetArcGeometry(V(*a), V(*mid), V(*b))
    B.Add(sh)


k = RC * (1 - math.sqrt(0.5))   # arc midpoint offset from the corner
edge_seg((RC, 0), (W - RC, 0))
edge_seg((W - RC, 0), (W, RC), (W - k, k))
edge_seg((W, RC), (W, H - RC))
edge_seg((W, H - RC), (W - RC, H), (W - k, H - k))
edge_seg((W - RC, H), (RC, H))
edge_seg((RC, H), (0, H - RC), (k, H - k))
edge_seg((0, H - RC), (0, RC))
edge_seg((0, RC), (RC, 0), (k, k))

# ------------------------------------------------------------------ occupancy grid
G = 0.1
NX, NY = int(round(W / G)), int(round(H / G))
occ = np.zeros((NY, NX), dtype=np.int32)
sat = None


def rebuild():
    global sat
    sat = np.zeros((NY + 1, NX + 1), dtype=np.int64)
    sat[1:, 1:] = occ.cumsum(0).cumsum(1)


def gi(x0, y0, x1, y1):
    return (max(0, int(math.floor(x0 / G))), max(0, int(math.floor(y0 / G))),
            min(NX, int(math.ceil(x1 / G))), min(NY, int(math.ceil(y1 / G))))


def mark(rect):
    a, b, c, d = gi(*rect)
    if c > a and d > b:
        occ[b:d, a:c] = 1


def is_free(rect):
    x0, y0, x1, y1 = rect
    if x0 < EDGE_KEEP or y0 < EDGE_KEEP or x1 > W - EDGE_KEEP or y1 > H - EDGE_KEEP:
        return False
    a, b, c, d = gi(*rect)
    return sat[d, c] - sat[b, c] - sat[d, a] + sat[b, a] == 0


def rot_rect(r, deg):
    x0, y0, x1, y1 = r
    deg %= 360
    if deg == 0:
        return r
    if deg == 90:
        return (y0, -x1, y1, -x0)
    if deg == 180:
        return (-x1, -y1, -x0, -y0)
    return (-y1, x0, -y0, x1)


def rot_vec(v, deg):
    x, y = v
    deg %= 360
    return {0: (x, y), 90: (y, -x), 180: (-x, -y), 270: (-y, x)}[deg]


CY0, PAD0 = {}, {}


def frame(ref):
    """Courtyard rect and pad offsets at rot 0 (mm, relative to the footprint origin)."""
    if ref in CY0:
        return CY0[ref], PAD0[ref]
    f = fp(ref)
    o = f.GetOrientationDegrees()
    f.SetOrientationDegrees(0)
    f.BuildCourtyardCaches()   # the cache is built at load time, i.e. at the loaded orientation
    c = f.GetPosition()
    cy = f.GetCourtyard(pcbnew.B_CrtYd if f.IsFlipped() else pcbnew.F_CrtYd)
    bb = cy.BBox() if cy.OutlineCount() else f.GetBoundingBox(False)
    rect = tuple(pcbnew.ToMM(v) for v in (bb.GetX() - c.x, bb.GetY() - c.y, bb.GetRight() - c.x, bb.GetBottom() - c.y))
    if ref == "MCU401":   # module body only: its antenna keep-out lies past the board edge
        rect = (-9.7, -12.9, 9.7, 13.7)
    pads = {}
    for p in f.Pads():
        pads.setdefault(p.GetNumber(), []).append((pcbnew.ToMM(p.GetPosition().x - c.x), pcbnew.ToMM(p.GetPosition().y - c.y)))
    f.SetOrientationDegrees(o)
    f.BuildCourtyardCaches()
    CY0[ref], PAD0[ref] = rect, pads
    return rect, pads


PLACED = {}
INFL = 0.1


def put(ref, x, y, rot=0.0, reserve=True, back=False):
    f = fp(ref)
    rect, _ = frame(ref)
    if f.IsFlipped() != back:
        f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
    f.SetOrientationDegrees(rot)
    f.SetPosition(V(x, y))
    if back:
        reserve = False   # occupancy grid covers the top side only
    rr = rot_rect(rect, int(round(rot)) % 360)
    PLACED[ref] = (x, y, rot)
    if reserve:
        mark((x + rr[0] - INFL, y + rr[1] - INFL, x + rr[2] + INFL, y + rr[3] + INFL))


DIRS = {"R": 0, "U": 90, "L": 180, "D": 270}


def two(ref, x, y, d):
    """2-pad part centred at (x, y); d = direction from pad 1 to pad 2."""
    put(ref, x, y, DIRS[d])


def put_c(ref, cx, cy, rot=0):
    """Place so the courtyard centre lands on (cx, cy)."""
    rect, _ = frame(ref)
    rr = rot_rect(rect, rot)
    put(ref, cx - (rr[0] + rr[2]) / 2, cy - (rr[1] + rr[3]) / 2, rot)


def pad_xy(ref, num):
    f = fp(ref)
    for p in f.Pads():
        if p.GetNumber() == num:
            return loc(p.GetPosition())
    raise KeyError((ref, num))


def reserve(x0, y0, x1, y1):
    mark((x0, y0, x1, y1))


TOP_SHEETS = {"/Battery_Charger/", "/MCU/", "/User_IO/"}
CLEAN_SHEETS = {"/Synthesizer/", "/Receiver/", "/Baseband_I/", "/Baseband_Q/", "/ADC/"}
CLEAN_REGS = {"LDO303", "C313", "C314", "C315", "C316", "C317", "R310", "R311", "TP302", "TP303",
              "LDO304", "C318", "C319", "C320", "C321", "C322", "R312", "R313", "TP304", "TP305",
              "LDO305", "C323", "C324", "C325", "C326", "C327", "TP306", "TP307"}


def zone_of(ref):
    """'top' = digital/power half above the LO guard lane, 'clean' = RF/analog half below it."""
    sh = fp(ref).GetSheetname()
    if sh in TOP_SHEETS:
        return "top"
    if sh in CLEAN_SHEETS:
        return "clean"
    if sh == "/Regulators/":
        return "clean" if ref in CLEAN_REGS else "top"
    return None


def autoplace(ref, tx, ty, padnum=None, rots=(0, 90, 180, 270), maxr=30.0):
    """Place `ref` at the free spot where pad `padnum` (or the centre) is nearest to (tx, ty).
    Vectorised: for each rotation, every grid position is tested at once with the summed-area table."""
    rect, pads = frame(ref)
    po = pads[padnum][0] if padnum else ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)
    best = None
    for r in rots:
        rr = rot_rect(rect, r)
        x0, y0, x1, y1 = rr[0] - INFL, rr[1] - INFL, rr[2] + INFL, rr[3] + INFL
        w = int(math.ceil((x1 - x0) / G)); h = int(math.ceil((y1 - y0) / G))
        lo_i = int(math.ceil(EDGE_KEEP / G)); lo_j = lo_i
        hi_i = NX - lo_i - w; hi_j = NY - lo_j - h
        if hi_i < lo_i or hi_j < lo_j:
            continue
        S = sat
        win = (S[lo_j + h:hi_j + h + 1, lo_i + w:hi_i + w + 1] - S[lo_j:hi_j + 1, lo_i + w:hi_i + w + 1]
               - S[lo_j + h:hi_j + h + 1, lo_i:hi_i + 1] + S[lo_j:hi_j + 1, lo_i:hi_i + 1])
        jj, ii = np.nonzero(win == 0)
        if not len(ii):
            continue
        cx = (ii + lo_i) * G - x0
        cy = (jj + lo_j) * G - y0
        zn = zone_of(ref)
        if zn == "top":                       # aggressor half: whole box above the LO guard lane
            keep = cy + y1 <= YL - 1.6
        elif zn == "clean":                   # RF / analog half: whole box below it
            keep = cy + y0 >= YL + 1.6
        else:
            keep = np.ones_like(cx, dtype=bool)
        if not keep.any():
            continue
        cx, cy = cx[keep], cy[keep]
        pv = rot_vec(po, r)
        d = np.hypot(cx + pv[0] - tx, cy + pv[1] - ty)
        k = int(np.argmin(d))
        if d[k] <= maxr and (best is None or d[k] < best[0] - 1e-9):
            best = (float(d[k]), r, float(cx[k]), float(cy[k]))
    if best is None:
        print("  !! no room for", ref)
        return False
    _, r, x, y = best
    put(ref, round(x, 2), round(y, 2), r)
    rebuild()
    return True


# ------------------------------------------------------------------ net helpers
_NETS = {}


def nets_of(ref):
    if ref not in _NETS:
        _NETS[ref] = {p.GetNumber(): p.GetNetname() for p in fp(ref).Pads() if p.GetNumber()}
    return _NETS[ref]


def sheet(ref):
    return fp(ref).GetSheetname()


RAIL_SKIP = {"GND", ""}

# ================================================================== hand placement
# mounting holes, fiducials
for ref, x, y in (("MH1101", 4, 4), ("MH1102", W - 4, 4), ("MH1103", 4, H - 4), ("MH1104", W - 4, H - 4)):
    put(ref, x, y)
for ref, x, y in (("FID1101", 42.5, 1.8), ("FID1102", 68.0, 1.8), ("FID1103", 1.6, 32.4)):
    put(ref, x, y)

# --- RF core (see module docstring). Right-side PLL pins at x = XP + 2.44:
#     VCC_RF YP-1.75, B_N YP-1.25, B_P YP-0.75, A_N YP-0.25, A_P YP+0.25
SMA_Y = H - 4.76                     # SMA flange on the bottom edge (frame x = -4.76)
XP, YP = 11.0, H - 14.5
YL = YP - 16.0                       # LO guard lane centre: aggressors above, RF/analog below
put("PLL601", XP, YP, 90)
TX_X = 15.45                          # A_P turn: leaves a ~1 mm slot at the PLL for VCC_PLL + GND_PLL/GND_RF vias
put("J601", TX_X, SMA_Y, 90)          # TX: centre pad straight under A_P's turn
put("J602", 27.75, SMA_Y, 90)        # MON
XD, YD = 85.5 + XS, H - 15.0
put("DEMOD701", XD, YD, 180)
put("T701", XD, YD + 6.2, 180)       # balanced pins up (to C702/C703), unbalanced pin 1 down to J701
put("J701", XD + 0.9, SMA_Y, 90)     # RX: centre pad straight under balun pin 1
two("C702", XD + 0.6, YD + 3.65, "U")
two("C703", XD - 0.6, YD + 3.65, "U")

# A pair: A_P turns down at x 14.45 to TX through C619; A_N runs east to MON through C618.
#   R613 (A_P) and R611 (A_N) pull-ups share a rail end decoupled by C626 (schematic note).
two("C619", TX_X, YP + 4.0, "D")
two("R613", TX_X + 0.8, YP + 1.4, "U")
two("R611", TX_X + 2.0, YP + 1.0, "U")
two("C626", TX_X + 2.0, YP + 2.9, "D")
two("C618", TX_X + 5.05, YP - 0.25, "R")
# B pair -> LO: B_N turns north at x ~15.4, B_P at ~15.8 (coupled 100R pair), DC blocks side by side.
#   R614 (B_N) taps from the west next to VCC_RF; R615 (B_P) from the east; C627 at R615's rail end,
#   C610 (2.2 pF) + C611 (1 uF) on VCC_RF pin 16.
two("R614", 14.6, YP - 2.35, "D")
two("C620", 15.3, YP - 4.5, "U")
two("C621", 16.4, YP - 4.5, "U")
two("R615", 16.95, YP - 1.5, "L")
two("C627", 18.45, YP - 2.2, "U")
two("C610", 13.7, YP - 4.2, "U")
two("R612", 26.55, H - 9.6, "L")     # MON 50R termination at J602 (populate R612 or J602)

# PLL bottom corner: VCC_PLL decap fed down the slot beside the TX turn, CP_OUT C1, VCC_CP decap
two("C609", 13.55, YP + 4.1, "D")    # pad 1 (+3V3_SYN_PLL) at the top, nearest pin 10's trace
two("C622", 12.2, YP + 4.65, "D")    # 0603, pad 1 (CP_OUT) at the top under pin 7
two("C607", 10.95, YP + 4.1, "D")    # VCC_CP (pin 6)

# reference: TCXO OUT (pin 3, top-right) -> C617 -> REF_IN (left side, YP+0.25)
put("Y601", 3.8, YP, 0)
two("C617", 6.95, YP - 0.05, "R")

# ADL5380 at rot 180, pins: right side x XD+1.94 (VCC1 YD-1.25, GND, ILO YD-0.25, IHI YD+0.25, GND, GND),
#   left side x XD-1.94 (VCC2 YD-1.25, GND, QLO YD-0.25, QHI YD+0.25, GND, GND), top y YD-1.94 (ENBL XD+1.25,
#   GND, LOIP XD+0.25, LOIN XD-0.25, GND, NC), bottom y YD+1.94 (ADJ XD-1.25, GND, RFIN XD-0.25, RFIP XD+0.25,
#   GND, VCC3 XD+1.25). Decaps go diagonally off the supply corners so I/Q exits and the LO/RF entries stay clear.
two("C704", XD + 3.62, YD - 1.4, "R")    # VCC1: 100 pF closest
two("C705", XD + 3.62, YD - 2.55, "R")    #       100 nF
two("C706", XD - 3.62, YD - 1.4, "L")    # VCC2
two("C707", XD - 3.62, YD - 2.55, "L")
two("C708", XD + 3.15, YD + 3.0, "D")    # VCC3 (bottom right, beside C702)
two("C709", XD + 4.25, YD + 3.0, "D")
two("R702", XD + 1.6, YD - 3.62, "U")     # ENBL -> GND (0R)
two("R703", XD - 1.75, YD + 3.62, "U")    # ADJ (DNP above 5 GHz)
two("R704", XD + 3.2, YD, "U")           # I diff load (DNP) across IHI/ILO
two("R705", XD - 3.2, YD, "D")           # Q diff load (DNP) across QHI/QLO

# --- RF corridors (kept free of other parts; widths include gaps and fence vias)
reserve(TX_X - 0.85, YP - 0.3, TX_X + 0.3, H - 7.0)  # TX
reserve(13.5, YP - 0.9, 27.6, YP + 0.4)          # MON east
reserve(26.9, YP - 0.5, 28.6, H - 7.0)           # MON down to J602
reserve(13.5, YP - 1.6, 16.0, YP - 0.5)          # LO leaving the pins
reserve(14.8, YL - 1.4, 17.0, YP - 1.6)          # LO north through C620/C621 to the guard lane
reserve(14.8, YL - 1.4, XD + 1.3, YL + 1.4)      # LO east along the guard lane (dirty half above, clean below)
reserve(XD - 1.1, YL - 1.4, XD + 1.1, YD - 1.9)  # LO down into DEMOD (top pins)
reserve(XD - 1.3, YD + 2.0, XD + 1.5, H - 7.0)    # RX: C702/C703, balun, J701 launch
reserve(TX_X + 1.05, YP + 0.45, 26.85, H - 7.0)  # TX-MON gap: GND pour + fence vias only
reserve(XD + 4.7, YD - 6.0, XD + 6.1, YD + 0.7)  # I outputs: east past R704, then north to INA801
reserve(58.0, YD - 0.7, XD - 3.8, YD + 0.7)      # Q outputs west to INA901

# --- anchors: ICs, connectors, bulky parts
# Dirty half (y < YL): ESP32 top-left (short SPI to the PLL, antenna past the top edge), USB-C + charger +
# bucks top-centre, connectors/buttons top-right. Clean half (y > YL): PLL/TCXO/LDO305 left, Q chain + ADC +
# LDO304 + I filters centre, DEMOD + LDO303 + I in-amp right.
put("MCU401", 18.5, 6.75, 0)         # antenna end (frame y -12.75..-6.75) past the top edge


def usb_edge_offset():
    """Distance from the USB footprint origin to its front face (opening side), rot 0 frame."""
    rect, _ = frame("USB201")
    return rect[3]


put("USB201", 33.5, usb_edge_offset() - 0.6, 180)   # opening faces up, front 0.6 mm past the edge
put_c("CHG201", 41.0, 13.0, 0)
put_c("J201", 51.0, 4.2, 0)          # battery (XH-2)
put_c("J203", 59.5, 3.6, 0)          # charger thermistor (PH-2)
put_c("BUCK301", 50.0, 12.0, 0)
put_c("L301", 50.0, 20.0, 0)
put_c("BUCK302", 60.5, 12.0, 0)
put_c("L302", 60.5, 19.0, 0)
put_c("SW301", W - 3.3, 29.0, 90)    # power slide switch on the right edge, near the bucks
put_c("J501", 20.0, 27.4, 90)        # display header, horizontal under the ESP32 (DISP/I2C lines short)
put_c("J301", 77.0, 3.6, 0)          # external LNA supply (PH-2), top edge
put_c("LDO306", 75.0, 12.0, 0)       # +V_LNA, next to J301
put_c("LDO305", 7.5, 41.5, 0)        # +3V3_SYN, above the synthesizer, west of the LO riser
put_c("LDO304", 45.5, 44.5, 0)       # +5V_A (baseband + ADC)
put_c("ADC1001", 60.0, 46.5, 0)
put_c("OPA801", 70.5, 45.0, 0)       # I filters (west of the LO descent; INA801 output crosses on L4)
put_c("INA801", 86.6, 42.5, 90)      # I in-amp, east of the LO descent, next to the I outputs
put_c("LDO303", 65.5, 56.5, 0)       # +5V_RF -> R701 -> +5V_DEMOD
put_c("INA901", 50.0, 52.0, 0)       # Q in-amp, at the end of the Q lane
put_c("OPA901", 36.0, 50.0, 0)
rebuild()

# ================================================================== auto placement
ANCHORS = {"PLL601", "DEMOD701", "MCU401", "USB201", "CHG201", "BUCK301", "BUCK302", "LDO303", "LDO304",
           "LDO305", "LDO306", "ADC1001", "INA801", "INA901", "OPA801", "OPA901", "J201", "J203", "J301",
           "J501", "J601", "J602", "J701", "T701", "Y601", "L301", "L302", "SW301"}


def place_near_pad(ref, anchor, net, apad=None, rpad=None):
    """Put `ref`'s pad on `net` (or pad `rpad`) as close as possible to `anchor`'s pad on `net` (or `apad`)."""
    pn = [rpad] if rpad else [n for n, nn in nets_of(ref).items() if nn == net]
    ap = [apad] if apad else [n for n, nn in nets_of(anchor).items() if nn == net]
    if not pn or not ap:
        return False
    tx, ty = pad_xy(anchor, ap[0])
    return autoplace(ref, tx, ty, pn[0])


ALL = [f.GetReference() for f in B.GetFootprints()]
todo = [r for r in ALL if r not in PLACED]

# explicit first-ring targets: (ref, anchor, net) -- decaps on their own supply pins, filter parts on pins
FIRST = [
    # MAX2871: per-pin decaps from the schematic (gen_hier supply table), then filter/bias parts
    ("C608", "PLL601", "+3V3_SYN_DIG", "28"), ("C612", "PLL601", "+3V3_SYN_DIG", "32"),
    ("C613", "PLL601", "+3V3_SYN_VCO", "17"),
    ("C624", "PLL601", "/Synthesizer/TUNE"), ("R617", "PLL601", "/Synthesizer/TUNE"),
    ("C614", "PLL601", "/Synthesizer/NOISE_FILT"), ("C616", "PLL601", "/Synthesizer/BIAS_FILT"),
    ("C615", "PLL601", "/Synthesizer/REG"), ("R610", "PLL601", "/Synthesizer/RSET"),
    ("C611", "PLL601", "+3V3_SYN_RF", "16"), ("R619", "PLL601", "/Synthesizer/TUNE"),
    ("R616", "C622", "/Synthesizer/CP_OUT"),
    ("C623", "R616", "/Synthesizer/LF_C2"),   # 100n C0G 1206 (was a film cap on the back)
    ("R605", "PLL601", "/Synthesizer/SYN_SCK_R"), ("R606", "PLL601", "/Synthesizer/SYN_MOSI_R"),
    ("R607", "PLL601", "/Synthesizer/SYN_LE_R"), ("R608", "PLL601", "/Synthesizer/SYN_CE"),
    ("R609", "PLL601", "/Synthesizer/SYN_RFOUT_EN"),
    ("C604", "Y601", "+3V3_SYN_REF"), ("C605", "Y601", "+3V3_SYN_REF"), ("C606", "Y601", "+3V3_SYN_REF"),
    # ADL5380: 100 pF closest, then 100 nF, per supply pin
    # LDOs: OUT cap, IN cap, NR/SS cap, FB divider
]
for n in (3, 4, 5, 6):
    ldo = f"LDO30{n}"
    out = {3: "+5V_RF", 4: "+5V_A", 5: "+3V3_SYN", 6: "+V_LNA"}[n]
    caps = {3: ("C317", "C313", "C314", "C315", "C316", "R310", "R311"),
            4: ("C322", "C318", "C319", "C320", "C321", "R312", "R313"),
            5: ("C327", "C323", "C324", "C325", "C326", None, None),
            6: ("C332", "C328", "C329", "C330", "C331", "R314", "R315")}[n]
    cout, cin, cin2, cnr, cff, rtop, rbot = caps
    FIRST += [(cin2, ldo, "+VPRE"), (cin, ldo, "+VPRE"), (cout, ldo, out), (cnr, ldo, f"/Regulators/LDO{n}_NR")]
    FIRST += [(cff, ldo, f"/Regulators/LDO{n}_FB")]
    if rtop:
        FIRST += [(rtop, ldo, f"/Regulators/LDO{n}_FB"), (rbot, ldo, f"/Regulators/LDO{n}_FB")]
FIRST += [
    # bucks: 0.1 uF tightest on VIN/GND, then 10 uF, BST, SS, RT, FB divider; output caps at the inductor
    ("C302", "BUCK301", "+VSYS"), ("C301", "BUCK301", "+VSYS"), ("C304", "BUCK301", "/Regulators/BUCK1_BST"),
    ("C303", "BUCK301", "/Regulators/BUCK1_SS"), ("R302", "BUCK301", "/Regulators/BUCK1_RT"),
    ("R304", "BUCK301", "/Regulators/BUCK1_FB"), ("R303", "BUCK301", "/Regulators/BUCK1_FB"),
    ("C305", "L301", "+VPRE"), ("C306", "L301", "+VPRE"),
    ("C308", "BUCK302", "+VSYS"), ("C307", "BUCK302", "+VSYS"), ("C310", "BUCK302", "/Regulators/BUCK2_BST"),
    ("C309", "BUCK302", "/Regulators/BUCK2_SS"), ("R305", "BUCK302", "/Regulators/BUCK2_RT"),
    ("R307", "BUCK302", "/Regulators/BUCK2_FB"), ("R306", "BUCK302", "/Regulators/BUCK2_FB"),
    ("C311", "L302", "+3V3_D"), ("C312", "L302", "+3V3_D"),
    # BQ25883: SYS caps first, PMID, then the rest (SLUSDL3A 11.1)
    ("C204", "CHG201", "+VSYS"), ("C205", "CHG201", "+VSYS"), ("C202", "CHG201", "/Battery_Charger/CHG_PMID"),
    ("L201", "CHG201", "/Battery_Charger/CHG_SW"), ("C203", "CHG201", "/Battery_Charger/CHG_BTST"),
    ("C210", "CHG201", "/Battery_Charger/CHG_REGN"), ("C201", "CHG201", "+VBUS"),
    ("C208", "CHG201", "+VBAT"), ("C209", "CHG201", "+VBAT"), ("C206", "CHG201", "+VSYS"), ("C207", "CHG201", "+VSYS"),
    # PCM1808
    ("C1002", "ADC1001", "+5V_A"), ("C1004", "ADC1001", "+3V3_D"), ("C1006", "ADC1001", "/ADC/ADC_VREF"),
    ("C1001", "ADC1001", "+5V_A"), ("C1003", "ADC1001", "+3V3_D"), ("C1005", "ADC1001", "/ADC/ADC_VREF"),
    ("R1001", "ADC1001", "/ADC/ADC_FMT"), ("R1002", "ADC1001", "/ADC/ADC_DOUT"),
    # baseband op-amps / in-amps
    ("C806", "INA801", "+5V_A"), ("C807", "INA801", "+5V_A"), ("C815", "OPA801", "+5V_A"), ("C816", "OPA801", "+5V_A"),
    ("C906", "INA901", "+5V_A"), ("C907", "INA901", "+5V_A"), ("C915", "OPA901", "+5V_A"), ("C916", "OPA901", "+5V_A"),
    ("R805", "INA801", "/Baseband_I/BB_RG2"), ("R905", "INA901", "/Baseband_Q/BB_RG2"),
    # ESP32
    ("C402", "MCU401", "+3V3_D"), ("C401", "MCU401", "+3V3_D"), ("C403", "MCU401", "/MCU/ESP_EN"),
    ("R401", "MCU401", "/MCU/ESP_EN"), ("R402", "MCU401", "/MCU/ESP_BOOT"),
    ("R403", "MCU401", "/MCU/ESP_DN"), ("R404", "MCU401", "/MCU/ESP_DP"),
    ("R405", "MCU401", "/MCU/ESP_MCLK"), ("R406", "MCU401", "/MCU/ESP_BCK"), ("R407", "MCU401", "/MCU/ESP_LRCK"),
    ("SW401", "MCU401", "/MCU/ESP_EN"), ("SW402", "MCU401", "/MCU/ESP_BOOT"),
    # USB / protection
    ("ESD202", "USB201", "/Battery_Charger/USBC_DP"), ("ESD203", "USB201", "/Battery_Charger/USBC_CC1"),
    ("D204", "USB201", "+VBUS"), ("R201", "USB201", "/Battery_Charger/USB_SHIELD"),
    # battery path
    ("F201", "J201", "/Battery_Charger/BATT_IN"),
    # LNA supply connector
    ("C333", "J301", "/Regulators/LNA_5V"), ("C334", "J301", "/Regulators/LNA_5V"), ("R301", "J301", "/Regulators/LNA_5V"),
    # DEMOD supply
    ("R701", "DEMOD701", "+5V_DEMOD"), ("C701", "DEMOD701", "+5V_DEMOD"),
    # TCXO supply R
    ("R604", "Y601", "+3V3_SYN_REF"),
    # synth branch links + bulk
    ("R601", "C611", "+3V3_SYN_RF"), ("C602", "R601", "+3V3_SYN_RF"),
    ("R602", "C607", "+3V3_SYN_PLL"), ("C603", "R602", "+3V3_SYN_PLL"),
    ("R603", "C608", "+3V3_SYN_DIG"), ("C628", "R603", "+3V3_SYN_DIG"),
    ("R618", "C613", "+3V3_SYN_VCO"), ("C625", "R618", "+3V3_SYN_VCO"),
    # baseband: input film caps at the in-amp inputs, output film caps at the ADC inputs
    ("C801", "INA801", None, "4", "2"), ("C802", "INA801", None, "1", "2"),
    ("C901", "INA901", None, "4", "2"), ("C902", "INA901", None, "1", "2"),
    ("C812", "ADC1001", None, "13", "2"), ("C912", "ADC1001", None, "14", "2"),
    ("C813", "OPA801", "/Baseband_I/VREF"), ("C913", "OPA901", "/Baseband_Q/VREF"),
]
print("first ring:", len(FIRST))
for item in FIRST:
    ref, anchor, net = item[:3]
    apad = item[3] if len(item) > 3 else None
    rpad = item[4] if len(item) > 4 else None
    if ref in PLACED:
        continue
    if not place_near_pad(ref, anchor, net, apad, rpad):
        print("  first-ring miss", item)

# breadth-first: anything sharing a non-GND net with something placed, same sheet first
SHEET = {r: fp(r).GetSheetname() for r in [f.GetReference() for f in B.GetFootprints()]}


FAILED = set()


def bfs_pass(same_sheet=True):
    progress = True
    while progress:
        progress = False
        by_net = {}
        for other in PLACED:
            for onum, onet in nets_of(other).items():
                by_net.setdefault(onet, []).append((other, onum))
        for ref in sorted(r for r in ALL if r not in PLACED and r not in FAILED):
            best = None
            for pnum, net in nets_of(ref).items():
                if net in RAIL_SKIP or net.startswith("unconnected"):
                    continue
                for other, onum in by_net.get(net, []):
                    if same_sheet and SHEET[other] != SHEET[ref]:
                        continue
                    score = (net.startswith("+"), other not in ANCHORS)
                    if best is None or score < best[0]:
                        best = (score, other, onum, pnum)
            if best:
                _, other, onum, pnum = best
                tx, ty = pad_xy(other, onum)
                if not autoplace(ref, tx, ty, pnum, maxr=60.0):
                    FAILED.add(ref)
                    continue
                for onum2, onet2 in nets_of(ref).items():
                    by_net.setdefault(onet2, []).append((ref, onum2))
                progress = True


bfs_pass(True)
bfs_pass(False)
left = [r for r in ALL if r not in PLACED]
print("unplaced after BFS:", left)
for ref in left:   # e.g. test points on GND only: drop near the board centre-left
    autoplace(ref, 50, 30)

# thermal-via PTH pads inside exposed pads (and the module GND pad vias) connect solid; the pours use
# thermal reliefs only for real through-hole parts
for _f in B.GetFootprints():
    for _p in _f.Pads():
        if _p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and _p.GetNetname() == "GND" and \
                pcbnew.ToMM(_p.GetDrillSize().x) <= 0.4:
            _p.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)

# ================================================================== zones: sig/GND/GND/sig
# L2 and L3 are solid GND planes; L1 and L4 get GND pours (power is routed as traces / local fills).
gnd = GND_NET


def add_zone(layer, net, pts, prio=0, name=""):
    z = pcbnew.ZONE(B)
    z.SetLayer(layer)
    z.SetNetCode(net.GetNetCode())
    z.SetAssignedPriority(prio)
    z.SetZoneName(name)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(mm(OX + x), mm(OY + y))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)   # SMD solid (reflow), THT thermal reliefs
    z.SetLocalClearance(mm(0.2))                             # = CPWG gap on the RF lines
    z.SetMinThickness(mm(0.2))
    z.SetThermalReliefGap(mm(0.3))
    z.SetThermalReliefSpokeWidth(mm(0.4))
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)   # no floating copper
    B.Add(z)
    return z


FULL = [(0.3, 0.3), (W - 0.3, 0.3), (W - 0.3, H - 0.3), (0.3, H - 0.3)]
add_zone(pcbnew.In1_Cu, gnd, FULL, 0, "L2_GND")
add_zone(pcbnew.In2_Cu, gnd, FULL, 0, "L3_GND")
add_zone(pcbnew.F_Cu, gnd, FULL, 0, "L1_GND_POUR")
add_zone(pcbnew.B_Cu, gnd, FULL, 0, "L4_GND_POUR")

# SMA launches: L2 cut out under the 2.29 mm centre pad (out to the inner edge of the side GND pads),
# so the pad references the L3 GND plane (~47 ohm) instead of L2 (~13 ohm).
for ref in ("J601", "J602", "J701"):
    x, y, _ = PLACED[ref]
    top = y - 0.82                      # inner end of the centre pad
    k = pcbnew.ZONE(B)
    k.SetIsRuleArea(True)
    k.SetLayer(pcbnew.In1_Cu)
    k.SetDoNotAllowZoneFills(True)
    k.SetDoNotAllowTracks(True)
    k.SetDoNotAllowVias(True)
    k.SetDoNotAllowPads(False)
    k.SetDoNotAllowFootprints(False)
    k.SetZoneName(f"SMA_L2_CUT_{ref}")
    ol = k.Outline()
    ol.NewOutline()
    for px, py in ((x - 3.1, top), (x + 3.1, top), (x + 3.1, H), (x - 3.1, H)):
        ol.Append(mm(OX + px), mm(OY + py))
    B.Add(k)

B.Save(DST)
print("placed", len(PLACED), "of", len(ALL), "->", DST)
