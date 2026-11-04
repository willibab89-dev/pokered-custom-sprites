# Custom front sprites: BPS patches for Windows

The patch package contains two BPS patches for the 151 custom Pokémon front
sprites, with original back sprites and existing gameplay. Both patched ROMs
remain 1 MiB. Complete ROMs are not included in the downloadable artifact.

## Required original ROMs

Supply your own verified, unmodified English **USA/Europe** ROMs. These are the
Game Boy releases commonly named `Pokemon Red Version (USA, Europe) (SGB
Enhanced)` and `Pokemon Blue Version (USA, Europe) (SGB Enhanced)`, also listed
by this disassembly as `Pokemon Red (UE) [S][!]` and `Pokemon Blue (UE) [S][!]`.

Each input must be exactly **1,048,576 bytes**, without an added copier header.
The filename extension (`.gb` or `.gbc`) does not affect compatibility. Use the
Red patch only on Red and the Blue patch only on Blue. Japanese, other-language,
Virtual Console-modified, previously patched, or otherwise altered ROMs are not
supported unless their bytes match these hashes exactly.

| Original | SHA-1 | CRC32 |
| --- | --- | --- |
| Pokémon Red | `ea9bcae617fdf159b045185467ae58b2e4a48b9a` | `9F7FDD53` |
| Pokémon Blue | `d7037c83e1ae5b39bde3c30787637ba1d4c48ce2` | `D6DA8A1A` |

SHA-256 checksums:

```text
Red:  5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b
Blue: 2a951313c2640e8c2cb21f25d1db019ae6245d9c7121f754fa61afd7bee6452d
```

In Windows PowerShell, check your original before patching:

```powershell
Get-FileHash -LiteralPath 'C:\Games\Pokemon Red.gb' -Algorithm SHA1
Get-FileHash -LiteralPath 'C:\Games\Pokemon Blue.gb' -Algorithm SHA1
```

Compare the result with the table. Hashes are case-insensitive. Stop if it does
not match; do not force a patch or disable checksum validation.

## Download and apply on Windows

1. In the repository's **Actions** tab, open a successful **BPS patches** run.
   Under **Artifacts**, download **pokemon-custom-fronts-bps**. GitHub downloads
   it as a ZIP. You may need to sign in to GitHub to download artifacts.
2. Extract the entire ZIP using Windows **Extract All**. It contains
   `pokered-custom-fronts.bps`, `pokeblue-custom-fronts.bps`, this guide,
   `manifest.json`, and `SHA256SUMS.txt`.
3. Download the Windows version of **Floating IPS (Flips)** from its
   [official releases](https://github.com/Alcaro/Flips/releases) and extract it.
   Use a BPS-compatible patcher; Lunar IPS does not apply BPS files.
4. Open `flips.exe`, choose **Apply Patch**, and select the Red or Blue `.bps`.
   Select the matching original ROM whose SHA-1 you checked above.
5. Save to a **new** filename, such as `Pokemon Red - Custom Fronts.gbc` or
   `Pokemon Blue - Custom Fronts.gbc`. Keep the original ROM unchanged.
6. Open the patched file in your preferred Game Boy emulator. Optionally verify
   its SHA-256 with `Get-FileHash -Algorithm SHA256` and compare it to the
   corresponding `target.sha256` in `manifest.json`. The patched file must
   still be 1,048,576 bytes.

Flips checks the BPS input/output CRCs. If it reports that a patch is not intended
for the ROM, confirm the game and original hashes. Red and Blue patches are not
interchangeable. `SHA256SUMS.txt` verifies package contents; `manifest.json`
records input, output, and patch hashes for this particular build.

## How the patch workflow works

`.github/workflows/bps-patches.yml` runs on pull requests, pushes to `master`,
and manual dispatch. Before the workflow exists on the default branch, use its
pull-request run; the manual **Run workflow** button becomes available after
the workflow is merged into the default branch. Artifacts expire after 30 days;
run the workflow again to produce a fresh package.

The runner reconstructs the original Red/Blue ROMs from the pinned, pre-custom
disassembly commit `0dbf95cd12f5b1511c62ce69efe283000f780a8f`. It builds the
current source with RGBDS 1.0.4, audits all 151 sprite pointers/banks, and checks
front/back decompression and gameplay-field preservation against the original
build. Floating IPS is built from pinned commit
`359d414cff73b3e0400871d3c288a59b36564834` (v198).

The packager checks both original SHA-1 and SHA-256 hashes before creating
patches, validates BPS CRCs, reapplies each patch to an original in temporary
storage, and requires byte-for-byte equality with its custom build. Only the
two `.bps` files, instructions, manifest, and checksums are uploaded. Original,
custom, debug, and verification ROMs remain temporary runner files and are not
uploaded or committed. No original-ROM upload or ROM secret is required.

To reproduce locally after building both source versions:

```sh
python3 tools/build_bps_patches.py \
    --originals /path/to/verified-original-build \
    --targets /path/to/custom-build \
    --flips /path/to/flips \
    --output /path/to/new-empty-patch-directory
```

The original and target directories must contain `pokered.gbc` and
`pokeblue.gbc`. The reusable PNG importer remains `tools/front_sprites.py`;
after changing individual fronts, rerun the workflow to generate matching new
patches. This does not extend allocation to custom back sprites.
