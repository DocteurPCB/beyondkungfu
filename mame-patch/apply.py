# -*- coding: utf-8 -*-
"""Add the LLE Beyond Kung-Fu set ("bkungfulle") to a MAME source tree.

usage: python3 mame-patch/apply.py <mame-source-dir> <mcu-firmware-file>

- copies src/mame/irem/m62_bkungfu_mcu_lle.{h,cpp} into the tree;
- edits src/mame/irem/m62_bkungfu.cpp: an LLE machine config and a clone set
  bkungfulle whose "mcu" ROM is the reconstructed firmware (its CRC32/SHA1 are
  computed from the file you pass);
- registers bkungfulle in src/mame/mame.lst.
The original bkungfu (HLE) set is left untouched.  Running it twice is safe.
"""
import hashlib, os, shutil, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
mame, mcu = sys.argv[1], sys.argv[2]
fw = open(mcu, "rb").read()
assert len(fw) == 0x1000, f"firmware must be 4096 bytes, got {len(fw)}"
crc = f"{zlib.crc32(fw):08x}"
sha1 = hashlib.sha1(fw).hexdigest()

for f in ("m62_bkungfu_mcu_lle.h", "m62_bkungfu_mcu_lle.cpp"):
    shutil.copy(os.path.join(HERE, "src/mame/irem", f), os.path.join(mame, "src/mame/irem", f))

drv_path = os.path.join(mame, "src/mame/irem/m62_bkungfu.cpp")
drv = open(drv_path).read()


def sub(old, new):
    global drv
    assert old in drv, f"driver text not found: {old!r}"
    drv = drv.replace(old, new, 1)


if "bkungfulle" not in drv:
    sub('#include "m62_bkungfu_mcu.h"\n',
        '#include "m62_bkungfu_mcu.h"\n#include "m62_bkungfu_mcu_lle.h"\n')
    sub("\t\t, m_mcu(*this, \"mcu\")\n",
        "\t\t, m_mcu(*this, \"mcu\")\n\t\t, m_mcu_lle(*this, \"mculle\")\n")
    sub("\tvoid bkungfu(machine_config& config);\n",
        "\tvoid bkungfu(machine_config& config);\n\tvoid bkungfu_lle(machine_config &config);\n")
    sub("\tvoid mem_map(address_map &map) ATTR_COLD;\n",
        "\tvoid mem_map(address_map &map) ATTR_COLD;\n\tvoid mem_map_lle(address_map &map) ATTR_COLD;\n")
    sub("\trequired_device<bkungfu_mcu_device> m_mcu;\n",
        "\toptional_device<bkungfu_mcu_device> m_mcu;\n\toptional_device<bkungfu_mcu_lle_device> m_mcu_lle;\n")
    sub("void m62_bkungfu_state::io_map(address_map &map)\n",
        """void m62_bkungfu_state::mem_map_lle(address_map& map)
{
	map(0x0000, 0xbfff).rom();
	map(0xc000, 0xc0ff).ram().share("spriteram");
	map(0xc100, 0xc1ff).ram();

	map(0xc800, 0xcfff).rw(m_mcu_lle, FUNC(bkungfu_mcu_lle_device::mailbox_r), FUNC(bkungfu_mcu_lle_device::mailbox_from_main_w));
	map(0xe000, 0xefff).ram();
}

void m62_bkungfu_state::io_map(address_map &map)
""")
    i = drv.index("void m62_bkungfu_state::bkungfu(machine_config& config)")
    j = drv.index("\n}\n", i) + 3
    drv = drv[:j] + """
// Same machine, with the MCU run at low level on a 6803 core executing the
// reconstructed firmware (https://github.com/DocteurPCB/beyondkungfu).
void m62_bkungfu_state::bkungfu_lle(machine_config &config)
{
	kungfum(config);

	m_maincpu->set_addrmap(AS_PROGRAM, &m62_bkungfu_state::mem_map_lle);
	m_maincpu->set_addrmap(AS_IO, &m62_bkungfu_state::io_map);

	BKUNGFU_MCU_LLE(config, m_mcu_lle, 3.579545_MHz_XTAL); // 6801-family MCU, clock assumed = sound CPU's crystal
	m_mcu_lle->tilemap_ram_w().set(FUNC(m62_bkungfu_state::tilemap_ram_w));

	MCFG_VIDEO_START_REMOVE()
}
""" + drv[j:]
    i = drv.index("ROM_START( bkungfu )")
    j = drv.index("ROM_END", i) + len("ROM_END")
    body = drv[i:j]
    lle = body.replace("ROM_START( bkungfu )", "ROM_START( bkungfulle )")
    old_mcu = """	ROM_REGION( 0x1000, "mcu", 0 )
	ROM_LOAD( "mcu",     0x0000, 0x1000, NO_DUMP )

	ROM_REGION( 0x10000, "mcu:blitterdat", ROMREGION_ERASEFF )"""
    assert old_mcu in lle, "unexpected bkungfu ROM layout"
    lle = lle.replace(old_mcu, f"""	ROM_REGION( 0x1000, "mculle:fw", 0 ) // reconstructed firmware, not an Irem dump
	ROM_LOAD( "mcu",     0x0000, 0x1000, CRC({crc}) SHA1({sha1}) )

	ROM_REGION( 0x10000, "mculle:blitterdat", ROMREGION_ERASEFF )""")
    drv = drv[:j] + "\n\n" + lle + drv[j:]
    drv = drv.rstrip("\n") + (
        '\nGAME( 1987, bkungfulle, bkungfu, bkungfu_lle, kungfum, m62_bkungfu_state, empty_init, ROT0, '
        '"Irem", "Beyond Kung-Fu (location test, reconstructed MCU firmware)", '
        'MACHINE_SUPPORTS_SAVE | MACHINE_IMPERFECT_SOUND | MACHINE_IMPERFECT_GRAPHICS )\n')
else:
    # already patched: refresh the MCU clock and the firmware hashes
    import re
    drv = re.sub(r"BKUNGFU_MCU_LLE\(config, m_mcu_lle, [^)]*\);[^\n]*",
                 "BKUNGFU_MCU_LLE(config, m_mcu_lle, 3.579545_MHz_XTAL); // 6801-family MCU, clock assumed = sound CPU's crystal",
                 drv)
    drv = re.sub(r'ROM_LOAD\( "mcu",     0x0000, 0x1000, CRC\([0-9a-f]{8}\) SHA1\([0-9a-f]{40}\) \)',
                 f'ROM_LOAD( "mcu",     0x0000, 0x1000, CRC({crc}) SHA1({sha1}) )', drv)
open(drv_path, "w").write(drv)

lst_path = os.path.join(mame, "src/mame/mame.lst")
lst = open(lst_path).read()
if "bkungfulle" not in lst:
    lst = lst.replace("@source:irem/m62_bkungfu.cpp\nbkungfu\n",
                      "@source:irem/m62_bkungfu.cpp\nbkungfu\nbkungfulle\n", 1)
    assert "bkungfulle" in lst, "could not register bkungfulle in mame.lst"
    open(lst_path, "w").write(lst)

print(f"bkungfulle ajouté : mcu CRC({crc}) SHA1({sha1})")
