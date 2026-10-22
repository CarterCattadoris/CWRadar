"""Add the ADL5380/VCO-branch symbols to a copy of cwradar.kicad_sym.

Usage: python3 -I add_lib.py <in.kicad_sym> <out.kicad_sym>
"""
import re
import sys

STD = "/usr/share/kicad/symbols"
src, dst = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8").read()


def block(t, name):
    lines = t.split("\n")
    start = lines.index(f'\t(symbol "{name}"')
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "\t)")
    return "\n".join(lines[start:end + 1])


def set_prop(blk, key, val):
    new, n = re.subn(rf'(\(property "{re.escape(key)}" )"[^"]*"', lambda m: f'{m.group(1)}"{val}"', blk, count=1)
    assert n == 1, key
    return new


def rename(blk, old, new):
    blk = blk.replace(f'(symbol "{old}"', f'(symbol "{new}"', 1)
    return re.sub(rf'\(symbol "{re.escape(old)}_(\d+_\d+)"', rf'(symbol "{new}_\1"', blk)


def have(name):
    return f'\n\t(symbol "{name}"\n' in text


added = []
# power rails: copies of +3V3_SYN_RF
for rail in ["+3V3_SYN_VCO", "+5V", "+5V_DEMOD"]:
    if have(rail):
        continue
    added.append(block(text, "+3V3_SYN_RF").replace("+3V3_SYN_RF", rail))

# 100p C0G 0402 (Citrus format, MPN blank)
if not have("100p"):
    b = rename(block(text, "1u"), "1u", "100p")
    b = set_prop(set_prop(b, "Value", "100p"), "Description", "100 pF ±5% 50V C0G 0402")
    added.append(b)

# 0R in 0402 (the existing 0R is 0603 with a 0603 MPN)
if not have("0R_0402"):
    b = rename(block(text, "0R"), "0R", "0R_0402")
    b = set_prop(b, "Footprint", "Resistor_SMD:R_0402_1005Metric")
    b = set_prop(b, "Description", "0 Ohm Resistor 0402")
    for k in ["Manufacturer", "Mfg Part #", "Distributor Link 1", "Distributor Link 2", "LCSC"]:
        b = set_prop(b, k, "")
    added.append(b)

# 100n PPS film for the loop filter (C623), Panasonic ECHU(X) size E2
if not have("100n_PPS"):
    b = rename(block(text, "100n"), "100n", "100n_PPS")
    b = set_prop(b, "Footprint", "cwradar:C_Panasonic_ECHU_E2")
    b = set_prop(b, "Description", "0.1 µF ±2% 50V PPS film, Panasonic ECHU(X) size E2 (4.8 x 3.3 mm)")
    b = set_prop(b, "Manufacturer", "Panasonic")
    b = set_prop(b, "Mfg Part #", "ECH-U1H104GX9")
    for k in ["Distributor Link 1", "Distributor Link 2", "LCSC"]:
        b = set_prop(b, k, "")
    added.append(b)

# placeholder TCXO from the stock Epson 2520 4-pin outline (1 NC, 2 GND, 3 OUT, 4 VCC)
if not have("TCXO_2520"):
    osc = open(f"{STD}/Oscillator.kicad_sym", encoding="utf-8").read()
    old = "TG2520SMN-xx.xxxxxxMhz-xxxxNM"
    b = rename(block(osc, old), old, "TCXO_2520")
    b = set_prop(b, "Value", "TCXO")
    b = set_prop(b, "Footprint", "")
    b = set_prop(b, "Datasheet", "")
    b = set_prop(b, "Description", "TCXO placeholder, 2520 4-pin (1 NC/VC, 2 GND, 3 OUT, 4 VCC). Part TBD; check pinout against the chosen part")
    b = re.sub(r'\n\t\t\(property "ki_[^"]*" "[^"]*"\n.*?\n\t\t\)', "", b, flags=re.S)
    added.append(b)

# Johanson 5400 balun from the stock Transformer library, Citrus BOM fields added
if not have("5400BL15B050"):
    tr = open(f"{STD}/Transformer.kicad_sym", encoding="utf-8").read()
    b = block(tr, "5400BL15B050")
    b = set_prop(b, "Reference", "T")
    tmpl = re.search(r'\n\t\t\(property "Datasheet" .*?\n\t\t\)', b, re.S).group(0)
    extra = ""
    for k, v in [("Manufacturer", "Johanson Technology"), ("Mfg Part #", "5400BL15B050E"),
                 ("Distributor Link 1", ""), ("Distributor Link 2", ""), ("LCSC", "")]:
        f = re.sub(r'\(property "Datasheet" "[^"]*"', f'(property "{k}" "{v}"', tmpl, count=1)
        if "(hide yes)" not in f:
            f = f.replace("(do_not_autoplace no)", "(do_not_autoplace no)\n\t\t\t(hide yes)")
        extra += f
    b = b.replace(tmpl, tmpl + extra, 1)
    added.append(b)

# ADL5380: add the missing pin 12 (NC, DS Rev B Table 3) on the left edge
adl = block(text, "ADL5380ACPZ-R7")
if '(number "12"' not in adl:
    lines = adl.split("\n")
    starts = [i for i, ln in enumerate(lines) if ln.startswith("\t\t\t(pin ")]
    pins = [(i, next(j for j in range(i + 1, len(lines)) if lines[j] == "\t\t\t)")) for i in starts]
    i11, j11 = next((i, j) for i, j in pins if '(number "11"' in "\n".join(lines[i:j + 1]))
    pin12 = "\n".join(lines[i11:j11 + 1])
    assert pin12.count("(pin ") == 1
    pin12 = pin12.replace("(pin power_in line", "(pin no_connect line", 1)
    pin12 = re.sub(r'\(at [-\d.]+ [-\d.]+ \d+\)', "(at -17.78 -15.24 0)", pin12, count=1)
    pin12 = pin12.replace('(name "GND"', '(name "NC"', 1).replace('(number "11"', '(number "12"', 1)
    pin12 = pin12.replace("\t\t\t\t(hide yes)\n", "", 1)
    lines[j11 + 1:j11 + 1] = pin12.split("\n")
    text = text.replace(adl, "\n".join(lines), 1)

# ADL5380: hidden stacked GND/EP pins -> passive, so they don't form implicit "EP"/"GND" nets
adl = block(text, "ADL5380ACPZ-R7")
fixed = re.sub(r"\(pin power_in line(\n\t\t\t\t\(at [^\n]*\n\t\t\t\t\(length [^\n]*\n\t\t\t\t\(hide yes\))",
               r"(pin passive line\1", adl)
text = text.replace(adl, fixed, 1)

out = text.rstrip()
assert out.endswith(")")
out = out[:-1].rstrip("\n") + "\n" + "\n".join(added) + "\n)\n"
open(dst, "w", encoding="utf-8").write(out)
print("added:", [re.match(r'\t\(symbol "([^"]*)"', a).group(1) for a in added])
