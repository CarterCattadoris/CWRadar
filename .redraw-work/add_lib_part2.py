"""Add the main-board (Part 2) symbols to a copy of cwradar.kicad_sym.

Usage: python3 -I add_lib_part2.py <in.kicad_sym> <out.kicad_sym>

Parts are DigiKey-sourced (stock checked 2026-10-22). Passives follow the Citrus
format: value-named, Manufacturer / Mfg Part # / Distributor Link 1 (DigiKey).
Existing symbols are never modified.
"""
import json
import re
import sys

STD = "/usr/share/kicad/symbols"
WORK = "/home/eon/Formula/CWRadar/.redraw-work"
src, dst = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8").read()
# DigiKey product page + datasheet per MPN, pulled from the DigiKey API
PARTS = json.load(open(f"{WORK}/digikey_parts.json", encoding="utf-8"))


def block(t, name, indent=1):
    tab = "\t" * indent
    lines = t.split("\n")
    start = lines.index(f'{tab}(symbol "{name}"')
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == f"{tab})")
    return "\n".join(lines[start:end + 1])


def set_prop(blk, key, val):
    new, n = re.subn(rf'(\n\t\t\(property "{re.escape(key)}" )"[^"]*"', lambda m: f'{m.group(1)}"{val}"', blk, count=1)
    assert n == 1, key
    return new


def has_prop(blk, key):
    return f'\n\t\t(property "{key}" ' in blk


def add_prop(blk, key, val):
    """Append a hidden property after the last top-level property."""
    tmpl = (f'\t\t(property "{key}" "{val}"\n\t\t\t(at 0 0 0)\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no)\n'
            f'\t\t\t(hide yes)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n\t\t)')
    lines = blk.split("\n")
    last = max(i for i, ln in enumerate(lines) if ln.startswith("\t\t(property "))
    end = next(j for j in range(last + 1, len(lines)) if lines[j] == "\t\t)")
    lines[end + 1:end + 1] = tmpl.split("\n")
    return "\n".join(lines)


def put(blk, key, val):
    return set_prop(blk, key, val) if has_prop(blk, key) else add_prop(blk, key, val)


def rename(blk, old, new):
    blk = blk.replace(f'(symbol "{old}"', f'(symbol "{new}"', 1)
    return re.sub(rf'\(symbol "{re.escape(old)}_(\d+_\d+)"', rf'(symbol "{new}_\1"', blk)


def have(name):
    return f'\n\t(symbol "{name}"\n' in text


def fields(blk, value, fp, desc, mfr, mpn, ref=None):
    if ref:
        blk = set_prop(blk, "Reference", ref)
    blk = set_prop(blk, "Value", value)
    blk = set_prop(blk, "Footprint", fp)
    blk = put(blk, "Datasheet", PARTS[mpn]["datasheet"])
    blk = put(blk, "Description", desc)
    for k, v in [("Manufacturer", mfr), ("Mfg Part #", mpn), ("Distributor Link 1", PARTS[mpn]["digikey"]),
                 ("Distributor Link 2", ""), ("LCSC", "")]:
        blk = put(blk, k, v)
    return blk


added = []


def add(name, blk):
    if not have(name):
        added.append(blk)


def stock(lib_id, name):
    """Flattened copy of a stock symbol (extends resolved) under a new name."""
    lib, sym = lib_id.split(":")
    t = open(f"{STD}/{lib}.kicad_sym", encoding="utf-8").read()
    b = block(t, sym)
    m = re.search(r'\(extends "([^"]+)"\)', b)
    if m:
        b = block(t, m.group(1))
        sym = m.group(1)
    b = rename(b, sym, name)
    return re.sub(r'\n\t\t\(property "ki_[^"]*" "[^"]*"\n.*?\n\t\t\)', "", b, flags=re.S)


# -------------------------------------------------------------- passives
R_T, C_T = block(text, "10"), block(text, "10u")


