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

## ROMs

`bkungfulle` is a clone of `bkungfu`: keep your `bkungfu` set as it is and add
the firmware as `roms/bkungfulle/mcu` (or `mcu` inside `bkungfulle.zip`).

```bash
./bkungfu bkungfulle -rompath roms
```

## Caveats

- This is not Irem's firmware. It reproduces the HLE's behaviour, it does not
  recover the original code.
- The MCU-side bus (addresses, mailbox latches) and the 4 MHz clock are
  reconstructions; the real board may differ.
- The level background draws in about 1 s at this clock, against about 0.25 s
  on the real board (see `docs/SPEC.md`), so stage loads take a little longer.
