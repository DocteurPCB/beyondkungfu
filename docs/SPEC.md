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
| `0x0400` | CMDLAT: bit7 set by a Z80 write to mailbox offset 0; any MCU write clears it |
| `0x0401` | SLOTLAT: bit n set by a Z80 write to mailbox offset `0x10 + 4n`; MCU writes 1 to clear |
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
| + SP walks the cipher table, state machine, end-of-stream by address | 0.73 M | 0.73 s |

Other commands, measured in MAME (6803 at 1 MHz E clock; the emulator's cycle
model gives the same figures as MAME's core, e.g. 45.9 ms for a clear):

| Command | before | after `vpwpair` / faster clear |
|---------|--------|--------------------------------|
| 0x0F object (average) | 41.6 ms | 29.8 ms |
| 0x08 clear | 58.9 ms | 45.9 ms |
| 0x0A fixed HUD | 47.8 ms | 36.5 ms |
| 0x14 ROM text | 3.9 ms | 2.9 ms |
| 0x0C mailbox text | 10.8 ms | 7.7 ms |

At a stage start the Z80 waits for two clears, the fixed HUD and the
background: about 0.85 s in all, against an instant HLE.

A level needs 11,244 decoded bytes (attribute tokens cost two bytes) and 5,824
cell writes. Even with the fastest 6801 idioms (stack pointer as read pointer),
about 40 cycles per byte and 25 per cell remain, ~620 k cycles: roughly 0.6 s
at 1 MHz. So either the MCU runs well above 1 MHz, or it is a part with faster
instruction timings (HD6301-family parts execute many 6801 instructions in
fewer cycles), or the decryption is partly done in hardware. The MCU type and
clock are not confirmed; the crystal next to the MCU on the PCB would settle it.
Update: the PCB footage below shows the real MCU is slower than this firmware, so
the ~255 ms target above was wrong (see "Real-hardware timing").

Note: when reading sequentially the cipher index does not just increment; at a
page crossing it jumps by 2, so the firmware recomputes it from the pointer.

## Why mailbox latches

The HLE reacts to the Z80's writes as events. A real MCU has to notice them.
Polling mailbox[0] cannot work: command `0xFE` is acknowledged with `0xFE`, so a
new `0xFE` and an acknowledged command look the same. Our LLE glue therefore
latches "command written" and "slot n written" in two registers the firmware
polls. This is our convention: the real board's signalling is unknown.

When a command and slot triggers are pending together, the firmware handles the
command first, while the HLE handles writes in arrival order. A slot update
during a level draw is also handled after the draw. Final contents only differ
if the Z80 relies on that ordering.

## Real-hardware timing (measured on PCB footage)

Source: a ~24 s camera recording of an original PCB starting a game (PAL,
interlaced, analysed field by field at 50 Hz, i.e. 20 ms resolution).

| Event | Real PCB | HLE (MAME) | This firmware, 1 MHz E clock |
|-------|----------|------------|------------------------------|
| 0x08 clear, visible top-to-bottom wipe | ~140 ms | instant | 46 ms |
| first visible screen of the background (8 of 56 column strips) | ~200 ms | 35 ms | 89 ms |
| "1-PLAYER PRECINCT" text after the background starts | 1.13 s | 0.96 s | 0.94 s |

The Z80 sends the stage text a fixed ~0.95 s after command 0x02 (the player's
walk-in), but only once 0x02 has been acknowledged. On the PCB the text comes
0.17 s later than that, so the real MCU was still drawing: the whole background
takes about 1.1 s on hardware (1.4 s if the 200 ms for 8 columns is extrapolated
linearly to 56).

Consequences:
- The HLE's pacing (175 us per strip, 255 ms per level) matches the time the
  visible screen takes to fill (~14 frames), not the whole level: it draws
  about 4x too fast, and its clear is instant where the hardware's takes ~140 ms.
- This firmware at a 1 MHz E clock is faster than the real MCU: about 1.8x for
  the background and 3x for the clear. The real MCU is consistent with a ~1 MHz
  6801-family part running straightforward code (a plain 2-bytes-per-iteration
  clear loop takes ~150 ms at 1 MHz).
- No single clock makes this firmware match every command's timing, because its
  code is not Irem's; about 55 % of the current clock matches the background.