def res(name, value, fp, desc, mfr, mpn):
    add(name, fields(rename(R_T, "10", name), value, fp, desc, mfr, mpn))


def cap(name, value, fp, desc, mfr, mpn):
    add(name, fields(rename(C_T, "10u", name), value, fp, desc, mfr, mpn))


R0402 = "Resistor_SMD:R_0402_1005Metric"
for name, val, mfr, mpn in [
        ("10k", "10k", "YAGEO", "RC0402FR-0710KL"), ("4k7", "4k7", "Vishay Dale", "CRCW04024K70FKED"),
        ("1k5", "1k5", "Panasonic", "ERJ-2RKF1501X"), ("392", "392", "YAGEO", "RC0402FR-07392RL"),
        ("5k23", "5k23", "YAGEO", "RC0402FR-075K23L"), ("30k1", "30k1", "YAGEO", "RC0402FR-0730K1L"),
        ("113k", "113k", "YAGEO", "RC0402FR-07113KL"), ("30k9", "30k9", "YAGEO", "RC0402FR-0730K9L"),
        ("60k4", "60k4", "YAGEO", "RC0402FR-0760K4L"), ("31k6", "31k6", "YAGEO", "RC0402FR-0731K6L"),
        ("51k1", "51k1", "YAGEO", "RC0402FR-0751K1L"), ("20k5", "20k5", "YAGEO", "RC0402FR-0720K5L"),
        ("33", "33", "YAGEO", "RC0402FR-0733RL"), ("1k", "1k", "YAGEO", "RC0402FR-071KL"),
        ("226k", "226k", "Panasonic", "ERJ-2RKF2263X"), ("11k3", "11k3", "YAGEO", "RC0402FR-0711K3L"),
        ("680", "680", "YAGEO", "RC0402FR-07680RL")]:
    v = val.replace("k", ".") + " kOhm" if "k" in val else f"{val} Ohm"
    res(name, val, R0402, f"{v} ±1% 0402 thick film", mfr, mpn)
for name, val, mfr, mpn in [
        ("5k49_0p1", "5k49", "Panasonic", "ERA-2AEB5491X"), ("10k_0p1", "10k", "Panasonic", "ERA-2AEB103X"),
        ("3k32_0p1", "3k32", "Panasonic", "ERA-2AEB3321X"), ("1k1_0p1", "1k1", "Susumu", "RG1005P-112-B-T5"),
        ("15k_0p1", "15k", "Panasonic", "ERA-2AEB153X"), ("105k_0p1", "105k", "YAGEO", "RT0402BRD07105KL"),
        ("20k_0p1", "20k", "Panasonic", "ERA-2AEB203X")]:
    res(name, val, R0402, f"{val.replace('k', '.')} kOhm ±0.1% 25ppm 0402 thin film", mfr, mpn)

