"""Generate Frontend.kicad_sch (MAX2871 synthesizer) in Carter's wired style.

Usage: python3 -I gen_frontend.py <out.kicad_sch>
Reads lib symbols from the backed-up schematic, cwradar.kicad_sym and the
KiCad stock libraries; writes a complete flat A3 sheet.
"""
import json
import math
import re
import sys
import uuid

ROOT = "/home/eon/Formula/CWRadar"
WORK = f"{ROOT}/.redraw-work"
OLD = f"{WORK}/Frontend.pre-redraw.kicad_sch"
STD = "/usr/share/kicad/symbols"
ROOT_UUID = "b0666bf5-aed6-40cf-96a3-97fbd780bef0"
OUTDIR = sys.argv[1]
CWLIB = sys.argv[2] if len(sys.argv) > 2 else f"{ROOT}/library/symbols/cwradar.kicad_sym"
SYN_SHEET = "6d1c5a0e-3f7b-4c2a-9a51-5b0f2e8c6006"
BASE = [600]  # refdes block of the sheet being drawn (sheet number x 100)


def renum(ref):
    m = re.fullmatch(r"([A-Z]+)(\d+)", ref)
    return f"{m.group(1)}{BASE[0] + int(m.group(2))}"


UCTX = ["root", 0]  # deterministic UUIDs: (file, counter); symbols are keyed by ref instead


def U():
    UCTX[1] += 1
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"cwradar/{UCTX[0]}/{UCTX[1]}"))


def f(v):
    v = round(v, 4)
    return str(int(v)) if v == int(v) else f"{v:g}"


# ---------------------------------------------------------------- lib symbols
def top_block(text, name, indent):
    """Return the (symbol "name" ...) block at the given tab indent."""
    t = "\t" * indent
    lines = text.split("\n")
    start = lines.index(f'{t}(symbol "{name}"')
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == f"{t})")
    return "\n".join(lines[start:end + 1])


old_text = open(OLD, encoding="utf-8").read()
cw_text = open(CWLIB, encoding="utf-8").read()
EMBED = {}  # lib_id -> embedded block (2-tab indent)


def embed_from_old(lib_id):
    EMBED[lib_id] = top_block(old_text, lib_id, 2)


def embed_from_lib(lib_id, path_or_text, is_text=False):
    lib, name = lib_id.split(":")
    text = path_or_text if is_text else open(path_or_text, encoding="utf-8").read()
    blk = top_block(text, name, 1)
    blk = blk.replace(f'(symbol "{name}"', f'(symbol "{lib_id}"', 1)
    EMBED[lib_id] = "\n".join("\t" + ln for ln in blk.split("\n"))


embed_from_lib("Mechanical:MountingHole_Pad", f"{STD}/Mechanical.kicad_sym")
for lid in ["power:GND", "Device:C",
            "Connector:TestPoint", "Connector:Conn_Coaxial", "power:PWR_FLAG"]:
    embed_from_old(lid)
for n in ["1u", "10u", "0R", "10", "100n", "10n", "1n", "47", "100k", "120",
          "249", "49R9", "5k1", "12n", "820p", "+3V3_SYN", "+3V3_SYN_RF",
          "+3V3_SYN_PLL", "+3V3_SYN_DIG", "+3V3_SYN_REF", "+3V3_SYN_VCO",
          "MAX2871ETJ_T", "525L25010ITR", "ADL5380ACPZ-R7", "5400BL15B050", "100p", "0R_0402", "100n_C0G",
          "+5V", "+5V_DEMOD"]:
    embed_from_lib(f"cwradar:{n}", cw_text, is_text=True)
embed_from_lib("Device:R", f"{STD}/Device.kicad_sym")
# main-board sheets (Part 2): symbols from add_lib_part2.py
embed_from_lib("Mechanical:Fiducial", f"{STD}/Mechanical.kicad_sym")
for n in ["10k", "4k7", "1k5", "392", "5k23", "30k1", "113k", "30k9", "60k4", "31k6", "51k1", "20k5", "33", "1k",
          "226k", "11k3", "680", "5k49_0p1", "10k_0p1", "3k32_0p1", "1k1_0p1", "15k_0p1", "105k_0p1", "20k_0p1",
          "1u_25V", "10u_25V", "22u_25V", "47u_10V", "4u7_25V", "47n", "22n", "470p_C0G", "4n7_C0G", "6n8_C0G",
          "3n3_C0G", "100n_C0G", "2p2", "470n_C0G", "47u_POLY", "1uH", "6u8H", "10uH", "3A_FAST", "10k_NTC", "SMF6.5A",
          "LED_GRN", "LED_YEL", "LED_RED", "LED_ORG", "AO3401A", "2N7002K", "SW_TACT", "SW_SLIDE", "XH_2P",
          "PH_2P", "BOX_2x05", "TPS62933FDRLR", "OPA4388IPWR", "USBLC6-2SC6", "ESP32-S3-WROOM-1-N16R2",
          "USB4105-GF-A", "+VBUS", "+VBAT", "+VSYS", "+VPRE", "+5V_RF", "+5V_A", "+V_LNA", "+3V3_D",
          "BQ25883RGET", "TPS7A8300RGRR", "INA819IDR", "PCM1808PWR"]:
    embed_from_lib(f"cwradar:{n}", cw_text, is_text=True)

PIN_RE = re.compile(r'\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\).*?\(number "([^"]*)"', re.S)
PROP_RE = re.compile(r'^\t\t\t\(property "([^"]+)" "((?:[^"\\]|\\.)*)"', re.M)
UNIT_RE = re.compile(r'^\t\t\t\(symbol "[^"]*_(\d+)_\d+"$', re.M)


def lib_pins(lib_id, unit=None):
    """Pin positions; with a unit, only that unit's pins plus the shared (unit 0) ones."""
    blk = EMBED[lib_id]
    if unit is None:
        return {m.group(4): (float(m.group(1)), float(m.group(2))) for m in PIN_RE.finditer(blk)}
    heads = list(UNIT_RE.finditer(blk))
    pins = {}
    for h, nxt in zip(heads, heads[1:] + [None]):
        if int(h.group(1)) in (0, unit):
            part = blk[h.start():nxt.start() if nxt else len(blk)]
            pins.update({m.group(4): (float(m.group(1)), float(m.group(2))) for m in PIN_RE.finditer(part)})
    return pins


def lib_props(lib_id):
    return [(k, v) for k, v in PROP_RE.findall(EMBED[lib_id]) if not k.startswith("ki_")]


def xform(x, y, rot, px, py, mirror=False):
    if mirror in (True, "y"):  # (mirror y): flip left-right before rotating
        px = -px
    elif mirror == "x":  # (mirror x): flip top-bottom
        py = -py
    r = math.radians(rot)
    rx, ry = px * math.cos(r) - py * math.sin(r), px * math.sin(r) + py * math.cos(r)
    return (round(x + rx, 4), round(y - ry, 4))


# ------------------------------------------------------------------ elements
SYMS, WIRES, LABELS, JUNCS, NCS, TEXTS, RECTS = [], [], [], [], [], [], []
PINPOS = {}  # ref -> {pin: (x,y)}
pwr_n = [0]
flg_n = [0]


PARTS = json.load(open(f"{WORK}/digikey_parts.json", encoding="utf-8"))
SMA = {"Manufacturer": "Molex", "Mfg Part #": "0732511153", "Description": "SMA jack, edge mount, 1.6 mm PCB",
       "Datasheet": PARTS["0732511153"]["datasheet"], "Distributor Link 1": PARTS["0732511153"]["digikey"]}


def place(ref, lib_id, x, y, rot=0, value=None, fp=None, dnp=False, fields=None,
          mirror=False, extra=None, unit=None):
    if not ref.startswith("#"):
        ref = renum(ref)
    props = dict(lib_props(lib_id))
    props["Reference"] = ref
    if value is not None:
        props["Value"] = value
    if fp is not None:
        props["Footprint"] = fp
    props.update(extra or {})
    if rot in (90, 270) and fields:  # field angles are relative to the symbol: keep text horizontal
        swap = {"left": "right", "right": "left"}
        fields = {k: (v[0], v[1], 90, v[3], *[swap.get(j, j) for j in v[4:]]) if v[2] == 0 else v
                  for k, v in fields.items()}
    pins = {n: xform(x, y, rot, px, py, mirror) for n, (px, py) in lib_pins(lib_id, unit).items()}
    PINPOS[ref if unit is None else f"{ref}#{unit}"] = pins
    SYMS.append(dict(ref=ref, lib_id=lib_id, x=x, y=y, rot=rot, props=props,
                     dnp=dnp, fields=fields or {}, mirror=mirror, unit=unit))
    return pins


def gnd(x, y):
    pwr_n[0] += 1
    place(f"#PWR{pwr_n[0]:02d}", "power:GND", x, y,
          fields={"Reference": (x, y + 6.35, 0, True), "Value": (x, y + 3.81, 0, False)})


def rail(name, x, y, value_at=None):
    pwr_n[0] += 1
    place(f"#PWR{pwr_n[0]:02d}", f"cwradar:{name}", x, y,
          fields={"Reference": (x, y + 3.81, 0, True), "Value": value_at or (x, y - 3.556, 0, False)})


def flag(x, y):
    flg_n[0] += 1
    place(f"#FLG{flg_n[0]:02d}", "power:PWR_FLAG", x, y,
          fields={"Reference": (x, y - 1.905, 0, True), "Value": (x, y - 3.81, 0, False)})


def vpart(ref, lib_id, x, y, **kw):
    """Vertical 2-pin part centred at (x, y): pin 1 top, pin 2 bottom."""
    kw.setdefault("fields", {"Reference": (x + 2.54, y - 1.27, 0, False, "left"),
                             "Value": (x + 2.54, y + 1.27, 0, False, "left")})
    return place(ref, lib_id, x, y, 0, **kw)


def hpart(ref, lib_id, x, y, **kw):
    """Horizontal 2-pin part centred at (x, y): pin 1 left, pin 2 right."""
    cap = "Device:C" in lib_id or lib_id.split(":")[1][-1] in "unp"
    off = (5.715, 3.81) if cap else (4.445, 2.54)
    kw.setdefault("fields", {"Reference": (x, y - off[0], 90, False),
                             "Value": (x, y - off[1], 90, False)})
    return place(ref, lib_id, x, y, 90, **kw)


def wire(*pts):
    pts = [(round(p[0], 4), round(p[1], 4)) for p in pts]
    for a, b in zip(pts, pts[1:]):
        assert a[0] == b[0] or a[1] == b[1], f"diagonal wire {a}->{b}"
        WIRES.append((tuple(map(lambda v: round(v, 4), a)), tuple(map(lambda v: round(v, 4), b))))


def label(name, x, y, angle=0, small=False):
    LABELS.append((name, x, y, angle, 0.635 if small else 1.27))


HLABELS = []


def hlabel(name, x, y, angle, shape):
    HLABELS.append((name, x, y, angle, shape))


def text(s, x, y, size=1.27, anton=False, bold=False, just="left bottom"):
    TEXTS.append((s, x, y, size, anton, bold, just))


def box(x1, y1, x2, y2, title):
    RECTS.append((x1, y1, x2, y2))
    text(title, x1 + 1.27, y2 - 1.27, 5.08, anton=True, bold=True)


# ============================================================== SYNTH POWER
TX = 33.02  # trunk x
rail("+3V3_SYN", TX, 35.56)
wire((TX, 35.56), (17.78, 35.56)); flag(17.78, 35.56)
SH = 17.78  # one branch row; the blocks below SYNTH POWER move down by this
wire((TX, 35.56), (TX, 111.76))
wire((TX, 38.1), (22.86, 38.1))
vpart("C1", "cwradar:10u", 22.86, 41.91); gnd(22.86, 45.72)

rows = [  # y, ref, part, rail, branch caps [(ref, part, x)]
    (40.64, "R1", "cwradar:0R", "+3V3_SYN_RF", [("C2", "cwradar:1u", 50.8)]),
    (58.42, "R18", "cwradar:0R", "+3V3_SYN_VCO", [("C25", "cwradar:1u", 50.8)]),
    (76.2, "R2", "cwradar:0R", "+3V3_SYN_PLL", [("C3", "cwradar:1u", 50.8)]),
    (93.98, "R3", "cwradar:0R", "+3V3_SYN_DIG", [("C28", "cwradar:1u", 50.8)]),
    (111.76, "R4", "cwradar:10", "+3V3_SYN_REF", [("C4", "cwradar:10u", 50.8),
                                             ("C5", "cwradar:100n", 60.96),
                                             ("C6", "cwradar:10n", 71.12)]),
]
for y, rref, rpart, rname, caps in rows:
    note = {"Note": "0R branch link, bead fallback footprint."} if rref == "R18" else None
    hpart(rref, rpart, 40.64, y, extra=note)
    wire((TX, y), (36.83, y))
    fx = 78.74 if caps and len(caps) > 1 else 71.12
    wire((44.45, y), (50.8, y), (fx, y))
    rail(rname, 50.8, y)
    flag(fx, y)
    for cref, cpart, cx in caps:
        vpart(cref, cpart, cx, y + 3.81)
        gnd(cx, y + 7.62)
box(12.7, 22.86, 88.9, 116.84 + SH, "SYNTH POWER")

# ============================================================ MCU INTERFACE
for y, esp, ic, ref in [(130.81 + SH, "SYN_SCK", "SYN_SCK_R", "R5"),
                        (138.43 + SH, "SYN_MOSI", "SYN_MOSI_R", "R6"),
                        (146.05 + SH, "SYN_LE", "SYN_LE_R", "R7")]:
    hlabel(esp, 33.02, y, 180, "input")
    wire((33.02, y), (36.83, y))
    hpart(ref, "cwradar:47", 40.64, y)
    wire((44.45, y), (55.88, y))
    label(ic, 55.88, y, 0)
for y, net, ref in [(156.21 + SH, "SYN_CE", "R8"), (170.18 + SH, "SYN_RFOUT_EN", "R9")]:
    hlabel(net, 33.02, y, 180, "input")
    wire((33.02, y), (40.64, y))
    vpart(ref, "cwradar:100k", 40.64, y + 3.81)
    gnd(40.64, y + 7.62)
YLD = 184.15 + SH
hlabel("SYN_LD", 33.02, YLD, 180, "output")
wire((33.02, YLD), (48.26, YLD))
place("TP1", "Connector:TestPoint", 48.26, YLD, value="LD",
      fp="TestPoint:TestPoint_Pad_D1.0mm",
      fields={"Reference": (50.8, YLD - 5.08, 0, False, "left"), "Value": (50.8, YLD - 2.54, 0, False, "left")})
box(12.7, 120.65 + SH, 88.9, 198.12 + SH, "MCU INTERFACE")

