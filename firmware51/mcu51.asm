; =============================================================================
; Beyond Kung-Fu MCU firmware - Intel 8751 variant (8051 assembly, as31 syntax)
;
; Behavioural reimplementation of the MAME HLE (m62_bkungfu_mcu.cpp), for the
; hypothesis that the undumped MCU is an Intel 8751 (4 KB internal EPROM,
; 128 bytes RAM) on its own 8 MHz crystal, as on Irem's M72 boards.
; Not Irem's code.  Same behaviour as the 6803 variant in ../firmware/.
;
; External data memory (MOVX), our reconstruction of the board glue:
;   0400       CMDLAT  bit7 = Z80 wrote mailbox offset 0; any MCU write clears
;   0401       SLOTLAT bit n = Z80 wrote mailbox offset 10h+4n; write 1 clears
;   0800-0FFF  mailbox shared with the Z80 (C800-CFFF)
;   2000-5FFF  tilemap RAM
;   8000-FFFF  km-z.4h (logical address | 8000h)
; Code memory: 0000-0DFF program, 0E00 PTAB, 0F00 FTAB (cipher tables).
;
; Invariant: DPTR = PTAB, except inside routines that use MOVX @DPTR, which
; reload it before returning.  Data ROM reads use P2:R0 (MOVX A,@R0).
; =============================================================================

        .equ    PG, 0A0h                ; SFR P2: high byte for MOVX @Ri
        .equ    RDPL, 82h
        .equ    RDPH, 83h
        .equ    RB, 0F0h
        .equ    RACC, 0E0h
        .equ    TL0R, 8Ah
        .equ    TH0R, 8Ch
        .equ    TMODR, 89h
        .equ    TR0B, 8Ch               ; bit TCON.4
        .equ    F0B, 0D5h               ; bit PSW.5: parity returned by nextd

        .equ    CMDLAT, 0400h
        .equ    SLOTLAT, 0401h
        .equ    MBOX, 0800h
        .equ    TILEMAP, 2000h
        .equ    PTAB, 0E00h

        .equ    PACE_HALF, 13333        ; machine cycles (1.5 us at 8 MHz): 20 ms
        .equ    PACE_ROW, 2917          ; 4.375 ms

; ---- bits (byte 20h) ---------------------------------------------------------
        .equ    FULLB, 00h              ; stream reached its expected length
        .equ    RIGHTB, 01h             ; next cell is the right one of the pair

; ---- internal RAM ------------------------------------------------------------
        .equ    DLH, 21h                ; pacing deadline
        .equ    DLL, 22h
        .equ    EN, 23h
        .equ    FULLSEG, 24h
        .equ    BOSSF, 25h
        .equ    CROWS, 26h
        .equ    LIMNONE, 27h
        .equ    PART, 28h
        .equ    TMPA, 29h
        .equ    TMPB, 2Ah
        .equ    CRV, 2Bh
        .equ    LEVEL, 30h
        .equ    PAIR, 31h
        .equ    HALF, 32h
        .equ    EXPC, 33h
        .equ    SNUM, 34h
        .equ    ATTR, 35h
        .equ    ROWS, 36h
        .equ    BLKH, 37h
        .equ    BLKL, 38h
        .equ    RECH, 39h
        .equ    RECL, 3Ah
        .equ    BASEH, 3Bh
        .equ    BASEL, 3Ch
        .equ    WPH, 3Dh
        .equ    WENDH, 3Eh
        .equ    RUNNING, 40h
        .equ    INITF, 41h
        .equ    VALID, 42h
        .equ    SLOT, 43h
        .equ    SPEND, 44h
        .equ    TCH, 45h
        .equ    TAT, 46h
        .equ    PAIRM, 47h
        .equ    VOH, 48h
        .equ    VOL, 49h
        .equ    POSH, 4Ah
        .equ    POSL, 4Bh
        .equ    SRCH, 4Ch
        .equ    SRCL, 4Dh
        .equ    REMH, 4Eh
        .equ    REML, 4Fh
        .equ    TMODE, 50h
        .equ    TPB, 51h
        .equ    WID, 52h
        .equ    COLC, 53h
        .equ    RSH, 54h
        .equ    RSL, 55h
        .equ    DSH, 56h
        .equ    DSL, 57h
        .equ    NCH, 58h
        .equ    NCL, 59h
        .equ    OATTR, 5Ah
        .equ    P1S, 5Bh                ; 3 bytes each, BCD as sent by the Z80
        .equ    P2S, 5Eh
        .equ    TOPS, 61h
        .equ    TIMH, 64h
        .equ    TIML, 65h
        .equ    FLOORC, 66h
        .equ    FLOORST, 67h
        .equ    LIVES, 68h
        .equ    PEN, 69h
        .equ    BEN, 6Ah
        .equ    XB, 6Bh
        .equ    YB, 6Ch
        .equ    LCNT, 6Dh
        .equ    LIM, 6Eh
                                        ; stack: 70h-7Fh

; =============================================================================
        .org    0
        ljmp    reset

        .org    30h