for name, val, fp, desc, mfr, mpn in [
        ("1u_25V", "1u", "Capacitor_SMD:C_0603_1608Metric", "1 µF ±10% 25V X7R 0603", "KEMET", "C0603C105K3RACTU"),
        ("10u_25V", "10u", "Capacitor_SMD:C_0805_2012Metric", "10 µF ±10% 25V X5R 0805", "Taiyo Yuden", "TMK212BBJ106KD-T"),
        ("22u_25V", "22u", "Capacitor_SMD:C_1206_3216Metric", "22 µF ±10% 25V X5R 1206", "KYOCERA AVX", "12063D226KAT2A"),
        ("47u_10V", "47u", "Capacitor_SMD:C_1206_3216Metric", "47 µF ±20% 10V X5R 1206", "Murata", "GRM31CR61A476ME15L"),
        ("4u7_25V", "4u7", "Capacitor_SMD:C_0603_1608Metric", "4.7 µF ±10% 25V X5R 0603", "Murata", "GRM188R61E475KE11D"),
        ("47n", "47n", "Capacitor_SMD:C_0402_1005Metric", "47 nF ±10% 50V X7R 0402", "Murata", "GRM155R71H473KE14D"),
        ("22n", "22n", "Capacitor_SMD:C_0402_1005Metric", "22 nF ±10% 50V X7R 0402", "Samsung", "CL05B223KB5NNNC"),
        ("470p_C0G", "470p", "Capacitor_SMD:C_0402_1005Metric", "470 pF ±2% 50V C0G 0402", "Murata", "GRM1555C1H471GA01D"),
        ("4n7_C0G", "4n7", "Capacitor_SMD:C_0603_1608Metric", "4.7 nF ±2% 50V C0G 0603", "Murata", "GCM1885C1H472GA16D"),
        ("6n8_C0G", "6n8", "Capacitor_SMD:C_0603_1608Metric", "6.8 nF ±1% 50V C0G 0603", "KEMET", "C0603C682F5GACTU"),
        ("3n3_C0G", "3n3", "Capacitor_SMD:C_0603_1608Metric", "3.3 nF ±1% 50V C0G 0603", "Murata", "GCM1885C1H332FA16D"),
        ("100n_C0G", "100n", "Capacitor_SMD:C_1206_3216Metric", "0.1 µF ±2% 100V C0G 1206", "Murata", "GRM3195C2A104GA01D"),
        # RF DC blocks / HF decoupling: high-Q, series-resonant around 5.8 GHz (Carter, 2026-10-27)
        ("2p2", "2p2", "Capacitor_SMD:C_0402_1005Metric", "2.2 pF ±0.1 pF 50V C0G 0402, high-Q, series-resonant ~5.8 GHz",
         "Murata", "GJM1555C1H2R2BB01D"),
        ("1u_PET", "1u", "cwradar:C_AVX_CB_2824", "1 µF ±5% 100V PET stacked film, KYOCERA AVX CB 2824 (7.2 x 6.1 mm)",
         "KYOCERA AVX", "CB052E0105JBC")]:
    cap(name, val, fp, desc, mfr, mpn)

# polymer tantalum (polarized)
b = fields(stock("Device:C_Polarized", "47u_POLY"), "47u", "Capacitor_Tantalum_SMD:CP_EIA-3528-21_Kemet-B",
           "47 µF ±20% 10V polymer tantalum, 70 mΩ, 3528-21 (KEMET B)", "KEMET", "T520B476M010ATE070", ref="C")
add("47u_POLY", b)

# ------------------------------------------------- magnetics, discretes, switches, connectors
for name, val, fp, desc, mfr, mpn in [
        ("1uH", "1uH", "Inductor_SMD:L_Wuerth_MAPI-4020", "1 µH shielded, Isat 7.4 A, 13.5 mΩ, WE-MAPI 4020", "Würth Elektronik", "74438357010"),
        ("6u8H", "6.8uH", "Inductor_SMD:L_Wuerth_MAPI-4020", "6.8 µH shielded, 3 A, 74 mΩ, WE-MAPI 4020", "Würth Elektronik", "74438357068"),
        ("10uH", "10uH", "Inductor_SMD:L_Bourns_SRP7028A_7.3x6.6mm", "10 µH shielded, 3.5 A, 85 mΩ, SRP7028A", "Bourns", "SRP7028A-100M")]:
    add(name, fields(stock("Device:L", name), val, fp, desc, mfr, mpn, ref="L"))
add("3A_FAST", fields(stock("Device:Fuse", "3A_FAST"), "3A", "Fuse:Fuse_1206_3216Metric",
                      "Fuse 3 A fast-acting, 32 VDC, 1206", "Littelfuse", "0466003.NR", ref="F"))
add("10k_NTC", fields(stock("Device:Thermistor_NTC", "10k_NTC"), "10k B3435", "Resistor_SMD:R_0603_1608Metric",
                      "NTC 10 kΩ ±1% at 25 °C, B25/85 3435 K (103AT curve), 0603", "TDK", "NTCG163JF103FT1S", ref="RT"))
