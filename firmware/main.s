; -----------------------------------------------------------------------------
; Beyond Kung-Fu MCU firmware - reset, mailbox loop, commands, HUD, text,
; objects (6803 assembly).  Behavioural equivalent of command_w(),
; execute_slot(), update_slot(), draw_text(), draw_object() and friends in the
; MAME HLE.
;
; Mailbox signalling (our LLE bus convention, see docs/SPEC.md):
;   CMDLAT  bit7 set when the Z80 writes mailbox offset 0 (a command);
;           any MCU write clears it.
;   SLOTLAT bit n set when the Z80 writes mailbox offset $10 + 4n (a HUD
;           status slot trigger); an MCU write clears the bits written as 1.
; A level of the mailbox itself cannot be used: command $FE is acknowledged
; with $FE, so "new $FE" and "acknowledged" would look the same.
; -----------------------------------------------------------------------------

CMDLAT   .EQU $0400
SLOTLAT  .EQU $0401
MBOX     .EQU $0800      ; shared mailbox, Z80 $C800-$CFFF
TMEND    .EQU $6000      ; TILEMAP + $4000

RUNNING  .EQU $98
INITF    .EQU $99
VALID    .EQU $9A
SLOT     .EQU $9B
SPEND    .EQU $9C
TCH      .EQU $9D
P1S      .EQU $A0        ; 3 bytes each, BCD as sent by the Z80
P2S      .EQU $A3
TOPS     .EQU $A6
TIMH     .EQU $A9
TIML     .EQU $AA
FLOORC   .EQU $AB
FLOORST  .EQU $AC
LIVES    .EQU $AD
PEN      .EQU $AE
BEN      .EQU $AF
VOH      .EQU $B0        ; vram_page_w offset } LDD/STD VOH
VOL      .EQU $B1
T2H      .EQU $B2        ; scratch word
T2L      .EQU $B3
POSH     .EQU $B4        ; text / init position
POSL     .EQU $B5
TATTR    .EQU $B6
SRCH     .EQU $B7        ; text source pointer (logical)
SRCL     .EQU $B8
REMH     .EQU $B9        ; bytes left before giving up on a stream
REML     .EQU $BA
TMODE    .EQU $BB        ; 0 = ROM text, 1 = mailbox text
TPBH     .EQU $BC        ; mailbox address of the text's pos-lo/pos-hi/attr
TPBL     .EQU $BD
WID      .EQU $BE
COLC     .EQU $BF
RSH      .EQU $C0        ; object: current row start offset
RSL      .EQU $C1
DSH      .EQU $C2        ; object: current cell offset
DSL      .EQU $C3
NCH      .EQU $C4        ; object: cells drawn
NCL      .EQU $C5
OATTR    .EQU $C6
XB       .EQU $C7
YB       .EQU $C8
LCNT     .EQU $C9
LIMH     .EQU $CA
LIML     .EQU $CB
FULL     .EQU $CC
PART     .EQU $CD
BOSSF    .EQU $CE
EN       .EQU $CF
TAT      .EQU $DB        ; attribute for vpwpair
PAIRM    .EQU $DC        ; vpwpair: $0F = mask the attribute offset, $FF = don't
CROWS    .EQU $DF        ; clear: 64-byte blocks left in the current row
PACE_ROW .EQU 3915       ; E-clock ticks per tile row: 32 x 4.375 ms = 140 ms (E = 895 kHz)

; =============================================================================
reset:
        SEI
        LDS  #$00FF
        LDX  #$0080
r_clr:
        CLR  0,X
        INX
        CPX  #$00F0
        BNE  r_clr
        STAA CMDLAT
        LDAA #$FF
        STAA SLOTLAT

main:
        LDAA CMDLAT
        BPL  m_slots
        STAA CMDLAT             ; take the command
        LDAA MBOX
        JSR  command
m_slots:
        LDAA SLOTLAT
        BEQ  main
        STAA SLOTLAT            ; take these slot triggers
        TST  RUNNING
        BEQ  main               ; HLE ignores slot writes until command $FE
        STAA SPEND
        LDAA #$10
        STAA SLOT
