// license:BSD-3-Clause
// copyright-holders:DocteurPCB
/*
    Irem Beyond Kung-Fu MCU, low-level emulation of a reconstructed firmware,
    Intel 8751 hypothesis (as the MCU of Irem's M72 boards, on its own 8 MHz
    crystal).  The firmware reimplements the HLE in m62_bkungfu_mcu.cpp in
    8051 assembly, checked byte for byte against it.  It is NOT Irem's code.

    External data memory (MOVX; MOVX @Ri uses P2 as the high byte):
      0400       command latch: bit 7 set by a Z80 write to mailbox offset 0,
                 cleared by any MCU write
      0401       slot latch: bit n set by a Z80 write to mailbox offset 10+4n,
                 MCU writes 1 to clear
      0800-0FFF  mailbox, shared with the Z80 at C800-CFFF
      2000-5FFF  tilemap RAM (write-through to the video tilemap)
      8000-FFFF  external data ROM km-z.4h
    Program: the 4 KB internal EPROM (the "mcu" file).
*/

#include "emu.h"
#include "m62_bkungfu_mcu51.h"

DEFINE_DEVICE_TYPE(BKUNGFU_MCU51, bkungfu_mcu51_device, "bkungfu_mcu51", "Irem Beyond Kung-Fu MCU (reconstructed i8751 firmware)")

bkungfu_mcu51_device::bkungfu_mcu51_device(const machine_config &mconfig, const char *tag, device_t *owner, uint32_t clock)
	: device_t(mconfig, BKUNGFU_MCU51, tag, owner, clock)
	, m_cpu(*this, "cpu")
	, m_data_rom(*this, "blitterdat")
	, m_tilemap_ram_w(*this)
	, m_cmdlat(0)
	, m_slotlat(0)
{
}

void bkungfu_mcu51_device::device_add_mconfig(machine_config &config)
{
	I8751(config, m_cpu, DERIVED_CLOCK(1, 1));
	m_cpu->set_addrmap(AS_DATA, &bkungfu_mcu51_device::xdata_map);
}

void bkungfu_mcu51_device::xdata_map(address_map &map)
{
	map(0x0400, 0x0400).rw(FUNC(bkungfu_mcu51_device::cmdlat_r), FUNC(bkungfu_mcu51_device::cmdlat_w));
	map(0x0401, 0x0401).rw(FUNC(bkungfu_mcu51_device::slotlat_r), FUNC(bkungfu_mcu51_device::slotlat_w));
	map(0x0800, 0x0fff).rw(FUNC(bkungfu_mcu51_device::shared_r), FUNC(bkungfu_mcu51_device::shared_w));
	map(0x2000, 0x5fff).rw(FUNC(bkungfu_mcu51_device::tilemap_r), FUNC(bkungfu_mcu51_device::tilemap_w));
	map(0x8000, 0xffff).lr8(NAME([this] (offs_t offset) { return m_data_rom[offset]; }));
}

void bkungfu_mcu51_device::device_start()
{
	save_item(NAME(m_mailbox));
	save_item(NAME(m_tileshadow));
	save_item(NAME(m_cmdlat));
	save_item(NAME(m_slotlat));
}

void bkungfu_mcu51_device::device_reset()
{
	std::fill(std::begin(m_mailbox), std::end(m_mailbox), 0);
	m_cmdlat = 0;
	m_slotlat = 0;
}

void bkungfu_mcu51_device::tilemap_w(offs_t offset, u8 data)
{
	m_tileshadow[offset] = data;
	m_tilemap_ram_w(offset, data);
}

u8 bkungfu_mcu51_device::mailbox_r(offs_t offset)
{
	return m_mailbox[offset & 0x7ff];
}

void bkungfu_mcu51_device::mailbox_from_main_w(offs_t offset, u8 data)
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