# ============================================================== LOOP FILTER
Y0 = 214.63 + SH
label("CP_OUT", 22.86, Y0, 180)
wire((22.86, Y0), (52.07, Y0))
vpart("C22", "cwradar:12n", 33.02, Y0 + 3.81); gnd(33.02, Y0 + 7.62)
vpart("R16", "cwradar:120", 43.18, Y0 + 3.81)
wire((43.18, Y0 + 7.62), (43.18, Y0 + 10.16))
label("LF_C2", 43.18, Y0 + 8.89, 90, small=True)
vpart("C23", "cwradar:100n_C0G", 43.18, Y0 + 13.97); gnd(43.18, Y0 + 17.78)
hpart("R17", "cwradar:249", 55.88, Y0)
wire((59.69, Y0), (78.74, Y0))
vpart("C24", "cwradar:820p", 66.04, Y0 + 3.81); gnd(66.04, Y0 + 7.62)
label("TUNE", 73.66, Y0, 0)
# TUNE probe point: 100k keeps probe capacitance off the loop filter
vpart("R19", "cwradar:100k", 78.74, Y0 + 3.81,
      extra={"Note": "Isolates probe capacitance from loop filter. Place R at the TUNE node."})
wire((78.74, Y0 + 7.62), (78.74, Y0 + 10.16))
label("TUNE_TP", 78.74, Y0 + 8.89, 90, small=True)
place("TP2", "Connector:TestPoint", 78.74, Y0 + 10.16, rot=180, value="TUNE",
      fp="TestPoint:TestPoint_Pad_D1.0mm",
      fields={"Reference": (81.28, Y0 + 12.7, 0, False, "right"), "Value": (81.28, Y0 + 15.24, 0, False, "right")})
box(12.7, 201.93 + SH, 88.9, 250.19 + SH, "LOOP FILTER")

# ====================================================== MAX2871 SYNTHESIZER
PX, PY = 152.4, 146.05
dx, dy = round(PX - 127, 4), round(PY - 95.25, 4)
r4 = lambda x, y: (round(x, 4), round(y, 4))
P = place("PLL1", "cwradar:MAX2871ETJ_T", PX, PY,
          fp="cwradar:TQFN-32-1EP_5x5mm_P0.5mm_EP3.1x3.1mm_ThermalVias0.3",
          fields={"Reference": (127 + dx, 49.53 + dy, 0, False),
                  "Value": (127 + dx, 52.07 + dy, 0, False)})
# sanity: transform matches the MCP-reported pins of the old placement
assert P["1"] == r4(109.22 + dx, 77.47 + dy) and P["6"] == r4(144.78 + dx, 57.15 + dy), P
assert P["20"] == r4(109.22 + dx, 90.17 + dy) and P["18"] == r4(144.78 + dx, 133.35 + dy)

L = P["1"][0]   # left pin x
R = P["6"][0]   # right pin x

# left-side control/status labels
for pin, net in [("4", "SYN_CE"), ("1", "SYN_SCK_R"), ("2", "SYN_MOSI_R"),
                 ("3", "SYN_LE_R"), ("20", "TUNE")]:
    label(net, *P[pin], 180)
NCS.append(P["5"])
# right-side labels
for pin, net in [("26", "SYN_RFOUT_EN"), ("7", "CP_OUT"), ("25", "SYN_LD"),
                 ]:
    label(net, *P[pin], 0)
hlabel("SYN_MISO", *P["30"], 0, "output")

# supply-pin decoupling: staircase up to a 1u per pin (+ RF C0G on VCC_RF)
YT = 92.71
supply = [("6", "+3V3_SYN_PLL", 177.8, ["C7"]), ("28", "+3V3_SYN_DIG", 193.04, ["C8"]),
          ("10", "+3V3_SYN_PLL", 208.28, ["C9"]), ("16", "+3V3_SYN_RF", 223.52, ["C10", "C11"]),
          ("32", "+3V3_SYN_DIG", 251.46, ["C12"]), ("17", "+3V3_SYN_VCO", 266.7, ["C13"])]
for pin, rname, cx, caps in supply:
    py = P[pin][1]
    wire(P[pin], (cx, py), (cx, YT))
    rail(rname, cx, YT)
    xs = [cx + 5.08 + 10.16 * i for i in range(len(caps))]
    wire((cx, YT), (xs[-1], YT))
    for cref, x in zip(caps, xs):
        if cref == "C10":
            vpart(cref, "cwradar:2p2", x, YT + 3.81)
        else:
            vpart(cref, "cwradar:1u", x, YT + 3.81)
        gnd(x, YT + 7.62)

# VCO / bias decoupling and RSET: staircase down-left
YB = 165.1
for pin, cref, part, cx, net in [("23", "C16", "cwradar:1u", 127.0, "BIAS_FILT"),
                                 ("24", "C15", "cwradar:1u", 116.84, "REG"),
                                 ("19", "C14", "cwradar:1u", 106.68, "NOISE_FILT"),
                                 ("22", "R10", "cwradar:5k1", 96.52, "RSET")]:
    py = P[pin][1]
    wire(P[pin], (cx, py), (cx, YB))
    vpart(cref, part, cx, YB + 3.81)
    gnd(cx, YB + 7.62)
    label(net, cx + 1.27, py, 0, small=True)

# reference input coupling
ry = P["29"][1]
hpart("C17", "cwradar:1n", 125.73, ry,
      fields={"Reference": (125.73, ry - 2.794, 90, False), "Value": (125.73, ry + 3.175, 90, False)})
wire(P["29"], (129.54, ry))
label("REF_IN", 130.81, ry, 0, small=True)
label("REF_25M", 121.92, ry, 180)

# reference TCXO: CTS 525L25010ITR (25 MHz, +/-1 ppm, clipped sine), on the RC-filtered +3V3_SYN_REF branch
YX, YY = 106.68, 104.14
X = place("Y1", "cwradar:525L25010ITR", YX, YY,
          fields={"Reference": (96.52, 86.36, 0, False, "left"), "Value": (96.52, 88.9, 0, False, "left")})
rail("+3V3_SYN_REF", *X["4"])
gnd(*X["2"])
NCS.append(X["1"])
wire(X["3"], (121.92, YY))
label("REF_25M", 121.92, YY, 0)

# ground pins: short stubs onto a vertical bus
GX = R + 2.54
gys = sorted(P[p][1] for p in ["33", "8", "27", "9", "11", "31", "21", "18"])
for p in ["33", "8", "27", "9", "11", "31", "21", "18"]:
    wire(P[p], (GX, P[p][1]))
wire((GX, gys[0]), (GX, gys[-1] + 2.54))
gnd(GX, gys[-1] + 2.54)
wire((GX, gys[-1] + 2.54), (GX + 5.08, gys[-1] + 2.54))
flag(GX + 5.08, gys[-1] + 2.54)

# RF outputs: staircase down, bottom pin turns first, one row per output
NODE, DCB, J = 215.9, 228.6, 248.92
fan = [("14", "RFOUTB_P", 190.5, 205.74), ("15", "RFOUTB_N", 195.58, 187.96),
       ("12", "RFOUTA_P", 200.66, 170.18), ("13", "RFOUTA_N", 205.74, 152.4)]
pull = {"RFOUTA_N": ("R11", "C18"), "RFOUTA_P": ("R13", "C19"),
        "RFOUTB_N": ("R14", "C20"), "RFOUTB_P": ("R15", "C21")}
for pin, net, cx, Y in fan:
    py = P[pin][1]
    wire(P[pin], (cx, py), (cx, Y), (DCB - 3.81, Y))
    label(net, 207.01, Y, 0, small=True)
    rref, cref = pull[net]
    vpart(rref, "cwradar:49R9", NODE, Y - 3.81)
    rail("+3V3_SYN_RF", NODE, Y - 7.62)
    hpart(cref, "cwradar:2p2", DCB, Y)
    if net == "RFOUTA_P":
        wire((DCB + 3.81, Y), (J - 5.08, Y))
        label("TX_RF", DCB + 5.08, Y, 0, small=True)
        place("J1", "Connector:Conn_Coaxial", J, Y, value="TX SMA", fp="Connector_Coaxial:SMA_Molex_73251-1153_EdgeMount_Horizontal", extra=SMA,
              fields={"Reference": (J + 3.81, Y - 2.54, 0, False, "left"),
                      "Value": (J + 3.81, Y, 0, False, "left")})
        gnd(J, Y + 5.08)
    elif net == "RFOUTA_N":
        wire((DCB + 3.81, Y), (J - 5.08, Y))
        label("MON_RF", DCB + 5.08, Y, 0, small=True)
        vpart("R12", "cwradar:49R9", 238.76, Y + 3.81); gnd(238.76, Y + 7.62)
        place("J2", "Connector:Conn_Coaxial", J, Y, value="MON SMA",
              fp="Connector_Coaxial:SMA_Molex_73251-1153_EdgeMount_Horizontal", dnp=True, extra=SMA,
              fields={"Reference": (J + 3.81, Y - 2.54, 0, False, "left"),
                      "Value": (J + 3.81, Y, 0, False, "left")})
        gnd(J, Y + 5.08)
    else:
        lo = "LO_P" if net == "RFOUTB_P" else "LO_N"
        wire((DCB + 3.81, Y), (238.76, Y))
        hlabel(lo, 238.76, Y, 0, "output")

# HF decoupling at the pull-up supply ends: 2.2 pF GJM, series-resonant around 5.8 GHz
for cref, pair, y in [("C26", "R611/R613", 157.48), ("C27", "R614/R615", 193.04)]:
    rail("+3V3_SYN_RF", 279.4, y)
    wire((279.4, y), (284.48, y))
    vpart(cref, "cwradar:2p2", 284.48, y + 3.81,
          extra={"Note": f"Place at the shared supply end of {pair}. Series-resonant around 5.8 GHz."})
    gnd(284.48, y + 7.62)
    text(f"Place at {pair}\nsupply end", 276.86, y + 13.97, just="left top")
box(92.71, 82.55, 302.26, 215.9, "MAX2871 SYNTHESIZER")

# ===================================================================== notes
text("MAX2871 NOTES (DS Rev 4)\n"
     "- One 1u 10V X5R 0402 on every supply pin (C7-C9, C11-C13), branch caps C2/C3 and NOISE_FILT/BIAS_FILT/REG (C14-C16).\n"
     "  Place each 1u directly at its pin, own GND via at or in the pad. Check the part's DC-bias curve at 3.3V; no Y5V.\n"
     "- C10: 2.2 pF GJM1555C1H2R2BB01D on VCC_RF (series-resonant ~5.8 GHz), closest to pin 16.\n"
     "- C18-C21 DC blocks: 2.2 pF GJM (series-resonant ~5.8 GHz). R5-R7 47R series: place at the ESP32 end.\n"
     "- R8/R9 100k hold CE/RFOUT_EN low at boot.\n"
     "- Loop filter C22/R16/C23/R17/C24 = MAX2871 DS Rev 4 TOC table \"6.0 GHz closed-loop\n"
     "  phase noise\" config: fREF 50 MHz, fPFD 25 MHz, ~40 kHz BW, CP[3:0]=1111 (5.12 mA w/ RSET 5k1),\n"
     "  integer N=240. Ours: N=232 @ fPFD 25 MHz. Confirm Kvco @ 5.8 GHz in ADIsimPLL. All loop-filter caps C0G.\n"
     "- Firmware: program all regs twice at power-up (>=20 ms gap, order 5..0), RFA_EN/RFB_EN = 0 until second\n"
     "  pass; set MTLD=1 (reg4 b10) and MUTEDEL=1 (reg3 b17) so outputs mute when unlocked. PDP=1.\n"
     "- VCC_VCO on dedicated branch +3V3_SYN_VCO (R18). Pull-up node HF caps C26/C27: 2.2 pF GJM.\n"
     "- R12 (50R term) or J2 (SMA monitor): populate one. J1/J2: Molex 73251-1153 edge-launch SMA.\n"
     "- Bead-free star: R1-R3 0R 0603 branch links (fallback filter footprints). R4 10R + C4 10u = TCXO RC, fc ~1.6 kHz.\n"
     "- +3V3_SYN from dedicated low-noise LDO (TBD); LC/pi filter at LDO input if fed from a switcher. REF_25M from TCXO Y1 (CTS 525L25010ITR).\n"
     "- GND pins 8,9,11,18,21,27,31: own via each, not to EP. EP: >=9-via array.",
     96.52, 222.25, just="left top")
TEXTS[-1] = (re.sub(r"\b(C|R|J|TP)(\d{1,2})\b", lambda m: m.group(1) + str(600 + int(m.group(2))), TEXTS[-1][0]),) + TEXTS[-1][1:]


# ============================================================ connectivity
def on_seg(p, a, b):
    if a[0] == b[0] == p[0]:
        return min(a[1], b[1]) < p[1] < max(a[1], b[1])
    if a[1] == b[1] == p[1]:
        return min(a[0], b[0]) < p[0] < max(a[0], b[0])
    return False


def finish_wires(wires, pins, label_pts):
    """Split wires at pins/ends/labels, return (wires, junctions); fail on dangling ends."""
    ends = {pt for seg in wires for pt in seg}
    cuts = set(pins) | ends | set(label_pts)
    split = []
    for a, b in wires:
        inner = sorted([p for p in cuts if on_seg(p, a, b)],
                       key=lambda p: abs(p[0] - a[0]) + abs(p[1] - a[1]))
        pts = [a] + inner + [b]
        split += [(p, q) for p, q in zip(pts, pts[1:]) if p != q]
    wires = list(dict.fromkeys(split))
    deg = {}
    for a, b in wires:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
    for pt in pins:
        if pt in deg:
            deg[pt] += 1
    pin_set, lbl = set(pins), set(label_pts)
    for a, b in wires:
        for p in (a, b):
            if deg[p] < 2 and p not in pin_set and p not in lbl:
                raise SystemExit(f"dangling wire end at {p}")
    return wires, sorted(p for p, d in deg.items() if d >= 3)


r4 = lambda x, y: (round(x, 4), round(y, 4))
WIRES[:], JUNCS[:] = finish_wires(
    WIRES, [pt for pins in PINPOS.values() for pt in pins.values()],
    [r4(x, y) for _, x, y, *_ in LABELS] + [r4(x, y) for _, x, y, *_ in HLABELS])


# ================================================================== emit
def eff(size, justify=None, hide=False):
    j = f"\n\t\t\t\t(justify {justify})" if justify else ""
    return f"(effects\n\t\t\t\t(font\n\t\t\t\t\t(size {size} {size})\n\t\t\t\t){j}\n\t\t\t)"


def shift_ref(ref, offset):
    if not offset:
        return ref
    m = re.fullmatch(r"(#?[A-Z]+)(\d+)", ref)
    return f"{m.group(1)}{int(m.group(2)) + offset}"


