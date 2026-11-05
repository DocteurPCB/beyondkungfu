# -*- coding: utf-8 -*-
"""Assemble the MCU firmware sources into one image.  build() -> (base, blob, asm)"""
import os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from asm6803 import Assembler

SOURCES = ("decode.s", "draw.s", "drawloop.s", "main.s", "tables.s", "vectors.s")


def build():
    for gen in ("gen_tables.py", "gen_drawloop.py"):
        subprocess.run([sys.executable, os.path.join(HERE, gen)], check=True,
                       stdout=subprocess.DEVNULL)
    src = "".join(open(os.path.join(HERE, f)).read() + "\n" for f in SOURCES)
    asm = Assembler()
    base, blob = asm.assemble(src, org=0xF000)
    assert base + len(blob) <= 0x10000, "firmware does not fit below $10000"
    assert asm.labels["PTAB"] == 0xFB00, "PTAB must be page aligned at $FB00"
    assert asm.labels["code_end"] <= asm.labels["PTAB"], \
        f"code overlaps PTAB: code ends at {asm.labels['code_end']:#06x}"
    return base, blob, asm


if __name__ == "__main__":
    base, blob, asm = build()
    code = asm.labels["code_end"] - base
    print(f"firmware: image {len(blob)} octets @ {base:#06x}; code {code} octets "
          f"({asm.labels['PTAB'] - asm.labels['code_end']} libres avant PTAB), table 384 octets")
    if len(sys.argv) > 1:
        open(sys.argv[1], "wb").write(blob)
        print(f"écrit: {sys.argv[1]}")
