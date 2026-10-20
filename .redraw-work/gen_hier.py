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
CWLIB = f"{ROOT}/library/symbols/cwradar.kicad_sym"
STD = "/usr/share/kicad/symbols"
ROOT_UUID = "b0666bf5-aed6-40cf-96a3-97fbd780bef0"
OUTDIR = sys.argv[1]
SYN_SHEET = "6d1c5a0e-3f7b-4c2a-9a51-5b0f2e8c6006"


def renum(ref):
    m = re.fullmatch(r"([A-Z]+)(\d+)", ref)
    return f"{m.group(1)}{600 + int(m.group(2))}"


def U():
    return str(uuid.uuid4())


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


for lid in ["cwradar:MAX2871ETJ_T", "power:GND", "Device:C",
            "Connector:TestPoint", "Connector:Conn_Coaxial", "power:PWR_FLAG"]:
    embed_from_old(lid)
for n in ["1u", "10u", "0R", "10", "100n", "10n", "1n", "47", "100k", "120",
          "249", "49R9", "5k1", "12n", "820p", "+3V3_SYN", "+3V3_SYN_RF",
          "+3V3_SYN_PLL", "+3V3_SYN_DIG", "+3V3_SYN_REF"]:
    embed_from_lib(f"cwradar:{n}", cw_text, is_text=True)

PIN_RE = re.compile(r'\(pin \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+) ([-\d.]+)\).*?\(number "([^"]*)"', re.S)
PROP_RE = re.compile(r'^\t\t\t\(property "([^"]+)" "((?:[^"\\]|\\.)*)"', re.M)


def lib_pins(lib_id):
    return {m.group(4): (float(m.group(1)), float(m.group(2)))
            for m in PIN_RE.finditer(EMBED[lib_id])}


def lib_props(lib_id):
    return [(k, v) for k, v in PROP_RE.findall(EMBED[lib_id]) if not k.startswith("ki_")]


def xform(x, y, rot, px, py):
    r = math.radians(rot)
    rx, ry = px * math.cos(r) - py * math.sin(r), px * math.sin(r) + py * math.cos(r)
    return (round(x + rx, 4), round(y - ry, 4))


# ------------------------------------------------------------------ elements
SYMS, WIRES, LABELS, JUNCS, NCS, TEXTS, RECTS = [], [], [], [], [], [], []
PINPOS = {}  # ref -> {pin: (x,y)}
pwr_n = [0]
flg_n = [0]


def place(ref, lib_id, x, y, rot=0, value=None, fp=None, dnp=False, fields=None):
    if not ref.startswith("#"):
        ref = renum(ref)
    props = dict(lib_props(lib_id))
    props["Reference"] = ref
    if value is not None:
        props["Value"] = value
    if fp is not None:
        props["Footprint"] = fp
    pins = {n: xform(x, y, rot, px, py) for n, (px, py) in lib_pins(lib_id).items()}
    PINPOS[ref] = pins
    SYMS.append(dict(ref=ref, lib_id=lib_id, x=x, y=y, rot=rot, props=props,
                     dnp=dnp, fields=fields or {}))
    return pins


def gnd(x, y):
    pwr_n[0] += 1
    place(f"#PWR{pwr_n[0]:02d}", "power:GND", x, y,
          fields={"Reference": (x, y + 6.35, 0, True), "Value": (x, y + 3.81, 0, False)})


def rail(name, x, y):
    pwr_n[0] += 1
    place(f"#PWR{pwr_n[0]:02d}", f"cwradar:{name}", x, y,
          fields={"Reference": (x, y + 3.81, 0, True), "Value": (x, y - 3.556, 0, False)})


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
wire((TX, 35.56), (TX, 93.98))
wire((TX, 38.1), (22.86, 38.1))
vpart("C1", "cwradar:10u", 22.86, 41.91); gnd(22.86, 45.72)

