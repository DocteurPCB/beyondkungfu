# -*- coding: utf-8 -*-
"""Tiny Motorola 6803/6801 CPU emulator (subset) used to validate MCU firmware.

Memory model (our chosen MCU bus convention, see docs/SPEC.md):
  0x0009-0x000A : 6801 free-running counter (one tick per E cycle)
  0x0080-0x00FF : internal RAM (variables + stack)
  0x0800-0x0FFF : shared mailbox (2K)
  0x2000-0x5FFF : tilemap RAM (16K)
  0x6000-0xDFFF : km-z.4h, flat (logical address + 0x6000)
  0xF000-0xFFFF : internal firmware ROM (4K) + vectors

Cycle counts follow the 6801/6803 datasheet timings for the instructions the
firmware uses (approximate for a few rarely used ones).
"""
from asm6803 import OPC

DATA_BASE = 0x6000
DATA_END = 0xE000
REV = {v: k for k, v in OPC.items()}

MEMOPS = {"INC", "DEC", "CLR", "TST"}
WIDE_LD = {"LDX", "LDD", "LDS"}
WIDE_ST = {"STX", "STD", "STS"}
WIDE = WIDE_LD | WIDE_ST
ARITH16 = {"ADDD", "SUBD", "CPX"}
INH_CYC = {"INX": 3, "DEX": 3, "INS": 3, "DES": 3, "ABX": 3, "ASLD": 3, "LSLD": 3,
           "LSRD": 3, "PSHA": 3, "PSHB": 3, "PULA": 4, "PULB": 4, "PSHX": 4,
           "PULX": 5, "RTS": 5, "RTI": 10, "MUL": 10, "TSX": 3, "TXS": 3}


def cycles(mnem, mode):
    """6801/6803 cycle count for one instruction."""
    if mode == "INH":  return INH_CYC.get(mnem, 2)
    if mode == "REL":  return 6 if mnem == "BSR" else 3
    if mode == "IMM8": return 2
    if mode == "IMM16": return 4 if mnem in ARITH16 else 3
    if mnem == "JMP":  return 3
    if mnem in MEMOPS: return 6
    if mode == "DIR":
        if mnem == "JSR": return 5
        return 5 if mnem in ARITH16 else 4 if mnem in WIDE else 3
    # IDX / EXT
    if mnem == "JSR": return 6
    if mnem in ARITH16: return 6
    if mnem in WIDE: return 5
    return 4


CYC = {op: cycles(m, md) for op, (m, md) in REV.items()}


