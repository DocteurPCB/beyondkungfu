#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Reference port of bkungfu_mcu_device decrypt/decode, run against the real km-z.4h
import sys

ROM = open(sys.argv[1], "rb").read()
SIZE = 0x10000            # region is 0x10000, ERASEFF above 0x8000
MASK = SIZE - 1
def rom(a):               # read_data(): raw, masked, 0xFF above loaded size
    a &= MASK
    return ROM[a] if a < len(ROM) else 0xFF

def read_data(a):
    return rom(a)

def decrypt_data(a):                      # exact port
    if a >= 0x8000:
        return 0xFF
    cipher = rom(a)
    index = (a & 0xFF) + (a >> 8) & 0xFF
    index &= 0xFF
    if index & 1:
        return (((index ^ (0x7e if (index & 2) else 0x12)) - 0x20 - cipher) & 0xFF)
    return (cipher ^ index ^ (0x5e if (index & 2) else 0xAE)) & 0xFF

def decode_payload(a):                    # exact port
    value = decrypt_data(a)
    s = ((a & 0xFF) + (a >> 8)) & 0xFF
    if s & 1:
        return (0x60 - value) & 0xFF
    base = 0xA0 if (value & 0x20) else 0x60
    return (base - value - (0 if (value & 1) else 2)) & 0xFF

def decode_payload_word(a):
    return decode_payload(a) | (decode_payload(a + 1) << 8)

def word_raw(a):
    return rom(a) | (rom(a + 1) << 8)

print(f"ROM chargée: {len(ROM)} octets (0x{len(ROM):x})")

# ---- 1. Table des niveaux @0x200 (plaintext) vs valeurs documentées ----
expected = [0x184d,0x17dd,0x176d,0x16fd,0x168d,0x161d,0x15ad,0x153d,
            0x184d,0x17dd,0x176d,0x1a7d,0x1a0d,0x199d,0x192d,0x18bd]
print("\n=== Table des niveaux @0x0200 (lecture brute) ===")
ok = True
for i in range(16):
    v = word_raw(0x200 + i*2)
    flag = "OK" if v == expected[i] else f"!! attendu {expected[i]:04x}"
    if v != expected[i]: ok = False
    print(f"  0x{0x200+i*2:04x}: {v:04x}   {flag}")
print("  => " + ("TABLE CONFORME à la doc du driver ✔" if ok else "DIVERGENCE"))

# ---- 2. Table des objets @0x100 (17 pointeurs, plaintext) ----
print("\n=== Table des objets @0x0100 (IDs 0x80..0x90) ===")
for i in range(17):
    v = word_raw(0x100 + i*2)
    print(f"  id 0x{0x80+i:02x} -> record @{v:04x}")

# ---- 3. Pointeur de stream d'init HUD @0x140 ----
init_ptr = word_raw(0x140)
print(f"\n=== Stream d'init (commande 0x0a) : pointeur @0x140 = {init_ptr:04x} ===")
print("  premiers octets bruts:", " ".join(f"{rom(init_ptr+i):02x}" for i in range(16)))

# ---- 4. Décodage complet d'un niveau (stage 1 => block 0x184d) ----
def decode_level_block(block, label):
    print(f"\n=== Décodage du niveau block={block:04x} ({label}) ===")
    if block < 0x153d:
        print("  (block hors zone chiffrée)"); return
    good_entries = 0
    sample = []
    for e in range(56):                      # 56 entrées de 2 octets = 0x70
        entry = block + e*2
        record = decode_payload_word(entry)
        if 0x1aed <= record < 0x8000-8:
            good_entries += 1
            if len(sample) < 6: sample.append((e, record))
    print(f"  entrées valides (record dans 1aed..7ff7) : {good_entries}/56")
    print("  échantillon entrée->record :", ", ".join(f"[{e}]->{r:04x}" for e,r in sample))
    # décode la 1re entrée : 4 streams
    rec0 = decode_payload_word(block)
    print(f"  entrée 0 -> record {rec0:04x}")
    if not (0x1aed <= rec0 < 0x8000-8):
        print("  record 0 hors plage, stop"); return
    counts = []
    for stream in range(4):
        ptr = decode_payload_word(rec0 + stream*2)
        cells = []
        attr = 0
        p = ptr
        guard = 0
        while p < 0x8000 and guard < 64:
            val = decode_payload(p); p += 1; guard += 1
            if val == 0x00: break
            if val == 0x01:
                attr = decode_payload(p); p += 1; guard += 1; continue
            cells.append(val)
        counts.append(len(cells))
        head = " ".join(f"{c:02x}" for c in cells[:10])
        print(f"    stream {stream} @{ptr:04x} : {len(cells)} cellules | tiles: {head}...")
    print(f"  longueurs des 4 streams: {counts}  (attendu 20 ou 32, et toutes égales)")

decode_level_block(0x184d, "stage 1, etat initial")
decode_level_block(0x153d, "stage 8, etat initial")
