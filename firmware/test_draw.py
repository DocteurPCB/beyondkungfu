# -*- coding: utf-8 -*-
"""Run the 6803 draw_level_strip over every cell of every level-table slot and
compare the resulting tilemap byte-for-byte with the HLE reference model.
usage: test_draw.py <km-z.4h> [slot ...]"""
import sys, os, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from asm6803 import Assembler
from cpu6803 import CPU6803
from ref_mcu import RefMCU, TILEMAP_BYTES

DATA = open(sys.argv[1], "rb").read()
slots = [int(s, 0) for s in sys.argv[2:]] or list(range(16))

src = "".join(open(os.path.join(HERE, f)).read() + "\n" for f in ("decode.s", "draw.s"))
asm = Assembler()
base, blob = asm.assemble(src, org=0xF000)
print(f"firmware: {len(blob)} octets @ {base:#06x}  (draw_level_strip @ {asm.labels['draw_level_strip']:#06x})")

E = asm.equ
TM = E["TILEMAP"]
ref = RefMCU(DATA)
ok_all = True
for slot in slots:
    t0 = time.time()
    cpu = CPU6803(data_rom=DATA)
    cpu.load(base, blob)
    for col in range(0x38):
        for row in range(26):
            cpu.m[E["COL"]] = col
            cpu.m[E["ROW"]] = row
            cpu.m[E["LEVEL"]] = slot
            cpu.SP = 0x00FF
            cpu.call(asm.labels["draw_level_strip"])
    got = bytes(cpu.m[TM:TM + TILEMAP_BYTES])
    want = bytes(ref.compose_level(slot))
    diff = [i for i in range(TILEMAP_BYTES) if got[i] != want[i]]
    ok = not diff
    ok_all &= ok
    msg = "identique ✔" if ok else f"✗ {len(diff)} octets différents (1er @ {diff[0]:#06x}: fw={got[diff[0]]:02x} ref={want[diff[0]]:02x})"
    print(f"slot {slot:2d}: tilemap {msg}   [{cpu.steps:,} instructions 6803, {time.time()-t0:.1f}s]")

print("\n==> TOUS LES NIVEAUX IDENTIQUES À L'HLE" if ok_all else "\n==> ÉCHEC")
sys.exit(0 if ok_all else 1)