rows = [  # y, ref, part, rail, branch caps [(ref, part, x)]
    (40.64, "R1", "cwradar:0R", "+3V3_SYN_RF", [("C2", "cwradar:1u", 50.8)]),
    (58.42, "R2", "cwradar:0R", "+3V3_SYN_PLL", [("C3", "cwradar:1u", 50.8)]),
    (76.2, "R3", "cwradar:0R", "+3V3_SYN_DIG", []),
    (93.98, "R4", "cwradar:10", "+3V3_SYN_REF", [("C4", "cwradar:10u", 50.8),
                                            ("C5", "cwradar:100n", 60.96),
                                            ("C6", "cwradar:10n", 71.12)]),
]
for y, rref, rpart, rname, caps in rows:
    hpart(rref, rpart, 40.64, y)
    if y != 93.98:
        wire((TX, y), (36.83, y))
    else:
        wire((TX, y), (36.83, y))
    fx = 78.74 if caps and len(caps) > 1 else 71.12
    wire((44.45, y), (50.8, y), (fx, y))
    rail(rname, 50.8, y)
    flag(fx, y)
    for cref, cpart, cx in caps:
        vpart(cref, cpart, cx, y + 3.81)
        gnd(cx, y + 7.62)
box(12.7, 22.86, 88.9, 116.84, "SYNTH POWER")

# ============================================================ MCU INTERFACE
for y, esp, ic, ref in [(130.81, "SYN_SCK", "SYN_SCK_R", "R5"),
                        (138.43, "SYN_MOSI", "SYN_MOSI_R", "R6"),
                        (146.05, "SYN_LE", "SYN_LE_R", "R7")]:
    hlabel(esp, 33.02, y, 180, "input")
    wire((33.02, y), (36.83, y))
    hpart(ref, "cwradar:47", 40.64, y)
    wire((44.45, y), (55.88, y))
    label(ic, 55.88, y, 0)
for y, net, ref in [(156.21, "SYN_CE", "R8"), (170.18, "SYN_RFOUT_EN", "R9")]:
    hlabel(net, 33.02, y, 180, "input")
    wire((33.02, y), (40.64, y))
    vpart(ref, "cwradar:100k", 40.64, y + 3.81)
    gnd(40.64, y + 7.62)
hlabel("SYN_LD", 33.02, 184.15, 180, "output")
wire((33.02, 184.15), (48.26, 184.15))
place("TP1", "Connector:TestPoint", 48.26, 184.15, value="LD",
      fp="TestPoint:TestPoint_Pad_D1.0mm",
      fields={"Reference": (50.8, 179.07, 0, False, "left"), "Value": (50.8, 181.61, 0, False, "left")})
box(12.7, 120.65, 88.9, 198.12, "MCU INTERFACE")

# ============================================================== LOOP FILTER
Y0 = 214.63
label("CP_OUT", 22.86, Y0, 180)
wire((22.86, Y0), (52.07, Y0))
vpart("C22", "cwradar:12n", 33.02, Y0 + 3.81); gnd(33.02, Y0 + 7.62)
vpart("R16", "cwradar:120", 43.18, Y0 + 3.81)
wire((43.18, Y0 + 7.62), (43.18, Y0 + 10.16))
label("LF_C2", 43.18, Y0 + 8.89, 90, small=True)
vpart("C23", "cwradar:100n", 43.18, Y0 + 13.97); gnd(43.18, Y0 + 17.78)
hpart("R17", "cwradar:249", 55.88, Y0)
wire((59.69, Y0), (73.66, Y0))
vpart("C24", "cwradar:820p", 66.04, Y0 + 3.81); gnd(66.04, Y0 + 7.62)
label("TUNE", 73.66, Y0, 0)
box(12.7, 201.93, 88.9, 245.11, "LOOP FILTER")

# ====================================================== MAX2871 SYNTHESIZER
PX, PY = 152.4, 146.05
dx, dy = round(PX - 127, 4), round(PY - 95.25, 4)
r4 = lambda x, y: (round(x, 4), round(y, 4))
P = place("PLL1", "cwradar:MAX2871ETJ_T", PX, PY,
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
          ("32", "+3V3_SYN_DIG", 251.46, ["C12"]), ("17", "+3V3_SYN_RF", 266.7, ["C13"])]
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
        place("J1", "Connector:Conn_Coaxial", J, Y, value="TX", fp="",
              fields={"Reference": (J + 3.81, Y - 2.54, 0, False, "left"),
                      "Value": (J + 3.81, Y, 0, False, "left")})
        gnd(J, Y + 5.08)
    elif net == "RFOUTA_N":
        wire((DCB + 3.81, Y), (J - 5.08, Y))
        label("MON_RF", DCB + 5.08, Y, 0, small=True)
        vpart("R12", "cwradar:49R9", 238.76, Y + 3.81); gnd(238.76, Y + 7.62)
        place("J2", "Connector:Conn_Coaxial", J, Y, value="MON",
              fp="Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical", dnp=True,
              fields={"Reference": (J + 3.81, Y - 2.54, 0, False, "left"),
                      "Value": (J + 3.81, Y, 0, False, "left")})
        gnd(J, Y + 5.08)
    else:
        lo = "LO_P" if net == "RFOUTB_P" else "LO_N"
        wire((DCB + 3.81, Y), (238.76, Y))
        hlabel(lo, 238.76, Y, 0, "output")