add("SMF6.5A", fields(stock("Device:D_Zener", "SMF6.5A"), "SMF6.5A", "Diode_SMD:D_SOD-123F",
                      "TVS unidirectional 6.5 V standoff, 11.2 V clamp, SOD-123FL", "MCC", "SMF6.5A-TP", ref="D"))
for name, val, mpn, desc in [("LED_GRN", "GRN", "LTST-C191KGKT", "LED green 571 nm, 0603"),
                             ("LED_YEL", "YEL", "LTST-C191KSKT", "LED yellow 590 nm, 0603"),
                             ("LED_RED", "RED", "LTST-C191KRKT", "LED red 631 nm, 0603"),
                             ("LED_ORG", "ORG", "LTST-C191KFKT", "LED orange 605 nm (amber), 0603")]:
    add(name, fields(stock("Device:LED", name), val, "LED_SMD:LED_0603_1608Metric", desc, "Lite-On", mpn, ref="D"))
add("AO3401A", fields(stock("Transistor_FET:AO3401A", "AO3401A"), "AO3401A", "Package_TO_SOT_SMD:SOT-23",
                      "P-MOSFET -30 V, -4 A, VGS ±12 V, SOT-23", "Alpha & Omega", "AO3401A", ref="Q"))
add("2N7002K", fields(stock("Transistor_FET:2N7002K", "2N7002K"), "2N7002K", "Package_TO_SOT_SMD:SOT-23",
                      "N-MOSFET 60 V, 320 mA, ESD protected, SOT-23", "onsemi", "2N7002K", ref="Q"))
add("SW_TACT", fields(stock("Switch:SW_Push", "SW_TACT"), "SW_TACT", "Button_Switch_SMD:SW_SPST_TL3342",
                      "Tactile switch SPST-NO, SMD 4.2 x 3.2 mm", "E-Switch", "TL3342F160QG/TR", ref="SW"))
add("SW_SLIDE", fields(stock("Switch:SW_SPDT", "SW_SLIDE"), "SW_SLIDE", "Button_Switch_THT:SW_Slide_SPDT_Straight_CK_OS102011MS2Q",
                       "Slide switch SPDT, 100 mA 12 V, THT", "C&K", "OS102011MS2QN1", ref="SW"))
add("XH_2P", fields(stock("Connector_Generic:Conn_01x02", "XH_2P"), "XH_2P", "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
                    "JST XH header 2-pin, 2.50 mm, vertical THT, 3 A", "JST", "B2B-XH-A", ref="J"))
add("PH_2P", fields(stock("Connector_Generic:Conn_01x02", "PH_2P"), "PH_2P", "Connector_JST:JST_PH_B2B-PH-K_1x02_P2.00mm_Vertical",
                    "JST PH header 2-pin, 2.00 mm, vertical THT, 2 A", "JST", "B2B-PH-K-S", ref="J"))
add("BOX_2x05", fields(stock("Connector_Generic:Conn_02x05_Odd_Even", "BOX_2x05"), "BOX_2x05", "Connector_IDC:IDC-Header_2x05_P2.54mm_Vertical",
                       "Shrouded box header 2x5, 2.54 mm, vertical THT", "Würth Elektronik", "61201021621", ref="J"))

# ----------------------------------------------------------------- stock ICs
add("TPS62933FDRLR", fields(stock("Regulator_Switching:TPS62933F", "TPS62933FDRLR"), "TPS62933F", "Package_TO_SOT_SMD:SOT-583-8",
                            "3.8-30 V 3 A sync buck, FCCM, SOT-583", "Texas Instruments", "TPS62933FDRLR", ref="BUCK"))
add("OPA4388IPWR", fields(stock("Amplifier_Operational:OPA4376", "OPA4388IPWR"), "OPA4388", "Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
                          "Quad zero-drift RRIO op-amp, 10 MHz, 2.5-5.5 V, TSSOP-14", "Texas Instruments", "OPA4388IPWR", ref="OPA"))