ms_loop:
        LDAA SPEND
        LSRA
        STAA SPEND
        BCC  ms_next
        JSR  exec_slot
ms_next:
        LDAA SLOT
        ADDA #4
        STAA SLOT
        CMPA #$30
        BCS  ms_loop
        BRA  main

; =============================================================================
command:
        CMPA #$01
        LBEQ c01
        CMPA #$02
        LBEQ c02
        CMPA #$05
        LBEQ ack0
        CMPA #$08
        LBEQ c08
        CMPA #$0A
        LBEQ c0a
        CMPA #$0C
        LBEQ c0c
        CMPA #$0D
        LBEQ c0d
        CMPA #$14
        LBEQ c0d
        CMPA #$0F
        LBEQ c0f
        CMPA #$10
        LBEQ c10
        CMPA #$FE
        LBEQ cfe
        RTS                     ; unknown command: no acknowledge
ack0:
        LDAA CMDLAT             ; a new command arrived while this one ran:
        BMI  ack_skip           ; the Z80 has moved on, leave its command byte
        LDAA #$FE               ; in place for the main loop to execute
        STAA MBOX
ack_skip:
        RTS

c01:
        LDAA MBOX+1
        STAA LEVEL
        BRA  ack0
c02:
        JSR  draw_level
        BRA  ack0

c08:
        TST  RUNNING
        BEQ  c08b
        JSR  pace_start         ; top-to-bottom wipe, ~140 ms as on the PCB
        LDX  #TILEMAP           ; clear: (tile mbox[2], attribute mbox[1])
ct_row:
        LDAA #8                 ; 8 x 64 bytes = one tile row (512 bytes)
        STAA CROWS
        LDAA MBOX+2
        LDAB MBOX+1
ct_loop:
        STD  0,X
        STD  2,X
        STD  4,X
        STD  6,X
        STD  8,X
        STD  10,X
        STD  12,X
        STD  14,X
        STD  16,X
        STD  18,X
        STD  20,X
        STD  22,X
        STD  24,X
        STD  26,X
        STD  28,X
        STD  30,X
        STD  32,X
        STD  34,X
        STD  36,X
        STD  38,X
        STD  40,X
        STD  42,X
        STD  44,X
        STD  46,X
        STD  48,X
        STD  50,X
        STD  52,X
        STD  54,X
        STD  56,X
        STD  58,X
        STD  60,X
        STD  62,X
        PSHB
        LDAB #64
        ABX
        PULB
        DEC  CROWS
        BNE  ct_loop
        LDD  #PACE_ROW
        JSR  pace_wait
        CPX  #TMEND
        BNE  ct_row
c08b:
        CLR  INITF
        JMP  ack0

cfe:
        LDAA #1
        STAA RUNNING
        LDAA #$FE
        LDX  #MBOX
        STAA $10,X
        STAA $14,X
        STAA $18,X
        STAA $1C,X
        STAA $20,X
        STAA $24,X
        STAA $28,X
        STAA $2C,X
        LDX  #MBOX+$100
        STAA $02,X
        STAA $06,X
        STAA $18,X
        STAA $1C,X
        STAA MBOX
        RTS

; --- 0x0A: fixed HUD from the plaintext stream at ROM[$0140] ----------------
c0a:
        LDD  #$0140
        JSR  rword
        STD  SRCH
        CLR  TMODE
        LDX  #$FFFF
        STX  REMH
        CLR  POSH
        CLR  POSL
        CLR  TATTR
ih_loop:
        LDX  REMH
        LBEQ ack0               ; never terminated: acknowledge only
        JSR  tfetch
        TSTA
        BEQ  ih_term
        CMPA #$01
        BNE  ih_2
        JSR  tfetch
        STAA TATTR
        BRA  ih_loop
ih_2:
        CMPA #$02
        BNE  ih_ch
        JSR  tfetch
        STAA POSL
        JSR  tfetch
        STAA POSH
        BRA  ih_loop