def sym_block(s, inst_path, more=()):
    """more: extra (instance path, refdes offset) pairs for a sheet file used twice."""
    unit = s.get("unit")
    key = s["ref"] if unit is None else f"{s['ref']}#{unit}"
    suid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cwradar-sym{inst_path}/{key}"))
    bom = "no" if re.match(r"(TP|MH|FID)\d", s["ref"]) else "yes"  # test pads, holes, fiducials are not purchased
    mir = {True: "\n\t\t(mirror y)", "y": "\n\t\t(mirror y)", "x": "\n\t\t(mirror x)"}.get(s.get("mirror"), "")
    out = [f'\t(symbol\n\t\t(lib_id "{s["lib_id"]}")\n\t\t(at {f(s["x"])} {f(s["y"])} {s["rot"]}){mir}',
           f"\t\t(unit {unit or 1})\n\t\t(body_style 1)\n\t\t(exclude_from_sim no)\n\t\t(in_bom {bom})\n\t\t(on_board yes)\n\t\t(in_pos_files yes)",
           f'\t\t(dnp {"yes" if s["dnp"] else "no"})\n\t\t(uuid "{suid}")']
    for k, v in s["props"].items():
        fld = s["fields"].get(k)
        if fld:
            x, y, ang, hide = fld[:4]
            just = fld[4] if len(fld) > 4 else None
        else:
            x, y, ang, hide, just = s["x"], s["y"], 0, True, None
        h = "\n\t\t\t(hide yes)" if hide else ""
        out.append(f'\t\t(property "{k}" "{v}"\n\t\t\t(at {f(x)} {f(y)} {ang}){h}\n'
                   f'\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n\t\t\t{eff(1.27, just)}\n\t\t)')
    for n in lib_pins(s["lib_id"], unit):
        out.append(f'\t\t(pin "{n}"\n\t\t\t(uuid "{uuid.uuid5(uuid.NAMESPACE_URL, suid + "/" + n)}")\n\t\t)')
    paths = "".join(f'\t\t\t\t(path "{p}"\n\t\t\t\t\t(reference "{shift_ref(s["ref"], off)}")\n'
                    f'\t\t\t\t\t(unit {unit or 1})\n\t\t\t\t)\n' for p, off in [(inst_path, 0), *more])
    out.append(f'\t\t(instances\n\t\t\t(project "Frontend"\n{paths}\t\t\t)\n\t\t)\n\t)')
    return "\n".join(out)


def header(title, file_uuid):
    return (f'(kicad_sch\n\t(version 20260306)\n\t(generator "eeschema")\n\t(generator_version "10.0")\n'
            f'\t(uuid "{file_uuid}")\n\t(paper "A3")\n\t(title_block\n\t\t(title "{title}")\n'
            f'\t\t(date "2026-10-15")\n\t\t(rev "V1")\n\t\t(company "Senior Design")\n'
            f'\t\t(comment 1 "Carter Cattadoris")\n\t)')


def hlabel_block(name, x, y, ang, shape):
    just = "left" if ang == 0 else "right"
    return (f'\t(hierarchical_label "{name}"\n\t\t(shape {shape})\n\t\t(at {f(x)} {f(y)} {ang})\n'
            f'\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n\t\t\t(justify {just})\n\t\t)\n\t\t(uuid "{U()}")\n\t)')


def wire_block(a, b):
    return (f'\t(wire\n\t\t(pts\n\t\t\t(xy {f(a[0])} {f(a[1])}) (xy {f(b[0])} {f(b[1])})\n\t\t)\n'
            f'\t\t(stroke\n\t\t\t(width 0)\n\t\t\t(type default)\n\t\t)\n\t\t(uuid "{U()}")\n\t)')


def junction_block(p):
    return f'\t(junction\n\t\t(at {f(p[0])} {f(p[1])})\n\t\t(diameter 0)\n\t\t(color 0 0 0 0)\n\t\t(uuid "{U()}")\n\t)'


FOOT = '\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n'

# -------------------------------------------------------------- root layout
# name, file, page, (x, y, w, h), pins [(name, shape, edge, y)]
B = "bidirectional"
SHEETS = [
    ("Battery_Charger", "battery_charger.kicad_sch", 2, (20.32, 30.48, 45.72, 50.8),
     [("USB_D_P", B, "R", 40.64), ("USB_D_N", B, "R", 45.72), ("CC1_SENSE", "output", "R", 50.8),
      ("CC2_SENSE", "output", "R", 55.88), ("CHG_INT", "output", "R", 60.96),
      ("I2C_SDA", B, "R", 66.04), ("I2C_SCL", B, "R", 71.12)]),
    ("Regulators", "regulators.kicad_sch", 3, (20.32, 96.52, 45.72, 25.4),
     [("EN_ANALOG", "input", "R", 106.68)]),
    ("MCU", "mcu.kicad_sch", 4, (96.52, 30.48, 40.64, 106.68),
     [("USB_D_P", B, "L", 40.64), ("USB_D_N", B, "L", 45.72), ("CC1_SENSE", "input", "L", 50.8),
      ("CC2_SENSE", "input", "L", 55.88), ("CHG_INT", "input", "L", 60.96),
      ("I2C_SDA", B, "L", 66.04), ("I2C_SCL", B, "L", 71.12), ("EN_ANALOG", "output", "L", 106.68),
      ("SYN_SCK", "output", "R", 40.64), ("SYN_MOSI", "output", "R", 45.72),
      ("SYN_MISO", "input", "R", 50.8), ("SYN_LE", "output", "R", 55.88),
      ("SYN_CE", "output", "R", 60.96), ("SYN_LD", "input", "R", 66.04),
      ("SYN_RFOUT_EN", "output", "R", 71.12),
      ("DISP_SCK", "output", "R", 91.44), ("DISP_MOSI", "output", "R", 93.98),
      ("DISP_CS", "output", "R", 96.52), ("DISP_DC", "output", "R", 99.06),
      ("DISP_RST", "output", "R", 101.6), ("DISP_BL", "output", "R", 104.14),
      ("STATUS_LED", "output", "R", 106.68), ("BTN1", "input", "R", 109.22), ("BTN2", "input", "R", 111.76),
      ("I2S_MCLK", "output", "R", 116.84), ("I2S_BCK", "output", "R", 121.92),
      ("I2S_LRCK", "output", "R", 127.0), ("I2S_DOUT", "input", "R", 132.08)]),
    ("User_IO", "user_io.kicad_sch", 5, (167.64, 83.82, 40.64, 30.48),
     [("SYN_RFOUT_EN", "input", "L", 86.36), ("DISP_SCK", "input", "L", 91.44),
      ("DISP_MOSI", "input", "L", 93.98), ("DISP_CS", "input", "L", 96.52), ("DISP_DC", "input", "L", 99.06),
      ("DISP_RST", "input", "L", 101.6), ("DISP_BL", "input", "L", 104.14),
      ("STATUS_LED", "input", "L", 106.68), ("BTN1", "output", "L", 109.22), ("BTN2", "output", "L", 111.76),
      ("I2C_SDA", B, "R", 91.44), ("I2C_SCL", B, "R", 93.98)]),
    ("Synthesizer", "synthesizer.kicad_sch", 6, (167.64, 30.48, 40.64, 45.72),
     [("SYN_SCK", "input", "L", 40.64), ("SYN_MOSI", "input", "L", 45.72),
      ("SYN_MISO", "output", "L", 50.8), ("SYN_LE", "input", "L", 55.88),
      ("SYN_CE", "input", "L", 60.96), ("SYN_LD", "output", "L", 66.04),
      ("SYN_RFOUT_EN", "input", "L", 71.12), ("LO_P", "output", "R", 45.72),
      ("LO_N", "output", "R", 50.8)]),
    ("Receiver", "receiver.kicad_sch", 7, (238.76, 30.48, 40.64, 45.72),
     [("LO_P", "input", "L", 45.72), ("LO_N", "input", "L", 50.8),
      ("I_P", "output", "R", 35.56), ("I_N", "output", "R", 40.64),
      ("Q_P", "output", "R", 60.96), ("Q_N", "output", "R", 66.04)]),
    ("Baseband_I", "baseband.kicad_sch", 8, (309.88, 27.94, 35.56, 17.78),
     [("IN_P", "input", "L", 35.56), ("IN_N", "input", "L", 40.64), ("OUT", "output", "R", 38.1)]),
    ("Baseband_Q", "baseband.kicad_sch", 9, (309.88, 53.34, 35.56, 17.78),
     [("IN_P", "input", "L", 60.96), ("IN_N", "input", "L", 66.04), ("OUT", "output", "R", 63.5)]),
    ("ADC", "adc.kicad_sch", 10, (370.84, 30.48, 30.48, 106.68),
     [("ADC_L", "input", "L", 38.1), ("ADC_R", "input", "L", 50.8),
      ("I2S_MCLK", "input", "L", 116.84), ("I2S_BCK", "input", "L", 121.92),
      ("I2S_LRCK", "input", "L", 127.0), ("I2S_DOUT", "output", "L", 132.08)]),
    ("Mechanical", "mechanical.kicad_sch", 11, (20.32, 160.02, 45.72, 25.4), []),
]
SHEET_UUID = {name: (SYN_SHEET if name == "Synthesizer" else str(uuid.uuid5(uuid.NAMESPACE_URL, "cwradar/" + name)))
              for name, *_ in SHEETS}
FILE_UUID = {file: str(uuid.uuid5(uuid.NAMESPACE_URL, "cwradar-file/" + file)) for _, file, *_ in SHEETS}


def pin_xy(sheet, pname):
    name, file, page, (x, y, w, h), pins = next(s for s in SHEETS if s[0] == sheet)
    _, _, edge, py = next(p for p in pins if p[0] == pname)
    return (x if edge == "L" else round(x + w, 4), py)


# root wires: (from sheet, pin, to sheet, pin, via points)
LINKS = [("Battery_Charger", p, "MCU", p, []) for p in
         ["USB_D_P", "USB_D_N", "CC1_SENSE", "CC2_SENSE", "CHG_INT", "I2C_SDA", "I2C_SCL"]]
LINKS += [("Regulators", p, "MCU", p, []) for p in ["EN_ANALOG"]]
LINKS += [("MCU", p, "Synthesizer", p, []) for p in
          ["SYN_SCK", "SYN_MOSI", "SYN_MISO", "SYN_LE", "SYN_CE", "SYN_LD", "SYN_RFOUT_EN"]]
# SYN_RFOUT_EN also drives the TX LED on User_IO: tap the MCU -> Synthesizer wire
LINKS += [("MCU", "SYN_RFOUT_EN", "User_IO", "SYN_RFOUT_EN", [(152.4, 71.12), (152.4, 86.36)])]
LINKS += [("MCU", p, "User_IO", p, []) for p in
          ["DISP_SCK", "DISP_MOSI", "DISP_CS", "DISP_DC", "DISP_RST", "DISP_BL", "STATUS_LED", "BTN1", "BTN2"]]
LINKS += [("Synthesizer", p, "Receiver", p, []) for p in ["LO_P", "LO_N"]]
LINKS += [("Receiver", "I_P", "Baseband_I", "IN_P", []), ("Receiver", "I_N", "Baseband_I", "IN_N", []),
          ("Receiver", "Q_P", "Baseband_Q", "IN_P", []), ("Receiver", "Q_N", "Baseband_Q", "IN_N", []),
          ("Baseband_I", "OUT", "ADC", "ADC_L", []),
          ("Baseband_Q", "OUT", "ADC", "ADC_R", [(355.6, 63.5), (355.6, 50.8)])]
LINKS += [("MCU", p, "ADC", p, []) for p in ["I2S_MCLK", "I2S_BCK", "I2S_LRCK", "I2S_DOUT"]]

root_wires = []
for s1, p1, s2, p2, via in LINKS:
    pts = [pin_xy(s1, p1)] + via + [pin_xy(s2, p2)]
    for a, b in zip(pts, pts[1:]):
        assert a[0] == b[0] or a[1] == b[1], (s1, p1, a, b)
        root_wires.append((r4(*a), r4(*b)))
# I2C also reaches the display header on User_IO: root-level local labels (no global labels)
root_labels = [("I2C_SDA", 81.28, 66.04, 0), ("I2C_SCL", 81.28, 71.12, 0),
               ("I2C_SDA", 215.9, 91.44, 0), ("I2C_SCL", 215.9, 93.98, 0)]
for p in ["I2C_SDA", "I2C_SCL"]:
    a = pin_xy("User_IO", p)
    root_wires.append((r4(*a), r4(215.9, a[1])))
root_pins = [pin_xy(s[0], p[0]) for s in SHEETS for p in s[4]]
root_wires, root_juncs = finish_wires(root_wires, root_pins, [r4(x, y) for _, x, y, _ in root_labels])

LAYOUT_NOTES = (
    "LAYOUT_NOTES (record only; layout by Carter)\n"
    "- Floorplan: RF zone at one end (Synthesizer, Receiver, both RF connectors, J301 beside the RX connector).\n"
    "  Baseband and ADC in the middle, I and Q side by side as mirror images. Power and digital at the far end,\n"
    "  both bucks and the charger farthest from RF and baseband. ESP32 at the edge opposite the RF zone,\n"
    "  antenna keepout clear of copper on all layers.\n"
    "- Baseband: lay out Q as an exact copy of I (multichannel / repeat layout). Star-route VREF_BUF within each channel.\n"
    "- Power path: +VBUS, +VSYS, +VBAT as pours or >= 1.0 mm traces. Keep the BQ25883 SW loop and both buck SW loops\n"
    "  minimal. No analog nets under or adjacent to any SW node or inductor.\n"
    "- USB: BQ25883 D+/D- stubs (R202/R203) < 5 mm. Keep pour >= 0.5 mm from the pair.\n"
    "- Placement: RT201 right next to J201 (pack location). 33R display / I2S series resistors at the ESP32 end.\n"
    "- Exposed pads (BQ25883, TPS7A8300 x4): thermal vias, windowpane paste. RGR EP: TI land 2.05 mm, KiCad fp 2.0 mm.\n"
    "- Thermal: LDO305 (+3V3_SYN) dissipates ~0.46 W. GND pad-via array to L2.")

UCTX[:] = ["Frontend.kicad_sch", 0]
out = [header("CW Radar Main Board", ROOT_UUID), "\t(lib_symbols\n\t)"]
out += [junction_block(p) for p in root_juncs] + [wire_block(a, b) for a, b in root_wires]
for name, x, y, ang in root_labels:
    out.append(f'\t(label "{name}"\n\t\t(at {f(x)} {f(y)} {ang})\n\t\t(effects\n\t\t\t(font\n'
               f'\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n\t\t\t(justify left bottom)\n\t\t)\n\t\t(uuid "{U()}")\n\t)')
notes = LAYOUT_NOTES.replace('"', '\\"').replace("\n", "\\n")
out.append(f'\t(text "{notes}"\n\t\t(exclude_from_sim no)\n\t\t(at 20.32 205.74 0)\n'
           f'\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n\t\t\t)\n\t\t\t(justify left top)\n\t\t)\n\t\t(uuid "{U()}")\n\t)')
for name, file, page, (x, y, w, h), pins in SHEETS:
    blk = [f'\t(sheet\n\t\t(at {f(x)} {f(y)})\n\t\t(size {f(w)} {f(h)})\n\t\t(exclude_from_sim no)\n'
           f'\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n\t\t(fields_autoplaced yes)\n'
           f'\t\t(stroke\n\t\t\t(width 0.1524)\n\t\t\t(type solid)\n\t\t)\n\t\t(fill\n\t\t\t(color 0 0 0 0.0000)\n\t\t)\n'
           f'\t\t(uuid "{SHEET_UUID[name]}")',
           f'\t\t(property "Sheetname" "{name}"\n\t\t\t(at {f(x)} {f(round(y - 0.7116, 4))} 0)\n\t\t\t{eff(1.27, "left bottom")}\n\t\t)',
           f'\t\t(property "Sheetfile" "{file}"\n\t\t\t(at {f(x)} {f(round(y + h + 0.5884, 4))} 0)\n\t\t\t{eff(1.27, "left top")}\n\t\t)']
    for pname, shape, edge, py in pins:
        px, ang, just = (x, 180, "left") if edge == "L" else (round(x + w, 4), 0, "right")
        blk.append(f'\t\t(pin "{pname}" {shape}\n\t\t\t(at {f(px)} {f(py)} {ang})\n\t\t\t(uuid "{U()}")\n'
                   f'\t\t\t{eff(1.27, just)}\n\t\t)')
    blk.append(f'\t\t(instances\n\t\t\t(project "Frontend"\n\t\t\t\t(path "/{ROOT_UUID}"\n'
               f'\t\t\t\t\t(page "{page}")\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)')
    out.append("\n".join(blk))
