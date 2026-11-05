# MAME patch: run the reconstructed MCU firmware (LLE)

Stock MAME runs Beyond Kung-Fu with a C++ simulation of the MCU (HLE) and
never executes an `mcu` file. This patch adds a clone set, **`bkungfulle`**,
in which the MCU is a real 6803 core running this project's firmware.
The original `bkungfu` set is left untouched.

## What the patch adds

- `src/mame/irem/m62_bkungfu_mcu_lle.{h,cpp}`: the LLE MCU device. It has the
  same Z80-side interface as the HLE (mailbox at `C800-CFFF`, tilemap writes),
  and inside it a 6803 with the memory map described in `docs/SPEC.md`.
- `src/mame/irem/m62_bkungfu.cpp`: an LLE machine config and the `bkungfulle`
  clone set, whose `mcu` ROM entry carries the CRC32/SHA1 of your firmware file.
- `src/mame/mame.lst`: registers `bkungfulle`.

## Build

```bash
python3 firmware/build.py mcu
```

```bash
python3 mame-patch/apply.py /path/to/mame mcu
```

```bash
cd /path/to/mame && make -j8 SUBTARGET=bkungfu SOURCES=src/mame/irem/m62.cpp,src/mame/irem/m62_v.cpp,src/mame/irem/m62_bkungfu.cpp,src/mame/irem/m62_bkungfu_mcu.cpp,src/mame/irem/m62_bkungfu_mcu_lle.cpp REGENIE=1
```

(Or rebuild your usual full MAME after `apply.py`.) Rerun `apply.py` after any
firmware change: it refreshes the CRC32/SHA1 in the driver.

## Intel 8751 variant

`apply51.py` adds a third set, `bkungfu8751`, whose MCU is a MAME `I8751` core
at 8 MHz running `firmware51/`. It works with or without `apply.py`:

```bash
python3 firmware51/build51.py mcu51
```

```bash
python3 mame-patch/apply51.py /path/to/mame mcu51
```

Add `src/mame/irem/m62_bkungfu_mcu51.cpp` to the `SOURCES` list when building a
subtarget, and put the file as `roms/bkungfu8751/mcu`.

## ROMs

`bkungfulle` is a clone of `bkungfu`: keep your `bkungfu` set as it is and add
the firmware as `roms/bkungfulle/mcu` (or `mcu` inside `bkungfulle.zip`).

```bash
./bkungfu bkungfulle -rompath roms
```

## Tested

Built from MAME master (Nov 2026) with the subtarget command above. `bkungfulle`
passes `-verifyroms`, boots, and runs the intro, title, attract mode and a
game. Recording 60 s of both sets and comparing frame by frame: 96 % of the
LLE frames are exact copies of HLE frames, shifted by 50 ms (intro) to 300 ms
(in game) because the LLE MCU is slower than the instant HLE. The remaining
frames show screens while they are being drawn (title objects, stage
background), which the HLE never shows. No frame differs in content.

## Caveats

- This is not Irem's firmware. It reproduces the HLE's behaviour, it does not
  recover the original code.
- The MCU-side bus (addresses, mailbox latches) is a reconstruction. The MCU is a
  6801-family part with internal ROM (exact type unconfirmed), emulated here by
  an MC6803 core reading the firmware at F000-FFFF; its clock is assumed to be
  3.579545 MHz, like the sound board's MC6803.
- The firmware paces the level background (1.12 s) and the clear (140 ms) to
  match PCB footage; other commands are not paced.