box(92.71, 82.55, 281.94, 215.9, "MAX2871 SYNTHESIZER")

# ===================================================================== notes
text("MAX2871 NOTES (DS Rev 4)\n"
     "- One 1u 10V X5R 0402 on every supply pin (C7-C9, C11-C13), branch caps C2/C3 and NOISE_FILT/BIAS_FILT/REG (C14-C16).\n"
     "  Place each 1u directly at its pin, own GND via at or in the pad. Check the part's DC-bias curve at 3.3V; no Y5V.\n"
     "- C10: C0G 0402 on VCC_RF, series-resonant at 5.8 GHz when mounted (~1-3 pF, from vendor S-params), closest to pin 16.\n"
     "- C18-C21 DC blocks: 0402 C0G near series resonance at 5.8 GHz. R5-R7 47R series: place at the ESP32 end.\n"
     "- R8/R9 100k hold CE/RFOUT_EN low at boot. Loop filter C22/R16/C23/R17/C24 = DS 6 GHz values; re-sim with Kvco @ 5.8 GHz. PDP=1.\n"
     "- R12 (50R term) or J2 (U.FL monitor): populate one. J1 TX connector type TBD.\n"
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
    out = [f'\t(symbol\n\t\t(lib_id "{s["lib_id"]}")\n\t\t(at {f(s["x"])} {f(s["y"])} {s["rot"]})',
           "\t\t(unit 1)\n\t\t(body_style 1)\n\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(in_pos_files yes)",
           f'\t\t(dnp {"yes" if s["dnp"] else "no"})\n\t\t(uuid "{U()}")']
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
        out.append(f'\t\t(pin "{n}"\n\t\t\t(uuid "{U()}")\n\t\t)')
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

# --------------------------------------------------------- synthesizer sheet
inst = f"/{ROOT_UUID}/{SHEET_UUID['Synthesizer']}"
body = [header("Synthesizer", FILE_UUID["synthesizer.kicad_sch"]), "\t(lib_symbols"]
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
open(f"{OUTDIR}/synthesizer.kicad_sch", "w", encoding="utf-8").write("\n".join(body))

# synthesizer ports must match its sheet pins exactly
syn_ports = {(n, sh) for n, _, _, _, sh in HLABELS}
syn_pins = {(p[0], p[1]) for p in next(s for s in SHEETS if s[0] == "Synthesizer")[4]}
assert syn_ports == syn_pins, (syn_ports ^ syn_pins)

# ------------------------------------------------- placeholder sub-sheets
done = {"synthesizer.kicad_sch"}
for name, file, page, geom, pins in SHEETS:
    if file in done:
        continue
    done.add(file)
    title = "Baseband" if file == "baseband.kicad_sch" else name
    blks = [header(title, FILE_UUID[file]), "\t(lib_symbols\n\t)"]
    for i, (pname, shape, edge, py) in enumerate(pins):
        blks.append(hlabel_block(pname, 50.8 if edge == "L" else 152.4, 50.8 + 5.08 * i,
                                 180 if edge == "L" else 0, shape))
    blks.append(FOOT)
    open(f"{OUTDIR}/{file}", "w", encoding="utf-8").write("\n".join(blks))

print(f"synth: {len(SYMS)} symbols, {len(WIRES)} wires, {len(JUNCS)} junctions, "
      f"{len(LABELS)} labels, {len(HLABELS)} ports; root: {len(root_wires)} wires, {len(SHEETS)} sheets")
