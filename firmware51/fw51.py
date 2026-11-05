# -*- coding: utf-8 -*-
"""The 8751 firmware wrapped as an MCU with the same Z80-facing interface as
tools/ref_mcu.RefMCU and firmware/fwmcu.FirmwareMCU: z80_write, z80_post,
run, run_cycles, .mailbox, .tram.  Models our board glue: mailbox latches at
0400/0401, mailbox at 0800, tilemap at 2000, km-z.4h at 8000 (MOVX space)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build51 import build
from cpu8051 import CPU8051

CMDLAT, SLOTLAT, MBOX, TILEMAP, DATA = 0x0400, 0x0401, 0x0800, 0x2000, 0x8000
CLOCK_HZ = 8_000_000            # own crystal, as the 8751 on Irem's M72
SENTINEL = 0xFFF0


class FirmwareMCU51:
    def __init__(self, data, image=None, labels=None):
        if image is None:
            image, labels = build()
        self.labels = labels
        self.data = data
        self.lat = [0, 0]
        self.cpu = CPU8051(image, self._xrd, self._xwr)
        self.main = labels["main"]
        self.run()

    # board glue -------------------------------------------------------------
    def _xrd(self, a):
        if a >= DATA:
            i = a - DATA
            return self.data[i] if i < len(self.data) else 0xFF
        if a == CMDLAT: return self.lat[0]
        if a == SLOTLAT: return self.lat[1]
        return self.cpu.xmem[a]

    def _xwr(self, a, v):
        if a >= DATA: return                       # ROM
        if a == CMDLAT: self.lat[0] = 0; return    # any write clears
        if a == SLOTLAT: self.lat[1] &= ~v & 0xFF; return
        self.cpu.xmem[a] = v & 0xFF

    # running ----------------------------------------------------------------
    def run(self, max_steps=50_000_000):
        c = self.cpu
        for _ in range(max_steps):
            if c.pc == self.main and self.lat == [0, 0]:
                return
            c.step()
        raise RuntimeError(f"firmware never went idle (PC={c.pc:04x})")

    def run_cycles(self, n):
        end = self.cpu.cycles + n
        while self.cpu.cycles < end:
            self.cpu.step()

    def call(self, label, r6=0, r7=0, max_steps=10_000_000):
        """Call a routine directly (unit tests); returns A."""
        c = self.cpu
        c.iram[6], c.iram[7] = r6, r7
        c.push(SENTINEL & 0xFF); c.push(SENTINEL >> 8)
        c.pc = self.labels[label]
        for _ in range(max_steps):
            if c.pc == SENTINEL:
                return c.A
            c.step()
        raise RuntimeError("runaway")

    # Z80 side ---------------------------------------------------------------
    def z80_post(self, offset, data):
        if offset < 0x800:
            self.cpu.xmem[MBOX + offset] = data & 0xFF
        if offset == 0:
            self.lat[0] |= 0x80
        if 0x10 <= offset < 0x30 and not offset & 3:
            self.lat[1] |= 1 << ((offset - 0x10) >> 2)

    def z80_write(self, offset, data):
        self.z80_post(offset, data)
        self.run()

    @property
    def mailbox(self):
        return self.cpu.xmem[MBOX:MBOX + 0x800]

    @property
    def tram(self):
        return self.cpu.xmem[TILEMAP:TILEMAP + 0x4000]

    def ms(self, cycles):
        return cycles * 12 / CLOCK_HZ * 1000
