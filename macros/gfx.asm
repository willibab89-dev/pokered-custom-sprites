MACRO? RGB
	REPT _NARG / 3
		dw palred (\1) + palgreen (\2) + palblue (\3)
		SHIFT 3
	ENDR
ENDM

DEF palred   EQUS "(1 << B_COLOR_RED) *"
DEF palgreen EQUS "(1 << B_COLOR_GREEN) *"
DEF palblue  EQUS "(1 << B_COLOR_BLUE) *"

DEF palettes EQUS "* PAL_SIZE"
DEF palette  EQUS "+ PAL_SIZE *"
DEF color    EQUS "+ PAL_COLORS *"

DEF tiles EQUS "* TILE_SIZE"
DEF tile  EQUS "+ TILE_SIZE *"

MACRO? dbsprite
; x tile, y tile, x pixel, y pixel, vtile offset, attributes
	db (\2 * TILE_WIDTH) % $100 + \4, (\1 * TILE_WIDTH) % $100 + \3, \5, \6
ENDM

; Open an indivisible, freely placed ROMX section; caller must POPS.
; Keep INCBIN literal at the call site so scan_includes tracks dependencies.
; Back pictures remain in their original sections and use the legacy bank lookup.
MACRO mon_frontpic
	PUSHS
	SECTION "Front sprite \1", ROMX
\1::
	ASSERT BANK(\1) < $40, "Front sprites exceed the original 1 MiB ROM"
ENDM
