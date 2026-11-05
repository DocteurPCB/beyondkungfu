# -*- coding: utf-8 -*-
"""Add the Intel 8751 LLE Beyond Kung-Fu set ("bkungfu8751") to a MAME tree.

usage: python3 mame-patch/apply51.py <mame-source-dir> <mcu-8751-firmware-file>

- copies src/mame/irem/m62_bkungfu_mcu51.{h,cpp} into the tree;
- edits src/mame/irem/m62_bkungfu.cpp: an 8751 machine config and a clone set
  bkungfu8751 whose "mcu" ROM is the 8751 firmware (CRC32/SHA1 computed from
  the file you pass);
- registers bkungfu8751 in src/mame/mame.lst.
Works whether or not apply.py (6803 set bkungfulle) was run.  Rerunnable.
"""
import hashlib, os, re, shutil, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
mame, mcu = sys.argv[1], sys.argv[2]
fw = open(mcu, "rb").read()
assert len(fw) == 0x1000, f"firmware must be 4096 bytes, got {len(fw)}"
crc = f"{zlib.crc32(fw):08x}"
sha1 = hashlib.sha1(fw).hexdigest()

for f in ("m62_bkungfu_mcu51.h", "m62_bkungfu_mcu51.cpp"):
    shutil.copy(os.path.join(HERE, "src/mame/irem", f), os.path.join(mame, "src/mame/irem", f))

drv_path = os.path.join(mame, "src/mame/irem/m62_bkungfu.cpp")
drv = open(drv_path).read()


def sub(old, new):
    global drv
    assert old in drv, f"driver text not found: {old!r}"
    drv = drv.replace(old, new, 1)


if "bkungfu8751" not in drv:
    sub('#include "m62_bkungfu_mcu.h"\n',
        '#include "m62_bkungfu_mcu.h"\n#include "m62_bkungfu_mcu51.h"\n')
    sub("\t\t, m_mcu(*this, \"mcu\")\n",
        "\t\t, m_mcu(*this, \"mcu\")\n\t\t, m_mcu51(*this, \"mcu51\")\n")
    sub("\tvoid bkungfu(machine_config& config);\n",
        "\tvoid bkungfu(machine_config& config);\n\tvoid bkungfu_8751(machine_config &config);\n")
    sub("\tvoid mem_map(address_map &map) ATTR_COLD;\n",
        "\tvoid mem_map(address_map &map) ATTR_COLD;\n\tvoid mem_map_51(address_map &map) ATTR_COLD;\n")
    drv = drv.replace("\trequired_device<bkungfu_mcu_device> m_mcu;\n",
                      "\toptional_device<bkungfu_mcu_device> m_mcu;\n", 1)
    sub("\toptional_device<bkungfu_mcu_device> m_mcu;\n",
        "\toptional_device<bkungfu_mcu_device> m_mcu;\n\toptional_device<bkungfu_mcu51_device> m_mcu51;\n")
    sub("void m62_bkungfu_state::io_map(address_map &map)\n",
        """void m62_bkungfu_state::mem_map_51(address_map& map)
{
	map(0x0000, 0xbfff).rom();
	map(0xc000, 0xc0ff).ram().share("spriteram");
	map(0xc100, 0xc1ff).ram();

	map(0xc800, 0xcfff).rw(m_mcu51, FUNC(bkungfu_mcu51_device::mailbox_r), FUNC(bkungfu_mcu51_device::mailbox_from_main_w));
	map(0xe000, 0xefff).ram();
}

void m62_bkungfu_state::io_map(address_map &map)
""")
    i = drv.index("void m62_bkungfu_state::bkungfu(machine_config& config)")
    j = drv.index("\n}\n", i) + 3
    drv = drv[:j] + """
// Same machine, MCU run at low level as an Intel 8751 (hypothesis: as on
// Irem's M72 boards, own 8 MHz crystal) executing the reconstructed firmware
// (https://github.com/DocteurPCB/beyondkungfu, firmware51/).
void m62_bkungfu_state::bkungfu_8751(machine_config &config)
{
	kungfum(config);

	m_maincpu->set_addrmap(AS_PROGRAM, &m62_bkungfu_state::mem_map_51);
	m_maincpu->set_addrmap(AS_IO, &m62_bkungfu_state::io_map);

	BKUNGFU_MCU51(config, m_mcu51, 8_MHz_XTAL); // type and clock unconfirmed
	m_mcu51->tilemap_ram_w().set(FUNC(m62_bkungfu_state::tilemap_ram_w));

	MCFG_VIDEO_START_REMOVE()
}
""" + drv[j:]
    i = drv.index("ROM_START( bkungfu )")
    j = drv.index("ROM_END", i) + len("ROM_END")
    body = drv[i:j].replace("ROM_START( bkungfu )", "ROM_START( bkungfu8751 )")
    old_mcu = """	ROM_REGION( 0x1000, "mcu", 0 )
	ROM_LOAD( "mcu",     0x0000, 0x1000, NO_DUMP )

	ROM_REGION( 0x10000, "mcu:blitterdat", ROMREGION_ERASEFF )"""
    assert old_mcu in body, "unexpected bkungfu ROM layout"
    body = body.replace(old_mcu, f"""	ROM_REGION( 0x1000, "mcu51:cpu", 0 ) // reconstructed i8751 firmware, not an Irem dump
	ROM_LOAD( "mcu",     0x0000, 0x1000, CRC({crc}) SHA1({sha1}) )

	ROM_REGION( 0x10000, "mcu51:blitterdat", ROMREGION_ERASEFF )""")
    drv = drv[:j] + "\n\n" + body + drv[j:]
    drv = drv.rstrip("\n") + (
        '\nGAME( 1987, bkungfu8751, bkungfu, bkungfu_8751, kungfum, m62_bkungfu_state, empty_init, ROT0, '
        '"Irem", "Beyond Kung-Fu (location test, reconstructed i8751 MCU firmware)", '
        'MACHINE_SUPPORTS_SAVE | MACHINE_IMPERFECT_SOUND | MACHINE_IMPERFECT_GRAPHICS )\n')
else:
    i = drv.index("ROM_START( bkungfu8751 )")
    j = drv.index("ROM_END", i)
    blk = re.sub(r'ROM_LOAD\( "mcu",     0x0000, 0x1000, CRC\([0-9a-f]{8}\) SHA1\([0-9a-f]{40}\) \)',
                 f'ROM_LOAD( "mcu",     0x0000, 0x1000, CRC({crc}) SHA1({sha1}) )', drv[i:j])
    drv = drv[:i] + blk + drv[j:]
open(drv_path, "w").write(drv)

lst_path = os.path.join(mame, "src/mame/mame.lst")
lst = open(lst_path).read()
if "bkungfu8751" not in lst:
    lst = lst.replace("@source:irem/m62_bkungfu.cpp\nbkungfu\n",
                      "@source:irem/m62_bkungfu.cpp\nbkungfu\nbkungfu8751\n", 1)
    assert "bkungfu8751" in lst, "could not register bkungfu8751 in mame.lst"
    open(lst_path, "w").write(lst)

print(f"bkungfu8751 ajouté : mcu CRC({crc}) SHA1({sha1})")