out.append(FOOT)
open(f"{OUTDIR}/Frontend.kicad_sch", "w", encoding="utf-8").write("\n".join(out))

# ------------------------------------------------------- drawn sub-sheets
def emit_sheet(sheet, title, file, also=()):
    """Write the current element lists as a sub-sheet; its ports must match the sheet pins.
    also: (sheet name, refdes offset) for further instances of the same file."""
    inst = f"/{ROOT_UUID}/{SHEET_UUID[sheet]}"
    more = [(f"/{ROOT_UUID}/{SHEET_UUID[s2]}", off) for s2, off in also]
    UCTX[:] = [file, 0]
    body = [header(title, FILE_UUID[file]), "\t(lib_symbols"]
    body += [EMBED[lid] for lid in sorted({s["lib_id"] for s in SYMS})]
    body.append("\t)")
    body += [junction_block(p) for p in JUNCS]
    body += [f'\t(no_connect\n\t\t(at {f(p[0])} {f(p[1])})\n\t\t(uuid "{U()}")\n\t)' for p in NCS]
    body += [wire_block(a, b) for a, b in WIRES]
    for x1, y1, x2, y2 in RECTS:
        body.append(f'\t(rectangle\n\t\t(start {f(x1)} {f(y1)})\n\t\t(end {f(x2)} {f(y2)})\n'
                    f'\t\t(stroke\n\t\t\t(width 0.254)\n\t\t\t(type solid)\n\t\t)\n\t\t(fill\n\t\t\t(type none)\n\t\t)\n\t\t(uuid "{U()}")\n\t)')
    for s, x, y, size, anton, bold, just in TEXTS:
        s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        face = '\n\t\t\t\t(face "Anton")' if anton else ""
        extra = "\n\t\t\t\t(thickness 0.254)\n\t\t\t\t(bold yes)\n\t\t\t\t(color 0 0 0 1)" if bold else ""
        body.append(f'\t(text "{s}"\n\t\t(exclude_from_sim no)\n\t\t(at {f(x)} {f(y)} 0)\n'
                    f'\t\t(effects\n\t\t\t(font{face}\n\t\t\t\t(size {size} {size}){extra}\n\t\t\t)\n'
                    f'\t\t\t(justify {just})\n\t\t)\n\t\t(uuid "{U()}")\n\t)')
    for name, x, y, ang, size in LABELS:
        just = {0: "left bottom", 90: "left bottom", 180: "right bottom", 270: "right bottom"}[ang]
        body.append(f'\t(label "{name}"\n\t\t(at {f(x)} {f(y)} {ang})\n\t\t(effects\n\t\t\t(font\n'
                    f'\t\t\t\t(size {size} {size})\n\t\t\t)\n\t\t\t(justify {just})\n\t\t)\n\t\t(uuid "{U()}")\n\t)')
    body += [hlabel_block(*h) for h in HLABELS]
    body += [sym_block(s, inst, more) for s in SYMS]
    body.append(FOOT)
    open(f"{OUTDIR}/{file}", "w", encoding="utf-8").write("\n".join(body))
    ports = {(n, sh) for n, _, _, _, sh in HLABELS}
    pins = {(p[0], p[1]) for p in next(s for s in SHEETS if s[0] == sheet)[4]}
    assert ports == pins, (sheet, ports ^ pins)
    print(f"{sheet}: {len(SYMS)} symbols, {len(WIRES)} wires, {len(JUNCS)} junctions, "
          f"{len(LABELS)} labels, {len(HLABELS)} ports")


emit_sheet("Synthesizer", "Synthesizer", "synthesizer.kicad_sch")

# ================================================================ RECEIVER
for lst in (SYMS, WIRES, LABELS, JUNCS, NCS, TEXTS, RECTS, HLABELS):
    lst.clear()
PINPOS.clear()
BASE[0] = 700
pwr_n[0] = flg_n[0] = 700

# ------------------------------------------------------------- DEMOD POWER
rail("+5V_RF", 33.02, 35.56)
wire((33.02, 35.56), (33.02, 40.64), (36.83, 40.64))
hpart("R1", "cwradar:0R", 40.64, 40.64, extra={"Note": "0R branch link, bead fallback footprint."})
wire((44.45, 40.64), (50.8, 40.64), (71.12, 40.64))
rail("+5V_DEMOD", 50.8, 40.64)
flag(71.12, 40.64)
vpart("C1", "cwradar:10u", 50.8, 44.45); gnd(50.8, 48.26)
text("+5V_RF from LDO303 (Regulators)", 40.64, 30.48)
box(12.7, 22.86, 88.9, 63.5, "DEMOD POWER")

# ----------------------------------------------------- ADL5380 DEMODULATOR
DX, DY = 190.5, 139.7
D = place("DEMOD1", "cwradar:ADL5380ACPZ-R7", DX, DY,
          fields={"Reference": (177.8, 115.57, 0, False, "left"), "Value": (177.8, 118.11, 0, False, "left")})
assert D["21"] == (172.72, 132.08) and D["9"] == (172.72, 139.7) and D["6"] == (208.28, 121.92), D

# RF input: RX coax -> balun -> DC blocks -> RFIN/RFIP
YN, YP = 124.46, 134.62  # balun balanced pins 3 / 4
J = place("J1", "Connector:Conn_Coaxial", 101.6, YP, value="RX SMA", fp="Connector_Coaxial:SMA_Molex_73251-1153_EdgeMount_Horizontal", extra=SMA,
          mirror=True, fields={"Reference": (96.52, 127.0, 0, False, "right"),  # mirrored: shows left
                               "Value": (96.52, 129.54, 0, False, "right")})
gnd(*J["2"])
T = place("T1", "cwradar:5400BL15B050", 129.54, 129.54, mirror="x",
          fields={"Reference": (129.54, 114.3, 0, False), "Value": (129.54, 116.84, 0, False)})
assert T["4"] == (134.62, YN) and T["3"] == (134.62, YP), T
wire(J["1"], T["1"])
label("RX_RF", 109.22, YP, 0, small=True)
gx2, gy2 = T["2"]  # GND pins face up on the mirrored balun
wire((gx2, gy2), (gx2, gy2 - 2.54), (gx2 - 5.08, gy2 - 2.54), (gx2 - 5.08, gy2))
gnd(gx2 - 5.08, gy2)
# balanced polarity chosen for a crossing-free layout (RF inversion flips I and Q together)
for tp, bal, cref, dem, pin in [("3", "RX_BAL_P", "C2", "DEMOD_RFIP", "22"),
                                ("4", "RX_BAL_N", "C3", "DEMOD_RFIN", "21")]:
    y = T[tp][1]
    wire(T[tp], (153.67, y))
    label(bal, 139.7, y, 0, small=True)
    hpart(cref, "cwradar:2p2", 157.48, y,
          extra={"Note": "DC block, series-resonant ~5.8 GHz. Not the eval board's 100 pF (rated to 4 GHz)."})
    px, py = D[pin]
    if py == y:
        wire((161.29, y), (px, py))
    else:
        wire((161.29, y), (168.91, y), (168.91, py), (px, py))
    label(dem, 162.56, y, 0, small=True)

# LO in: already AC-coupled on the synthesizer sheet (C620/C621). LO_P -> LOIN so the pair
# routes without crossing; LO inversion flips I and Q together, so the Doppler sign is unchanged.
for pin, lo in [("10", "LO_P"), ("9", "LO_N")]:
    px, py = D[pin]
    hlabel(lo, 160.02, py, 180, "input")
    wire((160.02, py), (px, py))

# ADJ: open above 5 GHz, DNP footprint to VS for IIP3 tuning
ax, ay = D["19"]
wire((142.24, ay), (ax, ay))
label("DEMOD_ADJ", 162.56, ay, 0, small=True)
hpart("R3", "Device:R", 138.43, ay, value="DNP (open >5 GHz)", fp="Resistor_SMD:R_0402_1005Metric",
      dnp=True, fields={"Reference": (138.43, ay + 3.81, 90, False), "Value": (138.43, ay + 6.35, 90, False)})
rail("+5V_DEMOD", 134.62, ay)

# ENBL low = enabled; 0R so the trace can move to an MCU GPIO later
ex, ey = D["7"]
wire((152.4, ey), (ex, ey))
label("DEMOD_ENBL", 162.56, ey, 0, small=True)
vpart("R2", "cwradar:0R_0402", 152.4, ey + 3.81)
gnd(152.4, ey + 7.62)
NCS.append(D["12"])

# VCC1-3: staircase up, 100p C0G closest to the pin then 100n
YT = 104.14
for pin, cx, caps in [("6", 213.36, ["C4", "C5"]), ("13", 238.76, ["C6", "C7"]),
                      ("24", 264.16, ["C8", "C9"])]:
    px, py = D[pin]
    wire((px, py), (cx, py), (cx, YT))
    rail("+5V_DEMOD", cx, YT)
    xs = [cx + 5.08, cx + 15.24]
    wire((cx, YT), (xs[-1], YT))
    for cref, x, part in zip(caps, xs, ["cwradar:100p", "cwradar:100n"]):
        vpart(cref, part, x, YT + 3.81)
        gnd(x, YT + 7.62)

# GND pins and EP
gx = D["1"][0]
wire(D["1"], D["25"], (gx, D["25"][1] + 2.54))
gnd(gx, D["25"][1] + 2.54)

# baseband outputs: staircase down to one row per output
XH = 289.56
for pin, net, Y, fx in [("3", "I_P", 132.08, None), ("4", "I_N", 142.24, 220.98),
                        ("15", "Q_N", 157.48, 218.44), ("16", "Q_P", 167.64, 215.9)]:
    px, py = D[pin]
    if fx is None:
        assert py == Y
        wire((px, py), (XH, Y))
    else:
        wire((px, py), (fx, py), (fx, Y), (XH, Y))
    hlabel(net, XH, Y, 0, "output")
for rref, ytop, ybot in [("R4", 132.08, 142.24), ("R5", 157.48, 167.64)]:
    yc = round((ytop + ybot) / 2, 4)
    vpart(rref, "Device:R", 241.3, yc, value="DNP — diff load ≥500 Ω",
          fp="Resistor_SMD:R_0402_1005Metric", dnp=True)
    wire((241.3, ytop), (241.3, yc - 3.81))
    wire((241.3, yc + 3.81), (241.3, ybot))
for tref, net, x, y in [("TP1", "I_P", 269.24, 132.08), ("TP2", "I_N", 276.86, 142.24),
                        ("TP3", "Q_N", 269.24, 157.48), ("TP4", "Q_P", 276.86, 167.64)]:
    place(tref, "Connector:TestPoint", x, y, value=net, fp="TestPoint:TestPoint_Pad_D1.0mm",
          fields={"Reference": (x + 2.54, y - 5.08, 0, False, "left"),
                  "Value": (x + 2.54, y - 2.54, 0, False, "left")})
box(92.71, 96.52, 302.26, 177.8, "ADL5380 DEMODULATOR")

text("ADL5380 NOTES (DS Rev B)\n"
     "- VS 4.75–5.25 V on +5V_DEMOD; per-pin 100 pF C0G + 0.1 µF; budget ~250 mA (measure).\n"
     "- ENBL low = enabled (0R to GND). ADJ open for >5 GHz (DNP footprint to VS for IIP3 tuning).\n"
     "- RF: single-ended RX -> Johanson 5400BL15B050 balun -> series-resonant C0G DC blocks -> RFIP/RFIN.\n"
     "  Keep balun-to-pin traces < ~1.4 mm and symmetric.\n"
     "- LO: LO_P/LO_N already AC-coupled on MAX2871 sheet (C620/C621). No second DC block.\n"
     "- BB out: 50 Ω diff, CM ≈ VS-1.2 V with ADJ open. DNP diff load per pair. I/Q mapping: IHI(3)->I_P, ILO(4)->I_N,\n"
     "  QHI(16)->Q_P, QLO(15)->Q_N. RF: T701 pin 3 -> RX_BAL_P -> RFIP(22), pin 4 -> RX_BAL_N -> RFIN(21).\n"
     "  LO: LO_P -> LOIN(10), LO_N -> LOIP(9) (RF and LO polarity picked for crossing-free routing).\n"
     "  Swapping the I or the Q pair (not both) flips the Doppler sign;\n"
     "  swapping the RF or LO pair inverts I and Q together and does not.\n"
     "- EP: thermal vias + windowpane paste (layout).\n"
     "- +5V_RF comes from LDO303 (TPS7A8300, 5.0 V) on the Regulators sheet. Pin 12 NC: do not connect.",
     96.52, 184.15, just="left top")

WIRES[:], JUNCS[:] = finish_wires(  # set(): the ADL5380 GND/EP pins are stacked
    WIRES, sorted({pt for pins in PINPOS.values() for pt in pins.values()}),
    [r4(x, y) for _, x, y, *_ in LABELS] + [r4(x, y) for _, x, y, *_ in HLABELS])
emit_sheet("Receiver", "Receiver", "receiver.kicad_sch")

# ============================================================== MECHANICAL
for lst in (SYMS, WIRES, LABELS, JUNCS, NCS, TEXTS, RECTS, HLABELS):
    lst.clear()
PINPOS.clear()
BASE[0] = 1100
pwr_n[0] = flg_n[0] = 1100
for i in range(4):
    x = 38.1 + 20.32 * i
    H = place(f"MH{i + 1}", "Mechanical:MountingHole_Pad", x, 50.8, value="M3",
              fp="MountingHole:MountingHole_3.2mm_M3_Pad_Via",
              fields={"Reference": (x + 2.54, 48.26, 0, False, "left"), "Value": (x + 2.54, 50.8, 0, False, "left")})
    gnd(*H["1"])
box(25.4, 35.56, 116.84, 71.12, "MOUNTING")
text("M3 plated holes tied to GND, one per corner.", 27.94, 40.64)
text("Count and positions TBD at layout (4 placeholders).", 27.94, 43.18)
for i in range(3):  # JLC PCBA: top side, 1 mm copper / 2 mm mask
    x = 38.1 + 20.32 * i
    place(f"FID{i + 1}", "Mechanical:Fiducial", x, 93.98, value="Fiducial", fp="Fiducial:Fiducial_1mm_Mask2mm",
          fields={"Reference": (x + 2.54, 92.71, 0, False, "left"), "Value": (x + 2.54, 95.25, 0, False, "left")})
