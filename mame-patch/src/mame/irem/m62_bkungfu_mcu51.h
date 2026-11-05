// license:BSD-3-Clause
// copyright-holders:DocteurPCB
/*
    Irem Beyond Kung-Fu MCU, low-level, Intel 8751 hypothesis: a real 8751 core
    running the reconstructed firmware from
    https://github.com/DocteurPCB/beyondkungfu (firmware51/).

    Same Z80-facing interface as the HLE device.  The MCU-side bus is a
    reconstruction: the real board's wiring and MCU type are unknown.
*/
#ifndef MAME_IREM_M62_BKUNGFU_MCU51_H
#define MAME_IREM_M62_BKUNGFU_MCU51_H

#pragma once

#include "cpu/mcs51/i8051.h"

class bkungfu_mcu51_device : public device_t
{
public:
	bkungfu_mcu51_device(const machine_config &mconfig, const char *tag, device_t *owner, uint32_t clock);

	auto tilemap_ram_w() { return m_tilemap_ram_w.bind(); }

	u8 mailbox_r(offs_t offset);
	void mailbox_from_main_w(offs_t offset, u8 data);

protected:
	virtual void device_add_mconfig(machine_config &config) override ATTR_COLD;
	virtual void device_start() override ATTR_COLD;
	virtual void device_reset() override ATTR_COLD;

private:
	void xdata_map(address_map &map) ATTR_COLD;

	u8 cmdlat_r() { return m_cmdlat; }
	void cmdlat_w(u8 data) { m_cmdlat = 0; }
	u8 slotlat_r() { return m_slotlat; }
	void slotlat_w(u8 data) { m_slotlat &= ~data; }
	u8 shared_r(offs_t offset) { return m_mailbox[offset]; }
	void shared_w(offs_t offset, u8 data) { m_mailbox[offset] = data; }
	u8 tilemap_r(offs_t offset) { return m_tileshadow[offset]; }
	void tilemap_w(offs_t offset, u8 data);

	required_device<i8751_device> m_cpu;
	required_region_ptr<u8> m_data_rom;
	devcb_write8 m_tilemap_ram_w;

	u8 m_mailbox[0x800];
	u8 m_tileshadow[0x4000];
	u8 m_cmdlat;
	u8 m_slotlat;
};

DECLARE_DEVICE_TYPE(BKUNGFU_MCU51, bkungfu_mcu51_device)

#endif // MAME_IREM_M62_BKUNGFU_MCU51_H
