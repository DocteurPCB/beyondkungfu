# -*- coding: utf-8 -*-
"""Tiny Motorola 6803 CPU emulator (subset) used to validate MCU firmware.

Memory model (our chosen MCU bus convention, documented separately):
  0x0000-0x001F : I/O registers (0x0020 = data-ROM bank latch)
  0x0020        : BANK latch (bit0 selects which 16K half of km-z.4h)
  0x0040-0x00FF : scratch RAM
  0x0800-0x0FFF : shared mailbox (2K)  [not used by the decode self-test]
  0x2000-0x5FFF : tilemap RAM window   [not used by the decode self-test]
  0x8000-0xBFFF : 16K window onto km-z.4h, selected by BANK
  0xF000-0xFFFF : internal firmware ROM (4K)
"""

BANK_REG = 0x0020
WIN_BASE = 0x8000
WIN_SIZE = 0x4000

class CPU6803:
    def __init__(self, data_rom=b""):
        self.m = bytearray(0x10000)
        self.data_rom = data_rom          # km-z.4h, 0x8000 bytes
        self.A = self.B = 0
        self.X = 0; self.SP = 0x01FF; self.PC = 0
        self.H=self.I=self.N=self.Z=self.V=self.C = 0
        self.cycles = 0

    # ---- memory ----
    def rd(self, a):
        a &= 0xFFFF
        if WIN_BASE <= a < WIN_BASE + WIN_SIZE:
            bank = self.m[BANK_REG] & 1
            idx = bank * WIN_SIZE + (a - WIN_BASE)
            return self.data_rom[idx] if idx < len(self.data_rom) else 0xFF
        return self.m[a]

    def wr(self, a, v):
        self.m[a & 0xFFFF] = v & 0xFF

    def rd16(self, a):
        return (self.rd(a) << 8) | self.rd(a+1)

    def load(self, base, blob):
        for i, byte in enumerate(blob):
            self.m[(base+i) & 0xFFFF] = byte

    # ---- helpers ----
    def _setNZ(self, v):
        self.N = 1 if (v & 0x80) else 0
        self.Z = 1 if (v & 0xFF) == 0 else 0

    def _fetch(self):
        op = self.rd(self.PC); self.PC = (self.PC+1) & 0xFFFF; return op
    def _fetch16(self):
        hi = self._fetch(); lo = self._fetch(); return (hi<<8)|lo

    def _push(self, v):
        self.wr(self.SP, v & 0xFF); self.SP = (self.SP-1) & 0xFFFF
    def _pop(self):
        self.SP = (self.SP+1) & 0xFFFF; return self.rd(self.SP)
    def _push16(self, v):               # 6800 pushes low then high (so high at lower addr)
        self._push(v & 0xFF); self._push((v>>8) & 0xFF)
    def _pop16(self):
        hi = self._pop(); lo = self._pop(); return (hi<<8)|lo

    # ALU
    def _sub8(self, a, m, borrow=0, store=True):
        r = a - m - borrow
        self.C = 1 if (r & 0x100) else 0
        rr = r & 0xFF
        self.V = 1 if ((a ^ m) & (a ^ rr) & 0x80) else 0
        self._setNZ(rr)
        return rr
    def _add8(self, a, m, carry=0):
        r = a + m + carry
        self.C = 1 if (r & 0x100) else 0
        rr = r & 0xFF
        self.H = 1 if (((a & 0xf)+(m & 0xf)+carry) & 0x10) else 0
        self.V = 1 if ((a ^ rr) & (m ^ rr) & 0x80) else 0
        self._setNZ(rr)
        return rr

    # effective operand for a given mode
    def _ea(self, mode):
        if mode == "DIR": return self._fetch()
        if mode == "EXT": return self._fetch16()
        if mode == "IDX": return (self.X + self._fetch()) & 0xFFFF
        raise Exception(mode)

    def step(self):
        op = self._fetch()
        from asm6803 import OPC
        if not hasattr(self, "_rev"):
            self._rev = {v:k for k,v in OPC.items()}
        if op not in self._rev:
            raise Exception(f"unimplemented opcode {op:02x} at {(self.PC-1)&0xFFFF:04x}")
        mnem, mode = self._rev[op]

        # operand value fetch for read-style ops
        def operand_value():
            if mode == "IMM8": return self._fetch()
            if mode == "IMM16": return self._fetch16()
            ea = self._ea(mode); return ea  # caller reads
        # ---- control flow ----
        if mode == "REL":
            rel = self._fetch()
            if rel & 0x80: rel -= 0x100
            take = {
                "BRA":1,"BRN":0,
                "BHI": (self.C==0 and self.Z==0), "BLS": (self.C or self.Z),
                "BCC": self.C==0, "BCS": self.C==1, "BNE": self.Z==0, "BEQ": self.Z==1,
                "BVC": self.V==0, "BVS": self.V==1, "BPL": self.N==0, "BMI": self.N==1,
                "BGE": (self.N ^ self.V)==0, "BLT": (self.N ^ self.V)==1,
                "BGT": (self.Z==0 and (self.N ^ self.V)==0), "BLE": (self.Z or (self.N ^ self.V)),
            }.get(mnem, 0)
            if mnem == "BSR":
                self._push16(self.PC)
                self.PC = (self.PC + rel) & 0xFFFF
            elif take:
                self.PC = (self.PC + rel) & 0xFFFF
            return

        if mnem == "RTS":
            self.PC = self._pop16(); return
        if mnem == "RTI":
            # minimal
            self.PC = self._pop16(); return
        if mnem == "JMP":
            self.PC = self._ea(mode); return
        if mnem == "JSR":
            ea = self._ea(mode); self._push16(self.PC); self.PC = ea; return

        # ---- inherent accumulator ops ----
        if mode == "INH":
            self._inherent(mnem); return

        # ---- 16-bit loads/stores ----
        if mnem in ("LDX","LDD","LDS"):
            if mode == "IMM16": val = self._fetch16()
            else: val = self.rd16(self._ea(mode))
            if mnem=="LDX": self.X = val
            elif mnem=="LDD": self.A=(val>>8)&0xFF; self.B=val&0xFF
            else: self.SP = val
            self._setNZ((val>>8)); self.Z = 1 if val==0 else 0; self.V=0; return
        if mnem in ("STX","STD","STS"):
            ea = self._ea(mode)
            val = self.X if mnem=="STX" else (self.SP if mnem=="STS" else ((self.A<<8)|self.B))
            self.wr(ea, (val>>8)&0xFF); self.wr(ea+1, val&0xFF)
            self._setNZ((val>>8)); self.Z = 1 if (val&0xFFFF)==0 else 0; self.V=0; return
        if mnem in ("CPX",):
            val = self._fetch16() if mode=="IMM16" else self.rd16(self._ea(mode))
            r = (self.X - val) & 0xFFFF
            self.Z = 1 if r==0 else 0; self.N = 1 if (r & 0x8000) else 0; return
        if mnem in ("ADDD","SUBD"):
            val = self._fetch16() if mode=="IMM16" else self.rd16(self._ea(mode))
            d = (self.A<<8)|self.B
            r = d+val if mnem=="ADDD" else d-val
            self.C = 1 if (r & 0x10000) else 0
            r &= 0xFFFF; self.A=(r>>8)&0xFF; self.B=r&0xFF
            self.N=1 if (r&0x8000) else 0; self.Z=1 if r==0 else 0; return

        # ---- 8-bit accumulator ops (A or B) ----
        self._acc_op(mnem, mode); return

    def _get_m(self, mode):
        if mode == "IMM8": return self._fetch()
        return self.rd(self._ea(mode))

    def _acc_op(self, mnem, mode):
        reg = 'B' if mnem.endswith('B') else 'A'
        base = mnem[:-1]  # e.g. LDA, STA, ADD, SUB, AND, EOR, ORA->OR? handle below
        cur = self.B if reg=='B' else self.A
        def put(v):
            if reg=='B': self.B = v & 0xFF
            else: self.A = v & 0xFF
        if base == 'LDA':
            v = self._get_m(mode); put(v); self._setNZ(v); self.V=0; return
        if base == 'STA':
            ea = self._ea(mode); self.wr(ea, cur); self._setNZ(cur); self.V=0; return
        if base == 'ADD':
            m = self._get_m(mode); put(self._add8(cur, m)); return
        if base == 'ADC':
            m = self._get_m(mode); put(self._add8(cur, m, self.C)); return
        if base == 'SUB':
            m = self._get_m(mode); put(self._sub8(cur, m)); return
        if base == 'SBC':
            m = self._get_m(mode); put(self._sub8(cur, m, self.C)); return
        if base == 'CMP':
            m = self._get_m(mode); self._sub8(cur, m); return
        if base == 'AND':
            m = self._get_m(mode); r = cur & m; put(r); self._setNZ(r); self.V=0; return
        if base == 'BIT':
            m = self._get_m(mode); r = cur & m; self._setNZ(r); self.V=0; return
        if base == 'EOR':
            m = self._get_m(mode); r = cur ^ m; put(r); self._setNZ(r); self.V=0; return
        if base == 'ORA' or base == 'OR':
            m = self._get_m(mode); r = cur | m; put(r); self._setNZ(r); self.V=0; return
        raise Exception(f"acc op {mnem} {mode}")

    def _inherent(self, mnem):
        if mnem == 'NOP': return
        if mnem == 'CLRA': self.A=0; self.N=0;self.Z=1;self.V=0;self.C=0; return
        if mnem == 'CLRB': self.B=0; self.N=0;self.Z=1;self.V=0;self.C=0; return
        if mnem == 'TAB': self.B=self.A; self._setNZ(self.B); self.V=0; return
        if mnem == 'TBA': self.A=self.B; self._setNZ(self.A); self.V=0; return
        if mnem == 'ABA': self.A=self._add8(self.A,self.B); return
        if mnem == 'SBA': self.A=self._sub8(self.A,self.B); return
        if mnem == 'CBA': self._sub8(self.A,self.B); return
        if mnem == 'INX': self.X=(self.X+1)&0xFFFF; self.Z=1 if self.X==0 else 0; return
        if mnem == 'DEX': self.X=(self.X-1)&0xFFFF; self.Z=1 if self.X==0 else 0; return
        if mnem == 'INS': self.SP=(self.SP+1)&0xFFFF; return
        if mnem == 'DES': self.SP=(self.SP-1)&0xFFFF; return
        if mnem == 'INCA': self.A=(self.A+1)&0xFF; self._setNZ(self.A); self.V=1 if self.A==0x80 else 0; return
        if mnem == 'DECA': self.A=(self.A-1)&0xFF; self._setNZ(self.A); self.V=1 if self.A==0x7F else 0; return
        if mnem == 'INCB': self.B=(self.B+1)&0xFF; self._setNZ(self.B); return
        if mnem == 'DECB': self.B=(self.B-1)&0xFF; self._setNZ(self.B); return
        if mnem == 'TSTA': self._setNZ(self.A); self.V=0;self.C=0; return
        if mnem == 'TSTB': self._setNZ(self.B); self.V=0;self.C=0; return
        if mnem == 'PSHA': self._push(self.A); return
        if mnem == 'PSHB': self._push(self.B); return
        if mnem == 'PULA': self.A=self._pop(); return
        if mnem == 'PULB': self.B=self._pop(); return
        if mnem == 'PSHX': self._push16(self.X); return
        if mnem == 'PULX': self.X=self._pop16(); return
        if mnem in ('ASLA','LSLA'):
            self.C=(self.A>>7)&1; self.A=(self.A<<1)&0xFF; self._setNZ(self.A); return
        if mnem == 'LSRA':
            self.C=self.A&1; self.A=(self.A>>1)&0xFF; self._setNZ(self.A); return
        if mnem == 'ASRA':
            self.C=self.A&1; self.A=((self.A>>1)|(self.A&0x80))&0xFF; self._setNZ(self.A); return
        if mnem == 'RORA':
            c=self.A&1; self.A=((self.A>>1)|(self.C<<7))&0xFF; self.C=c; self._setNZ(self.A); return
        if mnem == 'ROLA':
            c=(self.A>>7)&1; self.A=((self.A<<1)|self.C)&0xFF; self.C=c; self._setNZ(self.A); return
        if mnem == 'COMA': self.A=(~self.A)&0xFF; self._setNZ(self.A); self.C=1;self.V=0; return
        if mnem == 'NEGA': self.A=self._sub8(0,self.A); return
        if mnem == 'SEC': self.C=1; return
        if mnem == 'CLC': self.C=0; return
        if mnem == 'SEI': self.I=1; return
        if mnem == 'CLI': self.I=0; return
        if mnem == 'MUL':
            r=self.A*self.B; self.A=(r>>8)&0xFF; self.B=r&0xFF; self.C=(r>>7)&1; return
        if mnem == 'ABX': self.X=(self.X+self.B)&0xFFFF; return
        if mnem == 'TAP':
            v=self.A; self.H=(v>>5)&1;self.I=(v>>4)&1;self.N=(v>>3)&1;self.Z=(v>>2)&1;self.V=(v>>1)&1;self.C=v&1; return
        if mnem == 'TPA':
            self.A=0xC0|(self.H<<5)|(self.I<<4)|(self.N<<3)|(self.Z<<2)|(self.V<<1)|self.C; return
        raise Exception(f"inherent {mnem} not implemented")

    def call(self, pc, max_steps=100000):
        """Call a subroutine at pc, return when its RTS pops the sentinel."""
        sentinel = 0xFFFE
        self._push16(sentinel)
        self.PC = pc
        for _ in range(max_steps):
            if self.PC == sentinel: return
            self.step()
        raise Exception("runaway (no RTS)")