text("Top side, 1 mm copper / 2 mm mask (JLC PCBA).", 27.94, 86.36)
box(25.4, 81.28, 116.84, 109.22, "FIDUCIALS")
text("Shield-can frames: TBD at layout (RF zone: Synthesizer + Receiver).", 27.94, 127.0)
box(25.4, 116.84, 116.84, 137.16, "SHIELD CANS")
emit_sheet("Mechanical", "Mechanical", "mechanical.kicad_sch")

# ===================================================== MAIN-BOARD SHEETS (Part 2)
# Values and calculations: see the NOTES text on each sheet. Parts are DigiKey-stocked (digikey_parts.json).
TP_FP = "TestPoint:TestPoint_Pad_D1.0mm"


def new_sheet(base):
    for lst in (SYMS, WIRES, LABELS, JUNCS, NCS, TEXTS, RECTS, HLABELS):
        lst.clear()
    PINPOS.clear()
    BASE[0] = base
    pwr_n[0] = flg_n[0] = base


def done_sheet(sheet, title, file, also=()):
    WIRES[:], JUNCS[:] = finish_wires(
        WIRES, sorted({pt for pins in PINPOS.values() for pt in pins.values()}),
        [r4(x, y) for _, x, y, *_ in LABELS] + [r4(x, y) for _, x, y, *_ in HLABELS])
    emit_sheet(sheet, title, file, also)


def left_f(x, y):
    """Reference/value to the left of a vertical part."""
    return {"Reference": (x - 2.54, y - 1.27, 0, False, "right"), "Value": (x - 2.54, y + 1.27, 0, False, "right")}


def below_f(x, y):
    """Reference/value under a horizontal part."""
    return {"Reference": (x, y + 2.54, 0, False), "Value": (x, y + 5.08, 0, False)}


def tp(ref, x, y, value, rot=0, left=False):
    dx, dy = {0: (2.54, -5.08), 180: (2.54, 3.81), 90: (-2.54, -3.81), 270: (2.54, -3.81)}[rot]
    if left:
        dx = -dx
    just = "right" if (rot == 90) != left else "left"
    place(ref, "Connector:TestPoint", x, y, rot=rot, value=value, fp=TP_FP,
          fields={"Reference": (x + dx, y + dy, 0, False, just), "Value": (x + dx, y + dy + 2.54, 0, False, just)})


def rail_tp(ref, name, x, y):
    """Rail test point: power symbol up, test pad down, pins coincident."""
    rail(name, x, y)
    tp(ref, x, y, name, rot=180)


# ===================================================== BATTERY & CHARGER (2xx)
new_sheet(200)
# ----------------------------------------------------------------- USB-C INPUT
J = place("USB1", "cwradar:USB4105-GF-A", 38.1, 81.28,
          fields={"Reference": (22.86, 55.88, 0, False, "left"), "Value": (22.86, 58.42, 0, False, "left")})
assert J["A4"] == (53.34, 66.04) and J["B7"] == (53.34, 81.28) and J["SH"] == (30.48, 104.14), J
gnd(*J["A1"])
vpart("R1", "cwradar:0R", 30.48, 107.95, fields=left_f(30.48, 107.95))  # shell link, can be changed later
gnd(30.48, 111.76)
label("USB_SHIELD", 30.48, 104.14, 180, small=True)
NCS += [J["A8"], J["B8"]]
wire(J["A7"], J["B7"])
wire(J["A6"], J["B6"])
# data: connector side -> ESD2 flow-through (1->6, 3->4), as on the CR6 DAQ board
wire(J["B7"], (60.96, 81.28), (60.96, 111.76), (81.28, 111.76))
wire(J["B6"], (58.42, 86.36), (58.42, 114.3), (81.28, 114.3))
label("USBC_DN", 66.04, 111.76, 0, small=True)
label("USBC_DP", 66.04, 114.3, 0, small=True)
E = place("ESD2", "cwradar:USBLC6-2SC6", 86.36, 111.76,
          fields={"Reference": (91.44, 104.14, 0, False, "left"), "Value": (91.44, 106.68, 0, False, "left")})
rail("+VBUS", *E["5"])
gnd(*E["2"])
wire(E["6"], (134.62, 111.76))
hlabel("USB_D_N", 134.62, 111.76, 0, "bidirectional")
wire(E["4"], (134.62, 114.3))
hlabel("USB_D_P", 134.62, 114.3, 0, "bidirectional")
# BC1.2 taps to the charger, 0R so detection can be removed (keep stubs < 5 mm)
vpart("R2", "cwradar:0R_0402", 101.6, 107.95)
label("CHG_DN", 101.6, 104.14, 90)
vpart("R3", "cwradar:0R_0402", 106.68, 118.11)
label("CHG_DP", 106.68, 121.92, 270)
# CC: Rd 5.1k (sink only) + 10k series to the ESP32 ADC
E = place("ESD3", "cwradar:USBLC6-2SC6", 86.36, 71.12,
          fields={"Reference": (91.44, 63.5, 0, False, "left"), "Value": (91.44, 66.04, 0, False, "left")})
rail("+VBUS", *E["5"])
gnd(*E["2"])
wire(J["A5"], E["1"])
wire(J["B5"], E["3"])
label("USBC_CC1", 66.04, 71.12, 0, small=True)
label("USBC_CC2", 66.04, 73.66, 0, small=True)
wire(E["6"], (96.52, 71.12), (96.52, 58.42), (107.95, 58.42))
label("USB_CC1", 96.52, 64.77, 90, small=True)
vpart("R4", "cwradar:5k1", 101.6, 62.23)
gnd(101.6, 66.04)
hpart("R5", "cwradar:10k", 111.76, 58.42)
wire((115.57, 58.42), (124.46, 58.42))
hlabel("CC1_SENSE", 124.46, 58.42, 0, "output")
wire(E["4"], (99.06, 73.66), (99.06, 86.36), (110.49, 86.36))
label("USB_CC2", 99.06, 80.01, 90, small=True)
vpart("R6", "cwradar:5k1", 104.14, 90.17)
gnd(104.14, 93.98)
hpart("R7", "cwradar:10k", 114.3, 86.36)
wire((118.11, 86.36), (124.46, 86.36))
hlabel("CC2_SENSE", 124.46, 86.36, 0, "output")
# VBUS: TVS at the connector, flag, bus to the charger
CX, CY = 190.5, 76.2
wire(J["A4"], (58.42, 66.04), (58.42, 33.02), (170.18, 33.02), (170.18, 55.88), (175.26, 55.88))
rail("+VBUS", 58.42, 33.02)
D = place("D4", "cwradar:SMF6.5A", 66.04, 36.83, rot=270,
          fields={"Reference": (68.58, 35.56, 0, False, "left"), "Value": (68.58, 38.1, 0, False, "left")})
assert D["1"] == (66.04, 33.02), D
gnd(*D["2"])
flag(78.74, 33.02)
box(12.7, 22.86, 139.7, 129.54, "USB-C INPUT")

# -------------------------------------------------------------------- CHARGER
CH = place("CHG1", "cwradar:BQ25883RGET", CX, CY,
           fields={"Reference": (177.8, 50.8, 0, False, "left"), "Value": (177.8, 100.33, 0, False, "left")})
assert CH["23"] == (175.26, 55.88) and CH["21"] == (205.74, 55.88) and CH["19"] == (190.5, 99.06), CH
wire((170.18, 45.72), (165.1, 45.72))
vpart("C1", "cwradar:1u_25V", 165.1, 49.53, fields=left_f(165.1, 49.53))
gnd(165.1, 53.34)
label("CHG_DP", *CH["24"], 180)
label("CHG_DN", *CH["1"], 180)
hlabel("I2C_SDA", *CH["4"], 180, "bidirectional")
hlabel("I2C_SCL", *CH["5"], 180, "bidirectional")
wire(CH["6"], (152.4, 76.2))
hlabel("CHG_INT", 152.4, 76.2, 180, "output")
vpart("R8", "cwradar:10k", 160.02, 72.39, fields=left_f(160.02, 72.39))
rail("+3V3_D", 160.02, 68.58)
wire(CH["3"], (167.64, 81.28))  # /CE low: charging enabled, firmware controls it over I2C
gnd(167.64, 81.28)
label("CHG_PG", *CH["9"], 180)
label("CHG_STAT", *CH["2"], 180)
wire(CH["8"], (172.72, 93.98))
hpart("R9", "cwradar:392", 168.91, 93.98, fields=below_f(168.91, 93.98))
gnd(165.1, 93.98)
label("CHG_ILIM", 173.99, 93.98, 0, small=True)
gnd(*CH["19"])
NCS.append(CH["10"])
# boost power stage: PMID -> L -> SW (DS Fig. 8.2), BTST cap SW -> BTST
wire(CH["21"], (210.82, 55.88), (210.82, 40.64), (214.63, 40.64))
hpart("L1", "cwradar:1uH", 218.44, 40.64)
wire((222.25, 40.64), (226.06, 40.64), (226.06, 60.96), CH["17"])
wire((210.82, 40.64), (200.66, 40.64))
vpart("C2", "cwradar:10u_25V", 200.66, 44.45, fields=left_f(200.66, 44.45))
gnd(200.66, 48.26)
label("CHG_PMID", 210.82, 50.8, 90, small=True)
label("CHG_SW", 226.06, 50.8, 90, small=True)
wire(CH["12"], (213.36, 68.58))
vpart("C3", "cwradar:47n", 213.36, 64.77)
label("CHG_BTST", 208.28, 68.58, 0, small=True)
# SYS 4 x 22u, BAT 2 x 22u (>= 44 uF / >= 10 uF effective after DC bias)
wire(CH["15"], (231.14, 73.66), (231.14, 45.72), (264.16, 45.72))
rail("+VSYS", 231.14, 45.72)
for i, x in enumerate([241.3, 248.92, 256.54, 264.16]):
    vpart(f"C{4 + i}", "cwradar:22u_25V", x, 49.53)
    gnd(x, 53.34)
wire(CH["13"], (264.16, 78.74))
rail("+VBAT", 236.22, 78.74)
for i, x in enumerate([256.54, 264.16]):
    vpart(f"C{8 + i}", "cwradar:22u_25V", x, 82.55)
    gnd(x, 86.36)
# REGN, TS divider (RT1 REGN-TS, RT2 TS-GND, NTC TS-GND)
wire(CH["11"], (236.22, 83.82))
vpart("R10", "cwradar:5k23", 213.36, 87.63)
vpart("C10", "cwradar:4u7_25V", 223.52, 87.63)
gnd(223.52, 91.44)
label("CHG_REGN", 236.22, 83.82, 0)
wire(CH["7"], (213.36, 91.44))
wire((209.55, 91.44), (209.55, 104.14), (243.84, 104.14))
label("CHG_TS", 209.55, 97.79, 90, small=True)
vpart("R11", "cwradar:30k1", 220.98, 107.95)
gnd(220.98, 111.76)
place("RT1", "cwradar:10k_NTC", 231.14, 107.95,
      fields={"Reference": (233.68, 106.68, 0, False, "left"), "Value": (233.68, 109.22, 0, False, "left")})
gnd(231.14, 111.76)
JT = place("J3", "cwradar:PH_2P", 248.92, 104.14, dnp=True,
           fields={"Reference": (251.46, 101.6, 0, False, "left"), "Value": (251.46, 109.22, 0, False, "left")})
assert JT["1"] == (243.84, 104.14), JT
gnd(*JT["2"])
text("RT201 and J203 are alternatives — populate one.\nJ203: external 10k NTC taped to the pack.", 210.82, 116.84, just="left top")
box(144.78, 22.86, 274.32, 121.92, "CHARGER")

# ------------------------------------------------------------- BATTERY INPUT
JB = place("J1", "cwradar:XH_2P", 25.4, 160.02, mirror=True,
           fields={"Reference": (22.86, 154.94, 0, False, "right"), "Value": (22.86, 157.48, 0, False, "right")})
assert JB["1"] == (30.48, 160.02) and JB["2"] == (30.48, 162.56), JB
wire(JB["2"], (30.48, 165.1))
gnd(30.48, 165.1)
hpart("F1", "cwradar:3A_FAST", 38.1, 160.02)
wire(JB["1"], (34.29, 160.02))
Q = place("Q1", "cwradar:AO3401A", 50.8, 162.56, rot=90,
          fields={"Reference": (53.34, 167.64, 0, False, "left"), "Value": (53.34, 170.18, 0, False, "left")})
assert Q["3"] == (45.72, 160.02) and Q["2"] == (55.88, 160.02) and Q["1"] == (50.8, 167.64), Q
wire((41.91, 160.02), Q["3"])
wire(Q["2"], (63.5, 160.02))
rail("+VBAT", 63.5, 160.02)
vpart("R12", "cwradar:100k", 50.8, 171.45, fields=left_f(50.8, 171.45))
gnd(50.8, 175.26)
label("BATT_IN", 31.75, 160.02, 0, small=True)
label("BATT_FUSED", 43.18, 160.02, 0, small=True)
label("BATT_GATE", 50.8, 167.64, 180, small=True)
text("Generic pack leads vary in polarity — verify pin 1 = + before connecting.\n"
     "Pack has a built-in BMS: no on-board cell protection, no VBAT divider (BQ25883 ADC reads VBAT/VSYS).\n"
     "Q201: drain to F201, source to +VBAT; body-diode anode toward J201.\n"
     "Correct polarity: VGS = -VBAT (-6 to -8.4 V, inside ±12 V), on both ways. Reversed: off, diode blocks.",
     15.24, 180.34, just="left top")
box(12.7, 142.24, 139.7, 200.66, "BATTERY INPUT")

# ---------------------------------------------------------------- CHARGE LED
label("CHG_REGN", 157.48, 139.7, 180)
wire((157.48, 139.7), (161.29, 139.7))
hpart("R13", "cwradar:1k5", 165.1, 139.7)
place("D1", "cwradar:LED_ORG", 172.72, 139.7, rot=180,
      fields={"Reference": (172.72, 134.62, 0, False), "Value": (172.72, 144.78, 0, False)})
wire((176.53, 139.7), (182.88, 139.7))
label("CHG_STAT", 182.88, 139.7, 0)
label("CHG_LED_A", 168.91, 139.7, 0, small=True)
text("Amber, lights only with USB present (REGN on).\n(5.0 - 1.9) V / 1k5 = ~2 mA. STAT sinks <= 6 mA, abs max 6 V.",
     147.32, 147.32, just="left top")
box(144.78, 127.0, 205.74, 172.72, "CHARGE LED")

# --------------------------------------------------------------- TEST POINTS
for i, name in enumerate(["+VBUS", "+VBAT", "+VSYS"]):
    rail_tp(f"TP{3 + i}", name, 215.9 + 15.24 * i, 139.7)
wire((231.14, 139.7), (231.14, 152.4), (238.76, 152.4))
flag(238.76, 152.4)  # +VBAT: pack, Q201 and BAT pins are all passive
tp("TP6", 264.16, 139.7, "GND")
gnd(264.16, 139.7)
for ref, net, x in [("TP1", "CHG_INT", 223.52), ("TP2", "CHG_PG", 248.92)]:
    label(net, x - 7.62, 160.02, 180)
    wire((x - 7.62, 160.02), (x, 160.02))
    tp(ref, x, 160.02, net)