reset:
        mov     sp,#6Fh
        mov     TMODR,#01h              ; timer 0: 16-bit, counts machine cycles
        setb    TR0B
        mov     r0,#20h
        clr     a
r_clr:  mov     @r0,a
        inc     r0
        cjne    r0,#6Fh,r_clr
        mov     dptr,#CMDLAT
        movx    @dptr,a                 ; clear the command latch
        inc     dptr
        mov     a,#0FFh
        movx    @dptr,a                 ; clear every slot latch bit
        mov     dptr,#PTAB

main:
        mov     dptr,#CMDLAT
        movx    a,@dptr
        jnb     acc.7,m_slots
        movx    @dptr,a                 ; take the command
        mov     dptr,#MBOX
        movx    a,@dptr
        mov     dptr,#PTAB
        lcall   command
m_slots:
        mov     dptr,#SLOTLAT
        movx    a,@dptr
        jz      m_none
        movx    @dptr,a                 ; take these slot triggers
        mov     dptr,#PTAB
        mov     r7,a
        mov     a,RUNNING
        jz      main                    ; ignored until command FE (HLE)
        mov     SPEND,r7
        mov     SLOT,#10h
ms_loop:
        mov     a,SPEND
        rrc     a
        mov     SPEND,a
        jnc     ms_next
        lcall   exec_slot
ms_next:
        mov     a,SLOT
        add     a,#4
        mov     SLOT,a
        cjne    a,#30h,ms_loop
        sjmp    main
m_none:
        mov     dptr,#PTAB
        sjmp    main

; =============================================================================
; data ROM access
; setp: R7:R6 = logical address (< 8000h) -> read pointer P2:R0
setp:
        mov     a,r7
        orl     a,#80h
        mov     PG,a
        mov     a,r6
        mov     r0,a
        ret

; nextp: A = payload-decoded byte at P2:R0, pointer advanced.  Uses R2.
; The cipher index is lo + hi of the LOGICAL address = R0 + P2 - 80h; it is
; recomputed for every byte, so the +2 jump at page crossings comes for free.
nextp:
        mov     a,r0
        add     a,PG
        add     a,#80h
        mov     r2,a                    ; index
        movx    a,@r0                   ; cipher byte
        inc     r0
        cjne    r0,#0,np_1
        inc     PG                      ; page crossing (wraps to 00 past the ROM)
np_1:   xch     a,r2                    ; A = index, R2 = cipher
        jb      acc.0,np_odd
        movc    a,@a+dptr               ; even: F(c ^ PTAB[i])
        xrl     a,r2
        inc     RDPH
        movc    a,@a+dptr               ; FTAB
        dec     RDPH
        ret
np_odd: movc    a,@a+dptr               ; odd: c + PTAB[i]
        add     a,r2
        ret

; nextd: A = decrypted byte (no payload transform), F0 = index parity (1 odd)
nextd:
        mov     a,r0
        add     a,PG
        add     a,#80h
        mov     r2,a
        movx    a,@r0
        inc     r0
        cjne    r0,#0,nd_1
        inc     PG
nd_1:   xch     a,r2
        jb      acc.0,nd_odd
        movc    a,@a+dptr               ; even: c ^ PTAB[i]
        xrl     a,r2
        clr     F0B
        ret
nd_odd: movc    a,@a+dptr               ; odd: 60h - PTAB[i] - c
        cpl     a
        add     a,#61h
        clr     c
        subb    a,r2
        setb    F0B
        ret

payload_at:                             ; R7:R6 logical -> A (test entry)
        lcall   setp
        ljmp    nextp
decrypt_at:
        lcall   setp
        ljmp    nextd

; pword: R7:R6 = little-endian payload word at P2:R0
pword:
        lcall   nextp
        mov     r6,a
        lcall   nextp
        mov     r7,a
        ret

; rword: R7:R6 = little-endian plaintext word at logical R7:R6 (< 8000h)
rword:
        mov     a,r7
        orl     a,#80h
        mov     RDPH,a
        mov     RDPL,r6
        movx    a,@dptr
        mov     r6,a
        inc     dptr
        movx    a,@dptr
        mov     r7,a
        mov     dptr,#PTAB
        ret

; rdlog: A = byte of the 64 KB "blitterdat" region at logical R7:R6
rdlog:
        mov     a,r7
        jb      acc.7,rl_ff             ; ROMREGION_ERASEFF above 32 KB
        orl     a,#80h
        mov     RDPH,a
        mov     RDPL,r6
        movx    a,@dptr
        mov     dptr,#PTAB
        ret
rl_ff:  mov     a,#0FFh
        ret

; mailbox byte access, page 08h: R5 = offset
mbr:    mov     RDPH,#08h
        mov     RDPL,r5
        movx    a,@dptr
        mov     dptr,#PTAB
        ret
mbw:    mov     RDPH,#08h
        mov     RDPL,r5
        movx    @dptr,a
        mov     dptr,#PTAB
        ret

; =============================================================================
; pacing on timer 0 (one tick per machine cycle); cumulative deadlines
rdtim:  mov     RB,TH0R
        mov     a,TL0R
        push    RACC
        mov     a,TH0R
        cjne    a,RB,rd_again
        pop     RACC
        ret
