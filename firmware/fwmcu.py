# -*- coding: utf-8 -*-
"""The 6803 firmware wrapped as an MCU with the same Z80-facing interface as
tools/ref_mcu.RefMCU: z80_write(offset, data), .mailbox, .tram.

It models our LLE bus glue: the shared mailbox at $0800, the tilemap at $2000,
km-z.4h at $6000, and the two mailbox latches (CMDLAT $0400, SLOTLAT $0401)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build import build
from cpu6803 import CPU6803

CMDLAT, SLOTLAT, MBOX, TILEMAP = 0x0400, 0x0401, 0x0800, 0x2000


class Bus(CPU6803):
    def wr(self, a, v):
        a &= 0xFFFF
        if a == CMDLAT:
            self.m[a] = 0                       # any write clears
        elif a == SLOTLAT:
            self.m[a] &= ~v & 0xFF              # write 1 to clear
        else:
            self.m[a] = v & 0xFF


class FirmwareMCU:
    def __init__(self, data, image=None):
        if image is None:
            base, image, self.asm = build()
            assert base == 0xF000 and len(image) == 0x1000, (hex(base), len(image))
        self.cpu = Bus(data_rom=data)
        self.cpu.load(0xF000, image)
        self.cpu.PC = self.cpu.rd16(0xFFFE)     # reset vector
        self.main = self.asm.labels["main"]
        self.run()

    def run(self, max_steps=20_000_000):
        """Run until the firmware is idle in its main loop."""
        c, m = self.cpu, self.cpu.m
        for _ in range(max_steps):
            if c.PC == self.main and m[CMDLAT] == 0 and m[SLOTLAT] == 0:
                return
            c.step()
        raise RuntimeError(f"firmware never went idle (PC={c.PC:04x})")

    def z80_post(self, offset, data):
        """A Z80 write that does NOT wait for the MCU (it may be busy)."""
        m = self.cpu.m
        if offset < 0x800:
            m[MBOX + offset] = data & 0xFF
        if offset == 0:
            m[CMDLAT] |= 0x80
        if 0x10 <= offset < 0x30 and not offset & 3:
            m[SLOTLAT] |= 1 << ((offset - 0x10) >> 2)

    def run_cycles(self, n):
        """Let the MCU run for n cycles, idle or not."""
        end = self.cpu.cycles + n
        while self.cpu.cycles < end:
            self.cpu.step()

    def z80_write(self, offset, data):
        m = self.cpu.m
        if offset < 0x800:
            m[MBOX + offset] = data & 0xFF
        if offset == 0:
            m[CMDLAT] |= 0x80
        if 0x10 <= offset < 0x30 and not offset & 3:
            m[SLOTLAT] |= 1 << ((offset - 0x10) >> 2)
        self.run()

    @property
    def mailbox(self):
        return self.cpu.m[MBOX:MBOX + 0x800]

    @property
    def tram(self):
        return self.cpu.m[TILEMAP:TILEMAP + 0x4000]
