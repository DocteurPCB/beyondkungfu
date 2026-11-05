; -----------------------------------------------------------------------------
; Beyond Kung-Fu MCU firmware - data ROM access + decryption (6803 assembly)
;
; Behavioural equivalent of decrypt_data() / decode_payload() in the MAME HLE
; (m62_bkungfu_mcu.cpp), built for speed:
;   - km-z.4h is mapped flat at DATA ($6000-$DFFF), no banking;
;   - bytes are read sequentially through PTR; the cipher index of each byte
;     is recomputed from the pointer, (PTRL + PTRH - $60) & $FF, which is
;     cheaper than a counter and correct across page crossings (where the
;     index jumps by 2, not 1);
;   - the cipher + payload transform cost one table read (tables.s) and,
;     for even indexes, a few instructions (ffun).
;
; Variables live in the 6801-family internal RAM ($80-$FF); 16-bit values are
; big-endian so LDX/LDD/STD work on them directly.
; -----------------------------------------------------------------------------

DATA     .EQU $6000      ; km-z.4h, logical $0000-$7FFF
DEND     .EQU $E000      ; DATA + $8000

PTRH     .EQU $80        ; physical read pointer } LDX PTRH
PTRL     .EQU $81        ;                       }
TMP      .EQU $83        ; 2-byte scratch ($83-$84)
WH       .EQU $85        ; 16-bit result } STD WH
WL       .EQU $86        ;               }

        .ORG $F000

; --- setp: D = logical address -> PTR = DATA + D ----------------------------
setp:
        ADDD #DATA
        STD  PTRH
        RTS

; --- nextp: A = payload-decoded byte at PTR; PTR++ ---------------------------
nextp:
        LDAB PTRL               ; B = cipher index = logical lo + logical hi
        ADDB PTRH
        ADDB #$A0               ; - (DATA >> 8)
        LDX  PTRH
        LDAA 0,X                ; cipher byte
        INX
        STX  PTRH
        LDX  #PTAB
        ABX
        BITB #1
        BEQ  np_even
        ADDA 0,X                ; odd index : c + PTAB[i]
        RTS
np_even:
        EORA 0,X                ; even index: F(c ^ PTAB[i])
        BRA  ffun

; --- ffun: A = F(A) = ($A0 if A&$20 else $60) - A - (0 if A&1 else 2) --------
ffun:
        TAB
        NEGA
        ADDA #$60
        BITB #$20
        BEQ  ff_1
        ADDA #$40
ff_1:
        BITB #$01
        BNE  ff_2
        SUBA #$02
ff_2:
        RTS

; --- nextd: A = decrypted byte (no payload transform) at PTR; PTR++ ---------
nextd:
        LDAB PTRL
        ADDB PTRH
        ADDB #$A0
        LDX  PTRH
        LDAA 0,X
        INX
        STX  PTRH
        BITB #1
        BEQ  nd_even
        STAA TMP                ; odd index : $60 - PTAB[i] - c
        LDX  #PTAB
        ABX
        LDAA #$60
        SUBA 0,X
        SUBA TMP
        RTS
nd_even:
        LDX  #PTAB              ; even index: c ^ PTAB[i]
        ABX
        EORA 0,X
        RTS

; --- random access (D = logical address) ------------------------------------
payload_at:
        BSR  setp
        BRA  nextp
decrypt_at:
        BSR  setp
        BRA  nextd

; --- pwordn: D = little-endian payload word at PTR (PTR += 2) ----------------
pwordn:
        BSR  nextp
        STAA WL
        BSR  nextp
        STAA WH
        LDD  WH
        RTS

; --- rword: D = little-endian plaintext word at logical address D -----------
rword:
        ADDD #DATA
        STD  TMP
        LDX  TMP
        LDAA 1,X
        LDAB 0,X
        RTS
