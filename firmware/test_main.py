# -*- coding: utf-8 -*-
"""Drive the 6803 firmware and the HLE reference with the same Z80 mailbox
writes, and compare tilemap + mailbox after every step.
usage: test_main.py <km-z.4h>"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
from fwmcu import FirmwareMCU
from ref_mcu import RefMCU

DATA = open(sys.argv[1], "rb").read()
ref, fw = RefMCU(DATA), FirmwareMCU(DATA)
fails = 0


def w(off, val):
    ref.z80_write(off, val)
    fw.z80_write(off, val)


def cmd(c, **params):
    for off, val in params.get("mb", {}).items():
        w(off, val)
    w(0, c)


def check(label):
    global fails
    bad_t = [i for i in range(0x4000) if ref.tram[i] != fw.tram[i]]
    bad_m = [i for i in range(0x800) if ref.mailbox[i] != fw.mailbox[i]]
    ok = not bad_t and not bad_m
    fails += not ok
    detail = "" if ok else (
        (f"  tilemap: {len(bad_t)} octets (1er @ {bad_t[0]:#06x} fw={fw.tram[bad_t[0]]:02x} ref={ref.tram[bad_t[0]]:02x})" if bad_t else "")
        + (f"  mailbox: {len(bad_m)} octets (1er @ {bad_m[0]:#05x} fw={fw.mailbox[bad_m[0]]:02x} ref={ref.mailbox[bad_m[0]]:02x})" if bad_m else ""))
    print(f"{'✔' if ok else '✗'} {label}{detail}")


def slot(s, trigger, p1=0, p2=0, p3=0):
    w(s + 1, p1); w(s + 2, p2); w(s + 3, p3); w(s, trigger)


def text_ok(n):
    """ROM texts whose stream terminates quickly (the table also holds junk)."""
    a = ref.read_data(2 * n) | (ref.read_data(2 * n + 1) << 8)
    i = 0
    while i < 256:
        v = ref.read_data(a + i); i += 1
        if v == 0: return True
        if v == 1: i += 1
        elif v == 2: i += 2
    return False


# --- before command FE: slot writes and texts are ignored, commands still ack
slot(0x10, 0x01, 0x12, 0x34, 0x56)
cmd(0x0C);                            check("avant FE : slot ignoré, texte 0x0C ignoré mais acquitté")
cmd(0x07);                            check("commande inconnue 0x07 : pas d'acquittement")
cmd(0xFE);                            check("0xFE : démarrage + acquittement de tous les slots")
cmd(0x08, mb={1: 0x00, 2: 0x20});     check("0x08 : effacement de la tilemap")
for s, args in [(0x10, (0x01, 0x01, 0x23, 0x45)), (0x14, (0x01, 0x00, 0x98, 0x70)),
                (0x18, (0x01, 0x05, 0x00, 0x00)), (0x1C, (0x01, 0x16, 0x24)),
                (0x24, (0x01, 0x02)), (0x28, (0x01, 0x23)), (0x2C, (0x01, 0x40)),
                (0x20, (0x01, 0x03))]:
    slot(s, *args)
check("slots avant 0x0A : valeurs mémorisées, rien de dessiné")
cmd(0x0A);                            check("0x0A : HUD fixe + redessin des slots reçus")
for s, args in [(0x10, (0x01, 0x99, 0x99, 0x99)), (0x1C, (0x01, 0x00, 0x07)),
                (0x20, (0x02, 0x00)), (0x20, (0x02, 0x05)), (0x20, (0x01, 0x07)),
                (0x24, (0x01, 0x09)), (0x28, (0x01, 0x40)), (0x28, (0x01, 0x07)),
                (0x28, (0x01, 0x00)), (0x28, (0x01, 0x41)), (0x2C, (0x01, 0x3F)),
                (0x2C, (0x01, 0x08))]:
    slot(s, *args)
    check(f"slot {s:#04x} déclencheur {args[0]:#04x} paramètre {args[1]:#04x}")
texts = [n for n in range(0x80) if text_ok(n)]
for n in texts:
    cmd(0x0D if n % 2 else 0x14, mb={1: n})
check(f"0x0D/0x14 : {len(texts)} textes ROM ({texts[0]:#x}..{texts[-1]:#x})")
msg = [0x02, 0x10, 0x03, 0x01, 0x07] + [0x41 + i for i in range(10)] + [0x01, 0x1A, 0x31, 0x32, 0x00]
for i, b in enumerate(msg):
    w(0x100 + i, b)
cmd(0x0C, mb={3: 0, 4: 0, 5: 0});     check("0x0C : texte préparé par le Z80 dans la mailbox")
for v in (0x00, 0x09, 0x37):
    cmd(0x10, mb={1: v, 2: 0x7E, 3: 0x02, 4: 0x05})
check("0x10 : chiffres crédits/continue (y compris position en bout de ligne)")
for oid in range(0x7F, 0x92):
    cmd(0x0F, mb={1: oid})
    check(f"0x0F : objet {oid:#04x}")
cmd(0x05);                            check("0x05 : acquittement simple")
for lvl in (1, 4, 0, 13):
    cmd(0x01, mb={1: lvl}); cmd(0x02)
    check(f"0x01 + 0x02 : décor du slot {lvl}")
cmd(0x08, mb={1: 0x19, 2: 0x05});     check("0x08 en cours de partie")
slot(0x10, 0x01, 0x00, 0x01, 0x00);   check("slot après 0x08 : HUD non redessiné (non initialisé)")
cmd(0x0A);                            check("0x0A à nouveau")
print(f"\n{'==> FIRMWARE = HLE sur tout le scénario' if fails == 0 else f'==> {fails} étape(s) en échec'}")
sys.exit(1 if fails else 0)
