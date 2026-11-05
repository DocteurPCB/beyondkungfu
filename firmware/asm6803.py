# -*- coding: utf-8 -*-
"""Minimal Motorola 6803/6801 assembler (subset) + CPU emulator.

Built from scratch to validate hand-written MCU firmware for Beyond Kung-Fu
against the MAME HLE reference, without needing to build MAME.

Only the opcodes the firmware actually uses are guaranteed; the table is easy
to extend.  Flags implemented for the arithmetic/logic ops used (H not needed).
"""

# ---------------------------------------------------------------------------
# Opcode table.  mode codes: INH, IMM8, IMM16, DIR, EXT, IDX, REL
# ---------------------------------------------------------------------------
OPC = {
    # inherent
    ("NOP", "INH"): 0x01, ("TAP","INH"):0x06, ("TPA","INH"):0x07,
    ("INX","INH"):0x08, ("DEX","INH"):0x09, ("CLV","INH"):0x0A, ("SEV","INH"):0x0B,
    ("CLC","INH"):0x0C, ("SEC","INH"):0x0D, ("CLI","INH"):0x0E, ("SEI","INH"):0x0F,
    ("SBA","INH"):0x10, ("CBA","INH"):0x11, ("TAB","INH"):0x16, ("TBA","INH"):0x17,
    ("ABA","INH"):0x1B,
    ("TSX","INH"):0x30, ("INS","INH"):0x31, ("PULA","INH"):0x32, ("PULB","INH"):0x33,
    ("DES","INH"):0x34, ("TXS","INH"):0x35, ("PSHA","INH"):0x36, ("PSHB","INH"):0x37,
    ("PULX","INH"):0x38, ("RTS","INH"):0x39, ("ABX","INH"):0x3A, ("RTI","INH"):0x3B,
    ("PSHX","INH"):0x3C, ("MUL","INH"):0x3D,
    ("NEGA","INH"):0x40, ("COMA","INH"):0x43, ("LSRA","INH"):0x44, ("RORA","INH"):0x46,
    ("ASRA","INH"):0x47, ("ASLA","INH"):0x48, ("LSLA","INH"):0x48, ("ROLA","INH"):0x49,
    ("DECA","INH"):0x4A, ("INCA","INH"):0x4C, ("TSTA","INH"):0x4D, ("CLRA","INH"):0x4F,
    ("NEGB","INH"):0x50, ("COMB","INH"):0x53, ("LSRB","INH"):0x54, ("RORB","INH"):0x56,
    ("ASRB","INH"):0x57, ("ASLB","INH"):0x58, ("LSLB","INH"):0x58, ("ROLB","INH"):0x59,
    ("DECB","INH"):0x5A, ("INCB","INH"):0x5C, ("TSTB","INH"):0x5D, ("CLRB","INH"):0x5F,
    # relative branches
    ("BRA","REL"):0x20, ("BRN","REL"):0x21, ("BHI","REL"):0x22, ("BLS","REL"):0x23,
    ("BCC","REL"):0x24, ("BCS","REL"):0x25, ("BNE","REL"):0x26, ("BEQ","REL"):0x27,
    ("BVC","REL"):0x28, ("BVS","REL"):0x29, ("BPL","REL"):0x2A, ("BMI","REL"):0x2B,
    ("BGE","REL"):0x2C, ("BLT","REL"):0x2D, ("BGT","REL"):0x2E, ("BLE","REL"):0x2F,
    ("BSR","REL"):0x8D,
    # A: imm/dir/idx/ext
    ("SUBA","IMM8"):0x80, ("CMPA","IMM8"):0x81, ("SBCA","IMM8"):0x82, ("ANDA","IMM8"):0x84,
    ("BITA","IMM8"):0x85, ("LDAA","IMM8"):0x86, ("EORA","IMM8"):0x88, ("ADCA","IMM8"):0x89,
    ("ORAA","IMM8"):0x8A, ("ADDA","IMM8"):0x8B,
    ("SUBA","DIR"):0x90, ("CMPA","DIR"):0x91, ("SBCA","DIR"):0x92, ("ANDA","DIR"):0x94,
    ("BITA","DIR"):0x95, ("LDAA","DIR"):0x96, ("STAA","DIR"):0x97, ("EORA","DIR"):0x98,
    ("ADCA","DIR"):0x99, ("ORAA","DIR"):0x9A, ("ADDA","DIR"):0x9B,
    ("SUBA","IDX"):0xA0, ("CMPA","IDX"):0xA1, ("ANDA","IDX"):0xA4, ("BITA","IDX"):0xA5,
    ("LDAA","IDX"):0xA6, ("STAA","IDX"):0xA7, ("EORA","IDX"):0xA8, ("ADDA","IDX"):0xAB,
    ("SUBA","EXT"):0xB0, ("CMPA","EXT"):0xB1, ("ANDA","EXT"):0xB4, ("BITA","EXT"):0xB5,
    ("LDAA","EXT"):0xB6, ("STAA","EXT"):0xB7, ("EORA","EXT"):0xB8, ("ADDA","EXT"):0xBB,
    # B: imm/dir/idx/ext
    ("SUBB","IMM8"):0xC0, ("CMPB","IMM8"):0xC1, ("ANDB","IMM8"):0xC4, ("BITB","IMM8"):0xC5,
    ("LDAB","IMM8"):0xC6, ("EORB","IMM8"):0xC8, ("ORAB","IMM8"):0xCA, ("ADDB","IMM8"):0xCB,
    ("LDAB","DIR"):0xD6, ("STAB","DIR"):0xD7, ("ADDB","DIR"):0xDB,
    ("LDAB","IDX"):0xE6, ("STAB","IDX"):0xE7,
    ("LDAB","EXT"):0xF6, ("STAB","EXT"):0xF7,
    # 16-bit
    ("LDX","IMM16"):0xCE, ("LDX","DIR"):0xDE, ("STX","DIR"):0xDF,
    ("LDX","IDX"):0xEE, ("STX","IDX"):0xEF, ("LDX","EXT"):0xFE, ("STX","EXT"):0xFF,
    ("LDD","IMM16"):0xCC, ("LDD","DIR"):0xDC, ("STD","DIR"):0xDD,
    ("LDD","IDX"):0xEC, ("STD","IDX"):0xED, ("LDD","EXT"):0xFC, ("STD","EXT"):0xFD,
    ("ADDD","IMM16"):0xC3, ("ADDD","DIR"):0xD3, ("SUBD","IMM16"):0x83, ("SUBD","DIR"):0x93, ("SUBD","EXT"):0xB3,
    ("LDS","IMM16"):0x8E, ("LDS","DIR"):0x9E, ("STS","DIR"):0x9F,
    ("CPX","IMM16"):0x8C, ("CPX","DIR"):0x9C,
    # mem idx/ext (inc/dec/clr/shift)
    ("INC","IDX"):0x6C, ("INC","EXT"):0x7C, ("DEC","IDX"):0x6A, ("DEC","EXT"):0x7A,
    ("CLR","IDX"):0x6F, ("CLR","EXT"):0x7F, ("TST","IDX"):0x6D, ("TST","EXT"):0x7D,
    ("JMP","IDX"):0x6E, ("JMP","EXT"):0x7E,
    ("JSR","IDX"):0xAD, ("JSR","DIR"):0x9D, ("JSR","EXT"):0xBD,
    # extra 6801 / B-accumulator forms
    ("LSRD","INH"):0x04, ("ASLD","INH"):0x05, ("LSLD","INH"):0x05,
    ("SUBB","DIR"):0xD0, ("CMPB","DIR"):0xD1, ("ANDB","DIR"):0xD4, ("BITB","DIR"):0xD5,
    ("EORB","DIR"):0xD8, ("ORAB","DIR"):0xDA,
    ("CMPB","EXT"):0xF1, ("ADDB","EXT"):0xFB, ("SUBB","EXT"):0xF0,
    ("CMPB","IDX"):0xE1, ("ADDB","IDX"):0xEB,
    ("STAA","IDX"):0xA7,
}