rd_again:
        pop     RACC
        sjmp    rdtim
pace_start:
        lcall   rdtim
        mov     DLL,a
        mov     DLH,RB
        ret
pace_wait:                              ; R7:R6 = ticks; keeps R3, R4
        mov     a,DLL
        add     a,r6
        mov     DLL,a
        mov     a,DLH
        addc    a,r7
        mov     DLH,a
pw_l:   lcall   rdtim
        clr     c
        subb    a,DLL
        mov     a,RB
        subb    a,DLH
        jb      acc.7,pw_l
        ret

; =============================================================================
; commands (A = mailbox[0])
command:
        cjne    a,#01h,cm_02
        ljmp    c01
cm_02:  cjne    a,#02h,cm_05
        ljmp    c02
cm_05:  cjne    a,#05h,cm_08
        ljmp    ack0
cm_08:  cjne    a,#08h,cm_0a
        ljmp    c08
cm_0a:  cjne    a,#0Ah,cm_0c
        ljmp    c0a
cm_0c:  cjne    a,#0Ch,cm_0d
        ljmp    c0c
cm_0d:  cjne    a,#0Dh,cm_14
        ljmp    c0d
cm_14:  cjne    a,#14h,cm_0f
        ljmp    c0d
cm_0f:  cjne    a,#0Fh,cm_10
        ljmp    c0f
cm_10:  cjne    a,#10h,cm_fe
        ljmp    c10
cm_fe:  cjne    a,#0FEh,cm_none
        ljmp    cfe
cm_none:
        ret                             ; unknown command: no acknowledge

; acknowledge, unless the Z80 already wrote a new command (it has moved on)
ack0:
        mov     dptr,#CMDLAT
        movx    a,@dptr
        jb      acc.7,ack_skip
        mov     dptr,#MBOX
        mov     a,#0FEh
        movx    @dptr,a
ack_skip:
        mov     dptr,#PTAB
        ret

c01:    mov     r5,#1
        lcall   mbr
        mov     LEVEL,a
        ljmp    ack0
c02:    lcall   draw_level
        ljmp    ack0

; ---- 0x08: clear, top-to-bottom wipe paced to ~140 ms ----------------------
c08:    mov     a,RUNNING
        jz      c08b
        mov     r5,#2
        lcall   mbr
        mov     r3,a                    ; tile
        mov     r5,#1
        lcall   mbr
        mov     r4,a                    ; attribute
        lcall   pace_start
        mov     dptr,#TILEMAP
        mov     CROWS,#32
ct_row: mov     r7,#64
ct_b:   mov     a,r3
        movx    @dptr,a
        inc     dptr
        mov     a,r4
        movx    @dptr,a
        inc     dptr
        mov     a,r3
        movx    @dptr,a
        inc     dptr
        mov     a,r4
        movx    @dptr,a
        inc     dptr
        mov     a,r3
        movx    @dptr,a
        inc     dptr
        mov     a,r4
        movx    @dptr,a
        inc     dptr
        mov     a,r3
        movx    @dptr,a
        inc     dptr
        mov     a,r4
        movx    @dptr,a
        inc     dptr
        djnz    r7,ct_b
        push    RDPL
        push    RDPH
        mov     r7,#(PACE_ROW >> 8)
        mov     r6,#(PACE_ROW & 0FFh)
        lcall   pace_wait
        pop     RDPH
        pop     RDPL
        djnz    CROWS,ct_row
        mov     dptr,#PTAB
c08b:   mov     INITF,#0
        ljmp    ack0

; ---- 0xFE: start ---------------------------------------------------------------
cfe:    mov     RUNNING,#1
        mov     a,#0FEh
        mov     RDPH,#08h
        mov     RDPL,#10h
        movx    @dptr,a
        mov     RDPL,#14h
        movx    @dptr,a
        mov     RDPL,#18h
        movx    @dptr,a
        mov     RDPL,#1Ch
        movx    @dptr,a
        mov     RDPL,#20h
        movx    @dptr,a
        mov     RDPL,#24h
        movx    @dptr,a
        mov     RDPL,#28h
        movx    @dptr,a
        mov     RDPL,#2Ch
        movx    @dptr,a
        mov     RDPH,#09h
        mov     RDPL,#02h
        movx    @dptr,a
        mov     RDPL,#06h
        movx    @dptr,a
        mov     RDPL,#18h
        movx    @dptr,a
        mov     RDPL,#1Ch
        movx    @dptr,a
        mov     dptr,#MBOX
        movx    @dptr,a
        mov     dptr,#PTAB
        ret

; ---- 0x0A: fixed HUD from the plaintext stream at ROM[0140h] ---------------
c0a:    mov     r7,#01h
        mov     r6,#40h
        lcall   rword
        mov     SRCH,r7
        mov     SRCL,r6
        mov     TMODE,#0
        mov     REMH,#0FFh
        mov     REML,#0FFh
        mov     POSH,#0
        mov     POSL,#0
        mov     TAT,#0
