# Beyond Kung-Fu MCU — reverse-engineered behaviour

Distilled from the MAME HLE (`m62_bkungfu_mcu.cpp`). This is the specification
the 6803 firmware must satisfy.

## Role

The MCU owns the **tilemap layer**. The Z80 never writes tiles directly; it
posts commands/parameters into a shared mailbox and the MCU composes the
background, objects, text and HUD into tilemap RAM, decoding them from a
partially-encrypted external ROM (`km-z.4h`, 32 KB).

## Z80-side interface (fixed by the PCB / MAME driver)

- Mailbox window: Z80 `0xC800..0xCFFF` → MCU mailbox (2 KB, offsets `0x000..0x7FF`).
- A **write to mailbox offset `0x00` is a command**; other writes just store bytes.
- When the MCU is "running", a write to a 4-aligned offset in `0x10..0x2F`
  triggers a HUD status update for that slot.
- The MCU acknowledges by writing `0xFE` back into the mailbox slot it completed.

## Assumed MCU-side memory map (our LLE convention — not confirmed hardware)

The HLE abstracts the MCU's own bus away, so we define a consistent one:

| Range | Use |
|-------|-----|
| `0x0080..0x00FF` | internal RAM (variables + stack), as on 6801-family parts |
| `0x0800..0x0FFF` | shared mailbox (2 KB), same bytes the Z80 sees |
| `0x2000..0x5FFF` | tilemap RAM (16 KB) the MCU writes into |
| `0x6000..0xDFFF` | `km-z.4h`, mapped flat (logical address + `0x6000`) |
| `0xF000..0xFFFF` | internal firmware ROM (4 KB) + reset/IRQ vectors |

## Data-ROM decoding  ✅ implemented in `firmware/decode.s`

- Offsets `0x0000..0x153C` are **plaintext** (pointer tables, text strings).
- From `0x153D` up, each byte is independently decoded (address-local cipher):
  ```
  index  = (addr_lo + addr_hi) & 0xFF
  if index & 1:  value = (index ^ (index&2 ? 0x7E : 0x12)) - 0x20 - cipher
  else:          value = cipher ^ index ^ (index&2 ? 0x5E : 0xAE)
  ```
- Level/object/pointer *payload* bytes get a second transform on top:
  ```
  if index & 1:  out = 0x60 - value
  else:          out = ((value&0x20) ? 0xA0 : 0x60) - value - ((value&1) ? 0 : 2)
  ```

## Pointer tables (plaintext)

- `0x0100`: 17 object records pointers (object IDs `0x80..0x90`).
- `0x0140`: pointer to the HUD init stream.
- `0x0200`: 16 level pointers. Slots 0..7 = stage 8,1..7 initial state; slots
  8..15 = redraw-after-animation state. Each points to a 0x70-byte block of
  56 two-byte entry pointers (payload-encoded).

## Commands (`command_w`, triggered by mailbox[0x00])

| Cmd | Action |
|-----|--------|
| `0x01` | latch level number from mailbox[1]; ack |
| `0x02` | start timed level draw (56 cols × 26 rows, one strip per ~175 µs) |
| `0x05` | no-op ack (seen after 0x0F) |
| `0x08` | clear tilemap (fill from mailbox[1..2]); reset init; ack |
| `0x0A` | run HUD init stream at ptr `0x140`; mark initialized; refresh HUD; ack |
| `0x0C` | draw text from a Z80-prepared stream in mailbox (`0x100`) |
| `0x0D` / `0x14` | draw ROM text, table indexed by mailbox[1] |
| `0x0F` | draw object id mailbox[1] |
| `0x10` | draw credits/continue digits |
| `0xFE` | set running; ack all HUD slots + a few fixed slots |

## Status slots (`execute_slot`, offsets in `0x10..0x2C`, 4-aligned)

`0x10` P1 score, `0x14` P2 score, `0x18` top score, `0x1C` timer,
`0x20` floor count (+state), `0x24` lives, `0x28` player energy bar,
`0x2C` boss energy bar. Each: store params, redraw that HUD element, ack.

## Stream grammars

- **Level strip**: entry → 4 tile-streams; `00` ends a stream, `01 <attr>` sets
  attribute, else literal tile. Upper streams = 20 cells, lower = 32; written in
  4-tile-wide columns, top→bottom, left→right (visible draw-in on hardware).
- **Object**: record = `width, dest_lo, dest_hi, stream_lo, stream_hi`; stream
  `5F <attr>` sets attribute, `5E`/`60` terminate, else payload-decoded tile;
  cells written row-major wrapping at `width`.
- **Text**: `00` ends, `01 <attr>`, `02 <lo> <hi>` sets position, else literal
  tile; advances 2 bytes/char, wraps within a 64-tile (0x80-byte) row.

## Tilemap byte format

Tiles are emitted as adjacent bytes: **tile code**, then **attribute**.
`code = tilebyte | ((attr & 0xE0) << 3) | (bg_bank << 11)`;
`palette = attr & 0x1F`. The background bank bit (code bit 11) comes from a
separate Z80 latch (I/O `0x83`), not from the MCU.

## Background tile bank

Tile code bit 11 comes from the Z80's background-bank latch (I/O `0x83`), not
the MCU. Rendering the level data with bank **1** gives the correct graphics
(it matches real-hardware footage); bank 0 gives scrambled tiles.

## Performance

The HLE paces level drawing at one strip per 175 µs, about 14 video frames
(~255 ms) for the 56 × 26 strips, tuned to match hardware footage.

Measured with the emulator's 6801 cycle counts (worst level slot):

| Version | Cycles | at 1 MHz |
|---------|--------|----------|
| per-strip decode, like the HLE | ~70 M | ~70 s |
| one pass per half column pair, table cipher | 1.25 M | 1.25 s |
| + hot loop inlined | 1.02 M | 1.02 s |

A level needs 11,244 decoded bytes (attribute tokens cost two bytes) and 5,824
cell writes. Even with the fastest 6801 idioms (stack pointer as read pointer),
about 40 cycles per byte and 25 per cell remain, ~620 k cycles: roughly 0.6 s
at 1 MHz. So either the MCU runs well above 1 MHz, or it is a part with faster
instruction timings (HD6301-family parts execute many 6801 instructions in
fewer cycles), or the decryption is partly done in hardware. The MCU type and
clock are not confirmed; the crystal next to the MCU on the PCB would settle it.

Note: when reading sequentially the cipher index does not just increment; at a
page crossing it jumps by 2, so the firmware recomputes it from the pointer.
