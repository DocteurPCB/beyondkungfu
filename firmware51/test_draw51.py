# -*- coding: utf-8 -*-
"""8751 firmware: commands 0x01 + 0x02 for every level-table slot; tilemap
compared byte for byte with the HLE reference; time at 8 MHz vs the PCB.
usage: test_draw51.py <km-z.4h> [slot ...]"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "tools")]
from fw51 import FirmwareMCU51
from build51 import build
from ref_mcu import RefMCU, TILEMAP_BYTES
DATA = open(sys.argv[1], "rb").read()
slots = [int(s, 0) for s in sys.argv[2:]] or list(range(16))
img, labels = build()
ref = RefMCU(DATA)
ok_all, worst = True, 0
for slot in slots:
    fw = FirmwareMCU51(DATA, img, labels)
    fw.z80_write(1, slot); fw.z80_write(0, 0x01)
    c0 = fw.cpu.cycles
    fw.z80_write(0, 0x02)
    cyc = fw.cpu.cycles - c0
    got, want = bytes(fw.tram), bytes(ref.compose_level(slot))
    diff = [i for i in range(TILEMAP_BYTES) if got[i] != want[i]]
    ok_all &= not diff; worst = max(worst, cyc)
    msg = "identique ✔" if not diff else f"✗ {len(diff)} octets (1er @ {diff[0]:#06x} fw={got[diff[0]]:02x} ref={want[diff[0]]:02x})"
    print(f"slot {slot:2d}: {msg}  {cyc:>8,} cycles machine = {fw.ms(cyc):6.1f} ms à 8 MHz")
print(f"\npire cas : {fw.ms(worst):.1f} ms à 8 MHz (vrai PCB ~1120 ms)")
print("==> TOUS LES NIVEAUX IDENTIQUES À L'HLE" if ok_all else "==> ÉCHEC")
sys.exit(0 if ok_all else 1)
