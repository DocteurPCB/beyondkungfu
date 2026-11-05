; -----------------------------------------------------------------------------
; Beyond Kung-Fu MCU firmware - level background drawing (6803 assembly)
;
; Behavioural equivalent of draw_level_strip() / draw_level_column_row() in the
; MAME HLE.  One call draws one (column, row) cell group: 4 tiles wide, at
;   tilemap offset ((ROW + 6) * 256 + COL * 4) * 2   (tile byte, attribute byte)
;
; The HLE buffers all four decoded streams (512 bytes).  The 6801 only has 128
; bytes of internal RAM, so instead we walk the four streams once, check that
; they all have the expected length, and capture just the four cells we need.
;
; Inputs : COL (0..55), ROW (0..25), LEVEL (table slot, low nibble used)
; Output : 8 bytes written to tilemap RAM ($2000 + offset)
; -----------------------------------------------------------------------------

TILEMAP  .EQU $2000      ; tilemap RAM base in the MCU address space

COL      .EQU $89
ROW      .EQU $8A
LEVEL    .EQU $8B
TMH      .EQU $8C        ; tilemap address, high } LDX TMH
TML      .EQU $8D        ;                  low  }
SE       .EQU $8E        ; source entry  (column pair + upper/lower half)
SR       .EQU $8F        ; source row inside the column pair
EXPC     .EQU $90        ; expected cells per stream (20 upper, 32 lower)
HALF     .EQU $91        ; EXPC / 2
BAND     .EQU $92        ; which stream pair (0: streams 0-1, 1: streams 2-3)
BR2      .EQU $93        ; first wanted cell index in the stream (bandrow*2)
CNT      .EQU $94        ; cell count of stream 0
SNUM     .EQU $95        ; current stream 0..3
NCELL    .EQU $96        ; cells seen so far in the current stream
ATTR     .EQU $97        ; current attribute
VTILE    .EQU $98        ; current tile code
KTMP     .EQU $99
RECH     .EQU $9A        ; stream record pointer } LDX RECH
RECL     .EQU $9B        ;                       }
BLKH     .EQU $9C        ; level block pointer   } LDX BLKH
BLKL     .EQU $9D        ;                       }
CAP      .EQU $A0        ; CAP+0..3 = 4 tiles, CAP+4..7 = 4 attributes

draw_level_strip:
; --- destination: TILEMAP + (ROW+6)*512 + COL*8 -----------------------------
        LDAA ROW
        ADDA #6
        ASLA                    ; (ROW+6)*2 = high byte of (ROW+6)*512
        CLRB
        STD  TMH
        LDAA COL
        LDAB #8
        MUL                     ; D = COL*8
        ADDD TMH
        ADDD #TILEMAP
        STD  TMH
; --- default cells: tile 05, attribute 19 (drawn even if the data is bad) ----
        LDX  TMH
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
; --- source entry / source row / expected length ----------------------------
        LDAA COL
        ANDA #$FE
        STAA SE
        LDAA ROW
        CMPA #10
        BCS  upper
        INC  SE                 ; lower 16 rows use the odd entry
        SUBA #10
        LDAB COL
        BITB #1
        BEQ  lo_even
        ADDA #16
lo_even:
        STAA SR
        LDAA #32
        STAA EXPC
        LDAA #16
        STAA HALF
        BRA  bandcalc
upper:
        LDAB COL
        BITB #1
        BEQ  up_even
        ADDA #10
up_even:
        STAA SR
        LDAA #20
        STAA EXPC
        LDAA #10
        STAA HALF
bandcalc:
        CLR  BAND
        LDAA SR
        CMPA HALF
        BCS  band0
        SUBA HALF
        INC  BAND
band0:
        ASLA
        STAA BR2                ; bandrow * 2
; --- level block pointer: plaintext word at $0200 + slot*2 ------------------
        LDAA LEVEL
        ANDA #$0F
        ASLA
        STAA DAL
        LDAA #$02
        STAA DAH
        JSR  read_data
        STAA BLKL
        LDX  DAH
        INX
        STX  DAH
        JSR  read_data
        STAA BLKH
        LDX  BLKH
        CPX  #$153D
        LBCS dls_done           ; block in plaintext area -> invalid
; --- entry = block + SE*2, record = pword(entry) ----------------------------
        LDAB SE
        ASLB
        ABX
        CPX  #$7FFF
        LBCC dls_done
        STX  DAH
        JSR  pword
        LDX  WH
        CPX  #$1AED
        LBCS dls_done
        CPX  #$7FF8
        LBCC dls_done
        STX  RECH
; --- walk the four tile streams ---------------------------------------------
        CLR  SNUM
s_loop:
        LDX  RECH
        LDAB SNUM
        ASLB
        ABX
        STX  DAH
        JSR  pword              ; stream pointer
        LDX  WH
        CPX  #$2349
        LBCS dls_done
        CPX  #$8000
        LBCC dls_done
        STX  DAH                ; DAH/DAL is now the stream read pointer
        CLR  ATTR
        CLR  NCELL
c_loop:
        LDAA NCELL
        CMPA #64
        LBCC c_end
        LDX  DAH
        CPX  #$8000
        LBCC c_end
        JSR  decode_payload
        LDX  DAH
        INX
        STX  DAH
        TSTA
        LBEQ c_end              ; 00 terminates the stream
        CMPA #$01
        BNE  c_cell
        CPX  #$8000             ; 01 <attr>
        LBCC dls_done
        JSR  decode_payload
        STAA ATTR
        LDX  DAH
        INX
        STX  DAH
        LBRA c_loop
c_cell:
        STAA VTILE
        LDAB SNUM               ; only streams BAND*2 and BAND*2+1 matter
        LSRB
        CMPB BAND
        BNE  c_next
        LDAB NCELL              ; ... and only cells BR2 and BR2+1
        SUBB BR2
        BCS  c_next
        CMPB #2
        BCC  c_next
        STAB KTMP               ; slot = (SNUM & 1) * 2 + (NCELL - BR2)
        LDAB SNUM
        ANDB #1
        ASLB
        ADDB KTMP
        LDX  #CAP
        ABX
        LDAA VTILE
        STAA 0,X
        LDAA ATTR
        STAA 4,X
c_next:
        INC  NCELL
        LBRA c_loop
c_end:
        LDAA SNUM
        BNE  c_cmp
        LDAA NCELL
        STAA CNT
        BRA  s_next
c_cmp:
        LDAA NCELL
        CMPA CNT
        LBNE dls_done           ; streams of different length -> invalid
s_next:
        INC  SNUM
        LDAA SNUM
        CMPA #4
        LBCS s_loop
; --- all four streams agree: check length, then write the 4 cells ------------
        LDAA CNT
        CMPA EXPC
        BNE  dls_done
        LDX  TMH
        LDAA CAP+0
        STAA 0,X
        LDAA CAP+4
        STAA 1,X
        LDAA CAP+1
        STAA 2,X
        LDAA CAP+5
        STAA 3,X
        LDAA CAP+2
        STAA 4,X
        LDAA CAP+6
        STAA 5,X
        LDAA CAP+3
        STAA 6,X
        LDAA CAP+7
        STAA 7,X
dls_done:
        RTS