ih_ch:
        STAA TCH
        LDD  POSH
        ANDA #$0F
        STD  VOH
        LDAA TATTR
        STAA TAT
        LDAA #$0F
        STAA PAIRM
        JSR  vpwpair
        LDAA POSL
        TAB
        ANDB #$80
        ADDA #2
        ANDA #$7F
        ABA
        STAA POSL
        BRA  ih_loop
ih_term:
        LDAA #1
        STAA INITF
        LDAA VALID              ; redraw every slot already received
        STAA SPEND
        LDAA #$10
        STAA SLOT
ih_r:
        LDAA SPEND
        LSRA
        STAA SPEND
        BCC  ih_rn
        JSR  update_slot
ih_rn:
        LDAA SLOT
        ADDA #4
        STAA SLOT
        CMPA #$30
        BCS  ih_r
        JMP  ack0

; --- 0x0C / 0x0D / 0x14: text --------------------------------------------------
c0c:
        LDAA #1
        STAA TMODE
        LDD  #$0100
        STD  SRCH
        LDD  #$0800
        STD  REMH
        LDD  #MBOX+3            ; pos-lo, pos-hi, attr at mailbox 3, 4, 5
        STD  TPBH
        JSR  draw_text
        JMP  ack0
c0d:
        CLR  TMODE
        LDAB MBOX+1
        CLRA
        ASLD                    ; text number * 2
        JSR  rword              ; pointer table at ROM $0000
        STD  SRCH
        LDX  #$FFFF
        STX  REMH
        LDD  #MBOX+2            ; pos-lo, pos-hi, attr at mailbox 2, 3, 4
        STD  TPBH
        JSR  draw_text
        JMP  ack0

; --- 0x0F: object --------------------------------------------------------------
c0f:
        LDAA MBOX+1
        JSR  draw_obj
        JMP  ack0

; --- 0x10: credits / continue digits ------------------------------------------
c10:
        TST  RUNNING
        LBEQ ack0
        LDAA MBOX+1
        LSRA
        LSRA
        LSRA
        LSRA
        ORAA #$30
        CLRB
        BSR  cr_put             ; pos+0: high digit
        LDAA MBOX+4
        LDAB #1
        BSR  cr_put             ; pos+1: attribute
        LDAA MBOX+1
        ANDA #$0F
        ORAA #$30
        LDAB #2
        BSR  cr_put             ; pos+2: low digit
        LDAA MBOX+4
        LDAB #3
        BSR  cr_put             ; pos+3: attribute
        JMP  ack0
cr_put:                         ; vram_page_w((pos + B) & 0xFFF, A)
        STAA TCH
        LDAA MBOX+3
        STAB T2L
        LDAB MBOX+2
        ADDB T2L
        ADCA #0
        ANDA #$0F
        STD  VOH
        LDAA TCH
        JMP  vpw

; =============================================================================
; vpw: vram_page_w(VOH:VOL, A) - one byte mirrored into the four 64-tile pages
;      real offset = ((off & ~$7F) << 2) | (off & $7F) | page;  dropped when
;      >= $4000 (i.e. off >= $1000), as tilemap_ram_w does.
vpw:
        PSHA
        LDAA VOH
        CMPA #$10
        BCC  vpw_drop
        LDAB VOL
        ANDB #$80
        ASLD
        ASLD
        STD  T2H
        LDAB VOL
        ANDB #$7F
        CLRA
        ADDD T2H
        ADDD #TILEMAP
        STD  T2H
        LDX  T2H
        PULA
        STAA 0,X
        STAA $80,X
        INC  T2H
        LDX  T2H
        STAA 0,X
        STAA $80,X
        RTS
vpw_drop:
        PULA
        RTS

