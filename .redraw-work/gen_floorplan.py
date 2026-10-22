"""Floorplan Frontend.kicad_pcb from the schematic netlist: placement only, no routing.

Usage: python3 -I gen_floorplan.py <netlist.xml> <board.kicad_pcb> [--only-new]

Loads the board (with its project), adds footprints for symbols that are missing, sets pad
nets and the symbol links (so "Update PCB from Schematic" adopts them), and moves every
footprint listed in PLACE. With --only-new, footprints already on the board stay where they
are (use this once placement is being tuned by hand in pcbnew).
Coordinates are board-relative mm: u to the right, v down, origin at the top-left corner.
"""
import os
import sys
import xml.etree.ElementTree as ET

import pcbnew

NETLIST, BOARD = sys.argv[1], sys.argv[2]
ONLY_NEW = "--only-new" in sys.argv
ROOT = "/home/eon/Formula/CWRadar"
STD_FP = "/usr/share/kicad/footprints"
X0, Y0, W, H = 100.0, 50.0, 100.0, 75.0  # board outline on the page, mm

mm = pcbnew.FromMM


def P(u, v):
    return pcbnew.VECTOR2I(mm(X0 + u), mm(Y0 + v))


# --------------------------------------------------------------- placement
# ref: (u, v, rotation). Rotation is pcbnew's (counter-clockwise, degrees).
PLACE = {
    # mounting holes
    "MH1101": (4, 4, 0), "MH1102": (96, 4, 0), "MH1103": (4, 71, 0), "MH1104": (96, 71, 0),
    # RF connectors on the top edge: RX top-left, TX top-right, MON (DNP) beside TX.
    # The Molex 73251-1153 board edge sits at local x = -4.76, so v = 4.76 puts it on the edge.
    "J701": (20, 4.76, 270), "J602": (72, 4.76, 270), "J601": (86, 4.76, 270),

    # ---- ADL5380 demodulator (rot 90: RF in on the left, LO in on the right, I down, Q up)
    "DEMOD701": (29, 12, 90),
    "T701": (23, 12, 90),                       # balanced pins 4 (top) / 3 (bottom) face the chip
    "C703": (25.35, 11.1, 0), "C702": (25.35, 12.9, 0),   # DC blocks N / P
    "R703": (25.2, 9.5, 0),                     # ADJ (DNP)
    "C708": (25.3, 14.6, 0), "C709": (25.4, 15.7, 0),     # VCC3
    "C706": (32.2, 9.0, 90), "C707": (33.3, 9.0, 90),     # VCC2
    "C704": (31.5, 15.4, 0), "C705": (31.5, 16.5, 0),     # VCC1
    "R702": (33.0, 14.0, 90),                   # ENBL 0R to GND
    "R704": (29.0, 15.4, 0), "R705": (29.0, 8.6, 0),      # DNP diff loads I / Q
    "TP701": (25.0, 20.0, 0), "TP702": (27.5, 20.0, 0), "TP703": (30.0, 20.0, 0), "TP704": (32.5, 20.0, 0),
    "R701": (37, 14.85, 90), "C701": (37.0, 18.2, 90),   # +5V_DEMOD branch

    # ---- MAX2871 synthesizer (rot 180: RF outputs face the top edge, B pair left, A pair right)
    "PLL601": (62, 17, 180),
    # LO pair (RFOUTB) heads left to the demod: pull-ups, HF cap, DC blocks
    "R615": (58.6, 9.6, 90), "R614": (57.5, 9.6, 90), "C627": (56.3, 9.0, 90),
    "C621": (54.5, 11.1, 0), "C620": (54.5, 12.6, 0),
    # TX/MON pair (RFOUTA) heads right
    "R611": (65.5, 9.6, 90), "R613": (66.6, 9.6, 90), "C626": (67.8, 9.0, 90),
    "C618": (69.5, 11.1, 0), "C619": (69.5, 12.6, 0), "R612": (72.0, 9.9, 90),
    # supply pins
    "C610": (59.85, 13.25, 0), "C611": (57.8, 13.6, 0),     # VCC_RF (16)
    "C609": (64.3, 13.25, 0),                    # VCC_PLL (10)
    "C607": (66.2, 16.15, 0),                    # VCC_CP (6)
    "C608": (62.85, 20.75, 0), "C612": (59.75, 20.75, 0),     # VCC_DIG (28), VCC_SD (32)
    "C613": (57.8, 15.25, 0),                   # VCC_VCO (17)
    "C614": (57.8, 16.3, 0), "R610": (57.8, 17.75, 0),    # NOISE_FILT (19), RSET (22)
    "C616": (56.4, 18.85, 0), "C615": (56.4, 20.2, 0),     # BIAS_FILT (23), REG (24)
    "C617": (61.3, 21.8, 90),                   # REF_IN coupling (29)
    # loop filter: CP_OUT (right side) around the bottom to TUNE (left side)
    "C622": (66.75, 14.9, 0), "R616": (66.5, 18.8, 90), "C623": (69.1, 22.2, 90),
    "R617": (63.0, 25.2, 0), "C624": (55.4, 21.6, 90),
    "R619": (54.0, 23.6, 90), "TP602": (54.0, 26.0, 0),
    # control: CE / RFOUT_EN pull-downs, LD test point
    "R608": (67.6, 17.2, 0), "R609": (64.6, 21.4, 90), "TP601": (66.0, 25.0, 0),
    # synth power branches: 0R links with branch caps above, trunk cap at the left
    "C601": (48.5, 29.5, 90),
    "R601": (52, 29.5, 90), "R618": (55, 29.5, 90), "R602": (58, 29.5, 90), "R603": (61, 29.5, 90),
    "R604": (64, 29.5, 90),
    "C602": (52, 26.8, 90), "C625": (55.65, 26.8, 90), "C603": (58, 26.8, 90), "C628": (61, 26.8, 90),
    "C604": (66.5, 29.5, 90), "C605": (68.5, 29.5, 90), "C606": (70.0, 29.5, 90),
    # SPI series resistors sit at the ESP32 end (MCU zone)
    "R605": (44.0, 37.5, 0), "R606": (44.0, 38.7, 0), "R607": (44.0, 39.9, 0),
}

