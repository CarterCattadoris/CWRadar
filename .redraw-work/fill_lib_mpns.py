"""Fill orderable MPNs into existing cwradar.kicad_sym symbols that had none (DigiKey, 2026-10-27).

Usage: python3 -I fill_lib_mpns.py <in.kicad_sym> <out.kicad_sym>
Only Manufacturer / Mfg Part # / Datasheet / Distributor Link 1 (and one description) change;
values, footprints and pins stay as they are.
"""
import json
import re
import sys

WORK = "/home/eon/Formula/CWRadar/.redraw-work"
PARTS = json.load(open(f"{WORK}/digikey_parts.json", encoding="utf-8"))
src, dst = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8").read()

# symbol -> (manufacturer, MPN, new description or None)
FILL = {
    "47": ("YAGEO", "RC0402FR-0747RL", None),
    "100k": ("YAGEO", "RC0402FR-07100KL", None),
    "120": ("YAGEO", "RC0402FR-07120RL", None),
    "249": ("YAGEO", "RC0402FR-07249RL", None),
    "49R9": ("YAGEO", "RC0402FR-0749R9L", None),
    "5k1": ("YAGEO", "RC0402FR-075K1L", None),
    "0R_0402": ("YAGEO", "RC0402JR-070RL", None),
    "1u": ("Samsung", "CL05A105KP5NNNC", None),
    "10n": ("Samsung", "CL05B103KB5NNNC", "10 nF ±10% 50V X7R 0402"),
    "1n": ("Murata", "GRM1555C1H102JA01D", "1 nF ±5% 50V C0G 0402"),
    "820p": ("Murata", "GRM1555C1H821JA01D", "820 pF ±5% 50V C0G 0402"),
    "12n": ("KEMET", "C0603C123J3GACTU", "12 nF ±5% 25V C0G 0603"),
    "100p": ("Murata", "GRM1555C1H101JA01D", None),
    "100n_PPS": ("Panasonic", "ECH-U1H104GX9", None),
    # DigiKey's ordering code for the same Johanson 5400BL15B050 (same datasheet, specs, pinout)
    "5400BL15B050": ("Johanson Technology", "5400BL15B0050001E", None),
}


def block(t, name):
    lines = t.split("\n")
    start = lines.index(f'\t(symbol "{name}"')
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "\t)")
    return "\n".join(lines[start:end + 1])


def set_prop(blk, key, val):
    new, n = re.subn(rf'(\n\t\t\(property "{re.escape(key)}" )"[^"]*"', lambda m: f'{m.group(1)}"{val}"', blk, count=1)
    assert n == 1, key
    return new


for name, (mfr, mpn, desc) in FILL.items():
    old = block(text, name)
    b = set_prop(old, "Manufacturer", mfr)
    b = set_prop(b, "Mfg Part #", mpn)
    b = set_prop(b, "Datasheet", PARTS[mpn]["datasheet"])
    b = set_prop(b, "Distributor Link 1", PARTS[mpn]["digikey"])
    if desc:
        b = set_prop(b, "Description", desc)
    text = text.replace(old, b, 1)
open(dst, "w", encoding="utf-8").write(text)
print(f"filled {len(FILL)} symbols")
