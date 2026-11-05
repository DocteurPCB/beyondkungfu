# -*- coding: utf-8 -*-
"""Intel 8051/8751 CPU emulator (full instruction set, machine-cycle counts,
timer 0/1 in modes 0-2) used to validate the 8751 variant of the firmware.

External data memory (MOVX) goes through xrd/xwr so the test harness can model
the board: mailbox latches, mailbox, tilemap, data ROM.  MOVX @Ri uses P2 as
the high address byte, as on the real chip.
"""

PSW, ACC, B_, SP, DPL, DPH, P0, P1, P2, P3 = 0xD0, 0xE0, 0xF0, 0x81, 0x82, 0x83, 0x80, 0x90, 0xA0, 0xB0
TCON, TMOD, TL0, TL1, TH0, TH1, IE = 0x88, 0x89, 0x8A, 0x8B, 0x8C, 0x8D, 0xA8

# machine cycles per opcode
CYC = [1] * 256
for op in (0x02, 0x10, 0x12, 0x20, 0x22, 0x30, 0x32, 0x40, 0x43, 0x50, 0x53, 0x60, 0x63,
           0x70, 0x72, 0x73, 0x75, 0x80, 0x82, 0x83, 0x85, 0x86, 0x87, 0x90, 0x92, 0x93,
           0xA0, 0xA3, 0xA6, 0xA7, 0xB0, 0xB4, 0xB5, 0xB6, 0xB7, 0xC0, 0xD0, 0xD5,
           0xE0, 0xE2, 0xE3, 0xF0, 0xF2, 0xF3):
    CYC[op] = 2
for op in range(0x88, 0x90): CYC[op] = 2            # MOV dir,Rn
for op in range(0xA8, 0xB0): CYC[op] = 2            # MOV Rn,dir
for op in range(0xB8, 0xC0): CYC[op] = 2            # CJNE Rn,#,rel
for op in range(0xD8, 0xE0): CYC[op] = 2            # DJNZ Rn,rel
for op in range(0x01, 0x100, 0x10): CYC[op] = 2     # AJMP
for op in range(0x11, 0x100, 0x20): CYC[op] = 2     # ACALL
CYC[0x84] = CYC[0xA4] = 4                           # DIV / MUL