; vpwpair: tile TCH at logical offset VOH:VOL (12 bits), attribute TAT at the
; next offset, each mirrored into the four pages.  Even offsets (the normal
; case) take a fast path: the pair is one STD per page, and the physical row
; address is offset>>7 * 512 + TILEMAP.  Odd offsets fall back to vpw, with
; the attribute offset masked to 12 bits or not according to PAIRM.
vpwpair:
        LDAB VOL
        BITB #$01
        BNE  vp_slow
        ASLB                    ; C = bit 7 of the offset
        LDAA VOH
        ROLA                    ; tile row = offset >> 7
        ASLA                    ; row * 2 = high byte of row * 512
        ADDA #$20               ; + TILEMAP ($2000)
        LDAB VOL
        ANDB #$7F
        STD  T2H
        LDX  T2H
        LDAA TCH
        LDAB TAT
        STD  0,X
        STD  $80,X
        INC  T2H
        LDX  T2H
        STD  0,X
        STD  $80,X
        RTS
vp_slow:
        LDAA TCH
        JSR  vpw
        LDD  VOH
        ADDD #1
        ANDA PAIRM
        STD  VOH
        LDAA TAT
        JMP  vpw

; --- rdlog: A = byte of the "blitterdat" region at logical D -----------------
rdlog:
        CMPA #$80
        BCC  rl_ff
        ADDD #DATA
        STD  TMP
        LDX  TMP
        LDAA 0,X
        RTS
rl_ff:
        LDAA #$FF               ; ROMREGION_ERASEFF above the 32K ROM
        RTS

; --- tfetch: A = next text/init source byte -----------------------------------
tfetch:
        TST  TMODE
        BNE  tf_mb
        LDD  SRCH
        JSR  rdlog
        BRA  tf_adv
tf_mb:
        LDAA SRCH
        ANDA #$07
        LDAB SRCL
        ADDD #MBOX
        STD  T2H
        LDX  T2H
        LDAA 0,X
tf_adv:
        LDX  SRCH
        INX
        STX  SRCH
        LDX  REMH
        DEX
        STX  REMH
        RTS

; --- draw_text: stream grammar 00 end / 01 attr / 02 lo hi / tile -------------
draw_text:
        TST  RUNNING
        BNE  dt_loop
        RTS
dt_loop:
        LDX  REMH
        BEQ  dt_end
        JSR  tfetch
        TSTA
        BEQ  dt_end
        CMPA #$01
        BNE  dt_2
        JSR  tfetch
        LDX  TPBH
        STAA 2,X                ; attribute
        BRA  dt_loop
dt_2:
        CMPA #$02
        BNE  dt_ch
        JSR  tfetch
        LDX  TPBH
        STAA 0,X                ; position low
        JSR  tfetch
        LDX  TPBH
        STAA 1,X                ; position high
        BRA  dt_loop
dt_ch:
        STAA TCH
        LDX  TPBH
        LDAA 2,X
        STAA TAT
        LDAA 1,X
        LDAB 0,X
        STD  POSH
        ANDA #$0F
        STD  VOH
        LDAA #$0F
        STAA PAIRM
        JSR  vpwpair
        LDAA POSL               ; advance 2 bytes, wrapping in the 64-tile row
        TAB
        ANDB #$80
        ADDA #2
        ANDA #$7F
        ABA
        LDX  TPBH
        STAA 0,X
        LDAA POSH
        STAA 1,X
        BRA  dt_loop
dt_end:
        RTS

; --- draw_obj: object A (ids $80-$90) -----------------------------------------
draw_obj:
        CMPA #$80
        LBCS do_ret
        CMPA #$90
        LBHI do_ret
        SUBA #$80
        ASLA
        TAB
        CLRA
        ADDD #$0100
        JSR  rword              ; record pointer
        STD  T2H
        LDX  T2H
        LBEQ do_ret
        CPX  #$7FFB
        LBCC do_ret
        LDD  T2H
        JSR  rdlog
        STAA WID
        LDD  T2H
        ADDD #1
        JSR  rword
        ANDA #$0F
        STD  RSH                ; pos & 0xFFF
        STD  DSH
        LDD  T2H
        ADDD #3
        JSR  rword
        STD  SRCH
        LDAA WID
        LBEQ do_ret
        CMPA #$20
        LBHI do_ret
        LDX  SRCH
        CPX  #$8000
        LBCC do_ret
        LDD  SRCH
        JSR  setp
        CLR  OATTR
        CLR  COLC
        CLR  NCH
        CLR  NCL
