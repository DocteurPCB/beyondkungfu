; -----------------------------------------------------------------------------
; Beyond Kung-Fu MCU firmware - level background drawing (6803 assembly)
;
; draw_level: whole-background draw of command 0x02, behaviourally equivalent
; to the HLE's 56 x 26 calls of draw_level_strip() (same final tilemap).
;
; The HLE re-decodes the four tile streams for every strip (1456 times per
; level).  Here each half of each column pair (upper 10 rows / lower 16 rows)
; is decoded ONCE, by the hot loop in drawloop.s, and every cell is written
; straight to its tilemap address:
;   stream s, cell n  ->  column 2*PAIR + (s >> 1)
;                         tile x  (s & 1) * 2 + (n & 1)
;                         row     row0 + n / 2
; Validation is the HLE's: all four streams must have the expected length
; (20 upper, 32 lower) and every pointer must be in range.  When it fails, the
; whole half is filled with the HLE's default cell (tile 05, attribute 19),
; which is exactly what the HLE leaves there.
; Only the order in which cells appear on screen differs from the HLE.
;
; Input: LEVEL = level-table slot (low nibble).
; -----------------------------------------------------------------------------

TILEMAP  .EQU $2000      ; tilemap RAM base in the MCU address space
PACE_HALF .EQU 17898     ; E-clock ticks per half column pair: 56 x 20 ms =
                         ; 1.12 s per level (PCB), at E = 3.579545 MHz / 4

LEVEL    .EQU $87
PAIR     .EQU $88        ; column pair 0..27
HALF     .EQU $89        ; 0 = upper rows 0-9, 1 = lower rows 10-25
EXPC     .EQU $8A        ; expected cells per stream: 20 / 32
SNUM     .EQU $8B        ; stream 0..3
ATTR     .EQU $8D        ; current attribute
ROWS     .EQU $8F
BLKH     .EQU $90        ; level block pointer (logical)   } LDX BLKH
BLKL     .EQU $91
RECH     .EQU $92        ; stream-record pointer (logical) } LDX RECH
RECL     .EQU $93
WPH      .EQU $94        ; tilemap write pointer           } LDX WPH
WPL      .EQU $95
BASEH    .EQU $96        ; tilemap address of the half's top-left cell
BASEL    .EQU $97
XPBH     .EQU $D0        ; next page boundary of the data pointer } CPX XPBH
XPBL     .EQU $D1
XSH      .EQU $D2        ; X saved while writing a cell
XSL      .EQU $D3
SAVSPH   .EQU $D4        ; real stack pointer while SP walks PTAB
SAVSPL   .EQU $D5
SPTH     .EQU $D6        ; scratch for SP arithmetic
SPTL     .EQU $D7
WENDH    .EQU $D8        ; high byte of the write pointer after the last row
STMP     .EQU $D9
IFIRST   .EQU $DA
PTABH    .EQU $FB        ; PTAB is page aligned at $FB00 (checked by build.py)

draw_level:
        LDAB LEVEL
        ANDB #$0F
        ASLB
        CLRA
        ADDD #$0200
        JSR  rword              ; plaintext level directory entry
        STD  BLKH
        JSR  pace_start
        CLR  PAIR
dl_pair:
        CLR  HALF
dl_half:
        BSR  draw_half
        LDD  #PACE_HALF         ; hardware-like pace: see docs/SPEC.md
        JSR  pace_wait
        INC  HALF
        LDAA HALF
        CMPA #2
        BCS  dl_half
        INC  PAIR
        LDAA PAIR
        CMPA #28
        BCS  dl_pair
        RTS

draw_half:
; --- expected length and top-left tilemap address ----------------------------
        LDAA #20
        LDAB #12                ; (0 + 6) * 2 = high byte of row 0's address
        TST  HALF
        BEQ  dh_up
        LDAA #32
        LDAB #32                ; (10 + 6) * 2
dh_up:
        STAA EXPC
        PSHB
        LDAA PAIR
        LDAB #16
        MUL                     ; PAIR * 16 = column 2*PAIR * 8 bytes
        STD  TMP
        PULA
        CLRB
        ADDD TMP
        ADDD #TILEMAP
        STD  BASEH
; --- level block -> entry -> stream record ----------------------------------
        LDX  BLKH
        CPX  #$153D
        LBCS dh_bad
        LDAB PAIR
        ASLB
        ADDB HALF               ; source entry
        ASLB
        ABX
        CPX  #$7FFF
        LBCC dh_bad
        STX  TMP
        LDD  TMP
        JSR  setp
        JSR  pwordn
        STD  RECH
        LDX  RECH
        CPX  #$1AED
        LBCS dh_bad
        CPX  #$7FF8
        LBCC dh_bad
; --- the four tile streams ----------------------------------------------------
        CLR  SNUM
dh_s:
        LDX  RECH
        LDAB SNUM
        ASLB
        ABX
        STX  TMP
        LDD  TMP
        JSR  setp
        JSR  pwordn             ; D = stream pointer (logical)
        STD  TMP
        LDX  TMP
        CPX  #$2349
        LBCS dh_bad
        CPX  #$8000
        LBCC dh_bad
        JSR  setp               ; PTR = physical start of the stream
        LDAB SNUM               ; write pointer = BASE + (s>>1)*8 + (s&1)*4
        ANDB #1
        ASLB
        ASLB
        LDAA SNUM
        ANDA #2
        ASLA
        ASLA
        ABA
        TAB
        LDX  BASEH
        ABX
        STX  WPH
        CLR  ATTR
        LDAA WPH                ; row after the last one: + (EXPC / 2) * 512
        ADDA EXPC
        STAA WENDH
        LDAA PTRH               ; next page boundary of the data pointer
        INCA
        CLRB
        STD  XPBH
        LDAB PTRL               ; cipher index of the first byte
        ADDB PTRH
        ADDB #$A0
        STAB IFIRST
        CLRA
        ADDD #PTAB-1            ; SP = PTAB - 1 + index: PULB gets PTAB[index]
        STD  SPTH
        LDX  PTRH
        STS  SAVSPH
        LDS  SPTH
        LDAB IFIRST
        BITB #1
        LBNE S10
        JMP  S00

; --- exits of the hot loop (drawloop.s) ----------------------------------------
dl_end:                         ; stream had exactly EXPC cells
        LDS  SAVSPH
        INC  SNUM
        LDAA SNUM
        CMPA #4
        LBCS dh_s
        RTS                     ; all four streams valid
dl_bad:
        LDS  SAVSPH
; --- invalid data: the HLE leaves its default cell everywhere in this half ----
dh_bad:
        LDX  BASEH
        LDAB EXPC
        LSRB
        STAB ROWS               ; 10 or 16 rows
fill_row:
        LDAA #$05
        LDAB #$19
        STAA 0,X
        STAB 1,X
        STAA 2,X
        STAB 3,X
        STAA 4,X
        STAB 5,X
        STAA 6,X
        STAB 7,X
        STAA 8,X
        STAB 9,X
        STAA 10,X
        STAB 11,X
        STAA 12,X
        STAB 13,X
        STAA 14,X
        STAB 15,X
        STX  TMP
        LDD  TMP
        ADDD #512
        STD  TMP
        LDX  TMP
        DEC  ROWS
        BNE  fill_row
        RTS