class CPU6803:
    def __init__(self, data_rom=b""):
        self.m = bytearray(0x10000)
        self.data_rom = data_rom          # km-z.4h, 0x8000 bytes
        self.A = self.B = 0
        self.X = 0; self.SP = 0x00FF; self.PC = 0
        self.H = self.I = self.N = self.Z = self.V = self.C = 0
        self.steps = 0
        self.cycles = 0

    # ---- memory ----
    def rd(self, a):
        a &= 0xFFFF
        if a == 0x09:                       # 6801 free-running counter, high
            return (self.cycles >> 8) & 0xFF
        if a == 0x0A:                       # ... and low (one tick per E cycle)
            return self.cycles & 0xFF
        if DATA_BASE <= a < DATA_END:
            idx = a - DATA_BASE
            return self.data_rom[idx] if idx < len(self.data_rom) else 0xFF
        return self.m[a]

    def wr(self, a, v):
        self.m[a & 0xFFFF] = v & 0xFF

    def rd16(self, a):
        return (self.rd(a) << 8) | self.rd(a + 1)

    def load(self, base, blob):
        self.m[base:base + len(blob)] = blob

    # ---- helpers ----
    def _nz(self, v):
        self.N = (v >> 7) & 1
        self.Z = 1 if (v & 0xFF) == 0 else 0

    def _fetch(self):
        op = self.rd(self.PC); self.PC = (self.PC + 1) & 0xFFFF; return op

    def _fetch16(self):
        hi = self._fetch(); return (hi << 8) | self._fetch()

    def _push(self, v):
        self.wr(self.SP, v); self.SP = (self.SP - 1) & 0xFFFF

    def _pop(self):
        self.SP = (self.SP + 1) & 0xFFFF; return self.rd(self.SP)

    def _push16(self, v):
        self._push(v & 0xFF); self._push((v >> 8) & 0xFF)

    def _pop16(self):
        hi = self._pop(); return (hi << 8) | self._pop()

    def _sub8(self, a, m, borrow=0):
        r = a - m - borrow
        rr = r & 0xFF
        self.C = 1 if r < 0 else 0
        self.V = 1 if ((a ^ m) & (a ^ rr) & 0x80) else 0
        self._nz(rr)
        return rr

    def _add8(self, a, m, carry=0):
        r = a + m + carry
        rr = r & 0xFF
        self.C = 1 if r > 0xFF else 0
        self.H = 1 if ((a & 0xF) + (m & 0xF) + carry) > 0xF else 0
        self.V = 1 if ((a ^ rr) & (m ^ rr) & 0x80) else 0
        self._nz(rr)
        return rr

    def _ea(self, mode):
        if mode == "DIR": return self._fetch()
        if mode == "EXT": return self._fetch16()
        return (self.X + self._fetch()) & 0xFFFF     # IDX

    def _cond(self, mnem):
        C, Z, N, V = self.C, self.Z, self.N, self.V
        if mnem == "BRA": return True
        if mnem == "BRN": return False
        if mnem == "BHI": return C == 0 and Z == 0
        if mnem == "BLS": return C == 1 or Z == 1
        if mnem == "BCC": return C == 0
        if mnem == "BCS": return C == 1
        if mnem == "BNE": return Z == 0
        if mnem == "BEQ": return Z == 1
        if mnem == "BVC": return V == 0
        if mnem == "BVS": return V == 1
        if mnem == "BPL": return N == 0
        if mnem == "BMI": return N == 1
        if mnem == "BGE": return (N ^ V) == 0
        if mnem == "BLT": return (N ^ V) == 1
        if mnem == "BGT": return Z == 0 and (N ^ V) == 0
        if mnem == "BLE": return Z == 1 or (N ^ V) == 1
        raise Exception(mnem)

    # ---- execution ----
    def step(self):
        self.steps += 1
        pc0 = self.PC
        op = self._fetch()
        try:
            mnem, mode = REV[op]
        except KeyError:
            raise Exception(f"unimplemented opcode {op:02x} at {pc0:04x}")
        self.cycles += CYC[op]

        if mode == "REL":
            rel = self._fetch()
            if rel & 0x80: rel -= 0x100
            if mnem == "BSR":
                self._push16(self.PC); self.PC = (self.PC + rel) & 0xFFFF
            elif self._cond(mnem):
                self.PC = (self.PC + rel) & 0xFFFF
            return
        if mnem == "RTS" or mnem == "RTI":
            self.PC = self._pop16(); return
        if mnem == "JMP":
            self.PC = self._ea(mode); return
        if mnem == "JSR":
            ea = self._ea(mode); self._push16(self.PC); self.PC = ea; return
        if mode == "INH":
            self._inherent(mnem); return

        if mnem in MEMOPS:
            ea = self._ea(mode); v = self.rd(ea)
            if mnem == "INC":
                v = (v + 1) & 0xFF; self.V = 1 if v == 0x80 else 0; self._nz(v); self.wr(ea, v)
            elif mnem == "DEC":
                v = (v - 1) & 0xFF; self.V = 1 if v == 0x7F else 0; self._nz(v); self.wr(ea, v)
            elif mnem == "CLR":
                self.wr(ea, 0); self.N = 0; self.Z = 1; self.V = 0; self.C = 0
            else:  # TST
                self._nz(v); self.V = 0; self.C = 0
            return

        if mnem in WIDE_LD:
            val = self._fetch16() if mode == "IMM16" else self.rd16(self._ea(mode))
            if mnem == "LDX": self.X = val
            elif mnem == "LDD": self.A = val >> 8; self.B = val & 0xFF
            else: self.SP = val
            self.N = (val >> 15) & 1; self.Z = 1 if val == 0 else 0; self.V = 0
            return
        if mnem in WIDE_ST:
            ea = self._ea(mode)
            val = self.X if mnem == "STX" else (self.SP if mnem == "STS" else (self.A << 8) | self.B)
            self.wr(ea, val >> 8); self.wr(ea + 1, val & 0xFF)
            self.N = (val >> 15) & 1; self.Z = 1 if val == 0 else 0; self.V = 0
            return
        if mnem == "CPX":   # 6801: full 16-bit compare, C valid
            val = self._fetch16() if mode == "IMM16" else self.rd16(self._ea(mode))
            r = self.X - val; rr = r & 0xFFFF
            self.C = 1 if r < 0 else 0
            self.V = 1 if ((self.X ^ val) & (self.X ^ rr) & 0x8000) else 0
            self.N = (rr >> 15) & 1; self.Z = 1 if rr == 0 else 0
            return
        if mnem in ("ADDD", "SUBD"):
            val = self._fetch16() if mode == "IMM16" else self.rd16(self._ea(mode))
            d = (self.A << 8) | self.B
            r = d + val if mnem == "ADDD" else d - val
            self.C = 1 if (r > 0xFFFF or r < 0) else 0
            r &= 0xFFFF; self.A = r >> 8; self.B = r & 0xFF
            self.N = (r >> 15) & 1; self.Z = 1 if r == 0 else 0
            return

        self._acc_op(mnem, mode)

    def _get_m(self, mode):
        if mode == "IMM8": return self._fetch()
        return self.rd(self._ea(mode))

    def _acc_op(self, mnem, mode):
        isB = mnem.endswith("B")
        base = mnem[:-1]
        cur = self.B if isB else self.A
        def put(v):
            if isB: self.B = v & 0xFF
            else: self.A = v & 0xFF
        if base == "LDA":
            v = self._get_m(mode); put(v); self._nz(v); self.V = 0
        elif base == "STA":
            self.wr(self._ea(mode), cur); self._nz(cur); self.V = 0
        elif base == "ADD": put(self._add8(cur, self._get_m(mode)))
        elif base == "ADC": put(self._add8(cur, self._get_m(mode), self.C))
        elif base == "SUB": put(self._sub8(cur, self._get_m(mode)))
        elif base == "SBC": put(self._sub8(cur, self._get_m(mode), self.C))
        elif base == "CMP": self._sub8(cur, self._get_m(mode))
        elif base == "AND":
            r = cur & self._get_m(mode); put(r); self._nz(r); self.V = 0
        elif base == "BIT":
            r = cur & self._get_m(mode); self._nz(r); self.V = 0
        elif base == "EOR":
            r = cur ^ self._get_m(mode); put(r); self._nz(r); self.V = 0
        elif base == "ORA":
            r = cur | self._get_m(mode); put(r); self._nz(r); self.V = 0
        else:
            raise Exception(f"acc op {mnem} {mode}")

    def _inherent(self, mnem):
        A, B = self.A, self.B
        if mnem == "NOP": return
        if mnem == "CLRA": self.A = 0; self.N = 0; self.Z = 1; self.V = 0; self.C = 0; return
        if mnem == "CLRB": self.B = 0; self.N = 0; self.Z = 1; self.V = 0; self.C = 0; return
        if mnem == "TAB": self.B = A; self._nz(A); self.V = 0; return
        if mnem == "TBA": self.A = B; self._nz(B); self.V = 0; return
        if mnem == "ABA": self.A = self._add8(A, B); return
        if mnem == "SBA": self.A = self._sub8(A, B); return
        if mnem == "CBA": self._sub8(A, B); return
        if mnem == "INX": self.X = (self.X + 1) & 0xFFFF; self.Z = 1 if self.X == 0 else 0; return
        if mnem == "DEX": self.X = (self.X - 1) & 0xFFFF; self.Z = 1 if self.X == 0 else 0; return
        if mnem == "ABX": self.X = (self.X + B) & 0xFFFF; return
        if mnem == "INS": self.SP = (self.SP + 1) & 0xFFFF; return
        if mnem == "DES": self.SP = (self.SP - 1) & 0xFFFF; return
        if mnem == "INCA": self.A = (A + 1) & 0xFF; self._nz(self.A); self.V = 1 if self.A == 0x80 else 0; return
        if mnem == "DECA": self.A = (A - 1) & 0xFF; self._nz(self.A); self.V = 1 if self.A == 0x7F else 0; return
        if mnem == "INCB": self.B = (B + 1) & 0xFF; self._nz(self.B); self.V = 1 if self.B == 0x80 else 0; return
        if mnem == "DECB": self.B = (B - 1) & 0xFF; self._nz(self.B); self.V = 1 if self.B == 0x7F else 0; return
        if mnem == "TSTA": self._nz(A); self.V = 0; self.C = 0; return
        if mnem == "TSTB": self._nz(B); self.V = 0; self.C = 0; return
        if mnem == "PSHA": self._push(A); return
        if mnem == "PSHB": self._push(B); return
        if mnem == "PULA": self.A = self._pop(); return
        if mnem == "PULB": self.B = self._pop(); return
        if mnem == "PSHX": self._push16(self.X); return
        if mnem == "PULX": self.X = self._pop16(); return
        if mnem in ("ASLA", "LSLA"): self.C = A >> 7; self.A = (A << 1) & 0xFF; self._nz(self.A); self.V = self.N ^ self.C; return
        if mnem in ("ASLB", "LSLB"): self.C = B >> 7; self.B = (B << 1) & 0xFF; self._nz(self.B); self.V = self.N ^ self.C; return
        if mnem == "LSRA": self.C = A & 1; self.A = A >> 1; self._nz(self.A); self.V = self.C; return
        if mnem == "LSRB": self.C = B & 1; self.B = B >> 1; self._nz(self.B); self.V = self.C; return
        if mnem == "ASRA": self.C = A & 1; self.A = (A >> 1) | (A & 0x80); self._nz(self.A); return
        if mnem == "RORA": c = A & 1; self.A = (A >> 1) | (self.C << 7); self.C = c; self._nz(self.A); return
        if mnem == "ROLA": c = A >> 7; self.A = ((A << 1) | self.C) & 0xFF; self.C = c; self._nz(self.A); return
        if mnem == "COMA": self.A = (~A) & 0xFF; self._nz(self.A); self.C = 1; self.V = 0; return
        if mnem == "NEGA": self.A = self._sub8(0, A); return
        if mnem in ("ASLD", "LSLD"):
            d = (A << 8) | B; self.C = d >> 15; d = (d << 1) & 0xFFFF
            self.A = d >> 8; self.B = d & 0xFF; self.N = d >> 15; self.Z = 1 if d == 0 else 0; return
        if mnem == "LSRD":
            d = (A << 8) | B; self.C = d & 1; d >>= 1
            self.A = d >> 8; self.B = d & 0xFF; self.N = 0; self.Z = 1 if d == 0 else 0; return
        if mnem == "MUL":
            r = A * B; self.A = r >> 8; self.B = r & 0xFF; self.C = (r >> 7) & 1; return
        if mnem == "SEC": self.C = 1; return
        if mnem == "CLC": self.C = 0; return
        if mnem == "SEI": self.I = 1; return
        if mnem == "CLI": self.I = 0; return
        raise Exception(f"inherent {mnem} not implemented")

    def call(self, pc, max_steps=1_000_000):
        """Call a subroutine at pc; return when its RTS pops the sentinel."""
        sentinel = 0xFFFE
        self._push16(sentinel)
        self.PC = pc
        for _ in range(max_steps):
            if self.PC == sentinel:
                return
            self.step()
        raise Exception(f"runaway (no RTS), PC={self.PC:04x}")