# future blocks, drawn on Dwgs.User: (u1, v1, u2, v2, label)
ZONES = [
    (0, 0, 100, 34, "RF (5.8 GHz): CPWG on L1 over solid L2 GND"),
    (0, 34, 38, 75, "ANALOG: BASEBAND I/Q + ADC"),
    (38, 34, 64, 75, "MCU: ESP32-S3-WROOM-1"),
    (64, 34, 100, 75, "POWER: USB-C, 2S CHARGER, BUCK, LDOs"),
    (42, 49.5, 60, 75, "WROOM-1 18 x 25.5 (antenna end at board edge)"),
    (58.0, 22.3, 61.0, 24.7, "Y601 TCXO 2520"),
]


# ------------------------------------------------------------------ netlist
def lib_path(lib):
    if lib == "cwradar":
        return f"{ROOT}/library/footprints/cwradar.pretty"
    return f"{STD_FP}/{lib}.pretty"


root = ET.parse(NETLIST).getroot()
comps = {}
for c in root.find("components"):
    props = {p.get("name"): p.get("value") for p in c.findall("property")}
    fl = c.find("fields")
    fields = {f.get("name"): (f.text or "") for f in (list(fl) if fl is not None else [])}
    fields["Datasheet"] = c.findtext("datasheet") or ""
    fields["Description"] = c.findtext("description") or ""
    comps[c.get("ref")] = dict(
        value=c.findtext("value"), fp=c.findtext("footprint") or "",
        path=c.find("sheetpath").get("tstamps") + c.findtext("tstamps"),
        sheetname=props.get("Sheetname", ""), sheetfile=props.get("Sheetfile", ""),
        dnp="dnp" in props, fields=fields)
pad_net = {}
for n in root.find("nets"):
    for node in n.findall("node"):
        pad_net[(node.get("ref"), node.get("pin"))] = n.get("name")

# -------------------------------------------------------------------- board
board = pcbnew.LoadBoard(BOARD)
board.SetCopperLayerCount(4)
ds = board.GetDesignSettings()
ds.m_SolderMaskExpansion = mm(0.05)
ds.m_SolderMaskMinWidth = mm(0.1)

# outline (replaced on every run)
for d in [d for d in board.GetDrawings() if d.GetLayer() in (pcbnew.Edge_Cuts, pcbnew.Dwgs_User)]:
    board.Delete(d)
edge = pcbnew.PCB_SHAPE(board)
edge.SetShape(pcbnew.SHAPE_T_RECT)
edge.SetStart(P(0, 0))
edge.SetEnd(P(W, H))
edge.SetLayer(pcbnew.Edge_Cuts)
edge.SetWidth(mm(0.05))
board.Add(edge)
for u1, v1, u2, v2, label in ZONES:
    r = pcbnew.PCB_SHAPE(board)
    r.SetShape(pcbnew.SHAPE_T_RECT)
    r.SetStart(P(u1, v1))
    r.SetEnd(P(u2, v2))
    r.SetLayer(pcbnew.Dwgs_User)
    r.SetWidth(mm(0.15))
    board.Add(r)
    t = pcbnew.PCB_TEXT(board)
    t.SetText(label)
    t.SetLayer(pcbnew.Dwgs_User)
    t.SetTextSize(pcbnew.VECTOR2I(mm(1.0), mm(1.0)))
    t.SetTextThickness(mm(0.15))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
    t.SetPosition(P(u1 + 0.8, v2 - 1.2 if v1 == 0 else v1 + 1.5))  # RF strip: top edge is full of SMAs
    board.Add(t)

