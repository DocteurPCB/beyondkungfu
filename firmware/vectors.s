; -----------------------------------------------------------------------------
; 6801-family vectors at the top of the internal ROM.  The firmware polls the
; mailbox latches and never enables interrupts, so every vector points at
; reset.
; -----------------------------------------------------------------------------
        .ORG $FFF0
        .WORD reset, reset, reset, reset    ; SCI, timer overflow, OCF, ICF
        .WORD reset, reset, reset, reset    ; IRQ1, SWI, NMI, RESET