add("USBLC6-2SC6", fields(stock("Power_Protection:USBLC6-2SC6", "USBLC6-2SC6"), "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6",
                          "ESD protection 2-line + VBUS, SOT-23-6", "STMicroelectronics", "USBLC6-2SC6", ref="ESD"))
add("ESP32-S3-WROOM-1-N16R2", fields(stock("RF_Module:ESP32-S3-WROOM-1", "ESP32-S3-WROOM-1-N16R2"), "ESP32-S3-WROOM-1-N16R2",
                                     "RF_Module:ESP32-S3-WROOM-1", "ESP32-S3 module, 16 MB flash, 2 MB quad PSRAM, PCB antenna",
                                     "Espressif", "ESP32-S3-WROOM-1-N16R2", ref="MCU"))
add("USB4105-GF-A", fields(stock("Connector:USB_C_Receptacle_USB2.0_16P", "USB4105-GF-A"), "USB4105-GF-A",
                           "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal",
                           "USB-C receptacle USB 2.0, 16-pin, SMD right angle", "GCT", "USB4105-GF-A", ref="USB"))

# ------------------------------------------------------------ power symbols
for rail in ["+VBUS", "+VBAT", "+VSYS", "+VPRE", "+5V_RF", "+5V_A", "+V_LNA", "+3V3_D"]:
    add(rail, block(text, "+3V3_SYN_RF").replace("+3V3_SYN_RF", rail))


# --------------------------------------------------------------- drawn ICs
def eff(size=1.27):
    return f"(effects\n\t\t\t\t\t\t(font\n\t\t\t\t\t\t\t(size {size} {size})\n\t\t\t\t\t\t)\n\t\t\t\t\t)"


def pin(num, name, typ, x, y, ang, hide=False):
    h = "\n\t\t\t\t(hide yes)" if hide else ""
    return (f"\t\t\t(pin {typ} line\n\t\t\t\t(at {x:g} {y:g} {ang})\n\t\t\t\t(length 2.54){h}\n"
            f'\t\t\t\t(name "{name}"\n\t\t\t\t\t{eff()}\n\t\t\t\t)\n'
            f'\t\t\t\t(number "{num}"\n\t\t\t\t\t{eff()}\n\t\t\t\t)\n\t\t\t)')


def prop(k, v, x, y, hide=True, just=None):
    h = "\n\t\t\t(hide yes)" if hide else ""
    j = f"\n\t\t\t\t(justify {just})" if just else ""
    return (f'\t\t(property "{k}" "{v}"\n\t\t\t(at {x:g} {y:g} 0)\n\t\t\t(show_name no)\n\t\t\t(do_not_autoplace no){h}\n'
            f"\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t){j}\n\t\t\t)\n\t\t)")