box(210.82, 127.0, 274.32, 172.72, "TEST POINTS")

text("CHARGER NOTES (BQ25883 SLUSDL3A)\n"
     "- ILIM: IINMAX = KILIM / RILIM (Eq. 3). KILIM 1012 / 1098 / 1185 (min/typ/max).\n"
     "  RILIM = 392R -> 2.58 / 2.80 / 3.02 A: worst case stays at the 3.0 A USB-C cap. Firmware sets IINDPM per CC1/CC2_SENSE.\n"
     "- TS: DS 8.3.7.4.1 Eq. 1-2 for 103AT, 0-60 C: RT1 = 5.24k -> 5.23k (REGN-TS), RT2 = 30.31k -> 30.1k (TS-GND).\n"
     "- VBUS 1u (C201) + PMID 10u (C202): 11 uF nominal, < 10 uF after DC bias at 5 V (USB-C cSnkBulk).\n"
     "- SYS 4 x 22u 25V 1206: ~11-12 uF each at 8.6 V -> >= 44 uF effective. BAT 2 x 22u (>= 10 uF effective).\n"
     "- L201 1 uH: Isat 7.4 A >= IIN + ripple/2 = 3.0 + 1.35/2 = 3.7 A (Eq. 5-6, 1.5 MHz). BTST 47n, REGN 4.7u.\n"
     "- /CE low (charging on, firmware gates it over I2C). OTG stays disabled: sink-only board.\n"
     "- I2C pull-ups live on the MCU sheet. /INT pull-up R208 here.",
     144.78, 177.8, just="left top")
done_sheet("Battery_Charger", "Battery & Charger", "battery_charger.kicad_sch")


# ============================================================ REGULATORS (3xx)
new_sheet(300)


def buck(n, by, rt, rtop, rbot, ind, out_rail, refs, title):
    """TPS62933F at (50.8, by). refs: C_in10u C_in100n C_ss R_rt C_bst L R_top R_bot C_out1 C_out2."""
    cin, cin2, css, rrt, cbst, lref, rt_ref, rb_ref, co1, co2 = refs
    B = place(f"BUCK{n}", "cwradar:TPS62933FDRLR", 50.8, by,
              fields={"Reference": (45.72, by - 12.7, 0, False, "left"), "Value": (45.72, by - 10.16, 0, False, "left")})
    assert B["3"] == r4(43.18, by - 7.62) and B["8"] == r4(58.42, by + 7.62), B
    wire(B["3"], (40.64, by - 7.62), (40.64, by - 20.32), (25.4, by - 20.32))
    rail("+VSYS", 40.64, by - 20.32)
    vpart(cin, "cwradar:10u_25V", 25.4, by - 16.51, fields=left_f(25.4, by - 16.51))
    gnd(25.4, by - 12.7)
    vpart(cin2, "cwradar:100n", 33.02, by - 16.51)
    gnd(33.02, by - 12.7)
    label("EN_BUCK", *B["2"], 180)
    wire(B["7"], (27.94, by + 2.54))
    vpart(css, "cwradar:22n", 27.94, by + 6.35, fields=left_f(27.94, by + 6.35))
    gnd(27.94, by + 10.16)
    wire(B["1"], (38.1, by + 5.08))
    vpart(rrt, rt, 38.1, by + 8.89, fields=left_f(38.1, by + 8.89))
    gnd(38.1, by + 12.7)
    label(f"BUCK{n}_SS", 31.75, by + 2.54, 0, small=True)
    label(f"BUCK{n}_RT", 39.37, by + 5.08, 0, small=True)
    gnd(*B["4"])
    wire(B["6"], (63.5, by - 7.62))
    vpart(cbst, "cwradar:100n", 63.5, by - 3.81)
    label(f"BUCK{n}_BST", 59.69, by - 7.62, 0, small=True)
    wire(B["5"], (69.85, by))
    hpart(lref, ind, 73.66, by)
    wire((77.47, by), (106.68, by))
    label(f"BUCK{n}_SW", 64.77, by, 0, small=True)
    wire(B["8"], (81.28, by + 7.62))
    vpart(rt_ref, rtop, 81.28, by + 3.81)
    vpart(rb_ref, rbot, 76.2, by + 11.43, fields=left_f(76.2, by + 11.43))
    gnd(76.2, by + 15.24)
    label(f"BUCK{n}_FB", 66.04, by + 7.62, 0, small=True)
    for cref, x in [(co1, 91.44), (co2, 99.06)]:
        vpart(cref, "cwradar:22u_25V", x, by + 3.81)
        gnd(x, by + 7.62)
    rail(out_rail, 106.68, by)
    box(12.7, by - 27.94, 114.3, by + 27.94, title)


buck(1, 53.34, "cwradar:51k1", "cwradar:60k4", "cwradar:10k", "cwradar:10uH", "+VPRE",
     ["C1", "C2", "C3", "R2", "C4", "L1", "R3", "R4", "C5", "C6"], "5V6 PRE-BUCK")
buck(2, 129.54, "cwradar:20k5", "cwradar:31k6", "cwradar:10k", "cwradar:6u8H", "+3V3_D",
     ["C7", "C8", "C9", "R5", "C10", "L2", "R6", "R7", "C11", "C12"], "3V3 DIGITAL BUCK")

# --------------------------------------------------------------------- ENABLE
EY = 177.8  # EN_BUCK node row
rail("+VSYS", 25.4, EY - 7.62)
vpart("R8", "cwradar:113k", 25.4, EY - 3.81, fields=left_f(25.4, EY - 3.81))
vpart("R9", "cwradar:30k9", 25.4, EY + 3.81, fields=left_f(25.4, EY + 3.81))
gnd(25.4, EY + 7.62)
S = place("SW1", "cwradar:SW_SLIDE", 53.34, EY,
          fields={"Reference": (53.34, EY - 7.62, 0, False), "Value": (53.34, EY + 7.62, 0, False)})
assert S["2"] == r4(48.26, EY) and S["1"] == r4(58.42, EY - 2.54) and S["3"] == r4(58.42, EY + 2.54), S
wire((25.4, EY), S["2"])
label("EN_BUCK", 35.56, EY, 0)
tp("TP1", 30.48, EY, "EN_BUCK")
wire(S["1"], (63.5, EY - 2.54))
gnd(63.5, EY - 2.54)
NCS.append(S["3"])
text("OFF", 60.96, EY - 3.81, size=1.27)
text("ON (open)", 60.96, EY + 5.08, size=1.27)
text("SW301 only switches EN_BUCK (no load current); charging continues when OFF.\n"
     "EN divider, both EN pins in parallel (Ip, Ih doubled), DS Eq. 3-5:\n"
     "R1 = 113k, R2 = 30.9k -> start 5.48 V, stop 4.97 V; VEN at 8.8 V = 2.0 V (< 5.5 V, abs max 6 V).",
     15.24, EY + 15.24, just="left top")
box(12.7, EY - 15.24, 114.3, EY + 35.56, "BUCK ENABLE")


def ldo(n, x0, y0, out_rail, mode, refs, title):
    """TPS7A8300 block. mode 'adj' (5.0 V, 105k/20k 0.1%) or 'anyout33' (1.6 V + 800 mV + 100 mV)."""
    lx, ly = x0 + 40.64, y0 + 27.94
    cin, cin2, cnr, r1, cff, r2, cout, tp_out, tp_pg = refs
    L = place(f"LDO{n}", "cwradar:TPS7A8300RGRR", lx, ly,
              fields={"Reference": (lx - 10.16, ly - 15.24, 0, False, "left"), "Value": (lx + 15.24, ly + 15.24, 0, False, "left")})
    assert L["15"] == r4(lx - 12.7, ly - 10.16) and L["3"] == r4(lx + 12.7, ly - 2.54) and L["8"] == r4(lx, ly + 22.86), L
    wire(L["15"], (lx - 20.32, ly - 10.16), (lx - 20.32, ly - 20.32), (lx - 35.56, ly - 20.32))
    rail("+VPRE", lx - 20.32, ly - 20.32)
    vpart(cin, "cwradar:10u", lx - 27.94, ly - 16.51)
    gnd(lx - 27.94, ly - 12.7)
    vpart(cin2, "cwradar:100n", lx - 35.56, ly - 16.51)
    gnd(lx - 35.56, ly - 12.7)
    if n == 6:
        hlabel("EN_ANALOG", *L["14"], 180, "input")  # 100k pulldown on the MCU sheet: LNA starts off
    else:
        wire(L["14"], (lx - 15.24, ly - 5.08), (lx - 15.24, ly - 10.16))
    NCS.append(L["12"])  # BIAS open: VIN >= 1.4 V (DS 7.4.2)
    wire(L["13"], (lx - 22.86, ly))
    vpart(cnr, "cwradar:10n", lx - 22.86, ly + 3.81, fields=left_f(lx - 22.86, ly + 3.81))
    gnd(lx - 22.86, ly + 7.62)
    label(f"LDO{n}_NR", lx - 19.05, ly, 0, small=True)
    wire(L["1"], (lx + 48.26, ly - 10.16))
    rail(out_rail, lx + 30.48, ly - 10.16)
    vpart(cout, "cwradar:47u_10V", lx + 43.18, ly - 6.35)
    gnd(lx + 43.18, ly - 2.54)
    tp(tp_out, lx + 48.26, ly - 10.16, out_rail, left=True)
    if out_rail != "+3V3_SYN":  # +3V3_SYN is flagged on the synthesizer sheet
        flag(lx + 20.32, ly - 10.16)
    vpart(cff, "cwradar:10n", lx + 25.4, ly - 6.35)
    if mode == "adj":
        NCS.extend(L[p] for p in ["5", "6", "7", "9", "10", "11", "2"])  # ANY-OUT open, SNS open
        vpart(r1, "cwradar:105k_0p1", lx + 17.78, ly - 6.35)
        wire(L["3"], (lx + 33.02, ly - 2.54))
        vpart(r2, "cwradar:20k_0p1", lx + 33.02, ly + 1.27)
        gnd(lx + 33.02, ly + 5.08)
    else:
        NCS.extend(L[p] for p in ["5", "7", "9"])
        for p in ["6", "10", "11"]:  # 100 mV + 800 mV + 1.6 V to GND: 0.8 + 2.5 = 3.3 V
            wire(L[p], (lx - 15.24, L[p][1]))
        wire((lx - 15.24, ly + 7.62), (lx - 15.24, ly + 20.32))
        gnd(lx - 15.24, ly + 20.32)
        wire(L["2"], (lx + 15.24, ly - 5.08), (lx + 15.24, ly - 10.16))  # SNS to OUT
        wire(L["3"], (lx + 25.4, ly - 2.54))
    label(f"LDO{n}_FB", lx + 29.21 if mode == "adj" else lx + 19.05, ly - 2.54, 0, small=True)
    tp(tp_pg, *L["4"], "PG", rot=270)
    label(f"LDO{n}_PG", *L["4"], 0, small=True)
    gnd(*L["8"])
    box(x0, y0, x0 + 92.71, y0 + 68.58, title)


ldo(3, 121.92, 25.4, "+5V_RF", "adj", ["C13", "C14", "C15", "R10", "C16", "R11", "C17", "TP2", "TP3"],
    "+5V_RF LDO (ADL5380)")
ldo(4, 217.17, 25.4, "+5V_A", "adj", ["C18", "C19", "C20", "R12", "C21", "R13", "C22", "TP4", "TP5"],
    "+5V_A LDO (BASEBAND + ADC)")
ldo(5, 312.42, 25.4, "+3V3_SYN", "anyout33", ["C23", "C24", "C25", None, "C26", None, "C27", "TP6", "TP7"],
    "+3V3_SYN LDO (MAX2871)")
ldo(6, 121.92, 101.6, "+V_LNA", "adj", ["C28", "C29", "C30", "R14", "C31", "R15", "C32", "TP8", "TP9"],
    "+V_LNA LDO (ANTENNA BOARD)")

# ------------------------------------------------------------------ LNA POWER
rail("+V_LNA", 228.6, 119.38)
wire((228.6, 119.38), (234.95, 119.38))
hpart("R1", "cwradar:0R", 238.76, 119.38, extra={"Note": "0R 0603: footprint for a ferrite or a few ohms later."})
wire((242.57, 119.38), (271.78, 119.38))
label("LNA_5V", 246.38, 119.38, 0, small=True)
vpart("C33", "cwradar:10u", 254.0, 123.19)
gnd(254.0, 127)
vpart("C34", "cwradar:1u_25V", 261.62, 123.19)
gnd(261.62, 127)
JL = place("J1", "cwradar:PH_2P", 276.86, 119.38, extra={"Silk": "LNA 5V"},
           fields={"Reference": (279.4, 116.84, 0, False, "left"), "Value": (279.4, 124.46, 0, False, "left")})
assert JL["1"] == (271.78, 119.38), JL
gnd(*JL["2"])
text("J301 pin 1 = +V_LNA, pin 2 = GND. Silk: \"LNA 5V\". Place beside the RX connector.", 220.98, 137.16)
box(217.17, 101.6, 309.88, 170.18, "LNA POWER")

# --------------------------------------------------------------- TEST POINTS
for i, name in enumerate(["+VPRE", "+3V3_D"]):
    x = 325.12 + 25.4 * i
    rail_tp(f"TP{10 + i}", name, x, 121.92)
    wire((x, 121.92), (x + 12.7, 121.92))
    flag(x + 12.7, 121.92)  # outputs come through inductors: flag the rails for ERC
box(312.42, 101.6, 405.13, 170.18, "TEST POINTS")

text("REGULATOR NOTES (TPS62933F SLUSEA4D, TPS7A8300 SBVS197F)\n"
     "- FB: VOUT = 0.8 V x (1 + Rtop/Rbot). BUCK301 60.4k/10.0k = 5.63 V; BUCK302 31.6k/10.0k = 3.33 V (TI start 10.2k).\n"
     "- fSW: RT from Eq. 2, fSW = 17293 x RT^-0.942. BUCK302 RT 20.5k = 1.0 MHz.\n"
     "  BUCK301: Eq. 10 VIN_MIN = VOUT / (1 - fSW x tOFF_MIN 140 ns) = 6.51 V at 1 MHz > 6.2 V, so 1 MHz fails.\n"
     "  With losses D = (5.63 + 1.0 x (32m + 85m)) / (6.2 - 76m + 32m) = 0.934 -> fSW <= 474 kHz. RT 51.1k = 425 kHz (Dmax 0.940).\n"
     "- L: Eq. 16 at VIN 8.8 V. BUCK301 10 uH (K 0.48 at 8.8 V, 0.32 at 7.4 V; chosen for low DCR at 6.2 V dropout),\n"
     "  peak 1.24 A, Isat 3.5 A. BUCK302 6.8 uH at 1 MHz: K 0.38, peak 0.95 A, Isat 3 A.\n"
     "- SS: tSS = CSS x 0.8 V / 5.5 uA: 22n -> 3.2 ms. BST 100n 50V. CIN 10u 25V + 100n. COUT 2 x 22u 25V 1206.\n"
     "- LDOs (U303-U306): VIN +VPRE 5.63 V, BIAS open, NR/SS 10n, CIN 10u + 100n, COUT 47u 10V (>= 10 uF effective).\n"
     "  Adjustable (5.0 V, range 0.8-5.0 V): R1 105k / R2 20.0k 0.1% (DS Table 3), Vout = 0.8 x (1 + 105/20) = 5.00 V,\n"
     "  divider current 40 uA (> 5 uA). CFF 10n FB-OUT. ANY-OUT pins open, SNS open.\n"
     "  LDO305: ANY-OUT 1.6 V + 800 mV + 100 mV to GND (0.8 + 2.5 = 3.3 V, max 3.95 V), SNS to OUT, CFF 10n (DS low-noise).\n"
     "  PG open-drain to test pads only (add a probe pull-up); DS: CFF may disrupt PG.\n"
     "- LDO305 dissipation (5.63 - 3.3) V x 0.2 A = 0.47 W: thermal vias to L2.",
     124.46, 177.8, just="left top")
