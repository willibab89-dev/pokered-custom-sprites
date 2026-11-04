# Custom front sprite import

Imported all 151 canonical Pokémon front PNGs from
`pokered_front_sprites_import_ready.zip`, staged in `replacements`, using:

```sh
python3 tools/front_sprites.py --import-dir replacements
```

Archive SHA-256:
`204e160d3b9b94caa7c79a561e33b3050456dee91577cfbca79619960981280a`

The imported PNGs match the uploaded files byte-for-byte. No resizing, palette
rewriting, back-picture replacement, or gameplay-code changes were made. The
staging directory is locally excluded from Git; the canonical front PNGs are
the committed source files.

## Import and capacity results

- Exactly 151 valid canonical filenames; no missing or unknown Pokémon.
- Dimensions: 38 pictures at 40×40, 28 at 48×48, and 85 at 56×56.
- 57 pictures change dimensions relative to their original artwork. Existing
  base-stat dimension includes read the new dimensions automatically.
- All PNG palette conversions and compression/decompression round trips pass.
- Compressed fronts total 56,468 bytes in both games, 424 bytes above the
  original 56,044 bytes. Individual sizes range from 131 bytes (Kabuto) to
  604 bytes (Golem).
- Both Red and Blue pass all 151 linked-data, bank, pointer, dimension, and
  bank-boundary checks. Front pictures occupy 11 banks.
- Both ROMs remain 1,048,576 bytes, with the original MBC3 configuration and
  ROM-size header. Allocated ROMX banks retain 161,275 free bytes; banks above
  the current highest allocated bank `$2c`, through `$3f`, remain available.
- No palette, compression, pointer, or ROM-space errors remain.

## Regression results

The routine-level emulator suite passes 305 cases per game: 151 fronts,
151 backs, and three fossil/ghost pictures. Decompressed data matches the C
decompressor; stack and software/hardware ROM-bank restoration pass.

The pre-import preservation check confirms all gameplay fields and all 151
compressed back pictures remain identical. This check now treats front
dimensions as replaceable artwork metadata and verifies them against the new
compressed picture header; statistics, types, experience, moves, growth rates,
and TM/HM fields must still match the baseline exactly.

The visual suite passes 36 captures across Red/Blue, wild/trainer/Pokédex
screens, current Bulbasaur/Nidorino/Venusaur art, and separate 40/48/56-pixel
diagnostic pictures forced to bank `$3f`. Current art is measured at its actual
dimensions; Nidorino is now 56×56 rather than the original 48×48. Full front
buffer pixels, mirroring, and unchanged Rhydon back-picture crops pass.

Reproduce the tests after building:

```sh
python tools/test_front_sprites.py
python tools/test_sprite_rendering.py --output /tmp/custom-sprite-rendering
```

The optional test environment needs `pyboy==2.6.1` and `Pillow==11.3.0`.
For preservation testing, pass `--baseline /path/to/pre-import-build` to
`test_front_sprites.py`; that directory must contain pristine `.gbc` and `.sym`
files for both versions.

Visual coverage is representative, not every imported species in every game
screen. Battle turns/animations, status screens, owned Pokédex description
pagination, and SGB palettes remain outside the visual suite. See
[the sprite workflow](front-sprites.md) for alignment and test details.
