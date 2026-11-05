# -*- coding: utf-8 -*-
"""Reference model of the Beyond Kung-Fu MCU: a line-for-line Python port of
the MAME HLE device (src/mame/irem/m62_bkungfu_mcu.cpp).  It is the oracle the
6803 firmware is checked against.  Operates on the user-supplied km-z.4h.

The ported logic is derived from MAME code under this licence:

    license:BSD-3-Clause
    copyright-holders:David Haywood, Andrea Bogazzi

Differences with the HLE, all on purpose:
  - the timed level draw (command 0x02) runs to completion immediately;
  - the 64 KB "blitterdat" region is modelled as the 32 KB ROM followed by
    0xFF bytes, exactly as MAME loads it (ROMREGION_ERASEFF).
"""

TILEMAP_BYTES = 256 * 32 * 2
MAILBOX_BYTES = 0x800


class RefMCU:
    def __init__(self, data):
        assert len(data) == 0x8000
        self.data = data
        self.region = bytes(data) + b"\xff" * 0x8000      # "mcu:blitterdat"
        self.tram = bytearray(TILEMAP_BYTES)
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self):
        self.mailbox = bytearray(MAILBOX_BYTES)
        self.timer = 0
        self.p1score = self.topscore = self.p2score = 0
        self.lives = self.player_energy = self.boss_energy = 0
        self.floorcount = self.floorcount_state = 0
        self.valid = 0
        self.initialized = False
        self.running = False
        self.leveldraw_number = 0

    # ------------------------------------------------------------- data ROM
    def read_data(self, a):
        return self.region[a & 0xFFFF]

    def decrypt(self, a):
        if a >= 0x8000:
            return 0xFF
        c = self.data[a]
        i = ((a & 0xFF) + (a >> 8)) & 0xFF
        if i & 1:
            return ((i ^ (0x7E if i & 2 else 0x12)) - 0x20 - c) & 0xFF
        return (c ^ i ^ (0x5E if i & 2 else 0xAE)) & 0xFF

    def payload(self, a):
        v = self.decrypt(a)
        if ((a & 0xFF) + (a >> 8)) & 1:
            return (0x60 - v) & 0xFF
        return ((0xA0 if v & 0x20 else 0x60) - v - (0 if v & 1 else 2)) & 0xFF

    def pword(self, a):
        return self.payload(a) | (self.payload(a + 1) << 8)

    # -------------------------------------------------------------- tilemap
    def tilemap_w(self, offset, data):
        if offset < TILEMAP_BYTES:
            self.tram[offset] = data & 0xFF

    def vram_page_w(self, offset, data):
        xpart = offset & 0x7F
        ypart = offset & ~0x7F
        for page in range(0, 0x200, 0x80):
            self.tilemap_w((ypart << 2) | xpart | page, data)

    def write_number(self, x, y, number):
        self.vram_page_w(((y * 0x40 + x) << 1) & 0x0FFF, (number & 0x0F) + 0x30)

    def write_floor_dot(self, which, lit):
        self.vram_page_w(((3 * 0x40 + 0x20 + which * 2) << 1) & 0x0FFF, 0xD5 if lit else 0xD6)

    def write_lifebar(self, xbase, ybase, energy, boss):
        full = (energy & 0x78) >> 3
        for seg in range(8):
            part = 8 if seg < full else ((energy & 7) if seg == full else 0)
            tile = ((0xCC if boss else 0xC4) + 8 - part) & 0xFF if part else 0xC2
            self.vram_page_w(((ybase * 0x40 + xbase + seg) << 1) & 0x0FFF, tile)

    # ---------------------------------------------------------------- slots
    def update_slot(self, slot):
        if not self.initialized:
            return
        if slot == 0x10:
            for i in range(6): self.write_number(0x14 + i, 0, (self.p1score >> ((5 - i) * 4)) & 0x0F)
        elif slot == 0x14:
            for i in range(6): self.write_number(0x29 + i, 0, (self.p2score >> ((5 - i) * 4)) & 0x0F)
        elif slot == 0x18:
            for i in range(6): self.write_number(0x1F + i, 0, (self.topscore >> ((5 - i) * 4)) & 0x0F)
        elif slot == 0x1C:
            for i in range(4): self.write_number(0x25 + i, 5, (self.timer >> ((3 - i) * 4)) & 0x0F)
        elif slot == 0x20:
            for i in range(8):
                self.write_floor_dot(i, i <= self.floorcount - (1 if self.floorcount_state == 0x02 else 0))
        elif slot == 0x24:
            self.write_number(0x2D, 5, self.lives)
        elif slot == 0x28:
            if self.player_energy <= 0x40: self.write_lifebar(0x17, 2, self.player_energy, False)
        elif slot == 0x2C:
            if self.boss_energy <= 0x40: self.write_lifebar(0x17, 4, self.boss_energy, True)

    def complete(self, offset):
        self.mailbox[offset & 0x7FF] = 0xFE

    def execute_slot(self, slot):
        m = self.mailbox
        trigger, p1, p2, p3 = m[slot], m[slot + 1], m[slot + 2], m[slot + 3]
        if slot == 0x10:   self.p1score = (p1 << 16) | (p2 << 8) | p3
        elif slot == 0x14: self.p2score = (p1 << 16) | (p2 << 8) | p3
        elif slot == 0x18: self.topscore = (p1 << 16) | (p2 << 8) | p3
        elif slot == 0x1C: self.timer = (p1 << 8) | p2
        elif slot == 0x20: self.floorcount = p1; self.floorcount_state = trigger
        elif slot == 0x24: self.lives = p1
        elif slot == 0x28: self.player_energy = p1
        elif slot == 0x2C: self.boss_energy = p1
        else: return
        self.valid |= 1 << ((slot - 0x10) >> 2)
        self.update_slot(slot)
        self.complete(slot)

    # ------------------------------------------------- Z80 mailbox interface
    def z80_write(self, offset, data):
        """mailbox_from_main_w"""
        if offset < 0x800:
            self.mailbox[offset] = data & 0xFF
            if self.running and 0x10 <= offset < 0x30 and not (offset & 3):
                self.execute_slot(offset)
        if offset == 0:
            self.command(data & 0xFF)

    # --------------------------------------------------------------- drawing
    def draw_text(self, table_offset, use_mailbox):
        if not self.running:
            return
        if use_mailbox:
            addr, data, mask, pl, ph, at = 0x100, self.mailbox, 0x7FF, 3, 4, 5
        else:
            addr = self.read_data(table_offset) | (self.read_data(table_offset + 1) << 8)
            data, mask, pl, ph, at = self.region, 0xFFFF, 2, 3, 4
        remaining = mask + 1
        while remaining > 0:
            v = data[addr & mask]; addr += 1; remaining -= 1
            if v == 0:
                return
            if v == 1:
                if remaining < 1: break
                remaining -= 1
                self.mailbox[at] = data[addr & mask]; addr += 1
            elif v == 2:
                if remaining < 2: break
                remaining -= 2
                self.mailbox[pl] = data[addr & mask]; addr += 1
                self.mailbox[ph] = data[addr & mask]; addr += 1
            else:
                pos = (self.mailbox[ph] << 8) | self.mailbox[pl]
                self.vram_page_w(pos & 0x0FFF, v)
                self.vram_page_w((pos + 1) & 0x0FFF, self.mailbox[at])
                pos = (pos & ~0x7F) | ((pos + 2) & 0x7F)
                self.mailbox[pl] = pos & 0xFF
                self.mailbox[ph] = (pos >> 8) & 0xFF

    def draw_credits_continue(self):
        if not self.running:
            return
        m = self.mailbox
        pos = (m[3] << 8) | m[2]
        at = m[4]
        self.vram_page_w(pos & 0x0FFF, (m[1] >> 4) | 0x30)
        self.vram_page_w((pos + 1) & 0x0FFF, at)
        self.vram_page_w((pos + 2) & 0x0FFF, (m[1] & 0x0F) | 0x30)
        self.vram_page_w((pos + 3) & 0x0FFF, at)

    def clear_tilemap(self):
        if not self.running:
            return
        for pos in range(0, 0x1000, 2):
            self.vram_page_w(pos, self.mailbox[2])
            self.vram_page_w(pos + 1, self.mailbox[1])

    def draw_object(self, oid):
        if oid < 0x80 or oid > 0x90:
            return
        t = 0x100 + 2 * (oid - 0x80)
        rec = self.read_data(t) | (self.read_data(t + 1) << 8)
        if rec == 0 or rec >= 0x8000 - 5:
            return
        width = self.read_data(rec)
        pos = (self.read_data(rec + 1) | (self.read_data(rec + 2) << 8)) & 0xFFF
        p = self.read_data(rec + 3) | (self.read_data(rec + 4) << 8)
        if width == 0 or width > 0x20 or p >= 0x8000:
            return
        cells, attr = [], 0
        while p < 0x8000 and len(cells) < 512:
            a = p
            v = self.decrypt(p); p += 1
            if v == 0x5F:
                if p >= 0x8000: break
                attr = self.payload(p); p += 1
                continue
            if v in (0x5E, 0x60):
                break
            cells.append((self.payload(a), attr))
        for n, (tile, at) in enumerate(cells):
            dest = (pos + (n // width) * 0x80 + (n % width) * 2) & 0xFFF
            self.vram_page_w(dest, tile)
            self.vram_page_w(dest + 1, at)

    def draw_level_strip(self, tram, level, column, row):
        off = ((row + 6) * 256 + column * 4) * 2
        for x in range(4):
            tram[off + x * 2] = 0x05
            tram[off + x * 2 + 1] = 0x19
        se = (column & ~1) + (1 if row >= 10 else 0)
        sr = row + (10 if column & 1 else 0) if row < 10 else row - 10 + (16 if column & 1 else 0)
        t = 0x200 + ((level & 0x0F) << 1)
        block = self.read_data(t) | (self.read_data(t + 1) << 8)
        entry = block + se * 2
        if block < 0x153D or entry >= 0x8000 - 1:
            return
        rec = self.pword(entry)
        if rec < 0x1AED or rec >= 0x8000 - 8:
            return
        tiles, attrs, count = [], [], -1
        for s in range(4):
            p = self.pword(rec + s * 2)
            if p < 0x2349 or p >= 0x8000:
                return
            tl, al, attr = [], [], 0
            while p < 0x8000 and len(tl) < 64:
                v = self.payload(p); p += 1
                if v == 0x00:
                    break
                if v == 0x01:
                    if p >= 0x8000:
                        return
                    attr = self.payload(p); p += 1
                    continue
                tl.append(v); al.append(attr)
            if count < 0:
                count = len(tl)
            elif count != len(tl):
                return
            tiles.append(tl); attrs.append(al)
        if count != (32 if se & 1 else 20):
            return
        half = count // 2
        band, br = sr // half, sr % half
        for x in range(4):
            s = band * 2 + x // 2
            idx = br * 2 + x % 2
            tram[off + x * 2] = tiles[s][idx]
            tram[off + x * 2 + 1] = attrs[s][idx]

    def compose_level(self, level):
        """Background draw of commands 0x01 + 0x02 on a blank tilemap."""
        tram = bytearray(TILEMAP_BYTES)
        for col in range(0x38):
            for row in range(26):
                self.draw_level_strip(tram, level, col, row)
        return tram

    # -------------------------------------------------------------- commands
    def command(self, c):
        m = self.mailbox
        if c == 0x01:
            self.leveldraw_number = m[1]; self.complete(0)
        elif c == 0x02:
            for col in range(0x38):
                for row in range(26):
                    self.draw_level_strip(self.tram, self.leveldraw_number, col, row)
            self.complete(0)
        elif c == 0x05:
            self.complete(0)
        elif c == 0x08:
            self.clear_tilemap(); self.initialized = False; self.complete(0)
        elif c == 0x0A:
            stream = self.region[0x140] | (self.region[0x141] << 8)
            pos, attr, remaining, terminated = 0, 0, 0x10000, False
            while remaining > 0:
                v = self.read_data(stream); stream += 1; remaining -= 1
                if v == 0:
                    terminated = True; break
                if v == 1:
                    if remaining < 1: break
                    remaining -= 1
                    attr = self.read_data(stream); stream += 1
                    continue
                if v == 2:
                    if remaining < 2: break
                    remaining -= 2
                    lo = self.read_data(stream); hi = self.read_data(stream + 1); stream += 2
                    pos = lo | (hi << 8)
                    continue
                self.vram_page_w(pos & 0x0FFF, v)
                self.vram_page_w((pos + 1) & 0x0FFF, attr)
                pos = (pos & ~0x7F) | ((pos + 2) & 0x7F)
            if not terminated:
                self.complete(0); return
            self.initialized = True
            for slot in range(0x10, 0x2D, 4):
                if self.valid & (1 << ((slot - 0x10) >> 2)):
                    self.update_slot(slot)
            self.complete(0)
        elif c == 0x0C:
            self.draw_text(0, True); self.complete(0)
        elif c in (0x0D, 0x14):
            self.draw_text(m[1] << 1, False); self.complete(0)
        elif c == 0x0F:
            self.draw_object(m[1]); self.complete(0)
        elif c == 0x10:
            self.draw_credits_continue(); self.complete(0)
        elif c == 0xFE:
            self.running = True
            for slot in range(0x10, 0x2D, 4):
                self.complete(slot)
            for o in (0x102, 0x106, 0x118, 0x11C, 0):
                self.complete(o)
