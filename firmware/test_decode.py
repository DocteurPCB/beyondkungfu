# -*- coding: utf-8 -*-
"""Assemble firmware/decode.s, run it on the 6803 emulator over the whole
km-z.4h data ROM, and compare byte-for-byte with the HLE reference."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from asm6803 import Assembler
from cpu6803 import CPU6803, BANK_REG

ROMPATH = sys.argv[1]
DATA = open(ROMPATH, "rb").read()
assert len(DATA) == 0x8000, f"expected 0x8000 bytes, got {len(DATA):#x}"

# ---- reference (ported verbatim from m62_bkungfu_mcu.cpp) ------------------
def ref_decrypt(a):
    if a >= 0x8000: return 0xFF
    cipher = DATA[a]
    index = ((a & 0xFF) + (a >> 8)) & 0xFF
    if index & 1:
        return ((index ^ (0x7e if (index & 2) else 0x12)) - 0x20 - cipher) & 0xFF
    return (cipher ^ index ^ (0x5e if (index & 2) else 0xAE)) & 0xFF

def ref_payload(a):
    value = ref_decrypt(a)
    s = ((a & 0xFF) + (a >> 8)) & 0xFF
    if s & 1: return (0x60 - value) & 0xFF
    base = 0xA0 if (value & 0x20) else 0x60
    return (base - value - (0 if (value & 1) else 2)) & 0xFF

# ---- assemble firmware ------------------------------------------------------
src = open(os.path.join(os.path.dirname(__file__), "decode.s")).read()
asm = Assembler()
base, blob = asm.assemble(src, org=0xF000)
print(f"firmware assemblé: {len(blob)} octets @ {base:#06x}")
for name in ("read_data", "decrypt", "decode_payload"):
    print(f"  {name:14s} @ {asm.labels[name]:#06x}")

cpu = CPU6803(data_rom=DATA)
cpu.load(base, blob)
R_DECRYPT = asm.labels["decrypt"]
R_PAYLOAD = asm.labels["decode_payload"]

def call_fw(routine, addr):
    cpu.A = cpu.B = 0; cpu.X = 0; cpu.SP = 0x00FF
    cpu.m[asm.equ['DAL']] = addr & 0xFF
    cpu.m[asm.equ['DAH']] = (addr >> 8) & 0xFF
    cpu.call(routine)
    return cpu.A

# ---- compare over the whole ROM --------------------------------------------
bad_d = bad_p = 0; first_bad = None
for a in range(0x8000):
    d_fw = call_fw(R_DECRYPT, a); d_ref = ref_decrypt(a)
    p_fw = call_fw(R_PAYLOAD, a); p_ref = ref_payload(a)
    if d_fw != d_ref:
        bad_d += 1; first_bad = first_bad or ("decrypt", a, d_fw, d_ref)
    if p_fw != p_ref:
        bad_p += 1; first_bad = first_bad or ("payload", a, p_fw, p_ref)

print(f"\nadresses testées : 0x0000..0x7FFF ({0x8000})")
print(f"decrypt       : {0x8000-bad_d}/{0x8000} identiques" + ("  ✔" if bad_d==0 else f"  ✗ {bad_d} erreurs"))
print(f"decode_payload: {0x8000-bad_p}/{0x8000} identiques" + ("  ✔" if bad_p==0 else f"  ✗ {bad_p} erreurs"))
if first_bad:
    k,a,fw,ref = first_bad
    print(f"  1re divergence: {k} @ {a:#06x}  fw={fw:#04x} ref={ref:#04x}")
else:
    print("\n==> FIRMWARE 6803 = HLE, octet pour octet, sur toute la ROM de données.")