INH = {k[0] for k in OPC if k[1]=="INH"}
REL = {k[0] for k in OPC if k[1]=="REL"}
IMM16_OPS = {"LDX","LDD","LDS","CPX","ADDD","SUBD"}
# long branches: "LBxx label" -> inverse short branch over a JMP (LBRA -> JMP)
INV = {"BCC":"BCS","BCS":"BCC","BEQ":"BNE","BNE":"BEQ","BPL":"BMI","BMI":"BPL",
       "BVC":"BVS","BVS":"BVC","BHI":"BLS","BLS":"BHI","BGE":"BLT","BLT":"BGE",
       "BGT":"BLE","BLE":"BGT"}
LREL = {"L"+b for b in INV} | {"LBRA"}

def _num(tok, labels, size8):
    tok = tok.strip()
    if tok in labels:
        return labels[tok]
    neg = False
    if tok.startswith("$"):
        return int(tok[1:], 16)
    if tok.startswith("%"):
        return int(tok[1:], 2)
    return int(tok, 0)

class Assembler:
    def __init__(self):
        self.labels = {}
        self.equ = {}

    def _resolve(self, tok):
        tok = tok.strip()
        if tok in self.labels: return self.labels[tok]
        if tok in self.equ: return self.equ[tok]
        if tok.startswith("$"): return int(tok[1:],16)
        if tok.startswith("%"): return int(tok[1:],2)
        # expression a+b / a-b with symbols/numbers
        for op in ("+","-"):
            if op in tok[1:]:
                i = tok.index(op,1)
                l = self._resolve(tok[:i]); r = self._resolve(tok[i+1:])
                return l + r if op=="+" else l - r
        return int(tok,0)

    def assemble(self, src, org=0xF000):
        lines = []
        for raw in src.splitlines():
            line = raw.split(";",1)[0].rstrip()
            if not line.strip(): continue
            lines.append(line)

        # ---- pass 1: sizes + labels + equ ----
        pc = org
        prog = []  # (pc, mnem, mode, operand_str)
        for line in lines:
            stripped = line.strip()
            # equ
            parts = stripped.split()
            if len(parts) >= 3 and parts[1].upper() == ".EQU":
                self.equ[parts[0]] = self._resolve(parts[2]); continue
            # label definition(s)
            while ":" in stripped.split()[0] if stripped.split() else False:
                lab = stripped.split()[0]
                name = lab[:-1]
                self.labels[name] = pc
                stripped = stripped[len(lab):].strip()
                if not stripped: break
            if not stripped: continue
            parts = stripped.split(None, 1)
            mnem = parts[0].upper()
            operand = parts[1].strip() if len(parts) > 1 else ""
            if mnem == ".ORG":
                pc = self._resolve(operand); continue
            if mnem == ".BYTE":
                vals = [v for v in operand.split(",")]
                prog.append((pc, ".BYTE", "DATA", operand)); pc += len(vals); continue
            if mnem == ".WORD":
                vals = [v for v in operand.split(",")]
                prog.append((pc, ".WORD", "DATA", operand)); pc += 2*len(vals); continue
            mode, size = self._mode_size(mnem, operand)
            prog.append((pc, mnem, mode, operand)); pc += size

        # ---- pass 2: emit ----
        out = {}
        for (pc, mnem, mode, operand) in prog:
            if mnem == ".BYTE":
                for i,v in enumerate(operand.split(",")):
                    out[pc+i] = self._resolve(v) & 0xFF
                continue
            if mnem == ".WORD":
                for i,v in enumerate(operand.split(",")):
                    w = self._resolve(v) & 0xFFFF
                    out[pc+2*i] = w >> 8; out[pc+2*i+1] = w & 0xFF
                continue
            if mode == "LREL":
                target = self._resolve(operand) & 0xFFFF
                if mnem == "LBRA":
                    out[pc] = 0x7E; out[pc+1] = target >> 8; out[pc+2] = target & 0xFF
                else:
                    out[pc] = OPC[(INV[mnem[1:]], "REL")]; out[pc+1] = 0x03
                    out[pc+2] = 0x7E; out[pc+3] = target >> 8; out[pc+4] = target & 0xFF
                continue
            op = OPC[(mnem, mode)]
            out[pc] = op
            if mode == "INH":
                pass
            elif mode == "REL":
                target = self._resolve(operand)
                rel = target - (pc + 2)
                assert -128 <= rel <= 127, f"branch out of range at {pc:04x} to {operand}"
                out[pc+1] = rel & 0xFF
            elif mode == "IMM8":
                out[pc+1] = self._imm(operand) & 0xFF
            elif mode == "IMM16":
                w = self._imm(operand) & 0xFFFF
                out[pc+1] = w >> 8; out[pc+2] = w & 0xFF
            elif mode == "DIR":
                out[pc+1] = self._resolve(operand) & 0xFF
            elif mode == "IDX":
                out[pc+1] = self._idx_off(operand) & 0xFF
            elif mode == "EXT":
                w = self._resolve(operand) & 0xFFFF
                out[pc+1] = w >> 8; out[pc+2] = w & 0xFF
        # flatten
        lo = min(out); hi = max(out)
        blob = bytearray(hi-lo+1)
        base = lo
        for a,v in out.items(): blob[a-base] = v
        return base, bytes(blob)

    def _imm(self, operand):
        operand = operand.strip()
        assert operand.startswith("#"), f"expected immediate: {operand}"
        return self._resolve(operand[1:])

    def _idx_off(self, operand):
        operand = operand.strip()
        # forms: ",X"  or  "$05,X"  or  "label,X"
        assert operand.endswith(",X") or operand.endswith(",x")
        off = operand[:-2].strip()
        return 0 if off=="" else self._resolve(off)

    def _mode_size(self, mnem, operand):
        if mnem in INH: return "INH", 1
        if mnem in REL: return "REL", 2
        if mnem in LREL: return "LREL", (3 if mnem == "LBRA" else 5)
        operand = operand.strip()
        if operand.endswith(",X") or operand.endswith(",x"):
            return "IDX", 2
        if operand.startswith("#"):
            return ("IMM16", 3) if mnem in IMM16_OPS else ("IMM8", 2)
        # direct vs extended: resolve value; <0x100 and the DIR opcode exists -> DIR
        try:
            val = self._resolve(operand)
        except (ValueError, KeyError):
            # forward reference (a label, i.e. a 16-bit address) -> extended
            return "EXT", 3
        if 0 <= val < 0x100 and (mnem, "DIR") in OPC:
            return "DIR", 2
        return "EXT", 3
