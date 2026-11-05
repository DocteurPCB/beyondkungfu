# -*- coding: utf-8 -*-
"""Reference model of the Beyond Kung-Fu MCU, ported line-for-line from the
MAME HLE (src/mame/irem/m62_bkungfu_mcu.cpp).  Used as the oracle the 6803
firmware is checked against.  Operates on the user-supplied km-z.4h."""

TILEMAP_BYTES = 256 * 32 * 2


class RefMCU:
    def __init__(self, data):
        assert len(data) == 0x8000
        self.data = data

    def read_data(self, a):
        return self.data[a] if a < 0x8000 else 0xFF

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

    def draw_level_strip(self, tram, level, column, row):
        off = ((row + 6) * 256 + column * 4) * 2
        for x in range(4):
            tram[off + x * 2] = 0x05
            tram[off + x * 2 + 1] = 0x19
        se = (column & ~1) + (1 if row >= 10 else 0)
        if row < 10:
            sr = row + (10 if column & 1 else 0)
        else:
            sr = row - 10 + (16 if column & 1 else 0)
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
        """Full background draw as triggered by commands 0x01 + 0x02."""
        tram = bytearray(TILEMAP_BYTES)
        for col in range(0x38):
            for row in range(26):
                self.draw_level_strip(tram, level, col, row)
        return tram
