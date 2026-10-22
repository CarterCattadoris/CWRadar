"""Generate Frontend.kicad_sch (MAX2871 synthesizer) in Carter's wired style.

Usage: python3 -I gen_frontend.py <out.kicad_sch>
Reads lib symbols from the backed-up schematic, cwradar.kicad_sym and the
KiCad stock libraries; writes a complete flat A3 sheet.
"""
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
          "MAX2871ETJ_T", "TCXO_2520", "ADL5380ACPZ-R7", "5400BL15B050", "100p", "0R_0402", "100n_PPS",
          "+5V", "+5V_DEMOD"]:
    embed_from_lib(f"cwradar:{n}", cw_text, is_text=True)
embed_from_lib("Device:R", f"{STD}/Device.kicad_sym")

PIN_RE = re.compile(r'\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\).*?\(number "([^"]*)"', re.S)
PROP_RE = re.compile(r'^\t\t\t\(property "([^"]+)" "((?:[^"\\]|\\.)*)"', re.M)


def lib_pins(lib_id):
    return {m.group(4): (float(m.group(1)), float(m.group(2)))
            for m in PIN_RE.finditer(EMBED[lib_id])}


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


def place(ref, lib_id, x, y, rot=0, value=None, fp=None, dnp=False, fields=None,
          mirror=False, extra=None):
    if not ref.startswith("#"):
        ref = renum(ref)
    props = dict(lib_props(lib_id))
    props["Reference"] = ref
    if value is not None:
        props["Value"] = value
    if fp is not None:
        props["Footprint"] = fp
    props.update(extra or {})
    pins = {n: xform(x, y, rot, px, py, mirror) for n, (px, py) in lib_pins(lib_id).items()}
    PINPOS[ref] = pins
    SYMS.append(dict(ref=ref, lib_id=lib_id, x=x, y=y, rot=rot, props=props,
                     dnp=dnp, fields=fields or {}, mirror=mirror))
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
vpart("C23", "cwradar:100n_PPS", 43.18, Y0 + 13.97); gnd(43.18, Y0 + 17.78)
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
            vpart(cref, "Device:C", x, YT + 3.81, value="TBD",
                  fp="Capacitor_SMD:C_0402_1005Metric")
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