def ic(name, ref, value, fp, desc, mfr, mpn, w, top, bot, left=(), right=(), up=(), down=()):
    """Box symbol, body x in [-w, w], y in [bot, top]. Side pins: (num, name, type, y);
    up/down pins: (num, name, type, x). Repeated (num) entries at one spot are stacked."""
    pins, seen = [], set()

    def stacked(num, nm, typ, x, y, ang):
        # repeats at one spot: hidden passive, like the ADL5380 GND/EP stack
        dup = (x, y) in seen
        seen.add((x, y))
        pins.append(pin(num, nm, "passive" if dup else typ, x, y, ang, hide=dup))

    for side, ang, items in [("L", 0, left), ("R", 180, right)]:
        x = -w - 2.54 if side == "L" else w + 2.54
        for num, nm, typ, y in items:
            stacked(num, nm, typ, x, y, ang)
    for side, ang, items in [("U", 270, up), ("D", 90, down)]:
        y = top + 2.54 if side == "U" else bot - 2.54
        for num, nm, typ, x in items:
            stacked(num, nm, typ, x, y, ang)
    out = [f'\t(symbol "{name}"\n\t\t(pin_names\n\t\t\t(offset 1.016)\n\t\t)\n\t\t(exclude_from_sim no)\n'
           f"\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(in_pos_files yes)\n\t\t(duplicate_pin_numbers_are_jumpers no)",
           prop("Reference", ref, -w, top + 1.27, False, "left bottom"),
           prop("Value", value, -w, bot - 1.27, False, "left top"),
           prop("Footprint", fp, 0, 0), prop("Datasheet", PARTS[mpn]["datasheet"], 0, 0), prop("Description", desc, 0, 0),
           prop("Manufacturer", mfr, 0, 0), prop("Mfg Part #", mpn, 0, 0), prop("Distributor Link 1", PARTS[mpn]["digikey"], 0, 0),
           prop("Distributor Link 2", "", 0, 0), prop("LCSC", "", 0, 0),
           f'\t\t(symbol "{name}_0_1"\n\t\t\t(rectangle\n\t\t\t\t(start {-w:g} {bot:g})\n\t\t\t\t(end {w:g} {top:g})\n'
           f"\t\t\t\t(stroke\n\t\t\t\t\t(width 0.254)\n\t\t\t\t\t(type default)\n\t\t\t\t)\n"
           f"\t\t\t\t(fill\n\t\t\t\t\t(type background)\n\t\t\t\t)\n\t\t\t)\n\t\t)",
           f'\t\t(symbol "{name}_1_1"', *pins, "\t\t)", "\t\t(embedded_fonts no)", "\t)"]
    return "\n".join(out)


# BQ25883 (SLUSDL3A, Pin Functions): VQFN-24 RGE0024H, EP = GND
add("BQ25883RGET", ic(
    "BQ25883RGET", "CHG", "BQ25883", "Package_DFN_QFN:Texas_RGE0024H_VQFN-24-1EP_4x4mm_P0.5mm_EP2.7x2.7mm_ThermalVias",
    "2-cell 2 A boost charger, power path, I2C, BC1.2, VQFN-24", "Texas Instruments", "BQ25883RGET",
    12.7, 22.86, -20.32,
    # boost: inductor PMID -> SW, QHS SW -> SYS (DS Fig. 8.2), so PMID/SW/BTST sit together on the right
    left=[("23", "VBUS", "power_in", 20.32), ("24", "D+", "bidirectional", 12.7), ("1", "D-", "bidirectional", 10.16),
          ("4", "SDA", "bidirectional", 5.08), ("5", "SCL", "input", 2.54), ("6", "~{INT}", "open_collector", 0),
          ("3", "~{CE}", "input", -5.08), ("9", "~{PG}", "open_collector", -7.62), ("2", "STAT", "open_collector", -12.7),
          ("8", "ILIM", "passive", -17.78)],
    # REGN 7.62 above TS so RT1 drops straight between them
    right=[("21", "PMID", "passive", 20.32), ("22", "PMID", "passive", 20.32), ("17", "SW", "passive", 15.24),
           ("18", "SW", "passive", 15.24), ("12", "BTST", "passive", 7.62), ("15", "SYS", "power_out", 2.54),
           ("16", "SYS", "power_out", 2.54), ("13", "BAT", "passive", -2.54), ("14", "BAT", "passive", -2.54),
           ("11", "REGN", "power_out", -7.62), ("7", "TS", "input", -15.24), ("10", "NC", "no_connect", -17.78)],
    down=[("19", "GND", "power_in", 0), ("20", "GND", "passive", 0), ("25", "EP", "passive", 0)]))