do_loop:
        LDX  PTRH
        CPX  #DEND
        LBCC do_ret
        LDX  NCH
        CPX  #512
        LBCC do_ret
        JSR  nextd              ; A = decrypted byte, B = its cipher index
        CMPA #$5F
        BNE  do_n5f
        LDX  PTRH               ; 5F <attr>
        CPX  #DEND
        LBCC do_ret
        JSR  nextp
        STAA OATTR
        BRA  do_loop
do_n5f:
        CMPA #$5E
        LBEQ do_ret
        CMPA #$60
        LBEQ do_ret
        BITB #1                 ; tile = payload transform of the same byte
        BEQ  do_even
        NEGA
        ADDA #$60
        BRA  do_tile
do_even:
        JSR  ffun
do_tile:
        STAA TCH
        LDAA OATTR
        STAA TAT
        LDD  DSH
        ANDA #$0F
        STD  VOH
        LDAA #$FF               ; destination + 1 is NOT masked in the HLE
        STAA PAIRM
        JSR  vpwpair
        LDX  NCH
        INX
        STX  NCH
        INC  COLC
        LDAA COLC
        CMPA WID
        BCS  do_right
        CLR  COLC
        LDD  RSH
        ADDD #$80
        STD  RSH
        STD  DSH
        LBRA do_loop
do_right:
        LDD  DSH
        ADDD #2
        STD  DSH
        LBRA do_loop
do_ret:
        RTS

; =============================================================================
; exec_slot: HUD status slot SLOT ($10..$2C): latch parameters, redraw, ack
exec_slot:
        LDAB SLOT
        LDX  #MBOX
        ABX
        LDAA SLOT
        CMPA #$10
        BNE  es14
        LDAA 1,X
        STAA P1S
        LDAA 2,X
        STAA P1S+1
        LDAA 3,X
        STAA P1S+2
        BRA  es_done
es14:
        CMPA #$14
        BNE  es18
        LDAA 1,X
        STAA P2S
        LDAA 2,X
        STAA P2S+1
        LDAA 3,X
        STAA P2S+2
        BRA  es_done
es18:
        CMPA #$18
        BNE  es1c
        LDAA 1,X
        STAA TOPS
        LDAA 2,X
        STAA TOPS+1
        LDAA 3,X
        STAA TOPS+2
        BRA  es_done
es1c:
        CMPA #$1C
        BNE  es20
        LDAA 1,X
        STAA TIMH
        LDAA 2,X
        STAA TIML
        BRA  es_done
es20:
        CMPA #$20
        BNE  es24
        LDAA 1,X
        STAA FLOORC
        LDAA 0,X
        STAA FLOORST
        BRA  es_done
es24:
        CMPA #$24
        BNE  es28
        LDAA 1,X
        STAA LIVES
        BRA  es_done
es28:
        CMPA #$28
        BNE  es2c
        LDAA 1,X
        STAA PEN
        BRA  es_done
es2c:
        LDAA 1,X
        STAA BEN
es_done:
        LDAB SLOT               ; valid |= 1 << ((slot - $10) >> 2)
        SUBB #$10
        LSRB
        LSRB
        LDAA #1
es_sh:
        TSTB
        BEQ  es_v
        ASLA
        DECB
        BRA  es_sh
es_v:
        ORAA VALID
        STAA VALID
        JSR  update_slot
        LDAB SLOT
        LDX  #MBOX
        ABX
        LDAA #$FE
        STAA 0,X
        RTS

; --- update_slot: redraw HUD element SLOT (only once initialised) ------------
update_slot:
        TST  INITF
        BNE  us_go
        RTS
us_go:
        LDAA SLOT
        CMPA #$10
        BNE  us14
        LDX  #P1S
        LDAA #$14
        BRA  us_score