ih_loop:
        mov     a,REMH
        orl     a,REML
        jz      ih_unterm
        lcall   tfetch
        jz      ih_term
        cjne    a,#1,ih_2
        lcall   tfetch
        mov     TAT,a
        sjmp    ih_loop
ih_2:   cjne    a,#2,ih_ch
        lcall   tfetch
        mov     POSL,a
        lcall   tfetch
        mov     POSH,a
        sjmp    ih_loop
ih_ch:  mov     TCH,a
        mov     VOL,POSL
        mov     a,POSH
        anl     a,#0Fh
        mov     VOH,a
        mov     PAIRM,#0Fh
        lcall   vpwpair
        lcall   advpos
        sjmp    ih_loop
ih_unterm:
        ljmp    ack0                    ; never terminated: acknowledge only
ih_term:
        mov     INITF,#1
        mov     SPEND,VALID             ; redraw every slot already received
        mov     SLOT,#10h
ih_r:   mov     a,SPEND
        rrc     a
        mov     SPEND,a
        jnc     ih_rn
        lcall   update_slot
ih_rn:  mov     a,SLOT
        add     a,#4
        mov     SLOT,a
        cjne    a,#30h,ih_r
        ljmp    ack0

; advpos: POSL = (POSL & 80h) | ((POSL + 2) & 7Fh)
advpos: mov     a,POSL
        mov     r7,a
        anl     a,#80h
        mov     r6,a
        mov     a,r7
        add     a,#2
        anl     a,#7Fh
        orl     a,r6
        mov     POSL,a
        ret

; ---- text: 0x0C (Z80-prepared, mailbox) / 0x0D, 0x14 (ROM table) ----------
c0c:    mov     TMODE,#1
        mov     SRCH,#01h
        mov     SRCL,#00h
        mov     REMH,#08h
        mov     REML,#00h
        mov     TPB,#3                  ; pos-lo, pos-hi, attr at mailbox 3, 4, 5
        lcall   draw_text
        ljmp    ack0
c0d:    mov     r5,#1
        lcall   mbr
        mov     r6,a
        mov     r7,#0
        mov     a,r6                    ; text number * 2
        add     a,r6
        mov     r6,a
        clr     a
        addc    a,r7
        mov     r7,a
        lcall   rword                   ; pointer table at ROM 0000h
        mov     SRCH,r7
        mov     SRCL,r6
        mov     TMODE,#0
        mov     REMH,#0FFh
        mov     REML,#0FFh
        mov     TPB,#2                  ; pos-lo, pos-hi, attr at mailbox 2, 3, 4
        lcall   draw_text
        ljmp    ack0

; tfetch: A = next text/init source byte (Z flag not valid: test A)
tfetch: mov     a,TMODE
        jnz     tf_mb
        mov     r7,SRCH
        mov     r6,SRCL
        lcall   rdlog
        sjmp    tf_adv
tf_mb:  mov     a,SRCH
        anl     a,#07h
        add     a,#08h
        mov     RDPH,a
        mov     RDPL,SRCL
        movx    a,@dptr
        mov     dptr,#PTAB
tf_adv: mov     TMPB,a
        inc     SRCL
        mov     a,SRCL
        jnz     tf_1
        inc     SRCH
tf_1:   mov     a,REML
        jnz     tf_2
        dec     REMH
tf_2:   dec     REML
        mov     a,TMPB
        ret

draw_text:
        mov     a,RUNNING
        jnz     dt_loop
        ret
dt_loop:
        mov     a,REMH
        orl     a,REML
        jz      dt_end
        lcall   tfetch
        jz      dt_end
        cjne    a,#1,dt_2
        lcall   tfetch                  ; 01 <attr>
        mov     TMPA,a
        mov     a,TPB
        add     a,#2
        mov     r5,a
        mov     a,TMPA
        lcall   mbw
        sjmp    dt_loop
dt_2:   cjne    a,#2,dt_ch
        lcall   tfetch                  ; 02 <lo> <hi>
        mov     r5,TPB
        lcall   mbw
        lcall   tfetch
        mov     a,TPB
        inc     a
        mov     r5,a
        mov     a,TMPB
        lcall   mbw
        sjmp    dt_loop
dt_ch:  mov     TCH,a
        mov     a,TPB
        add     a,#2
        mov     r5,a
        lcall   mbr
        mov     TAT,a
        mov     r5,TPB
        lcall   mbr
        mov     POSL,a
        mov     a,TPB
        inc     a
        mov     r5,a
        lcall   mbr
        mov     POSH,a
        mov     VOL,POSL
        anl     a,#0Fh
        mov     VOH,a
        mov     PAIRM,#0Fh
        lcall   vpwpair
        lcall   advpos
        mov     r5,TPB
        mov     a,POSL
        lcall   mbw
        ljmp    dt_loop
dt_end: ret

; ---- 0x0F: object ---------------------------------------------------------------
c0f:    mov     r5,#1
        lcall   mbr
        lcall   draw_obj
        ljmp    ack0