class CPU8051:
    def __init__(self, code, xrd=None, xwr=None):
        self.code = bytearray(0x10000)
        self.code[:len(code)] = code
        self.iram = bytearray(256)
        self.sfr = bytearray(256)
        self.sfr[SP] = 0x07
        self.sfr[P0] = self.sfr[P1] = self.sfr[P2] = self.sfr[P3] = 0xFF
        self.pc = 0
        self.cycles = 0
        self.xmem = bytearray(0x10000)
        self.xrd = xrd or (lambda a: self.xmem[a])
        self.xwr = xwr or (lambda a, v: self.xmem.__setitem__(a, v))

    # ---------------------------------------------------------------- access
    @property
    def A(self): return self.sfr[ACC]
    @A.setter
    def A(self, v): self.sfr[ACC] = v & 0xFF

    def cy(self): return self.sfr[PSW] >> 7
    def set_cy(self, c): self.sfr[PSW] = (self.sfr[PSW] & 0x7F) | (0x80 if c else 0)

    def rn(self, n): return ((self.sfr[PSW] >> 3) & 3) * 8 + n

    def dget(self, a):
        if a < 0x80: return self.iram[a]
        if a == PSW: return self._psw()
        return self.sfr[a]

    def dset(self, a, v):
        v &= 0xFF
        if a < 0x80: self.iram[a] = v
        else: self.sfr[a] = v

    def _psw(self):
        p = bin(self.sfr[ACC]).count("1") & 1
        return (self.sfr[PSW] & 0xFE) | p

    def bit_addr(self, b):
        return (0x20 + (b >> 3), b & 7) if b < 0x80 else (b & 0xF8, b & 7)

    def bget(self, b):
        a, n = self.bit_addr(b)
        return (self.dget(a) >> n) & 1

    def bset(self, b, v):
        a, n = self.bit_addr(b)
        x = self.dget(a)
        self.dset(a, (x | (1 << n)) if v else (x & ~(1 << n)))

    def fetch(self):
        v = self.code[self.pc]; self.pc = (self.pc + 1) & 0xFFFF; return v

    def rel(self):
        r = self.fetch(); return r - 256 if r & 0x80 else r

    def push(self, v):
        self.sfr[SP] = (self.sfr[SP] + 1) & 0xFF; self.iram[self.sfr[SP]] = v & 0xFF

    def pop(self):
        v = self.iram[self.sfr[SP]]; self.sfr[SP] = (self.sfr[SP] - 1) & 0xFF; return v

    @property
    def dptr(self): return (self.sfr[DPH] << 8) | self.sfr[DPL]
    @dptr.setter
    def dptr(self, v): self.sfr[DPH] = (v >> 8) & 0xFF; self.sfr[DPL] = v & 0xFF

    # ------------------------------------------------------------ arithmetic
    def _add(self, v, c=0):
        a = self.A
        r = a + v + c
        ac = ((a & 0xF) + (v & 0xF) + c) > 0xF
        ov = ((a ^ r) & (v ^ r) & 0x80) != 0
        psw = self.sfr[PSW] & ~(0x80 | 0x40 | 0x04)
        self.sfr[PSW] = psw | (0x80 if r > 0xFF else 0) | (0x40 if ac else 0) | (0x04 if ov else 0)
        self.A = r

    def _subb(self, v):
        a, c = self.A, self.cy()
        r = a - v - c
        ac = ((a & 0xF) - (v & 0xF) - c) < 0
        ov = ((a ^ v) & (a ^ r) & 0x80) != 0
        psw = self.sfr[PSW] & ~(0x80 | 0x40 | 0x04)
        self.sfr[PSW] = psw | (0x80 if r < 0 else 0) | (0x40 if ac else 0) | (0x04 if ov else 0)
        self.A = r

    # ----------------------------------------------------------------- timer
    def _timers(self, n):
        tcon, tmod = self.sfr[TCON], self.sfr[TMOD]
        for t, (tl, th, tr, tf) in enumerate(((TL0, TH0, 0x10, 0x20), (TL1, TH1, 0x40, 0x80))):
            if not tcon & tr: continue
            mode = (tmod >> (4 * t)) & 3
            if mode == 1:
                v = ((self.sfr[th] << 8) | self.sfr[tl]) + n
                if v > 0xFFFF: self.sfr[TCON] |= tf
                v &= 0xFFFF; self.sfr[th] = v >> 8; self.sfr[tl] = v & 0xFF
            elif mode == 2:
                v = self.sfr[tl] + n
                while v > 0xFF:
                    self.sfr[TCON] |= tf; v = v - 0x100 + self.sfr[th]
                self.sfr[tl] = v
            elif mode == 0:
                v = ((self.sfr[th] << 5) | (self.sfr[tl] & 0x1F)) + n
                if v > 0x1FFF: self.sfr[TCON] |= tf
                v &= 0x1FFF; self.sfr[th] = v >> 5; self.sfr[tl] = (self.sfr[tl] & 0xE0) | (v & 0x1F)

    # ------------------------------------------------------------------ step
    def step(self):
        op = self.fetch()
        n = CYC[op]
        self._exec(op)
        self.cycles += n
        self._timers(n)

    def _src(self, op):
        """Operand of the low-nibble addressing modes 4..F (#, dir, @Ri, Rn)."""
        lo = op & 0x0F
        if lo == 4: return self.fetch()
        if lo == 5: return self.dget(self.fetch())
        if lo in (6, 7): return self.iram[self.iram[self.rn(lo - 6)]]
        return self.iram[self.rn(lo - 8)]

    def _dst_get_set(self, op):
        """Location for INC/DEC/MOV-to style ops with low nibble 5..F."""
        lo = op & 0x0F
        if lo == 5:
            a = self.fetch(); return (lambda: self.dget(a)), (lambda v: self.dset(a, v))
        if lo in (6, 7):
            a = self.iram[self.rn(lo - 6)]
            return (lambda: self.iram[a]), (lambda v: self.iram.__setitem__(a, v & 0xFF))
        r = self.rn(lo - 8)
        return (lambda: self.iram[r]), (lambda v: self.iram.__setitem__(r, v & 0xFF))

    def _exec(self, op):
        hi, lo = op >> 4, op & 0x0F
        # ---- AJMP / ACALL ----
        if lo == 1:
            a = ((op & 0xE0) << 3) | self.fetch()
            tgt = (self.pc & 0xF800) | a
            if hi & 1:
                self.push(self.pc & 0xFF); self.push(self.pc >> 8)
            self.pc = tgt
            return
        # ---- column 4..F arithmetic/logic rows ----
        if lo >= 4 and hi in (0x2, 0x3, 0x9, 0x4, 0x5, 0x6):
            if hi == 0x4 and lo >= 4: self.A = self.A | self._src(op); return
            if hi == 0x5 and lo >= 4: self.A = self.A & self._src(op); return
            if hi == 0x6 and lo >= 4: self.A = self.A ^ self._src(op); return
            if hi == 0x2: self._add(self._src(op)); return
            if hi == 0x3: self._add(self._src(op), self.cy()); return
            if hi == 0x9: self._subb(self._src(op)); return
        if hi == 0x0 and lo >= 5:                       # INC
            g, s = self._dst_get_set(op); s(g() + 1); return
        if hi == 0x1 and lo >= 5:                       # DEC
            g, s = self._dst_get_set(op); s(g() - 1); return
        if hi == 0x7 and lo >= 6:                       # MOV @Ri/Rn,#imm
            g, s = self._dst_get_set(op); s(self.fetch()); return
        if hi == 0x8 and lo >= 6:                       # MOV dir,@Ri/Rn
            v = self._src(op); self.dset(self.fetch(), v); return
        if hi == 0xA and lo >= 6:                       # MOV @Ri/Rn,dir
            g, s = self._dst_get_set(op); s(self.dget(self.fetch())); return
        if hi == 0xB and lo >= 4:                       # CJNE
            if lo == 4: x, y = self.A, self.fetch()
            elif lo == 5: x, y = self.A, self.dget(self.fetch())
            elif lo in (6, 7): x, y = self.iram[self.iram[self.rn(lo - 6)]], self.fetch()
            else: x, y = self.iram[self.rn(lo - 8)], self.fetch()
            r = self.rel()
            self.set_cy(x < y)
            if x != y: self.pc = (self.pc + r) & 0xFFFF
            return
        if hi == 0xC and lo >= 5:                       # XCH
            if lo == 5:
                a = self.fetch(); t = self.dget(a); self.dset(a, self.A); self.A = t
            else:
                g, s = self._dst_get_set(op if lo > 5 else op); t = g(); s(self.A); self.A = t
            return
        if hi == 0xD and lo >= 8:                       # DJNZ Rn
            r = self.rn(lo - 8); off = self.rel()
            self.iram[r] = (self.iram[r] - 1) & 0xFF
            if self.iram[r]: self.pc = (self.pc + off) & 0xFFFF
            return
        if hi == 0xD and lo in (6, 7):                  # XCHD
            a = self.iram[self.rn(lo - 6)]; t = self.iram[a]
            self.iram[a] = (t & 0xF0) | (self.A & 0x0F); self.A = (self.A & 0xF0) | (t & 0x0F); return
        if hi == 0xE and lo >= 5:                       # MOV A,src
            self.A = self._src(op); return
        if hi == 0xF and lo >= 5:                       # MOV dst,A
            g, s = self._dst_get_set(op); s(self.A); return
        # ---- the rest, one by one ----
        f = getattr(self, f"_op{op:02X}", None)
        if f is None:
            raise Exception(f"8051: unimplemented opcode {op:02X} at {(self.pc - 1) & 0xFFFF:04X}")
        f()

    # single opcodes
    def _op00(self): pass
    def _op02(self): self.pc = (self.fetch() << 8) | self.fetch()
    def _op03(self): a = self.A; self.A = (a >> 1) | ((a & 1) << 7)
    def _op04(self): self.A = self.A + 1
    def _op10(self):
        b = self.fetch(); r = self.rel()
        if self.bget(b): self.bset(b, 0); self.pc = (self.pc + r) & 0xFFFF
    def _op12(self):
        t = (self.fetch() << 8) | self.fetch()
        self.push(self.pc & 0xFF); self.push(self.pc >> 8); self.pc = t
    def _op13(self):
        a, c = self.A, self.cy(); self.set_cy(a & 1); self.A = (a >> 1) | (c << 7)
    def _op14(self): self.A = self.A - 1
    def _op20(self):
        b = self.fetch(); r = self.rel()
        if self.bget(b): self.pc = (self.pc + r) & 0xFFFF
    def _op22(self): hi = self.pop(); lo = self.pop(); self.pc = (hi << 8) | lo
    def _op32(self): self._op22()
    def _op23(self): a = self.A; self.A = ((a << 1) | (a >> 7))
    def _op30(self):
        b = self.fetch(); r = self.rel()
        if not self.bget(b): self.pc = (self.pc + r) & 0xFFFF
    def _op33(self):
        a, c = self.A, self.cy(); self.set_cy(a >> 7); self.A = (a << 1) | c
    def _op40(self):
        r = self.rel()
        if self.cy(): self.pc = (self.pc + r) & 0xFFFF
    def _op42(self): a = self.fetch(); self.dset(a, self.dget(a) | self.A)
    def _op43(self): a = self.fetch(); self.dset(a, self.dget(a) | self.fetch())
    def _op50(self):
        r = self.rel()
        if not self.cy(): self.pc = (self.pc + r) & 0xFFFF
    def _op52(self): a = self.fetch(); self.dset(a, self.dget(a) & self.A)
    def _op53(self): a = self.fetch(); self.dset(a, self.dget(a) & self.fetch())
    def _op60(self):
        r = self.rel()
        if self.A == 0: self.pc = (self.pc + r) & 0xFFFF
    def _op62(self): a = self.fetch(); self.dset(a, self.dget(a) ^ self.A)
    def _op63(self): a = self.fetch(); self.dset(a, self.dget(a) ^ self.fetch())
    def _op70(self):
        r = self.rel()
        if self.A != 0: self.pc = (self.pc + r) & 0xFFFF
    def _op72(self): self.set_cy(self.cy() | self.bget(self.fetch()))
    def _op73(self): self.pc = (self.A + self.dptr) & 0xFFFF
    def _op74(self): self.A = self.fetch()
    def _op75(self): a = self.fetch(); self.dset(a, self.fetch())
    def _op80(self): r = self.rel(); self.pc = (self.pc + r) & 0xFFFF
    def _op82(self): self.set_cy(self.cy() & self.bget(self.fetch()))
    def _op83(self): self.A = self.code[(self.A + self.pc) & 0xFFFF]
    def _op84(self):
        a, b = self.A, self.sfr[B_]
        psw = self.sfr[PSW] & ~(0x80 | 0x04)
        if b == 0: self.sfr[PSW] = psw | 0x04; return
        self.A = a // b; self.sfr[B_] = a % b; self.sfr[PSW] = psw
    def _op85(self): s = self.fetch(); d = self.fetch(); self.dset(d, self.dget(s))
    def _op90(self): self.dptr = (self.fetch() << 8) | self.fetch()
    def _op92(self): self.bset(self.fetch(), self.cy())
    def _op93(self): self.A = self.code[(self.A + self.dptr) & 0xFFFF]
    def _opA0(self): self.set_cy(self.cy() | (1 - self.bget(self.fetch())))
    def _opA2(self): self.set_cy(self.bget(self.fetch()))
    def _opA3(self): self.dptr = (self.dptr + 1) & 0xFFFF
    def _opA4(self):
        r = self.A * self.sfr[B_]
        self.A = r & 0xFF; self.sfr[B_] = r >> 8
        self.sfr[PSW] = (self.sfr[PSW] & ~(0x80 | 0x04)) | (0x04 if r > 0xFF else 0)
    def _opB0(self): self.set_cy(self.cy() & (1 - self.bget(self.fetch())))
    def _opB2(self): b = self.fetch(); self.bset(b, 1 - self.bget(b))
    def _opB3(self): self.set_cy(1 - self.cy())
    def _opC0(self): self.push(self.dget(self.fetch()))
    def _opC2(self): self.bset(self.fetch(), 0)
    def _opC3(self): self.set_cy(0)
    def _opC4(self): a = self.A; self.A = ((a << 4) | (a >> 4))
    def _opD0(self): a = self.fetch(); self.dset(a, self.pop())
    def _opD2(self): self.bset(self.fetch(), 1)
    def _opD3(self): self.set_cy(1)
    def _opD4(self):
        a, psw = self.A, self.sfr[PSW]
        if (a & 0x0F) > 9 or psw & 0x40: a += 6
        if a > 0xFF: psw |= 0x80
        if ((a >> 4) & 0x1F) > 9 or psw & 0x80: a += 0x60
        if a > 0xFF: psw |= 0x80
        self.sfr[PSW] = psw; self.A = a
    def _opD5(self):
        a = self.fetch(); r = self.rel(); v = (self.dget(a) - 1) & 0xFF
        self.dset(a, v)
        if v: self.pc = (self.pc + r) & 0xFFFF
    def _opE0(self): self.A = self.xrd(self.dptr)
    def _opE2(self): self.A = self.xrd((self.sfr[P2] << 8) | self.iram[self.rn(0)])
    def _opE3(self): self.A = self.xrd((self.sfr[P2] << 8) | self.iram[self.rn(1)])
    def _opE4(self): self.A = 0
    def _opF0(self): self.xwr(self.dptr, self.A)
    def _opF2(self): self.xwr((self.sfr[P2] << 8) | self.iram[self.rn(0)], self.A)
    def _opF3(self): self.xwr((self.sfr[P2] << 8) | self.iram[self.rn(1)], self.A)
    def _opF4(self): self.A = ~self.A