done_sheet("Regulators", "Regulators", "regulators.kicad_sch")


# ================================================================== MCU (4xx)
new_sheet(400)
MX, MY = 190.5, 127.0
M = place("MCU1", "cwradar:ESP32-S3-WROOM-1-N16R2", MX, MY,
          fields={"Reference": (177.8, 96.52, 0, False, "left"), "Value": (193.04, 160.02, 0, False, "left")})
assert M["3"] == (175.26, 104.14) and M["25"] == (205.74, 149.86) and M["2"] == (190.5, 99.06), M
wire(M["2"], (190.5, 88.9), (210.82, 88.9))
rail("+3V3_D", 190.5, 88.9)
vpart("C1", "cwradar:22u_25V", 200.66, 92.71)
gnd(200.66, 96.52)
vpart("C2", "cwradar:100n", 210.82, 92.71)
gnd(210.82, 96.52)
gnd(*M["1"])
# left: EN, IO0-IO16
label("ESP_EN", *M["3"], 180)
label("ESP_BOOT", *M["27"], 180)
for pin, net, shape in [("39", "CC1_SENSE", "input"), ("38", "CC2_SENSE", "input"),
                        ("4", "SYN_SCK", "output"), ("5", "SYN_MOSI", "output"), ("6", "SYN_MISO", "input"),
                        ("7", "SYN_LE", "output"), ("12", "I2C_SDA", "bidirectional"),
                        ("17", "I2C_SCL", "bidirectional"), ("18", "CHG_INT", "input"), ("19", "BTN1", "input"),
                        ("8", "SYN_CE", "output"), ("9", "SYN_RFOUT_EN", "output"),
                        ("10", "SYN_LD", "input"), ("11", "BTN2", "input"), ("23", "I2S_DOUT", "input"),
                        ("31", "DISP_SCK", "output"), ("32", "DISP_MOSI", "output"), ("33", "DISP_CS", "output"),
                        ("34", "DISP_DC", "output"), ("35", "DISP_RST", "output"), ("16", "STATUS_LED", "output"),
                        ("24", "DISP_BL", "output"), ("25", "EN_ANALOG", "output")]:
    px, py = M[pin]
    hlabel(net, px, py, 180 if px < MX else 0, shape)
for pin, net in [("20", "ESP_MCLK"), ("21", "ESP_BCK"), ("22", "ESP_LRCK")]:
    label(net, *M[pin], 180)
for pin, net in [("37", "ESP_TXD0"), ("36", "ESP_RXD0"), ("13", "ESP_DN"), ("14", "ESP_DP")]:
    label(net, *M[pin], 0)
NCS.extend(M[p] for p in ["15", "26", "28", "29", "30"])  # IO3, IO45 straps unused; IO35-37 spare on N16R2
text("Straps: GPIO0 BOOT (pull-up + SW402), GPIO3 and GPIO45 unused (no pull-up),\n"
     "GPIO46 = STATUS_LED (LED + R to GND only: reads low at boot). GPIO26-32 are not module pins.\n"
     "N16R2 (quad PSRAM): GPIO35-37 are free spares (NC). Pad-JTAG GPIO39-42 used: debug via USB-JTAG.",
     134.62, 167.64, just="left top")
box(132.08, 81.28, 248.92, 187.96, "ESP32-S3")

# --------------------------------------------------------------- RESET / BOOT
for y, net, sw, rpu, extra_c, tpref, tpval in [(96.52, "ESP_EN", "SW1", "R1", "C3", "TP1", "EN"),
                                              (124.46, "ESP_BOOT", "SW2", "R2", None, "TP2", "BOOT")]:
    wire((55.88, y), (106.68, y))
    label(net, 106.68, y, 0)
    vpart(rpu, "cwradar:10k", 86.36, y - 3.81, fields=left_f(86.36, y - 3.81))
    rail("+3V3_D", 86.36, y - 7.62)
    if extra_c:
        vpart(extra_c, "cwradar:1u", 73.66, y + 3.81, fields=left_f(73.66, y + 3.81))
        gnd(73.66, y + 7.62)
    place(sw, "cwradar:SW_TACT", 55.88, y + 5.08, rot=90,
          fields={"Reference": (52.07, y + 3.81, 0, False, "right"), "Value": (52.07, y + 6.35, 0, False, "right")})
    gnd(55.88, y + 10.16)
    tp(tpref, 96.52, y, tpval)
text("SW401 = EN (reset), SW402 = BOOT (GPIO0).", 15.24, 86.36)
box(12.7, 81.28, 127.0, 147.32, "RESET / BOOT")

# ----------------------------------------------------------------------- USB
for y, esp, net in [(160.02, "ESP_DN", "USB_D_N"), (167.64, "ESP_DP", "USB_D_P")]:
    label(esp, 25.4, y, 180)
    wire((25.4, y), (46.99, y))
    hpart(f"R{3 if net == 'USB_D_N' else 4}", "cwradar:0R_0402", 50.8, y)
    wire((54.61, y), (76.2, y))
    hlabel(net, 76.2, y, 0, "bidirectional")
text("GPIO19 = D-, GPIO20 = D+. 0R near the module (22R later if needed).", 15.24, 156.21)
box(12.7, 152.4, 127.0, 182.88, "USB")

# ---------------------------------------------------------------- I2S SERIES
for i, (esp, net) in enumerate([("ESP_MCLK", "I2S_MCLK"), ("ESP_BCK", "I2S_BCK"), ("ESP_LRCK", "I2S_LRCK")]):
    y = 195.58 + 7.62 * i
    label(esp, 25.4, y, 180)
    wire((25.4, y), (46.99, y))
    hpart(f"R{5 + i}", "cwradar:33", 50.8, y)
    wire((54.61, y), (76.2, y))
    hlabel(net, 76.2, y, 0, "output")
text("33R source termination at the ESP32. MCLK = GPIO12, BCK = GPIO13, LRCK = GPIO14.", 15.24, 220.98)
box(12.7, 187.96, 127.0, 233.68, "I2S SERIES")

# ------------------------------------------------- I2C PULL-UPS / EN_ANALOG
for i, net in enumerate(["I2C_SDA", "I2C_SCL"]):
    x = 266.7 + 12.7 * i
    rail("+3V3_D", x, 91.44)
    vpart(f"R{8 + i}", "cwradar:4k7", x, 95.25)
    label(net, x, 99.06, 270)
vpart("R10", "cwradar:100k", 304.8, 95.25)
label("EN_ANALOG", 304.8, 91.44, 90)
gnd(304.8, 99.06)
text("4k7 I2C pull-ups (charger + display header): the only ones.\nEN_ANALOG 100k pull-down: LNA starts off.",
     256.54, 111.76, just="left top")
box(254.0, 81.28, 335.28, 129.54, "PULL-UPS / PULL-DOWNS")

# -------------------------------------------------------------- UART TEST PADS
for i, (net, val) in enumerate([("ESP_TXD0", "TXD0"), ("ESP_RXD0", "RXD0")]):
    y = 144.78 + 7.62 * i
    label(net, 264.16, y, 180)
    wire((264.16, y), (276.86, y))
    tp(f"TP{3 + i}", 276.86, y, val)
text("UART0: TX GPIO43, RX GPIO44.", 289.56, 149.86)
box(254.0, 134.62, 335.28, 172.72, "UART0")
done_sheet("MCU", "MCU", "mcu.kicad_sch")


# ============================================================= USER I/O (5xx)
new_sheet(500)
# ------------------------------------------------------------ DISPLAY SERIES
for i, net in enumerate(["DISP_SCK", "DISP_MOSI", "DISP_CS", "DISP_DC", "DISP_RST", "DISP_BL"]):
    y = 40.64 + 7.62 * i
    hlabel(net, 25.4, y, 180, "input")
    wire((25.4, y), (36.83, y))
    hpart(f"R{1 + i}", "cwradar:33", 40.64, y)
    wire((44.45, y), (58.42, y))
    label(f"{net}_H", 58.42, y, 0)
text("33R in the line toward the header. Place at the ESP32 end.", 15.24, 35.56)
box(12.7, 30.48, 81.28, 91.44, "DISPLAY SERIES")

# ------------------------------------------------------------ DISPLAY HEADER
JH = place("J1", "cwradar:BOX_2x05", 132.08, 60.96,
           fields={"Reference": (129.54, 50.8, 0, False, "left"), "Value": (129.54, 71.12, 0, False, "left")})
assert JH["1"] == (127.0, 55.88) and JH["2"] == (139.7, 55.88), JH
wire(JH["1"], (121.92, 55.88), (121.92, 40.64), (101.6, 40.64))
rail("+3V3_D", 121.92, 40.64)
vpart("C1", "cwradar:10u", 101.6, 44.45)
gnd(101.6, 48.26)
vpart("C2", "cwradar:100n", 111.76, 44.45)
gnd(111.76, 48.26)
wire(JH["2"], (162.56, 55.88))
gnd(162.56, 55.88)
for pin, net in [("3", "DISP_SCK_H"), ("5", "DISP_CS_H"), ("7", "DISP_RST_H")]:
    label(net, *JH[pin], 180)
for pin, net in [("4", "DISP_MOSI_H"), ("6", "DISP_DC_H"), ("8", "DISP_BL_H")]:
    label(net, *JH[pin], 0)
hlabel("I2C_SDA", *JH["9"], 180, "bidirectional")
hlabel("I2C_SCL", *JH["10"], 0, "bidirectional")
text("J501 2x5 shrouded: 1 +3V3_D, 2 GND, 3 SCK, 4 MOSI,\n5 CS, 6 DC, 7 RST, 8 BL, 9 SDA, 10 SCL.", 88.9, 76.2, just="left top")
box(86.36, 30.48, 177.8, 91.44, "DISPLAY HEADER")

# -------------------------------------------------------------------- BUTTONS
for i, net in enumerate(["BTN1", "BTN2"]):
    y = 111.76 + 25.4 * i
    hlabel(net, 25.4, y, 180, "output")
    wire((25.4, y), (60.96, y))
    vpart(f"R{7 + i}", "cwradar:10k", 48.26, y - 3.81)
    rail("+3V3_D", 48.26, y - 7.62)
    vpart(f"C{3 + i}", "cwradar:100n", 38.1, y + 3.81, fields=left_f(38.1, y + 3.81))
    gnd(38.1, y + 7.62)
    place(f"SW{1 + i}", "cwradar:SW_TACT", 60.96, y + 5.08, rot=90,
          fields={"Reference": (63.5, y + 3.81, 0, False, "left"), "Value": (63.5, y + 6.35, 0, False, "left")})
    gnd(60.96, y + 10.16)
text("10k pull-up, 100n debounce (tau 1 ms), switch to GND.", 15.24, 152.4)
box(12.7, 99.06, 81.28, 165.1, "BUTTONS")

# ----------------------------------------------------------------------- LEDS
for x, top, ref_r, rval, ref_d, led, extra in [(101.6, "rail", "R9", "cwradar:1k5", "D1", "cwradar:LED_GRN", None),
                                               (121.92, "STATUS_LED", "R10", "cwradar:680", "D2", "cwradar:LED_YEL", None),
                                               (147.32, "rail", "R11", "cwradar:680", "D3", "cwradar:LED_RED", {"Silk": "TX"})]:
    if top == "rail":
        rail("+3V3_D", x, 106.68)
    else:
        hlabel(top, x, 106.68, 90, "input")
    vpart(ref_r, rval, x, 110.49)
    place(ref_d, led, x, 118.11, rot=90, extra=extra,
          fields={"Reference": (x + 2.54, 116.84, 0, False, "left"), "Value": (x + 2.54, 119.38, 0, False, "left")})
    label({"D1": "LED_PWR_A", "D2": "LED_STAT_A", "D3": "LED_TX_A"}[ref_d], x, 114.3, 0, small=True)
    if ref_d != "D3":
        gnd(x, 121.92)
Q = place("Q1", "cwradar:2N7002K", 144.78, 127.0,
          fields={"Reference": (149.86, 125.73, 0, False, "left"), "Value": (149.86, 128.27, 0, False, "left")})
assert Q["3"] == (147.32, 121.92) and Q["1"] == (139.7, 127.0), Q
gnd(*Q["2"])
label("LED_TX_K", 147.32, 121.92, 0, small=True)
wire(Q["1"], (132.08, 127.0))
hlabel("SYN_RFOUT_EN", 132.08, 127.0, 180, "input")
text("D501 power  (3.3 - 1.9) / 1k5 = 0.9 mA\nD502 status (3.3 - 1.9) / 680 = 2.1 mA (GPIO46)\n"
     "D503 TX ENABLED: Q501 buffers SYN_RFOUT_EN, 2.1 mA. Silk \"TX\".", 88.9, 139.7, just="left top")
box(86.36, 99.06, 177.8, 165.1, "STATUS LEDS")
done_sheet("User_IO", "User I/O", "user_io.kicad_sch")


# ================================================ BASEBAND (8xx I, 9xx Q)
new_sheet(800)
MATCH = {"Matched": "I/Q"}
# ------------------------------------------------- input coupling, bias, RFI
for y, port, cref, bref, rref, cm in [(76.2, "IN_P", "C1", "R1", "R3", "C3"),
                                      (91.44, "IN_N", "C2", "R2", "R4", "C4")]:
    hlabel(port, 25.4, y, 180, "input")
    wire((25.4, y), (34.29, y))
    hpart(cref, "cwradar:470n_C0G", 38.1, y, extra=MATCH)
    wire((41.91, y), (54.61, y))
    if port == "IN_P":
        vpart(bref, "cwradar:100k", 48.26, y - 3.81, extra=MATCH)
        label("VREF_BUF", 48.26, y - 7.62, 90)
        vpart(cm, "cwradar:470p_C0G", 68.58, y + 3.81, extra=MATCH)
        gnd(68.58, y + 7.62)
    else:
        vpart(bref, "cwradar:100k", 48.26, y + 3.81, extra=MATCH)
        label("VREF_BUF", 48.26, y + 7.62, 270)
        vpart(cm, "cwradar:470p_C0G", 68.58, y + 3.81, extra=MATCH)
        gnd(68.58, y + 7.62)
    hpart(rref, "cwradar:1k", 58.42, y, extra=MATCH)
    wire((62.23, y), (91.44, y))
