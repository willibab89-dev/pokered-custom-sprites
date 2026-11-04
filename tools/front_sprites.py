#!/usr/bin/env python3
"""Import front PNGs and audit linked sprite banks. Run from any directory."""
import argparse
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run([str(a) for a in args], cwd=ROOT, check=True)


def manifest():
    includes = re.findall(r'INCLUDE "([^"]+)"',
                          (ROOT / 'data/pokemon/base_stats.asm').read_text())
    includes.append('data/pokemon/base_stats/mew.asm')
    result = []
    for filename in includes:
        text = (ROOT / filename).read_text()
        png = re.search(r'INCBIN "([^"]+)"', text)[1].replace('.pic', '.png')
        front, back = re.search(r'dw (\w+), (\w+)', text).groups()
        dex = re.search(r'db (DEX_\w+)', text)[1]
        result.append((png, front, back, dex))
    assert len(result) == 151
    return result


def symbols(path):
    return {name: (int(bank, 16), int(addr, 16))
            for bank, addr, name in re.findall(
                r'^([0-9a-fA-F]+):([0-9a-fA-F]+) (\S+)$',
                path.read_text(), re.M)}


def offset(symbol):
    bank, addr = symbol
    return bank * 0x4000 + (addr % 0x4000)


def audit(stem):
    rom = (ROOT / f'{stem}.gbc').read_bytes()
    syms = symbols(ROOT / f'{stem}.sym')
    assert len(rom) == 0x100000, 'ROM must remain 1 MiB'
    assert rom[0x148] == 5, 'incorrect ROM size header'
    used = {}
    for dex, (png, front, back, _) in enumerate(manifest(), 1):
        pic = (ROOT / png.replace('.png', '.pic')).read_bytes()
        bank, addr = syms[front]
        assert 0 < bank < 64 and 0x4000 <= addr < 0x8000
        assert addr + len(pic) <= 0x8000, f'{front} crosses a bank'
        start = offset(syms[front])
        assert rom[start:start + len(pic)] == pic, f'{front}: wrong ROM bytes'
        header = (offset(syms['MewBaseStats']) if dex == 151 else
                  offset(syms['BaseStats']) + (dex - 1) * 28)
        assert rom[header + 10] == pic[0], f'{front}: wrong dimensions'
        assert int.from_bytes(rom[header + 11:header + 13], 'little') == addr
        assert rom[header + 27] == bank, f'{front}: wrong bank byte'
        assert int.from_bytes(rom[header + 13:header + 15], 'little') == syms[back][1]
        used[bank] = used.get(bank, 0) + len(pic)
        print(f'{stem}: {Path(png).stem:12} {len(pic):4} bytes  {bank:02x}:{addr:04x}')
    print(f'{stem}: 151 fronts, {sum(used.values())} compressed bytes; '
          f'{len(used)} banks, ROM {len(rom)} bytes')
    print('Bank free-space summary:')
    current = None
    for line in (ROOT / f'{stem}.map').read_text().splitlines():
        if line.startswith('ROMX bank #'):
            current = line
        elif current and 'TOTAL EMPTY:' in line:
            print(f'  {current} {line.strip()}')
            current = None


def import_pngs(directory, rgbds):
    allowed = {Path(png).name: png for png, *_ in manifest()}
    sources = sorted(directory.glob('*.png'))
    if not sources:
        raise ValueError('No PNGs found')
    unknown = {p.name for p in sources} - allowed.keys()
    if unknown:
        raise ValueError(f'Unknown front sprite filenames: {sorted(unknown)}')
    run('make', 'tools')
    # Validate and compress the whole batch before changing any artwork.
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        for src in sources:
            data = src.read_bytes()
            if data[:8] != b'\x89PNG\r\n\x1a\n' or data[12:16] != b'IHDR':
                raise ValueError(f'{src}: invalid PNG header')
            width, height = struct.unpack('>II', data[16:24])
            if width != height or width not in range(8, 57, 8):
                raise ValueError(f'{src}: expected square, 8–56 pixels in steps of 8')
            tiles = temp / (src.stem + '.2bpp')
            pic = temp / (src.stem + '.pic')
            decoded = temp / (src.stem + '.decoded')
            run(rgbds / 'rgbgfx', '--colors', 'dmg', '-o', tiles, src.resolve())
            run(ROOT / 'tools/pkmncompress', tiles, pic)
            run(ROOT / 'tools/pkmncompress', '-u', pic, decoded)
            assert tiles.read_bytes() == decoded.read_bytes(), f'{src}: round-trip failed'
            print(f'{src.name}: {width}x{height}, {pic.stat().st_size} compressed bytes')
        for src in sources:
            dest = ROOT / allowed[src.name]
            if src.resolve() != dest.resolve():
                shutil.copyfile(src, dest)
            # Force make to regenerate dependencies even for same-size replacements.
            dest.touch()
            for suffix in ('.2bpp', '.pic'):
                dest.with_suffix(suffix).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rgbds', type=Path,
                        default=Path(shutil.which('rgbasm') or
                                     '/workspace/.toolchains/rgbds-1.0.4/rgbasm').parent)
    parser.add_argument('--import-dir', type=Path, help='PNG batch; canonical front filenames')
    args = parser.parse_args()
    args.rgbds = args.rgbds.resolve()
    if args.import_dir:
        import_pngs(args.import_dir.resolve(), args.rgbds)
    run('make', '-j4', f'RGBDS={args.rgbds}/', 'red', 'blue')
    for stem in ('pokered', 'pokeblue'):
        audit(stem)


if __name__ == '__main__':
    main()