us14:
        CMPA #$14
        BNE  us18
        LDX  #P2S
        LDAA #$29
        BRA  us_score
us18:
        CMPA #$18
        BNE  us1c
        LDX  #TOPS
        LDAA #$1F
us_score:
        STAA XB
        CLR  YB
        LDAB #3
        JMP  put_digits
us1c:
        CMPA #$1C
        BNE  us20
        LDX  #TIMH
        LDAA #$25
        STAA XB
        LDAA #5
        STAA YB
        LDAB #2
        JMP  put_digits
us20:
        CMPA #$20
        LBNE us24
        LDAA FLOORC             ; lit if i <= floorcount - (state == 2)
        LDAB FLOORST
        CMPB #2
        BNE  fd_l
        TSTA
        BEQ  fd_none
        DECA
fd_l:
        STAA LIML
        CLR  LIMH
        BRA  fd_go
fd_none:
        LDAA #$FF
        STAA LIMH
fd_go:
        CLR  LCNT
fd_loop:
        LDAB LCNT
        ASLB
        ASLB
        CLRA
        ADDD #$01C0             ; ((3*$40 + $20 + 2i) << 1)
        STD  VOH
        LDAA #$D6
        TST  LIMH
        BNE  fd_w
        LDAB LCNT
        CMPB LIML
        BHI  fd_w
        LDAA #$D5
fd_w:
        JSR  vpw
        INC  LCNT
        LDAA LCNT
        CMPA #8
        BCS  fd_loop
        RTS
us24:
        CMPA #$24
        BNE  us28
        LDAA #$2D
        STAA XB
        LDAA #5
        STAA YB
        LDAA LIVES
        JMP  write_num
us28:
        CMPA #$28
        BNE  us2c
        LDAA PEN
        LDAB #2
        CLR  BOSSF
        BRA  lifebar
us2c:
        LDAA BEN
        LDAB #4
        STAB BOSSF
lifebar:                        ; A = energy, B = row
        CMPA #$40
        BHI  lb_ret
        STAA EN
        STAB YB
        LDAA #$17
        STAA XB
        LDAA EN
        ANDA #$78
        LSRA
        LSRA
        LSRA
        STAA FULL
        CLR  LCNT
lb_loop:
        LDAB LCNT
        CMPB FULL
        BCS  lb_8
        BNE  lb_0
        LDAA EN
        ANDA #7
        BRA  lb_p
lb_8:
        LDAA #8
        BRA  lb_p
lb_0:
        CLRA
lb_p:
        TSTA
        BEQ  lb_empty
        STAA PART
        LDAA #$CC               ; $C4 + 8
        TST  BOSSF
        BEQ  lb_nb
        LDAA #$D4               ; $CC + 8
lb_nb:
        SUBA PART
        BRA  lb_w
lb_empty:
        LDAA #$C2
lb_w:
        STAA TCH
        LDAA YB
        LDAB #$40
        MUL
        ADDB XB
        ADCA #0
        ADDB LCNT
        ADCA #0
        ASLD
        ANDA #$0F
        STD  VOH
        LDAA TCH
        JSR  vpw
        INC  LCNT
        LDAA LCNT
        CMPA #8
        BCS  lb_loop
lb_ret:
        RTS

; --- put_digits: B bytes of BCD at X -> 2B digits from (XB, YB) ---------------
put_digits:
        PSHB
        LDAA 0,X
        PSHX
        LSRA
        LSRA
        LSRA
        LSRA
        BSR  write_num
        PULX
        LDAA 0,X
        PSHX
        BSR  write_num
        PULX
        INX
        PULB
        DECB
        BNE  put_digits
        RTS

; --- write_num: digit (A & $0F) + $30 at (XB, YB); XB++ ------------------------
write_num:
        ANDA #$0F
        ADDA #$30
        STAA TCH
        LDAA YB
        LDAB #$40
        MUL
        ADDB XB
        ADCA #0
        ASLD
        ANDA #$0F
        STD  VOH
        LDAA TCH
        JSR  vpw
        INC  XB
        RTS
code_end:
