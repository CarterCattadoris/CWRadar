"""Remove footprints from a board by editing the file text (BOARD.Remove() corrupts SWIG in KiCad 10.0.7 Python).

Usage: python3 strip_footprints.py <in.kicad_pcb> <out.kicad_pcb> REF [REF ...]
"""
import re
import sys

src, dst, refs = sys.argv[1], sys.argv[2], set(sys.argv[3:])
t = open(src, encoding="utf-8").read()
out, i, removed = [], 0, []
while True:
    j = t.find("\n\t(footprint ", i)
    if j < 0:
        out.append(t[i:])
        break
    k, depth = j + 2, 0
    m = k
    while True:
        c = t[m]
        if c == '"':
            m += 1
            while t[m] != '"':
                m += 2 if t[m] == "\\" else 1
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                break
        m += 1
    blk = t[k:m + 1]
    r = re.search(r'\(property "Reference" "([^"]+)"', blk)
    out.append(t[i:j])
    if r and r.group(1) in refs:
        removed.append(r.group(1))
    else:
        out.append(t[j:m + 1])
    i = m + 1
open(dst, "w", encoding="utf-8").write("".join(out))
print("removed", sorted(removed))
