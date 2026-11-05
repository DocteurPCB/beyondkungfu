; -----------------------------------------------------------------------------
; Beyond Kung-Fu MCU firmware - data ROM access + decryption (6803 assembly)
;
; Reimplements, in real 6803 code, the address-local cipher and payload
; transform that the MAME HLE (m62_bkungfu_mcu.cpp) performs in C++.
; Reference: decrypt_data() and decode_payload() in that file.
;
; Calling convention: logical data-ROM address (0x0000..0x7FFF) in DAL/DAH.
;   read_data      -> A = raw byte from km-z.4h (0xFF above 0x7FFF)
;   decrypt        -> A = decrypted byte
;   decode_payload -> A = payload-decoded byte
; -----------------------------------------------------------------------------

BANK_REG .EQU $20        ; data-ROM window bank latch (bit0)
DAL      .EQU $40        ; logical data address, low
DAH      .EQU $41        ; logical data address, high
XH       .EQU $42        ; scratch: window physical addr, high
XL       .EQU $43        ; scratch: window physical addr, low
CIPH     .EQU $44        ; cipher (raw) byte
IDX      .EQU $45        ; index = (DAL + DAH) & 0xFF
VAL      .EQU $46        ; decrypted value (for payload transform)

        .ORG $F000

; --- read_data: A = km-z.4h[DA], banked 16K window at $8000 ------------------
read_data:
        LDAA DAH
        CMPA #$80
        BCC  rd_ff              ; DA >= 0x8000 -> 0xFF
        LDAA DAH
        ANDA #$40               ; bit14 selects the 16K half
        BEQ  rd_b0
        LDAA #$01
        STAA BANK_REG
        BRA  rd_addr
rd_b0:
        CLRA
        STAA BANK_REG
rd_addr:
        LDAA DAH
        ANDA #$3F               ; offset within 16K half
        ADDA #$80               ; -> high byte of $8000 + offset
        STAA XH
        LDAA DAL
        STAA XL
        LDX  XH
        LDAA 0,X
        RTS
rd_ff:
        LDAA #$FF
        RTS

; --- decrypt: A = decrypted byte at DA --------------------------------------
decrypt:
        LDAA DAL
        ADDA DAH
        STAA IDX                ; index
        JSR  read_data
        STAA CIPH               ; cipher
        LDAA IDX
        BITA #$01
        BEQ  dec_even
; odd: (index ^ (index&2 ? 0x7e : 0x12)) - 0x20 - cipher
        LDAA IDX
        BITA #$02
        BEQ  dec_odd12
        LDAA IDX
        EORA #$7E
        BRA  dec_odd_sub
dec_odd12:
        LDAA IDX
        EORA #$12
dec_odd_sub:
        SUBA #$20
        SUBA CIPH
        RTS
; even: cipher ^ index ^ (index&2 ? 0x5e : 0xae)
dec_even:
        LDAA IDX
        BITA #$02
        BEQ  dec_even_ae
        LDAA CIPH
        EORA IDX
        EORA #$5E
        RTS
dec_even_ae:
        LDAA CIPH
        EORA IDX
        EORA #$AE
        RTS

; --- decode_payload: A = payload-decoded byte at DA -------------------------
decode_payload:
        JSR  decrypt
        STAA VAL
        LDAA DAL
        ADDA DAH
        BITA #$01
        BEQ  dp_even
; odd: 0x60 - value
        LDAA #$60
        SUBA VAL
        RTS
dp_even:
        LDAA VAL
        BITA #$20
        BEQ  dp_base60
        LDAA #$A0
        BRA  dp_sub
dp_base60:
        LDAA #$60
dp_sub:
        SUBA VAL                ; A = base - value
        LDAB VAL
        BITB #$01
        BNE  dp_done            ; value odd -> subtract 0
        SUBA #$02               ; value even -> subtract 2
dp_done:
        RTS