; ---- 0x10: credits / continue digits --------------------------------------
c10:    mov     a,RUNNING
        jz      c10x
        mov     r5,#1
        lcall   mbr
        mov     CRV,a
        mov     r5,#4
        lcall   mbr
        mov     TMPB,a                  ; attribute
        mov     r5,#2
        lcall   mbr
        mov     POSL,a
        mov     r5,#3
        lcall   mbr
        mov     POSH,a
        mov     a,CRV
        swap    a
        anl     a,#0Fh
        orl     a,#30h
        mov     r6,#0
        lcall   cr_put
        mov     a,TMPB
        mov     r6,#1
        lcall   cr_put
        mov     a,CRV
        anl     a,#0Fh
        orl     a,#30h
        mov     r6,#2
        lcall   cr_put
        mov     a,TMPB
        mov     r6,#3
        lcall   cr_put
c10x:   ljmp    ack0
cr_put: mov     TMPA,a                  ; vram_page_w((pos + R6) & 0FFFh, A)
        mov     a,POSL
        add     a,r6
        mov     VOL,a
        clr     a
        addc    a,POSH
        anl     a,#0Fh
        mov     VOH,a
        mov     a,TMPA
        ljmp    vpw

; =============================================================================
; vpw: vram_page_w(VOH:VOL, A): one byte mirrored into the 4 pages.
; physical = TILEMAP + (offset >> 7) * 512 + (offset & 7Fh) + page * 80h;
; offsets >= 1000h are dropped, as tilemap_ram_w does.  Uses R3-R5, DPTR.
vpw:    mov     r5,a
        mov     a,VOH
        anl     a,#0F0h
        jnz     vpw_x
        lcall   vaddr
        mov     a,r5
        movx    @dptr,a
        mov     a,r3
        orl     a,#80h
        mov     RDPL,a
        mov     a,r5
        movx    @dptr,a
        inc     RDPH
        mov     RDPL,r3
        mov     a,r5
        movx    @dptr,a
        mov     a,r3
        orl     a,#80h
        mov     RDPL,a
        mov     a,r5
        movx    @dptr,a
vpw_x:  mov     dptr,#PTAB
        ret

; vaddr: DPTR = R4:R3 = physical address of logical VOH:VOL in page 0
vaddr:  mov     a,VOL
        rlc     a                       ; C = bit 7
        mov     a,VOH
        rlc     a                       ; tile row
        rl      a                       ; * 2 = high byte of row * 512
        add     a,#(TILEMAP >> 8)
        mov     r4,a
        mov     RDPH,a
        mov     a,VOL
        anl     a,#7Fh
        mov     r3,a
        mov     RDPL,a
        ret

; vpwpair: tile TCH at VOH:VOL and attribute TAT at the next offset.  Even
; offsets: both bytes per page in one go.  Odd ones fall back to vpw, the
; attribute offset being masked to 12 bits or not according to PAIRM.
vpwpair:
        mov     a,VOL
        jb      acc.0,vp_slow
        lcall   vaddr
        lcall   wpair
        mov     a,r3
        orl     a,#80h
        mov     RDPL,a
        lcall   wpair
        inc     RDPH
        mov     RDPL,r3
        lcall   wpair
        mov     a,r3
        orl     a,#80h
        mov     RDPL,a
        lcall   wpair
        mov     dptr,#PTAB
        ret
wpair:  mov     a,TCH
        movx    @dptr,a
        inc     dptr
        mov     a,TAT
        movx    @dptr,a
        ret
vp_slow:
        mov     a,TCH
        lcall   vpw
        mov     a,VOL
        add     a,#1
        mov     VOL,a
        clr     a
        addc    a,VOH
        anl     a,PAIRM
        mov     VOH,a
        mov     a,TAT
        ljmp    vpw

; =============================================================================
; draw_obj: object A (ids 80h-90h)
draw_obj:
        mov     r7,a
        clr     c
        subb    a,#80h
        jc      do_retj
        mov     a,r7
        clr     c
        subb    a,#91h
        jnc     do_retj
        mov     a,r7
        clr     c
        subb    a,#80h
        rl      a
        mov     r6,a
        mov     r7,#01h                 ; 0100h + 2 * (id - 80h)
        lcall   rword                   ; record
        mov     a,r7
        orl     a,r6
        jz      do_retj
        clr     c
        mov     a,r6
        subb    a,#0FBh
        mov     a,r7
        subb    a,#7Fh
        jnc     do_retj                 ; record >= 8000h - 5
        mov     RECH,r7
        mov     RECL,r6
        lcall   rdlog
        mov     WID,a
        mov     a,RECL
        add     a,#1
        mov     r6,a
        clr     a
        addc    a,RECH
        mov     r7,a
        lcall   rword                   ; destination
        mov     a,r7
        anl     a,#0Fh
        mov     RSH,a
        mov     DSH,a
        mov     RSL,r6
        mov     DSL,r6
        mov     a,RECL
        add     a,#3
        mov     r6,a
        clr     a
        addc    a,RECH
        mov     r7,a
        lcall   rword                   ; stream
        mov     a,WID
        jz      do_retj
        clr     c
        subb    a,#21h
        jnc     do_retj                 ; width > 20h
        mov     a,r7
        jb      acc.7,do_retj           ; stream >= 8000h
        lcall   setp
        mov     OATTR,#0
        mov     COLC,#0
        mov     NCH,#0
        mov     NCL,#0
        sjmp    do_loop
