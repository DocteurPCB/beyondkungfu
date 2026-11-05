# -*- coding: utf-8 -*-
"""8751 firmware: payload_at / decrypt_at on every address of km-z.4h vs the
HLE reference.  usage: test_decode51.py <km-z.4h>"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "tools")]
from fw51 import FirmwareMCU51
from ref_mcu import RefMCU
DATA = open(sys.argv[1], "rb").read()
ref, fw = RefMCU(DATA), FirmwareMCU51(DATA)
bad = {"decrypt_at": [], "payload_at": []}
for a in range(0x8000):
    for label, want in (("decrypt_at", ref.decrypt(a)), ("payload_at", ref.payload(a))):
        got = fw.call(label, r6=a & 0xFF, r7=a >> 8)
        if got != want: bad[label].append((a, got, want))
for label, b in bad.items():
    print(f"{label:11s}: {0x8000 - len(b)}/{0x8000} identiques" + ("  ✔" if not b else f"  ✗ 1re @ {b[0][0]:#06x} fw={b[0][1]:02x} ref={b[0][2]:02x}"))
ok = not any(bad.values())
print("==> FIRMWARE 8751 = HLE, octet pour octet, sur toute la ROM de données." if ok else "==> ÉCHEC")
sys.exit(0 if ok else 1)
