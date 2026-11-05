# -*- coding: utf-8 -*-
"""Run the firmware's random-access decrypt_at / payload_at on every address of
km-z.4h and compare byte-for-byte with the HLE reference.
usage: test_decode.py <km-z.4h>"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from build import build
from cpu6803 import CPU6803
from ref_mcu import RefMCU

DATA = open(sys.argv[1], "rb").read()
ref = RefMCU(DATA)
base, blob, asm = build()
print(f"firmware assemblé: {len(blob)} octets @ {base:#06x}")
cpu = CPU6803(data_rom=DATA)
cpu.load(base, blob)


def call(label, addr):
    cpu.A, cpu.B = addr >> 8, addr & 0xFF
    cpu.SP = 0x00FF
    cpu.call(asm.labels[label])
    return cpu.A


bad = {"decrypt_at": 0, "payload_at": 0}
first = None
for a in range(0x8000):
    for label, want in (("decrypt_at", ref.decrypt(a)), ("payload_at", ref.payload(a))):
        got = call(label, a)
        if got != want:
            bad[label] += 1
            first = first or (label, a, got, want)

for label, n in bad.items():
    print(f"{label:11s}: {0x8000 - n}/{0x8000} identiques" + ("  ✔" if n == 0 else f"  ✗ {n} erreurs"))
if first:
    print("  1re divergence: %s @ %#06x  fw=%#04x ref=%#04x" % first)
    sys.exit(1)
print("\n==> FIRMWARE 6803 = HLE, octet pour octet, sur toute la ROM de données.")