do_retj:
        ret
do_loop:
        mov     a,PG
        jz      do_retj                 ; past the end of the ROM
        mov     a,NCH
        cjne    a,#2,do_go
        ret                             ; 512 cells
do_go:  lcall   nextd                   ; A = decrypted byte, F0 = parity
        cjne    a,#5Fh,do_n5f
        mov     a,PG                    ; 5F <attr>
        jz      do_retj
        lcall   nextp
        mov     OATTR,a
        sjmp    do_loop
do_n5f: cjne    a,#5Eh,do_n5e
        ret
do_n5e: cjne    a,#60h,do_t
        ret
do_t:   jnb     F0B,do_even             ; tile = payload transform of the byte
        cpl     a
        add     a,#61h                  ; odd: 60h - v
        sjmp    do_tile
do_even:
        inc     RDPH                    ; even: FTAB[v]
        movc    a,@a+dptr
        dec     RDPH
do_tile:
        mov     TCH,a
        mov     TAT,OATTR
        mov     a,DSH
        anl     a,#0Fh
        mov     VOH,a
        mov     VOL,DSL
        mov     PAIRM,#0FFh             ; destination + 1 is NOT masked (HLE)
        lcall   vpwpair
        inc     NCL
        mov     a,NCL
        jnz     do_n1
        inc     NCH
do_n1:  inc     COLC
        mov     a,COLC
        cjne    a,WID,do_right
        mov     COLC,#0
        mov     a,RSL
        add     a,#80h
        mov     RSL,a
        clr     a
        addc    a,RSH
        mov     RSH,a
        mov     DSH,RSH
        mov     DSL,RSL
        ljmp    do_loop
do_right:
        mov     a,DSL
        add     a,#2
        mov     DSL,a
        clr     a
        addc    a,DSH
        mov     DSH,a
        ljmp    do_loop

; =============================================================================
; HUD status slots
exec_slot:
        mov     RDPH,#08h
        mov     RDPL,SLOT
        movx    a,@dptr
        mov     r4,a                    ; trigger
        inc     dptr
        movx    a,@dptr
        mov     r5,a                    ; p1
        inc     dptr
        movx    a,@dptr
        mov     r6,a                    ; p2
        inc     dptr
        movx    a,@dptr
        mov     r7,a                    ; p3
        mov     dptr,#PTAB
        mov     a,SLOT
        cjne    a,#10h,es_14
        mov     P1S,r5
        mov     P1S+1,r6
        mov     P1S+2,r7
        sjmp    es_done
es_14:  cjne    a,#14h,es_18
        mov     P2S,r5
        mov     P2S+1,r6
        mov     P2S+2,r7
        sjmp    es_done
es_18:  cjne    a,#18h,es_1c
        mov     TOPS,r5
        mov     TOPS+1,r6
        mov     TOPS+2,r7
        sjmp    es_done
es_1c:  cjne    a,#1Ch,es_20
        mov     TIMH,r5
        mov     TIML,r6
        sjmp    es_done
es_20:  cjne    a,#20h,es_24
        mov     FLOORC,r5
        mov     FLOORST,r4
        sjmp    es_done
es_24:  cjne    a,#24h,es_28
        mov     LIVES,r5
        sjmp    es_done
es_28:  cjne    a,#28h,es_2c
        mov     PEN,r5
        sjmp    es_done
es_2c:  mov     BEN,r5
es_done:
        mov     a,SLOT                  ; VALID |= 1 << ((SLOT - 10h) >> 2)
        clr     c
        subb    a,#10h
        rr      a
        rr      a
        mov     r7,a
        mov     a,#1
        cjne    r7,#0,es_sh
        sjmp    es_v
es_sh:  rl      a
        djnz    r7,es_sh
es_v:   orl     VALID,a
        lcall   update_slot
        mov     RDPH,#08h
        mov     RDPL,SLOT
        mov     a,#0FEh
        movx    @dptr,a
        mov     dptr,#PTAB
        ret

update_slot:
        mov     a,INITF
        jnz     us_go
        ret
us_go:  mov     a,SLOT
        cjne    a,#10h,us_14
        mov     r1,#P1S
        mov     XB,#14h
        sjmp    us_score
us_14:  cjne    a,#14h,us_18
        mov     r1,#P2S
        mov     XB,#29h
        sjmp    us_score
us_18:  cjne    a,#18h,us_1c
        mov     r1,#TOPS
        mov     XB,#1Fh
us_score:
        mov     YB,#0
        mov     r7,#3
        ljmp    put_digits
us_1c:  cjne    a,#1Ch,us_20
        mov     r1,#TIMH
        mov     XB,#25h
        mov     YB,#5
        mov     r7,#2
        ljmp    put_digits
us_20:  cjne    a,#20h,us_24
        ljmp    floor_dots
