"""Replace footprints on the board from the schematic netlist (KiCad has no CLI "update PCB from schematic").

Usage: python3 sync_footprints.py <board.kicad_pcb> <netlist.net> <out.kicad_pcb> REF [REF ...]

For each REF: the old footprint is cut out of the board text (removing items through the KiCad 10.0.7 Python
API corrupts its SWIG type table), then the netlist footprint is loaded from its library and given the
reference, value, fields, schematic link (sheet path + symbol UUID) and pad nets from the netlist. It keeps
the old position, rotation and side. Run place_layout.py afterwards to re-place it.
"""
import os
import re
import sys
import tempfile

import pcbnew

BOARD, NET, OUT, REFS = sys.argv[1], sys.argv[2], sys.argv[3], set(sys.argv[4:])
STD = "/usr/share/kicad/footprints"
PROJ = os.path.dirname(os.path.abspath(BOARD))


# ------------------------------------------------------------------ netlist
def sexp_items(t, start, name):
    """Yield (start, end) of every '(name ...' block found from `start` on."""
    i = start
    while True:
        i = t.find(f"({name}", i)
        if i < 0:
            return
        if t[i + len(name) + 1] not in " \n\t\r":
            i += 1
            continue
        depth, j = 0, i
        while True:
            c = t[j]
            if c == '"':
                j += 1
                while t[j] != '"':
                    j += 2 if t[j] == "\\" else 1
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        yield i, j + 1
        i = j + 1


net_text = open(NET, encoding="utf-8").read()
flat = re.sub(r"\s+\)", ")", re.sub(r"\s+", " ", net_text))   # "( a )" -> "( a)"
comps = {}
for a, b in sexp_items(flat, flat.index("(components"), "comp"):
    c = flat[a:b]
    ref = re.search(r'\(ref "([^"]+)"\)', c).group(1)
    if ref not in REFS:
        continue
    fields = dict(re.findall(r'\(field \(name "([^"]+)"\) "((?:[^"\\]|\\.)*)"\)', c))
    fields.update({k: "" for k in re.findall(r'\(field \(name "([^"]+)"\)\)', c)})
    sheet = re.search(r'\(sheetpath \(names "([^"]*)"\) \(tstamps "([^"]*)"\)\)', c)
    uuid = re.findall(r'\(tstamps "([^"]*)"\)', c)[-1]
    comps[ref] = dict(
        value=re.search(r'\(value "([^"]*)"\)', c).group(1),
        footprint=re.search(r'\(footprint "([^"]*)"\)', c).group(1),
        datasheet=(re.search(r'\(datasheet "([^"]*)"\)', c) or [None, ""])[1],
        description=(re.search(r'\(description "([^"]*)"\)', c) or [None, ""])[1],
        fields=fields, sheetname=sheet.group(1), path=sheet.group(2) + uuid,
        sheetfile=(re.search(r'\(property \(name "Sheetfile"\) \(value "([^"]*)"\)\)', c) or [None, ""])[1])
missing = REFS - set(comps)
assert not missing, f"not in netlist: {missing}"
pad_net = {}
for a, b in sexp_items(flat, flat.index("(nets"), "net"):
    n = flat[a:b]
    name = re.search(r'\(name "([^"]*)"\)', n).group(1)
    for ref, pin in re.findall(r'\(node \(ref "([^"]+)"\) \(pin "([^"]+)"\)', n):
        if ref in REFS:
            pad_net[(ref, pin)] = name


# ------------------------------------------------------------------ libraries
def lib_path(lib):
    for table in (os.path.join(PROJ, "fp-lib-table"),):
        if os.path.exists(table):
            m = re.search(rf'\(lib \(name "{re.escape(lib)}"\).*?\(uri "([^"]+)"\)', open(table).read())
            if m:
                return m.group(1).replace("${KIPRJMOD}", PROJ)
    return f"{STD}/{lib}.pretty"


# ------------------------------------------------------------------ cut the old footprints from the text
board_text = open(BOARD, encoding="utf-8").read()
old = {}
out, last = [], 0
for a, b in sexp_items(board_text, 0, "footprint"):
    if board_text[a - 1] != "\t" or board_text[a - 2] != "\n":   # top level only
        continue
    blk = board_text[a:b]
    m = re.search(r'\(property "Reference" "([^"]+)"', blk)
    if m and m.group(1) in REFS:
        at = re.search(r'\n\t\t\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', blk)
        old[m.group(1)] = (float(at.group(1)), float(at.group(2)), float(at.group(3) or 0),
                           '\n\t\t(layer "B.Cu")' in blk)
        out.append(board_text[last:a - 1])      # drop the leading tab too
        last = b + 1 if board_text[b] == "\n" else b
out.append(board_text[last:])
fd, tmp = tempfile.mkstemp(suffix=".kicad_pcb")
with open(fd, "w", encoding="utf-8") as fh:
    fh.write("".join(out))
assert set(old) == REFS, f"not on board: {REFS - set(old)}"

# ------------------------------------------------------------------ add the new ones
B = pcbnew.LoadBoard(tmp)
nets = {B.GetNetInfo().GetNetItem(i).GetNetname(): B.GetNetInfo().GetNetItem(i)
        for i in range(B.GetNetCount())}
for ref in sorted(REFS):
    c = comps[ref]
    lib, name = c["footprint"].split(":", 1)
    f = pcbnew.FootprintLoad(lib_path(lib), name)
    assert f is not None, c["footprint"]
    f.SetFPIDAsString(c["footprint"])
    f.SetReference(ref)
    f.SetValue(c["value"])
    f.SetPath(pcbnew.KIID_PATH(c["path"]))
    f.SetSheetname(c["sheetname"])
    f.SetSheetfile(c["sheetfile"])
    flds = dict(c["fields"], Datasheet=c["datasheet"], Description=c["description"])
    for k, v in flds.items():
        if f.HasField(k):
            f.GetField(k).SetText(v)
        else:
            fld = pcbnew.PCB_FIELD(f, f.GetNextFieldOrdinal(), k)
            fld.SetText(v)
            fld.SetVisible(False)
            fld.SetLayer(pcbnew.F_Fab)
            f.Add(fld)
    x, y, rot, back = old[ref]
    B.Add(f)
    if back:
        f.Flip(f.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
    f.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    f.SetOrientationDegrees(rot)
    for p in f.Pads():
        nn = pad_net.get((ref, p.GetNumber()))
        if nn:
            if nn not in nets:
                ni = pcbnew.NETINFO_ITEM(B, nn)
                B.Add(ni)
                nets[nn] = ni
            p.SetNet(nets[nn])
    print(f"{ref}: {c['value']} {c['footprint']}")
B.Save(OUT)
os.unlink(tmp)
