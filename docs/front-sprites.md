# Front sprite replacement

All 151 front pictures can be replaced independently. No custom artwork is
included in this change. Back pictures, trainers, fossils, ghost graphics,
statistics, moves, maps, and gameplay source are retained.

## Build and import

Use RGBDS **1.0.4**, Python 3, GCC, and make (see INSTALL.md). In the cloud
environment the RGBDS binaries are in `/workspace/.toolchains/rgbds-1.0.4`.
From the checkout:

```sh
python3 tools/front_sprites.py --rgbds /workspace/.toolchains/rgbds-1.0.4
```

This builds Red and Blue, lists each front picture's compressed byte count and
linked bank/address, checks every header's pointer/bank/dimension byte against
the linked picture, and prints free space in the map's allocated banks. Empty,
unallocated banks below `$40` are also available to the linker. If RGBDS is on
PATH, omit `--rgbds`.

For future artwork, prepare a directory containing any subset of the 151 PNGs,
named exactly like `gfx/pokemon/front/*.png` (for example `bulbasaur.png`,
`nidoranf.png`, or `mr.mime.png`). Fossil PNGs are excluded. Then run:

```sh
python3 tools/front_sprites.py --import-dir /path/to/replacements
```

Images must be square, 8–56 pixels per side in multiples of eight, with colors
accepted by `rgbgfx --colors dmg` (the original four grayscale colors). The
56-pixel limit protects the game's 7×7-tile buffers. The existing compressor
supports square images only. Transparent pixels follow RGBDS's existing palette
conversion rules; use opaque artwork for predictable results.

Before copying anything, the importer validates every filename and dimension,
converts each PNG with RGBDS, compresses it with `tools/pkmncompress`, checks a
decompression round trip, and reports its compressed size. It then copies the
PNGs into the existing source paths, invalidates their generated `.2bpp`/`.pic`
files, and builds both games. No back PNGs are touched. Dimensions are already
read from the compressed file by the base-stat includes; no manual stat edit is
needed. Commit PNG source files, not ignored generated graphics or ROMs.

A failed link exits nonzero. Imported PNGs remain available for correction;
the command does not roll back user artwork. Do not distribute an older ROM
left from a failed build. Fix the reported input or capacity issue and rerun.

## Allocation and loading

The old loader inferred a shared front/back bank from ranges of **internal
species IDs**, with exceptions for Mew and fossil Kabutops. That made a growing
front picture overflow its fixed `Pics 1`–`Pics 5` group even when other banks
had space. Pictures are compressed streams which must fit entirely in one
16 KiB bank; the decompressor does not switch banks within a stream.

The [pret wiki's Improve the Pokemon picture system article](https://github.com/pret/pokered/wiki/Improve-the-Pokemon-picture-system)
stores a bank byte in the unused final byte of each 28-byte base-stat record.
Its approach fits this version, but assumes front and back pictures share a
bank and groups fossil/ghost pictures together. This implementation adapts the
bank-byte idea **for front pictures only**:

- `mon_frontpic` gives each front an independent floating ROMX section. RGBDS
  packs these indivisible sections into available holes after placing the
  sections constrained by `layout.link`. No hand-maintained bank list or custom
  packing algorithm is needed.
- `dw ...PicFront` remains the address pointer; `BANK(...PicFront)` in the last
  base-stat byte supplies the matching linked bank. Record lengths, gameplay
  fields, WRAM addresses, and the original decompression format remain unchanged.
- `UncompressMonSprite` selects the new bank byte only for ordinary fronts.
  Backs retain the legacy species-range bank selection. Mew's back explicitly
  uses `BANK(MewPicBack)`, independently of its relocated front.
- Fossil Kabutops, fossil Aerodactyl, and ghost bypass the new byte, because their
  special headers do not populate it. Their old data locations and lookup
  behavior are retained. Trainer picture loading is unchanged.

Every front section asserts `BANK(label) < $40`. The mapper remains MBC3 and
`rgbfix` retains the 1 MiB size header. Stock art totals **56,044 compressed
front bytes** in each version; moving it leaves substantial room elsewhere in
the original 64-bank image. Expansion is unnecessary for this infrastructure.
The linker can use spare banks up to `$3f` automatically. If a future workload
cannot fit, the link fails explicitly instead of silently producing a larger
ROM. Review sizes/free space and image complexity first. Supporting expansion
would be a separate mapper/capacity decision; removing the guard alone is not
an endorsed expansion workflow. No finite ROM can accommodate arbitrary input.

## Regression tests

The optional emulator tests require PyBoy:

```sh
python3 -m venv /tmp/sprite-tests
/tmp/sprite-tests/bin/pip install pyboy==2.6.1
/tmp/sprite-tests/bin/python tools/test_front_sprites.py
```

Build first with `tools/front_sprites.py`. The tests execute the ROM's actual
`GetMonHeader` and `UncompressMonSprite` routines under PyBoy for all 151 fronts,
all 151 backs, and the three special pictures, in both Red and Blue. They compare
both decompressed SRAM planes against the C decompressor and check stack and
software/hardware bank restoration. They run headlessly with LCD/interrupts off;
they do **not** exercise the VRAM upload, alignment, flipped rendering, or a full
battle/Pokédex/status-screen playthrough. Invalid/glitch species are outside the
supported set.

For an additional preservation check, save pristine `.gbc` and `.sym` files
before making changes, then supply their directory:

```sh
/tmp/sprite-tests/bin/python tools/test_front_sprites.py --baseline /path/to/pristine-build
```

This checks all original gameplay fields (excluding relocated pointers and the
repurposed padding byte) and all compressed back pictures against that build.
The baseline check also expects the original front dimensions.

Implementation validation used stock artwork: original ROM hashes matched;
all 151 PNGs passed batch import/round-trip and linked-data checks; Red, Blue,
and Blue debug built; the emulator suite and baseline preservation checks
passed. A temporary test forced Bulbasaur's front to bank `$3f` and reran the
Red/Blue emulator suite successfully; a forced bank `$40` failed the size guard.
Those temporary placement edits were removed and the normal build restored.