# TPS7A8300 (SBVS197F, Pin Functions): RGR VQFN-20, GND 8/18 + pad
add("TPS7A8300RGRR", ic(
    "TPS7A8300RGRR", "LDO", "TPS7A8300", "Package_DFN_QFN:QFN-20-1EP_3.5x3.5mm_P0.5mm_EP2x2mm_ThermalVias",
    "2 A low-noise LDO, ANY-OUT 0.8-3.95 V or adjustable to 5 V, VQFN-20 3.5x3.5", "Texas Instruments", "TPS7A8300RGRR",
    10.16, 12.7, -20.32,
    left=[("15", "IN", "power_in", 10.16), ("16", "IN", "passive", 10.16), ("17", "IN", "passive", 10.16),
          ("14", "EN", "input", 5.08), ("12", "BIAS", "passive", 2.54), ("13", "NR/SS", "passive", 0),
          ("5", "50mV", "passive", -5.08), ("6", "100mV", "passive", -7.62), ("7", "200mV", "passive", -10.16),
          ("9", "400mV", "passive", -12.7), ("10", "800mV", "passive", -15.24), ("11", "1.6V", "passive", -17.78)],
    # FB sits 7.62 under OUT so the divider top resistor and CFF drop straight between them
    # OUT passive: +3V3_SYN already carries a PWR_FLAG on the synthesizer sheet (power_out + flag = ERC error),
    # so the LDO rails are flagged instead, like the buck outputs behind their inductors
    right=[("1", "OUT", "passive", 10.16), ("19", "OUT", "passive", 10.16), ("20", "OUT", "passive", 10.16),
           ("2", "SNS", "input", 5.08), ("3", "FB", "input", 2.54), ("4", "PG", "open_collector", -5.08)],
    down=[("8", "GND", "power_in", 0), ("18", "GND", "passive", 0), ("21", "EP", "passive", 0)]))

# INA819 (SBOS959D Table 6-1): SOIC-8, same pinout as INA826
add("INA819IDR", ic(
    "INA819IDR", "INA", "INA819", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "Precision in-amp, G = 1 + 50k/RG, 4.5-36 V, 8 nV/rtHz, SOIC-8", "Texas Instruments", "INA819IDR",
    7.62, 10.16, -10.16,
    # RG pins 7.62 apart so the gain resistor drops straight between them
    left=[("4", "+IN", "input", 7.62), ("3", "RG", "passive", 3.81), ("2", "RG", "passive", -3.81),
          ("1", "-IN", "input", -7.62)],
    right=[("7", "OUT", "output", 0)],
    up=[("8", "+VS", "power_in", 0)],
    down=[("5", "-VS", "power_in", 0), ("6", "REF", "input", 2.54)]))

# PCM1808 (SLES177, Pin Functions): TSSOP-14
add("PCM1808PWR", ic(
    "PCM1808PWR", "ADC", "PCM1808", "Package_SO:TSSOP-14_4.4x5mm_P0.65mm",
    "Stereo 24-bit audio ADC, I2S / left-justified, 8-96 kHz, TSSOP-14", "Texas Instruments", "PCM1808PWR",
    10.16, 7.62, -7.62,
    # mode/format straps on the bottom edge beside the grounds they tie to
    left=[("13", "VINL", "input", 5.08), ("14", "VINR", "input", 2.54), ("1", "VREF", "passive", -2.54)],
    right=[("6", "SCKI", "input", 5.08), ("8", "BCK", "bidirectional", 2.54), ("7", "LRCK", "bidirectional", 0),
           ("9", "DOUT", "output", -2.54)],
    up=[("3", "VCC", "power_in", -2.54), ("4", "VDD", "power_in", 2.54)],
    down=[("2", "AGND", "power_in", -5.08), ("5", "DGND", "power_in", -2.54), ("10", "MD0", "input", 2.54),
          ("11", "MD1", "input", 5.08), ("12", "FMT", "input", 7.62)]))

out = text.rstrip()
assert out.endswith(")")
out = out[:-1].rstrip("\n") + "\n" + "\n".join(added) + "\n)\n"
open(dst, "w", encoding="utf-8").write(out)
print(f"added {len(added)}:", [re.match(r'\t\(symbol "([^"]*)"', a).group(1) for a in added])