label("BB_INP", 44.45, 76.2, 0, small=True)
label("BB_INN", 44.45, 91.44, 0, small=True)
label("BB_RFIP", 72.39, 76.2, 0, small=True)
label("BB_RFIN", 72.39, 91.44, 0, small=True)
wire((78.74, 76.2), (78.74, 80.01))
vpart("C5", "cwradar:4n7_C0G", 78.74, 83.82, extra=MATCH, fields=left_f(78.74, 83.82))
wire((78.74, 87.63), (78.74, 91.44))
box(12.7, 55.88, 83.82, 114.3, "INPUT + RFI")

# --------------------------------------------------------------- IN-AMP G=10
I = place("INA1", "cwradar:INA819IDR", 101.6, 83.82, extra=MATCH,
          fields={"Reference": (110.49, 93.98, 0, False, "left"), "Value": (110.49, 96.52, 0, False, "left")})
assert I["4"] == (91.44, 76.2) and I["1"] == (91.44, 91.44) and I["7"] == (111.76, 83.82) and I["6"] == (104.14, 96.52), I
wire(I["3"], (88.9, 80.01))
vpart("R5", "cwradar:5k49_0p1", 88.9, 83.82, extra=MATCH, fields=left_f(88.9, 83.82))
wire((88.9, 87.63), I["2"])
label("BB_RG3", 90.17, 80.01, 0, small=True)
label("BB_RG2", 90.17, 87.63, 0, small=True)
wire(I["8"], (101.6, 63.5), (116.84, 63.5))
rail("+5V_A", 101.6, 63.5)
vpart("C6", "cwradar:100n", 109.22, 67.31)
gnd(109.22, 71.12)
vpart("C7", "cwradar:1u_25V", 116.84, 67.31)
gnd(116.84, 71.12)
gnd(*I["5"])
wire(I["6"], (104.14, 101.6))
label("VREF_BUF", 104.14, 101.6, 270)
box(83.82, 55.88, 120.65, 114.3, "IN-AMP G=10")

# ---------------------------------------------------- HPF 10 Hz (section A)
wire(I["7"], (118.11, 83.82))
hpart("C8", "cwradar:100n_C0G", 121.92, 83.82, extra=MATCH)
wire((125.73, 83.82), (129.54, 83.82))
hpart("C9", "cwradar:100n_C0G", 133.35, 83.82, extra=MATCH)
A = place("OPA1", "cwradar:OPA4388IPWR", 149.86, 86.36, unit=1, extra=MATCH,
          fields={"Reference": (149.86, 78.74, 0, False), "Value": (149.86, 81.28, 0, False)})
assert A["3"] == (142.24, 83.82) and A["2"] == (142.24, 88.9) and A["1"] == (157.48, 86.36), A
wire((137.16, 83.82), A["3"])
wire((129.54, 83.82), (129.54, 73.66), (140.97, 73.66))
hpart("R6", "cwradar:113k", 144.78, 73.66, extra=MATCH)
wire((148.59, 73.66), (162.56, 73.66), (162.56, 86.36), A["1"])
vpart("R7", "cwradar:226k", 139.7, 87.63, extra=MATCH, fields=left_f(139.7, 87.63))
label("VREF_BUF", 139.7, 91.44, 270)
wire(A["2"], (142.24, 96.52), (160.02, 96.52), (160.02, 86.36))
label("BB_HPFX", 129.54, 78.74, 90, small=True)
label("BB_HPFP", 138.43, 83.82, 0, small=True)
label("BB_INAOUT", 113.03, 83.82, 0, small=True)
box(120.65, 55.88, 167.64, 114.3, "HPF 10 Hz")

# ---------------------------------------------------------- GAIN x4 (section B)
B2 = place("OPA1", "cwradar:OPA4388IPWR", 185.42, 88.9, unit=2, extra=MATCH,
           fields={"Reference": (185.42, 81.28, 0, False), "Value": (185.42, 83.82, 0, False)})
assert B2["5"] == (177.8, 86.36) and B2["6"] == (177.8, 91.44) and B2["7"] == (193.04, 88.9), B2
wire((162.56, 86.36), B2["5"])
label("BB_HPFOUT", 165.1, 86.36, 0, small=True)
wire(B2["6"], (175.26, 91.44), (175.26, 106.68), (190.5, 106.68))
wire((175.26, 101.6), (181.61, 101.6))
hpart("R8", "cwradar:10k_0p1", 185.42, 101.6, extra=MATCH)
wire((189.23, 101.6), (198.12, 101.6), (198.12, 88.9))
# Rg (populated) and the two DNP alternates in parallel, all returning to VREF_BUF
for ref, part, x, dnp in [("R9", "cwradar:3k32_0p1", 180.34, False), ("R10", "cwradar:10k_0p1", 185.42, True),
                          ("R11", "cwradar:1k1_0p1", 190.5, True)]:
    vpart(ref, part, x, 110.49, dnp=dnp, extra=MATCH,
          fields={"Reference": (x - 0.635, 116.84, 90, False, "right"), "Value": (x + 1.905, 116.84, 90, False, "right")})
wire((180.34, 114.3), (195.58, 114.3))
label("VREF_BUF", 195.58, 114.3, 270)
label("BB_GAINFB", 175.26, 97.79, 90, small=True)
box(167.64, 55.88, 200.66, 132.08, "GAIN x4")

# ---------------------------------------------------------- LPF 3 kHz (section C)
wire(B2["7"], (201.93, 88.9))
label("BB_GAINOUT", 194.31, 88.9, 0, small=True)
hpart("R12", "cwradar:11k3", 205.74, 88.9, extra=MATCH)
wire((209.55, 88.9), (213.36, 88.9))
hpart("R13", "cwradar:11k3", 217.17, 88.9, extra=MATCH)
C3U = place("OPA1", "cwradar:OPA4388IPWR", 233.68, 91.44, unit=3, extra=MATCH,
            fields={"Reference": (233.68, 83.82, 0, False), "Value": (233.68, 86.36, 0, False)})
assert C3U["10"] == (226.06, 88.9) and C3U["9"] == (226.06, 93.98) and C3U["8"] == (241.3, 91.44), C3U
wire((220.98, 88.9), C3U["10"])
label("BB_LPFP", 224.79, 88.9, 0, small=True)
wire((213.36, 88.9), (213.36, 76.2), (223.52, 76.2))
hpart("C10", "cwradar:6n8_C0G", 227.33, 76.2, extra=MATCH)
wire((231.14, 76.2), (243.84, 76.2), (243.84, 91.44))
vpart("C11", "cwradar:3n3_C0G", 223.52, 92.71, extra=MATCH, fields=left_f(223.52, 92.71))
gnd(223.52, 96.52)
wire(C3U["9"], (226.06, 99.06), (246.38, 99.06), (246.38, 91.44))
label("BB_LPFY", 213.36, 81.28, 90, small=True)
box(200.66, 55.88, 251.46, 114.3, "LPF 3 kHz")

# --------------------------------------------------------------------- OUTPUT
wire(C3U["8"], (254.0, 91.44))
label("BB_LPFOUT", 248.92, 91.44, 0, small=True)
hpart("C12", "cwradar:470n_C0G", 257.81, 91.44, extra=MATCH)
wire((261.62, 91.44), (276.86, 91.44))
hlabel("OUT", 276.86, 91.44, 0, "output")
box(251.46, 55.88, 292.1, 114.3, "OUTPUT")

# --------------------------------------------------------- VREF 2.000 V (section D)
rail("+5V_A", 40.64, 129.54)
vpart("R14", "cwradar:10k_0p1", 40.64, 133.35, extra=MATCH, fields=left_f(40.64, 133.35))
vpart("R15", "cwradar:10k_0p1", 40.64, 140.97, extra=MATCH, fields=left_f(40.64, 140.97))
gnd(40.64, 144.78)
D4 = place("OPA1", "cwradar:OPA4388IPWR", 73.66, 139.7, unit=4, extra=MATCH,
           fields={"Reference": (73.66, 132.08, 0, False), "Value": (73.66, 134.62, 0, False)})
assert D4["12"] == (66.04, 137.16) and D4["13"] == (66.04, 142.24) and D4["14"] == (81.28, 139.7), D4
wire((40.64, 137.16), D4["12"])
place("C13", "cwradar:47u_POLY", 53.34, 140.97, extra=MATCH,
      fields={"Reference": (55.88, 139.7, 0, False, "left"), "Value": (55.88, 142.24, 0, False, "left")})
gnd(53.34, 144.78)
label("VREF", 45.72, 137.16, 0, small=True)
wire(D4["13"], (66.04, 147.32), (83.82, 147.32), (83.82, 139.7))
wire(D4["14"], (87.63, 139.7))
hpart("R16", "cwradar:47", 91.44, 139.7, extra=MATCH)
wire((95.25, 139.7), (109.22, 139.7))
vpart("C14", "cwradar:100n_C0G", 101.6, 143.51, extra=MATCH)
gnd(101.6, 147.32)
label("VREF_BUF", 109.22, 139.7, 0)
label("BB_VREFOUT", 82.55, 139.7, 0, small=True)
box(12.7, 121.92, 127.0, 157.48, "VREF 2.500 V")

# ------------------------------------------------------------------ OPA POWER
P = place("OPA1", "cwradar:OPA4388IPWR", 139.7, 139.7, unit=5,
          fields={"Reference": (142.24, 144.78, 0, False, "left"), "Value": (142.24, 147.32, 0, False, "left")})
wire(P["4"], (137.16, 129.54), (154.94, 129.54))
rail("+5V_A", 137.16, 129.54)
vpart("C15", "cwradar:100n", 147.32, 133.35)
gnd(147.32, 137.16)
vpart("C16", "cwradar:1u_25V", 154.94, 133.35)
gnd(154.94, 137.16)
gnd(*P["11"])
box(127.0, 121.92, 162.56, 157.48, "OPA SUPPLY")

text("BASEBAND NOTES (one file, two instances: Baseband_I 8xx, Baseband_Q 9xx; every signal-path part has Matched = I/Q)\n"
     "- In-amp INA819 (DigiKey sub for INA826, same pinout): G = 1 + 50k / RG = 1 + 50 / 5.49 = 10.11.\n"
     "  5 V single supply, VCM = VREF = 2.5 V: centred in DS Fig. 7-52 (VS = 5 V, VREF 2.5 V curve), ~1 V margin both ways.\n"
     "- HPF unity Sallen-Key: C1 = C2 = 100n C0G 1206, R1 113k (to OUT), R2 226k (to VREF_BUF): f0 = 9.96 Hz, Q = 0.707.\n"
     "- Gain x4: 1 + 10.0k / 3.32k = 4.01. DNP alternates 10.0k (x2) / 1.10k (x10) in parallel with Rg.\n"
     "- LPF unity Sallen-Key: R1 = R2 = 11.3k, C1 6.8n (to OUT), C2 3.3n (to GND): f0 = 2.97 kHz, Q = 0.72.\n"
     "- Coupling caps C1/C2/C12: 470n C0G 1206 (1 uF C0G is 1825/2220 only). Input with 100k bias: fc = 3.4 Hz;\n"
     "  output into PCM1808 60k: fc = 5.6 Hz. Both well under the 10 Hz HPF (adds ~1.7 dB at 10 Hz, ~0.5 dB at 20 Hz).\n"
     "- VREF: 10.0k / 10.0k 0.1% from +5V_A = 2.500 V (mid-rail), 47u polymer, follower + 47R -> VREF_BUF + 100n C0G.\n"
     "  Bias, HPF R2, Rg and INA REF return to VREF_BUF only. No X5R/X7R on signal nets, VREF or VREF_BUF.\n"
     "- Op-amp OPA4388 (DigiKey sub for OPA4376, same pinout): zero-drift, no 1/f noise.",
     12.7, 162.56, just="left top")
done_sheet("Baseband_I", "Baseband", "baseband.kicad_sch", also=[("Baseband_Q", 100)])


# ================================================================= ADC (10xx)
new_sheet(1000)
AD = place("ADC1", "cwradar:PCM1808PWR", 190.5, 101.6,
           fields={"Reference": (180.34, 88.9, 0, False, "left"), "Value": (196.85, 116.84, 0, False, "left")})
assert AD["13"] == (177.8, 96.52) and AD["3"] == (187.96, 91.44) and AD["12"] == (198.12, 111.76), AD
wire(AD["3"], (187.96, 81.28), (172.72, 81.28))
rail("+5V_A", 187.96, 81.28)
vpart("C1", "cwradar:10u", 180.34, 85.09)
gnd(180.34, 88.9)
vpart("C2", "cwradar:100n", 172.72, 85.09, fields=left_f(172.72, 85.09))
gnd(172.72, 88.9)
wire(AD["4"], (193.04, 76.2), (208.28, 76.2))
rail("+3V3_D", 193.04, 76.2)
vpart("C3", "cwradar:10u", 200.66, 80.01)
gnd(200.66, 83.82)
vpart("C4", "cwradar:100n", 208.28, 80.01)
gnd(208.28, 83.82)
hlabel("ADC_L", *AD["13"], 180, "input")
hlabel("ADC_R", *AD["14"], 180, "input")
wire(AD["1"], (162.56, 104.14))
vpart("C5", "cwradar:10u", 170.18, 107.95)
gnd(170.18, 111.76)
vpart("C6", "cwradar:100n", 162.56, 107.95, fields=left_f(162.56, 107.95))
gnd(162.56, 111.76)
label("ADC_VREF", 173.99, 104.14, 0, small=True)
wire(AD["2"], AD["5"])
gnd(*AD["2"])
wire(AD["10"], AD["11"])  # MD1 = MD0 = low: slave mode (DS Table 2)
gnd(*AD["10"])
vpart("R1", "cwradar:10k", 198.12, 115.57)  # FMT low = I2S (DS Table 3), resistor so it can change
gnd(198.12, 119.38)
label("ADC_FMT", 198.12, 111.76, 0, small=True)
hlabel("I2S_MCLK", *AD["6"], 0, "input")
hlabel("I2S_BCK", *AD["8"], 0, "input")
hlabel("I2S_LRCK", *AD["7"], 0, "input")
wire(AD["9"], (207.01, 104.14))
hpart("R2", "cwradar:33", 210.82, 104.14)
wire((214.63, 104.14), (226.06, 104.14))
hlabel("I2S_DOUT", 226.06, 104.14, 0, "output")
label("ADC_DOUT", 204.47, 104.14, 0, small=True)
text("fs and MCLK ratio set in firmware (datasheet: 8-96 kHz; SCKI 256/384/512 fs).\n"
     "MD1 = MD0 = GND: slave mode, ratio auto-detected. FMT low via R1001 = 24-bit I2S.\n"
     "Inputs AC-coupled on the baseband sheets (470n C0G); VINL/R biased internally at VCC/2.\n"
     "VREF, VCC, VDD: 10u + 100n each (DS 10.1.1, 10.1.4).", 142.24, 124.46, just="left top")
box(139.7, 66.04, 254.0, 147.32, "PCM1808 ADC")
done_sheet("ADC", "ADC", "adc.kicad_sch")

print(f"root: {len(root_wires)} wires, {len(SHEETS)} sheets")