us_24:  cjne    a,#24h,us_28
        mov     XB,#2Dh
        mov     YB,#5
        mov     a,LIVES
        ljmp    write_num
us_28:  cjne    a,#28h,us_2c
        mov     a,PEN
        mov     YB,#2
        mov     BOSSF,#0
        sjmp    lifebar
us_2c:  mov     a,BEN
        mov     YB,#4
        mov     BOSSF,#1
lifebar:                                ; A = energy, drawn only if <= 40h
        mov     EN,a
        clr     c
        subb    a,#41h
        jnc     lb_ret
        mov     XB,#17h
        mov     a,EN
        anl     a,#78h
        rr      a
        rr      a
        rr      a
        mov     FULLSEG,a
        mov     LCNT,#0
lb_loop:
        mov     a,LCNT
        clr     c
        subb    a,FULLSEG
        jc      lb_8
        jnz     lb_0
        mov     a,EN
        anl     a,#7
        sjmp    lb_p
lb_8:   mov     a,#8
        sjmp    lb_p
lb_0:   clr     a
lb_p:   jz      lb_empty
        mov     PART,a
        mov     a,BOSSF
        jnz     lb_b
        mov     a,#0CCh                 ; C4h + 8
        sjmp    lb_s
lb_b:   mov     a,#0D4h                 ; CCh + 8
lb_s:   clr     c
        subb    a,PART
        sjmp    lb_w
lb_empty:
        mov     a,#0C2h
lb_w:   mov     TMPA,a
        mov     a,YB                    ; ((YB * 40h + XB + seg) << 1) & 0FFFh
        mov     RB,#40h
        mul     ab
        add     a,XB
        mov     r6,a
        clr     a
        addc    a,RB
        mov     r7,a
        mov     a,r6
        add     a,LCNT
        mov     r6,a
        clr     a
        addc    a,r7
        mov     r7,a
        lcall   shl_vo
        mov     a,TMPA
        lcall   vpw
        inc     LCNT
        mov     a,LCNT
        cjne    a,#8,lb_loop
lb_ret: ret

; shl_vo: VOH:VOL = (R7:R6 << 1) & 0FFFh
shl_vo: mov     a,r6
        clr     c
        rlc     a
        mov     VOL,a
        mov     a,r7
        rlc     a
        anl     a,#0Fh
        mov     VOH,a
        ret

floor_dots:                             ; lit if i <= floorcount - (state == 2)
        mov     r7,FLOORC
        mov     a,FLOORST
        cjne    a,#2,fd_l
        mov     a,r7
        jz      fd_none
        dec     r7
fd_l:   mov     LIM,r7
        mov     LIMNONE,#0
        sjmp    fd_go
fd_none:
        mov     LIMNONE,#1
fd_go:  mov     LCNT,#0
fd_loop:
        mov     a,LCNT                  ; offset 01C0h + 4i
        rl      a
        rl      a
        add     a,#0C0h
        mov     VOL,a
        mov     VOH,#01h
        mov     r7,#0D6h
        mov     a,LIMNONE
        jnz     fd_w
        mov     a,LIM
        clr     c
        subb    a,LCNT
        jc      fd_w
        mov     r7,#0D5h
fd_w:   mov     a,r7
        lcall   vpw
        inc     LCNT
        mov     a,LCNT
        cjne    a,#8,fd_loop
        ret

; put_digits: R7 bytes of BCD at @R1 -> 2*R7 digits from (XB, YB)
put_digits:
        mov     a,@r1
        swap    a
        lcall   write_num
        mov     a,@r1
        lcall   write_num
        inc     r1
        djnz    r7,put_digits
        ret

; write_num: digit (A & 0Fh) + 30h at (XB, YB); XB++.  Keeps R1, R7.
write_num:
        anl     a,#0Fh
        add     a,#30h
        mov     TMPA,a
        mov     a,YB
        mov     RB,#40h
        mul     ab
        add     a,XB
        mov     VOL,a
        clr     a
        addc    a,RB
        mov     VOH,a
        mov     a,VOL                   ; << 1, & 0FFFh
        clr     c
        rlc     a
        mov     VOL,a
        mov     a,VOH
        rlc     a
        anl     a,#0Fh
        mov     VOH,a
        mov     a,TMPA
        lcall   vpw
        inc     XB
        ret

; =============================================================================
; level background (command 0x02), paced to 20 ms per half column pair
draw_level:
        mov     a,LEVEL
        anl     a,#0Fh
        rl      a
        mov     r6,a
        mov     r7,#02h
        lcall   rword                   ; plaintext directory entry at 0200h
        mov     BLKH,r7
        mov     BLKL,r6
        lcall   pace_start
        mov     PAIR,#0
dl_pair:
        mov     HALF,#0
dl_half:
        lcall   draw_half
        mov     r7,#(PACE_HALF >> 8)
        mov     r6,#(PACE_HALF & 0FFh)
        lcall   pace_wait
        inc     HALF
        mov     a,HALF
        cjne    a,#2,dl_half
        inc     PAIR
        mov     a,PAIR
        cjne    a,#28,dl_pair
        ret

