# -*- coding: utf-8 -*-
"""Assemble the MCU firmware sources into one image.  build() -> (base, blob, asm)"""
import os, sys, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from asm6803 import Assembler

SOURCES = ("decode.s", "draw.s", "main.s", "tables.s", "vectors.s")


def build():
    if not os.path.exists(os.path.join(HERE, "tables.s")):
        subprocess.run([sys.executable, os.path.join(HERE, "gen_tables.py")], check=True)
    src = "".join(open(os.path.join(HERE, f)).read() + "\n" for f in SOURCES)
    asm = Assembler()
    base, blob = asm.assemble(src, org=0xF000)
    assert base + len(blob) <= 0x10000, "firmware does not fit below $10000"
    return base, blob, asm


if __name__ == "__main__":
    base, blob, asm = build()
    used = asm.labels["FTAB"] + 256 - base          # code + tables, before the vectors
    print(f"firmware: image {len(blob)} octets @ {base:#06x}; code + tables {used} octets, "
          f"{0xFFF0 - base - used} libres avant les vecteurs")
    if len(sys.argv) > 1:
        open(sys.argv[1], "wb").write(blob)
        print(f"écrit: {sys.argv[1]}")