nets = {}


def net(name):
    if name not in nets:
        ni = board.FindNet(name)
        if ni is None:
            ni = pcbnew.NETINFO_ITEM(board, name)
            board.Add(ni)
        nets[name] = ni
    return nets[name]


have = {fp.GetReference(): fp for fp in board.GetFootprints()}
missing_fp, placed, unplaced = [], [], []
for ref, c in sorted(comps.items()):
    if not c["fp"]:
        missing_fp.append(ref)
        continue
    fp = have.get(ref)
    new = fp is None
    if new:
        lib, name = c["fp"].split(":", 1)
        fp = pcbnew.FootprintLoad(lib_path(lib), name)
        if fp is None:
            raise SystemExit(f"{ref}: footprint {c['fp']} not found")
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        board.Add(fp)
    fp.SetReference(ref)
    fp.SetValue(c["value"])
    fp.SetPath(pcbnew.KIID_PATH(c["path"]))
    fp.SetSheetname(c["sheetname"])
    fp.SetSheetfile(c["sheetfile"])
    fp.SetDNP(c["dnp"])
    for k, v in c["fields"].items():
        if k not in ("Footprint", "Value", "Reference"):
            fp.SetField(k, v)
            fp.GetField(k).SetVisible(False)
    if ref.startswith("MH"):
        fp.Reference().SetVisible(False)
    for pad in fp.Pads():
        name = pad_net.get((ref, pad.GetNumber()))
        if name:
            pad.SetNet(net(name))
    for fld in (fp.Reference(), fp.Value()):
        fld.SetTextThickness(max(fld.GetTextThickness(), mm(0.16)))
    if ref in PLACE and (new or not ONLY_NEW):
        u, v, rot = PLACE[ref]
        fp.SetOrientationDegrees(0)
        fp.SetPosition(P(u, v))
        fp.SetOrientationDegrees(rot)
        placed.append(ref)
    elif new:
        unplaced.append(ref)
        fp.SetPosition(P(W + 10, 5 + 3 * len(unplaced)))  # parking lot right of the board

# --------------------------------------------------------------- legalize
# Nudge passives/test points just clear of any courtyard they overlap; ICs, connectors,
# the balun and mounting holes stay where PLACE puts them.
FIXED = ("PLL", "DEMOD", "J", "T", "MH")


def bbox(fp):
    fp.BuildCourtyardCaches()
    cy = fp.GetCourtyard(pcbnew.F_CrtYd)
    return cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False, False)


moved = {}
if not ONLY_NEW:
    fps = [fp for fp in board.GetFootprints() if fp.GetReference() in placed]
    for _ in range(60):
        hit = False
        for i, a in enumerate(fps):
            for b in fps[i + 1:]:
                ba, bb = bbox(a), bbox(b)
                if not ba.Intersects(bb):
                    continue
                ma = not a.GetReference().startswith(FIXED)
                mb = not b.GetReference().startswith(FIXED)
                if not (ma or mb):
                    continue
                mv, other = (b, a) if mb and (not ma or bbox(b).GetArea() <= ba.GetArea()) else (a, b)
                bm, bo = bbox(mv), bbox(other)
                ox = min(bm.GetRight(), bo.GetRight()) - max(bm.GetLeft(), bo.GetLeft())
                oy = min(bm.GetBottom(), bo.GetBottom()) - max(bm.GetTop(), bo.GetTop())
                c_m, c_o = bm.GetCenter(), bo.GetCenter()
                step = mm(0.05)
                if ox <= oy:
                    d = pcbnew.VECTOR2I(ox + step if c_m.x >= c_o.x else -(ox + step), 0)
                else:
                    d = pcbnew.VECTOR2I(0, oy + step if c_m.y >= c_o.y else -(oy + step))
                mv.Move(d)
                r = mv.GetReference()
                acc = moved.get(r, (0, 0))
                moved[r] = (acc[0] + pcbnew.ToMM(d.x), acc[1] + pcbnew.ToMM(d.y))
                hit = True
        if not hit:
            break

board.Save(BOARD)
print(f"placed {len(placed)}, parked off-board {unplaced}, no footprint {missing_fp}")
if moved:
    print("nudged (du, dv mm):", {k: (round(x, 2), round(y, 2)) for k, (x, y) in sorted(moved.items())})