; draw_half: one half (upper 10 rows / lower 16 rows) of column pair PAIR,
; decoded once; cells written straight to the tilemap.  Invalid data: the
; whole half gets the HLE's default cell (tile 05, attribute 19).
draw_half:
        mov     a,HALF
        jnz     dh_lo
        mov     EXPC,#20
        mov     r5,#12                  ; (0 + 6) * 2 = page of row 0
        sjmp    dh_b
dh_lo:  mov     EXPC,#32
        mov     r5,#32                  ; (10 + 6) * 2
dh_b:   mov     a,PAIR
        mov     RB,#16
        mul     ab                      ; PAIR * 16 = column 2*PAIR * 8 bytes
        mov     BASEL,a
        mov     a,RB
        add     a,r5
        add     a,#(TILEMAP >> 8)
        mov     BASEH,a
        clr     c                       ; block >= 153Dh
        mov     a,BLKL
        subb    a,#3Dh
        mov     a,BLKH
        subb    a,#15h
        jc      dh_badj
        mov     a,PAIR                  ; entry = block + (2*PAIR + HALF) * 2
        rl      a
        add     a,HALF
        rl      a
        add     a,BLKL
        mov     r6,a
        clr     a
        addc    a,BLKH
        mov     r7,a
        clr     c                       ; entry < 7FFFh
        mov     a,r6
        subb    a,#0FFh
        mov     a,r7
        subb    a,#7Fh
        jnc     dh_badj
        lcall   setp
        lcall   pword                   ; stream record
        clr     c                       ; 1AEDh <= record < 7FF8h
        mov     a,r6
        subb    a,#0EDh
        mov     a,r7
        subb    a,#1Ah
        jc      dh_badj
        clr     c
        mov     a,r6
        subb    a,#0F8h
        mov     a,r7
        subb    a,#7Fh
        jnc     dh_badj
        mov     RECH,r7
        mov     RECL,r6
        mov     SNUM,#0
        sjmp    dh_s
dh_badj:
        ljmp    dh_bad
dh_s:   mov     a,SNUM
        rl      a
        add     a,RECL
        mov     r6,a
        clr     a
        addc    a,RECH
        mov     r7,a
        lcall   setp
        lcall   pword                   ; stream pointer
        clr     c                       ; 2349h <= pointer < 8000h
        mov     a,r6
        subb    a,#49h
        mov     a,r7
        subb    a,#23h
        jc      dh_badj
        mov     a,r7
        jb      acc.7,dh_badj
        lcall   setp
        mov     a,SNUM                  ; write pointer: BASE + (s>>1)*8 + (s&1)*4
        anl     a,#2
        rl      a
        rl      a
        mov     r5,a
        mov     a,SNUM
        anl     a,#1
        rl      a
        rl      a
        add     a,r5
        add     a,BASEL
        mov     r1,a
        clr     a
        addc    a,BASEH
        mov     WPH,a
        add     a,EXPC                  ; + (EXPC/2 rows) * 2 pages
        mov     WENDH,a
        mov     ATTR,#0
        clr     FULLB
        clr     RIGHTB
dh_c:   mov     a,PG
        jz      dh_end                  ; HLE: while (dataptr < 0x8000 ...)
        lcall   nextp
        jz      dh_end                  ; 00 terminates the stream
        cjne    a,#1,dh_cell
        mov     a,PG                    ; 01 <attr>
        jz      dh_badj                 ; attribute past the end -> invalid
        lcall   nextp
        mov     ATTR,a
        sjmp    dh_c
dh_cell:
        jb      FULLB,dh_badj           ; one cell too many -> invalid
        mov     r4,PG                   ; write tile + attribute at WPH:R1
        mov     PG,WPH
        movx    @r1,a
        inc     r1
        mov     a,ATTR
        movx    @r1,a
        inc     r1
        mov     PG,r4
        cpl     RIGHTB
        jb      RIGHTB,dh_c             ; left cell written, right one next
        mov     a,r1                    ; right cell: back to x0, next row
        clr     c
        subb    a,#4
        mov     r1,a
        mov     a,WPH
        add     a,#2
        mov     WPH,a
        cjne    a,WENDH,dh_c
        setb    FULLB                   ; exactly the expected length so far
        sjmp    dh_c
dh_end: jnb     FULLB,dh_bad            ; stream shorter than expected
        inc     SNUM
        mov     a,SNUM
        cjne    a,#4,dh_sj
        ret
dh_sj:  ljmp    dh_s

dh_bad: mov     a,EXPC                  ; EXPC/2 rows of 16 bytes = 05/19 cells
        rr      a
        mov     ROWS,a
        mov     r5,BASEH
fr_row: mov     RDPH,r5
        mov     RDPL,BASEL
        mov     r4,#8
fr_b:   mov     a,#05h
        movx    @dptr,a
        inc     dptr
        mov     a,#19h
        movx    @dptr,a
        inc     dptr
        djnz    r4,fr_b
        inc     r5
        inc     r5
        djnz    ROWS,fr_row
        mov     dptr,#PTAB
        ret

code_end:
        .org    0E00h
        .inc    tables51.inc
