; -----------------------------------------------------------------------------
; Beyond Kung-Fu MCU firmware - level background drawing (6803 assembly)
;
; draw_level: whole-background draw of command 0x02, behaviourally equivalent
; to the HLE's 56 x 26 calls of draw_level_strip() (same final tilemap).
;
; The HLE re-decodes the four tile streams for every strip (1456 times per
; level).  Here each half of each column pair (upper 10 rows / lower 16 rows)
; is decoded ONCE and every cell is written straight to its tilemap address:
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

LEVEL    .EQU $87
PAIR     .EQU $88        ; column pair 0..27
HALF     .EQU $89        ; 0 = upper rows 0-9, 1 = lower rows 10-25
EXPC     .EQU $8A        ; expected cells per stream: 20 / 32
SNUM     .EQU $8B        ; stream 0..3
NCELL    .EQU $8C        ; cells seen in the current stream
ATTR     .EQU $8D        ; current attribute
CNT      .EQU $8E        ; cell count of stream 0
ROWS     .EQU $8F
BLKH     .EQU $90        ; level block pointer (logical)   } LDX BLKH
BLKL     .EQU $91
RECH     .EQU $92        ; stream-record pointer (logical) } LDX RECH
RECL     .EQU $93
WPH      .EQU $94        ; tilemap write pointer           } LDX WPH
WPL      .EQU $95
BASEH    .EQU $96        ; tilemap address of the half's top-left cell
BASEL    .EQU $97

draw_level:
        LDAB LEVEL
        ANDB #$0F
        ASLB
        CLRA
        ADDD #$0200
        JSR  rword              ; plaintext level directory entry
        STD  BLKH
        CLR  PAIR
dl_pair:
        CLR  HALF
dl_half:
        BSR  draw_half
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
        JSR  setp
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
        CLR  NCELL
dh_c:
; --- hot loop: fetch + decrypt + payload transform, inlined ------------------
        LDX  PTRH
        CPX  #DEND
        BCC  dh_end             ; HLE: while (dataptr < 0x8000 ...)
        LDAB PTRL
        ADDB PTRH
        ADDB #$A0               ; B = cipher index of this byte
        LDAA 0,X                ; cipher byte
        INX
        STX  PTRH
        LDX  #PTAB
        ABX
        BITB #1
        BEQ  c_even
        ADDA 0,X                ; odd index : c + PTAB[i]
        CMPA #$01
        BHI  c_cell
        BRA  c_tok
c_even:
        EORA 0,X                ; even index: FTAB[c ^ PTAB[i]]
        TAB
        LDX  #FTAB
        ABX
        LDAA 0,X
        CMPA #$01
        BLS  c_tok
; --- tile cell ---------------------------------------------------------------
c_cell:
        LDAB NCELL
        CMPB EXPC
        BCC  c_over             ; beyond this half: counted, not drawn
        LDX  WPH
        STAA 0,X
        LDAA ATTR
        STAA 1,X
        INCB
        STAB NCELL
        BITB #1
        BEQ  c_down
        INX                     ; even cell -> odd cell, 1 tile right
        INX
        STX  WPH
        BRA  dh_c
c_down:
        LDAB #255               ; odd cell -> next tile row, back to x0:
        ABX                     ; + 510 bytes
        LDAB #255
        ABX
        STX  WPH
        BRA  dh_c
c_over:
        INCB                    ; only reachable past the expected length,
        STAB NCELL              ; where the HLE's 64-cell cap can matter
        CMPB #64
        BCS  dh_c
        BRA  dh_end
; --- tokens 00 (end) and 01 <attr> ------------------------------------------
c_tok:
        TSTA
        BEQ  dh_end
        LDX  PTRH
        CPX  #DEND
        LBCC dh_bad             ; HLE: attribute byte past the end -> invalid
        JSR  nextp
        STAA ATTR
        LBRA dh_c
dh_end:
        LDAA NCELL
        TST  SNUM
        BNE  dh_cmp
        STAA CNT
        BRA  dh_next
dh_cmp:
        CMPA CNT
        BNE  dh_bad             ; streams of different length
dh_next:
        INC  SNUM
        LDAA SNUM
        CMPA #4
        LBCS dh_s
        LDAA CNT
        CMPA EXPC
        BNE  dh_bad
        RTS
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