# reference TCXO placeholder (part TBD), on the RC-filtered +3V3_SYN_REF branch
YX, YY = 106.68, 104.14
X = place("Y1", "cwradar:TCXO_2520", YX, YY,
          value="25 MHz TCXO ±2.5 ppm clipped-sine — PART TBD", fp="",
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
    hpart(cref, "Device:C", DCB, Y, value="TBD", fp="Capacitor_SMD:C_0402_1005Metric")
    if net == "RFOUTA_P":
        wire((DCB + 3.81, Y), (J - 5.08, Y))
        label("TX_RF", DCB + 5.08, Y, 0, small=True)
        place("J1", "Connector:Conn_Coaxial", J, Y, value="TX SMA", fp="Connector_Coaxial:SMA_Molex_73251-1153_EdgeMount_Horizontal", extra={"Manufacturer": "Molex", "Mfg Part #": "73251-1153", "Description": "SMA jack, edge mount, 1.6 mm PCB"},
              fields={"Reference": (J + 3.81, Y - 2.54, 0, False, "left"),
                      "Value": (J + 3.81, Y, 0, False, "left")})
        gnd(J, Y + 5.08)
    elif net == "RFOUTA_N":
        wire((DCB + 3.81, Y), (J - 5.08, Y))
        label("MON_RF", DCB + 5.08, Y, 0, small=True)
        vpart("R12", "cwradar:49R9", 238.76, Y + 3.81); gnd(238.76, Y + 7.62)
        place("J2", "Connector:Conn_Coaxial", J, Y, value="MON SMA",
              fp="Connector_Coaxial:SMA_Molex_73251-1153_EdgeMount_Horizontal", dnp=True, extra={"Manufacturer": "Molex", "Mfg Part #": "73251-1153", "Description": "SMA jack, edge mount, 1.6 mm PCB"},
              fields={"Reference": (J + 3.81, Y - 2.54, 0, False, "left"),
                      "Value": (J + 3.81, Y, 0, False, "left")})
        gnd(J, Y + 5.08)
    else:
        lo = "LO_P" if net == "RFOUTB_P" else "LO_N"
        wire((DCB + 3.81, Y), (238.76, Y))
        hlabel(lo, 238.76, Y, 0, "output")

# HF decoupling at the pull-up supply ends: C0G series-resonant at 5.8 GHz, value TBD
for cref, pair, y in [("C26", "R611/R613", 157.48), ("C27", "R614/R615", 193.04)]:
    rail("+3V3_SYN_RF", 279.4, y)
    wire((279.4, y), (284.48, y))
    vpart(cref, "Device:C", 284.48, y + 3.81, value="TBD", fp="Capacitor_SMD:C_0402_1005Metric",
          extra={"Note": f"Place at the shared supply end of {pair}. C0G 0402, series-resonant at 5.8 GHz (~1-3 pF)."})
    gnd(284.48, y + 7.62)
    text(f"Place at {pair}\nsupply end", 276.86, y + 13.97, just="left top")
box(92.71, 82.55, 302.26, 215.9, "MAX2871 SYNTHESIZER")

# ===================================================================== notes
text("MAX2871 NOTES (DS Rev 4)\n"
     "- One 1u 10V X5R 0402 on every supply pin (C7-C9, C11-C13), branch caps C2/C3 and NOISE_FILT/BIAS_FILT/REG (C14-C16).\n"
     "  Place each 1u directly at its pin, own GND via at or in the pad. Check the part's DC-bias curve at 3.3V; no Y5V.\n"
     "- C10: C0G 0402 on VCC_RF, series-resonant at 5.8 GHz when mounted (~1-3 pF, from vendor S-params), closest to pin 16.\n"
     "- C18-C21 DC blocks: 0402 C0G near series resonance at 5.8 GHz. R5-R7 47R series: place at the ESP32 end.\n"
     "- R8/R9 100k hold CE/RFOUT_EN low at boot.\n"
     "- Loop filter C22/R16/C23/R17/C24 = MAX2871 DS Rev 4 TOC table \"6.0 GHz closed-loop\n"
     "  phase noise\" config: fREF 50 MHz, fPFD 25 MHz, ~40 kHz BW, CP[3:0]=1111 (5.12 mA w/ RSET 5k1),\n"
     "  integer N=240. Ours: N=232 @ fPFD 25 MHz. Confirm Kvco @ 5.8 GHz in ADIsimPLL. All loop-filter caps C0G/film.\n"
     "- Firmware: program all regs twice at power-up (>=20 ms gap, order 5..0), RFA_EN/RFB_EN = 0 until second\n"
     "  pass; set MTLD=1 (reg4 b10) and MUTEDEL=1 (reg3 b17) so outputs mute when unlocked. PDP=1.\n"
     "- VCC_VCO on dedicated branch +3V3_SYN_VCO (R18). Pull-up node HF caps C26/C27 C0G series-resonant.\n"
     "- R12 (50R term) or J2 (SMA monitor): populate one. J1/J2: Molex 73251-1153 edge-launch SMA.\n"
     "- Bead-free star: R1-R3 0R 0603 branch links (fallback filter footprints). R4 10R + C4 10u = TCXO RC, fc ~1.6 kHz.\n"
     "- +3V3_SYN from dedicated low-noise LDO (TBD); LC/pi filter at LDO input if fed from a switcher. REF_25M from TCXO (TBD).\n"
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


def sym_block(s, inst_path):
    suid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cwradar-sym{inst_path}/{s['ref']}"))
    bom = "no" if re.match(r"(TP|MH)\d", s["ref"]) else "yes"  # test pads and holes are not purchased
    mir = {True: "\n\t\t(mirror y)", "y": "\n\t\t(mirror y)", "x": "\n\t\t(mirror x)"}.get(s.get("mirror"), "")
    out = [f'\t(symbol\n\t\t(lib_id "{s["lib_id"]}")\n\t\t(at {f(s["x"])} {f(s["y"])} {s["rot"]}){mir}',
           f"\t\t(unit 1)\n\t\t(body_style 1)\n\t\t(exclude_from_sim no)\n\t\t(in_bom {bom})\n\t\t(on_board yes)\n\t\t(in_pos_files yes)",
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
    for n in lib_pins(s["lib_id"]):
        out.append(f'\t\t(pin "{n}"\n\t\t\t(uuid "{uuid.uuid5(uuid.NAMESPACE_URL, suid + "/" + n)}")\n\t\t)')
    out.append(f'\t\t(instances\n\t\t\t(project "Frontend"\n\t\t\t\t(path "{inst_path}"\n'
               f'\t\t\t\t\t(reference "{s["ref"]}")\n\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)')
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
     [("USB_DP", B, "R", 40.64), ("USB_DN", B, "R", 45.72), ("CHG_SDA", B, "R", 55.88),
      ("CHG_SCL", "input", "R", 60.96), ("CHG_INT", "output", "R", 66.04),
      ("CHG_STAT", "output", "R", 71.12)]),
    ("Regulators", "regulators.kicad_sch", 3, (20.32, 96.52, 45.72, 25.4),
     [("VBAT_SENSE", "output", "R", 106.68), ("EN_ANALOG", "input", "R", 111.76)]),
    ("MCU", "mcu.kicad_sch", 4, (96.52, 30.48, 40.64, 106.68),
     [("USB_DP", B, "L", 40.64), ("USB_DN", B, "L", 45.72), ("CHG_SDA", B, "L", 55.88),
      ("CHG_SCL", "output", "L", 60.96), ("CHG_INT", "input", "L", 66.04),
      ("CHG_STAT", "input", "L", 71.12), ("VBAT_SENSE", "input", "L", 106.68),
      ("EN_ANALOG", "output", "L", 111.76),
      ("SYN_SCK", "output", "R", 40.64), ("SYN_MOSI", "output", "R", 45.72),
      ("SYN_MISO", "input", "R", 50.8), ("SYN_LE", "output", "R", 55.88),
      ("SYN_CE", "output", "R", 60.96), ("SYN_RFOUT_EN", "output", "R", 66.04),
      ("SYN_LD", "input", "R", 71.12),
      ("I2S_MCLK", "output", "R", 116.84), ("I2S_BCK", B, "R", 121.92),
      ("I2S_LRCK", B, "R", 127.0), ("I2S_DOUT", "input", "R", 132.08)]),
    ("User_IO", "user_io.kicad_sch", 5, (96.52, 160.02, 40.64, 25.4), []),
    ("Synthesizer", "synthesizer.kicad_sch", 6, (167.64, 30.48, 40.64, 50.8),
     [("SYN_SCK", "input", "L", 40.64), ("SYN_MOSI", "input", "L", 45.72),
      ("SYN_MISO", "output", "L", 50.8), ("SYN_LE", "input", "L", 55.88),
      ("SYN_CE", "input", "L", 60.96), ("SYN_RFOUT_EN", "input", "L", 66.04),
      ("SYN_LD", "output", "L", 71.12), ("LO_P", "output", "R", 45.72),
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
      ("I2S_MCLK", "input", "L", 116.84), ("I2S_BCK", B, "L", 121.92),
      ("I2S_LRCK", B, "L", 127.0), ("I2S_DOUT", "output", "L", 132.08)]),
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
         ["USB_DP", "USB_DN", "CHG_SDA", "CHG_SCL", "CHG_INT", "CHG_STAT"]]
LINKS += [("Regulators", p, "MCU", p, []) for p in ["VBAT_SENSE", "EN_ANALOG"]]
LINKS += [("MCU", p, "Synthesizer", p, []) for p in
          ["SYN_SCK", "SYN_MOSI", "SYN_MISO", "SYN_LE", "SYN_CE", "SYN_RFOUT_EN", "SYN_LD"]]
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
root_pins = [pin_xy(s[0], p[0]) for s in SHEETS for p in s[4]]
root_wires, root_juncs = finish_wires(root_wires, root_pins, [])

UCTX[:] = ["Frontend.kicad_sch", 0]
out = [header("CW Radar Main Board", ROOT_UUID), "\t(lib_symbols\n\t)"]
out += [junction_block(p) for p in root_juncs] + [wire_block(a, b) for a, b in root_wires]
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
def emit_sheet(sheet, title, file):
    """Write the current element lists as a sub-sheet; its ports must match the sheet pins."""
    inst = f"/{ROOT_UUID}/{SHEET_UUID[sheet]}"
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
    body += [sym_block(s, inst) for s in SYMS]
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
rail("+5V", 33.02, 35.56)
wire((33.02, 35.56), (33.02, 40.64), (36.83, 40.64))
hpart("R1", "cwradar:0R", 40.64, 40.64, extra={"Note": "0R branch link, bead fallback footprint."})
wire((44.45, 40.64), (50.8, 40.64), (71.12, 40.64))
rail("+5V_DEMOD", 50.8, 40.64)
flag(71.12, 40.64)
vpart("C1", "cwradar:10u", 50.8, 44.45); gnd(50.8, 48.26)
text("+5V source TBD (Regulators)", 40.64, 30.48)
box(12.7, 22.86, 88.9, 63.5, "DEMOD POWER")

# ----------------------------------------------------- ADL5380 DEMODULATOR
DX, DY = 190.5, 139.7
D = place("DEMOD1", "cwradar:ADL5380ACPZ-R7", DX, DY,
          fields={"Reference": (177.8, 115.57, 0, False, "left"), "Value": (177.8, 118.11, 0, False, "left")})
assert D["21"] == (172.72, 132.08) and D["9"] == (172.72, 139.7) and D["6"] == (208.28, 121.92), D

# RF input: RX coax -> balun -> DC blocks -> RFIN/RFIP
YN, YP = 124.46, 134.62  # balun balanced pins 3 / 4
J = place("J1", "Connector:Conn_Coaxial", 101.6, YP, value="RX SMA", fp="Connector_Coaxial:SMA_Molex_73251-1153_EdgeMount_Horizontal", extra={"Manufacturer": "Molex", "Mfg Part #": "73251-1153", "Description": "SMA jack, edge mount, 1.6 mm PCB"},
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
    hpart(cref, "Device:C", 157.48, y, value="TBD", fp="Capacitor_SMD:C_0402_1005Metric",
          extra={"Note": "DC block: C0G 0402, series-resonant at 5.8 GHz. Not the eval board's 100 pF (rated to 4 GHz)."})
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
     "- +5V is a placeholder rail; its source (Regulators sheet) is TBD. Pin 12 NC: do not connect.",
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
emit_sheet("Mechanical", "Mechanical", "mechanical.kicad_sch")

# ------------------------------------------------- placeholder sub-sheets
done = {"synthesizer.kicad_sch", "receiver.kicad_sch", "mechanical.kicad_sch"}
for name, file, page, geom, pins in SHEETS:
    if file in done:
        continue
    done.add(file)
    title = "Baseband" if file == "baseband.kicad_sch" else name
    UCTX[:] = [file, 0]
    blks = [header(title, FILE_UUID[file]), "\t(lib_symbols\n\t)"]
    for i, (pname, shape, edge, py) in enumerate(pins):
        blks.append(hlabel_block(pname, 50.8 if edge == "L" else 152.4, 50.8 + 5.08 * i,
                                 180 if edge == "L" else 0, shape))
    blks.append(FOOT)
    open(f"{OUTDIR}/{file}", "w", encoding="utf-8").write("\n".join(blks))

print(f"root: {len(root_wires)} wires, {len(SHEETS)} sheets")
