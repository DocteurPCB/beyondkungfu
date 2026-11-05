# -*- coding: utf-8 -*-
"""Render the background tilemap the MCU composes for each level slot, using
the user's own ROMs (no ROM data or rendered images are kept in this repo).

usage: render_level.py <romdir> <outdir>
needs: km-z.4h (MCU data), km-z.3d/3c/3a (gfx1), km-z-1j/1h/1f (char PROMs)
"""
import sys, os
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ref_mcu import RefMCU

romdir, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
R = lambda n: open(os.path.join(romdir, n), "rb").read()
ref = RefMCU(R("km-z.4h"))
GFX = R("km-z.3d") + R("km-z.3c") + R("km-z.3a")      # gfx1 region order
PROM = R("km-z-1j") + R("km-z-1h") + R("km-z-1f")     # chr_color_proms R, G, B

# Palette: 4-bit PROM nibbles through the {2200,1000,470,220} resistor net,
# then M62's global contrast boost (m62_amplify_contrast).
G = [1 / 2200, 1 / 1000, 1 / 470, 1 / 220]
lvl = [255 * sum(G[b] for b in range(4) if n >> b & 1) / sum(G) for n in range(16)]
pal = np.array([[lvl[PROM[i] & 15], lvl[PROM[0x100 + i] & 15], lvl[PROM[0x200 + i] & 15]]
                for i in range(256)])
ymax = max(1, (pal @ np.array([299, 587, 114])).max())
pal = np.clip(pal * (255000 / ymax), 0, 255).astype(np.uint8)

# Tiles: gfx_8x8x3_planar, plane at RGN_FRAC(0,3) is the MSB.
g = np.frombuffer(GFX, np.uint8).reshape(3, 4096, 8)
bits = np.unpackbits(g, axis=2).reshape(3, 4096, 8, 8)
TILES = (bits[0] << 2) | (bits[1] << 1) | bits[2]


def render(tram, bank=1, rows=range(6, 32), cols=range(0, 224)):
    """bank = background bank latch (Z80 I/O 0x83) = tile code bit 11.
    It is set by the Z80, not the MCU; 1 is correct for the stages checked."""
    img = np.zeros((len(rows) * 8, len(cols) * 8, 3), np.uint8)
    for yi, r in enumerate(rows):
        for xi, c in enumerate(cols):
            o = (r * 256 + c) * 2
            code = tram[o] | ((tram[o + 1] & 0xE0) << 3) | (bank << 11)
            img[yi * 8:yi * 8 + 8, xi * 8:xi * 8 + 8] = pal[(tram[o + 1] & 0x1F) * 8 + TILES[code]]
    return img


if __name__ == "__main__":
    for slot in range(16):
        Image.fromarray(render(ref.compose_level(slot))).save(
            os.path.join(outdir, f"slot{slot:02d}.png"))
        print(f"slot {slot:2d} rendu")
