// license:BSD-3-Clause
// copyright-holders:DocteurPCB
/*
    Irem Beyond Kung-Fu MCU, low-level emulation of a reconstructed firmware.

    The original MCU program has never been dumped.  The firmware run here is
    a behavioural reimplementation of the HLE in m62_bkungfu_mcu.cpp, written in
    6803 assembly and checked byte for byte against it (tilemap and mailbox).
    It is NOT Irem's code.

    MCU address map (reconstruction, see docs/SPEC.md in the project):
      0000-0014  6803 internal registers
      0080-00FF  6803 internal RAM
      0400       command latch: bit 7 set by a Z80 write to mailbox offset 0,
                 cleared by any MCU write
      0401       slot latch: bit n set by a Z80 write to mailbox offset 10+4n,
                 MCU writes 1 to clear
      0800-0FFF  mailbox, shared with the Z80 at C800-CFFF
      2000-5FFF  tilemap RAM (write-through to the video tilemap)
      6000-DFFF  external data ROM km-z.4h
      F000-FFFF  firmware (4 KB, the "mcu" file)

    The real MCU is a 6801-family part whose 4 KB internal ROM is undumped
    (exact type unconfirmed).  An MC6803 core reading the firmware at F000-FFFF
    behaves the same.  Clock: assumed to be the 3.579545 MHz crystal of the
    sound board's MC6803 (E = 895 kHz).
*/

#include "emu.h"
#include "m62_bkungfu_mcu_lle.h"

DEFINE_DEVICE_TYPE(BKUNGFU_MCU_LLE, bkungfu_mcu_lle_device, "bkungfu_mcu_lle", "Irem Beyond Kung-Fu MCU (reconstructed firmware)")

bkungfu_mcu_lle_device::bkungfu_mcu_lle_device(const machine_config &mconfig, const char *tag, device_t *owner, uint32_t clock)
	: device_t(mconfig, BKUNGFU_MCU_LLE, tag, owner, clock)
	, m_cpu(*this, "cpu")
	, m_firmware(*this, "fw")
	, m_data_rom(*this, "blitterdat")
	, m_tilemap_ram_w(*this)
	, m_cmdlat(0)
	, m_slotlat(0)
{
}

void bkungfu_mcu_lle_device::device_add_mconfig(machine_config &config)
{
	M6803(config, m_cpu, DERIVED_CLOCK(1, 1));
	m_cpu->set_addrmap(AS_PROGRAM, &bkungfu_mcu_lle_device::mcu_map);
}

void bkungfu_mcu_lle_device::mcu_map(address_map &map)
{
	map(0x0400, 0x0400).rw(FUNC(bkungfu_mcu_lle_device::cmdlat_r), FUNC(bkungfu_mcu_lle_device::cmdlat_w));
	map(0x0401, 0x0401).rw(FUNC(bkungfu_mcu_lle_device::slotlat_r), FUNC(bkungfu_mcu_lle_device::slotlat_w));
	map(0x0800, 0x0fff).rw(FUNC(bkungfu_mcu_lle_device::shared_r), FUNC(bkungfu_mcu_lle_device::shared_w));
	map(0x2000, 0x5fff).rw(FUNC(bkungfu_mcu_lle_device::tilemap_r), FUNC(bkungfu_mcu_lle_device::tilemap_w));
	map(0x6000, 0xdfff).lr8(NAME([this] (offs_t offset) { return m_data_rom[offset]; }));
	map(0xf000, 0xffff).lr8(NAME([this] (offs_t offset) { return m_firmware[offset]; }));
}

void bkungfu_mcu_lle_device::device_start()
{
	save_item(NAME(m_mailbox));
	save_item(NAME(m_tileshadow));
	save_item(NAME(m_cmdlat));
	save_item(NAME(m_slotlat));
}

void bkungfu_mcu_lle_device::device_reset()
{
	std::fill(std::begin(m_mailbox), std::end(m_mailbox), 0);
	m_cmdlat = 0;
	m_slotlat = 0;
}

void bkungfu_mcu_lle_device::tilemap_w(offs_t offset, u8 data)
{
	m_tileshadow[offset] = data;
	m_tilemap_ram_w(offset, data);
}

u8 bkungfu_mcu_lle_device::mailbox_r(offs_t offset)
{
	return m_mailbox[offset & 0x7ff];
}

void bkungfu_mcu_lle_device::mailbox_from_main_w(offs_t offset, u8 data)
{
	if (offset < 0x800)
		m_mailbox[offset] = data;
	if (offset == 0x00)
		m_cmdlat |= 0x80;
	if (offset >= 0x10 && offset < 0x30 && !(offset & 3))
		m_slotlat |= 1 << ((offset - 0x10) >> 2);

	// let the MCU see the write before the Z80 starts polling for the answer
	machine().scheduler().perfect_quantum(attotime::from_usec(100));
}
