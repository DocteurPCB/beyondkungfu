# -*- coding: utf-8 -*-
"""Run the firmware's draw_level for every level-table slot, compare the
resulting tilemap byte-for-byte with the HLE reference, and report the cost in
6803 cycles against the hardware's ~14-frame (~255 ms) level draw.
usage: test_draw.py <km-z.4h> [slot ...]"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from build import build
from cpu6803 import CPU6803
from ref_mcu import RefMCU, TILEMAP_BYTES

TARGET_MS = 1120                   # whole background on the real PCB (docs/SPEC.md)
CLOCK_HZ = 3_579_545 / 4          # MC6803 E clock, assuming the sound board's crystal

DATA = open(sys.argv[1], "rb").read()
slots = [int(s, 0) for s in sys.argv[2:]] or list(range(16))
base, blob, asm = build()
print(f"firmware: {len(blob)} octets @ {base:#06x}")
TM = asm.equ["TILEMAP"]
ref = RefMCU(DATA)
ok_all, worst = True, 0
for slot in slots:
    cpu = CPU6803(data_rom=DATA)
    cpu.load(base, blob)
    cpu.m[asm.equ["LEVEL"]] = slot
    cpu.SP = 0x00FF
    cpu.call(asm.labels["draw_level"], max_steps=50_000_000)
    got = bytes(cpu.m[TM:TM + TILEMAP_BYTES])
    want = bytes(ref.compose_level(slot))
    diff = [i for i in range(TILEMAP_BYTES) if got[i] != want[i]]
    ok_all &= not diff
    worst = max(worst, cpu.cycles)
    ms = cpu.cycles / CLOCK_HZ * 1000
    msg = "identique ✔" if not diff else \
        f"✗ {len(diff)} octets (1er @ {diff[0]:#06x}: fw={got[diff[0]]:02x} ref={want[diff[0]]:02x})"
    print(f"slot {slot:2d}: {msg}  {cpu.cycles:>9,} cycles = {ms:6.1f} ms à 3,58 MHz")

print(f"\npire cas: {worst:,} cycles = {worst / CLOCK_HZ * 1000:.1f} ms à 3,58 MHz "
      f"(vrai PCB ~{TARGET_MS:.0f} ms)")
print("==> TOUS LES NIVEAUX IDENTIQUES À L'HLE" if ok_all else "==> ÉCHEC")
sys.exit(0 if ok_all else 1)
