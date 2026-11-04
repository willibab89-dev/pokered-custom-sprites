#!/usr/bin/env python3
"""Execute ROM picture loading in PyBoy; compare against the C decompressor.

Install optional test dependency: python -m pip install pyboy==2.6.1
This is a routine-level emulator test, not a gameplay or visual test.
"""
import argparse
import re
from pathlib import Path
import subprocess
import tempfile

from front_sprites import ROOT, manifest, offset, symbols


def expected(pic, temp):
    output = temp / 'decoded.2bpp'
    subprocess.run([str(ROOT / 'tools/pkmncompress'), '-u', str(pic), str(output)],
                   check=True)
    data = output.read_bytes()
    width = pic.read_bytes()[0] >> 4
    # C output is row-major tiles; the ROM buffers are column-major planes.
    tiles = [data[i:i + 16] for i in range(0, len(data), 16)]
    column_major = b''.join(tiles[y * width + x]
                            for x in range(width) for y in range(width))
    size = 7 * 7 * 8
    return (column_major[::2].ljust(size, b'\0') +
            column_major[1::2].ljust(size, b'\0'))


def check_preserved(stem, baseline):
    """Compare gameplay fields and compressed backs with a pristine build."""
    old = (baseline / f'{stem}.gbc').read_bytes()
    new = (ROOT / f'{stem}.gbc').read_bytes()
    old_syms = symbols(baseline / f'{stem}.sym')
    new_syms = symbols(ROOT / f'{stem}.sym')
    source = (ROOT / 'gfx/pics.asm').read_text() + (ROOT / 'data/pokemon/mew.asm').read_text()
    for dex, (png, _, back, _) in enumerate(manifest(), 1):
        headers = []
        for rom, syms in ((old, old_syms), (new, new_syms)):
            start = (offset(syms['MewBaseStats']) if dex == 151 else
                     offset(syms['BaseStats']) + (dex - 1) * 28)
            data = rom[start:start + 28]
            # Dimensions, pointers, and front bank are artwork metadata; all
            # gameplay fields must remain identical to the pristine build.
            headers.append(data[:10] + data[15:27])
            if rom is new:
                pic = (ROOT / png.replace('.png', '.pic')).read_bytes()
                assert data[10] == pic[0], f'{stem}: dex {dex} dimensions do not match artwork'
        assert headers[0] == headers[1], f'{stem}: dex {dex} gameplay fields changed'
        path = re.search(rf'{back}::\s+INCBIN "([^"]+)"', source)[1]
        size = (ROOT / path).stat().st_size
        a, b = offset(old_syms[back]), offset(new_syms[back])
        assert old[a:a + size] == new[b:b + size], f'{stem}: {back} changed'
    print(f'{stem}: all original base-stat fields and back artwork preserved')


def check_rom(stem):
    from pyboy import PyBoy
    syms = symbols(ROOT / f'{stem}.sym')
    # Empty symbol file avoids PyBoy interpreting RGBDS constant records as labels.
    with tempfile.TemporaryDirectory() as folder:
        temp = Path(folder)
        sym = temp / 'empty.sym'
        sym.touch()
        boy = PyBoy(str(ROOT / f'{stem}.gbc'), window='null', sound_emulated=False,
                    symbols=str(sym), log_level='ERROR')
        boy.set_emulation_speed(0)
        boy.memory[0xff50] = 1  # disable boot ROM; run just the routines under test
        boy.memory[0xff40] = 0  # LCD off
        boy.memory[0xffff] = 0  # interrupts off
        rom = (ROOT / f'{stem}.gbc').read_bytes()
        order = (ROOT / 'data/pokemon/dex_order.asm').read_text().splitlines()
        dexes = [line.split()[1] for line in order if line.strip().startswith('db ')]

        def call(species, pointer_offset, pic):
            for name in ('wCurSpecies', 'wCurPartySpecies'):
                boy.memory[syms[name][1]] = species
            boy.memory[syms['wSpriteFlipped'][1]] = 0
            boy.memory[syms['hLoadedROMBank'][1]] = 0x1c
            boy.memory[0x2000] = 0x1c
            code = [0xf3]  # di
            for name in ('GetMonHeader', 'UncompressMonSprite'):
                if name == 'UncompressMonSprite':
                    code += [0x21, pointer_offset, 0]  # ld hl, header offset
                addr = syms[name][1]
                code += [0xcd, addr & 255, addr >> 8]
            code += [0x3e, 0x99, 0xea, 0x00, 0xc0, 0x18, 0xfe]
            boy.memory[0xc100:0xc100 + len(code)] = code
            boy.memory[0xc000] = 0
            boy.register_file.SP = 0xdff0
            boy.register_file.PC = 0xc100
            for _ in range(300):
                boy.tick(1, False)
                if boy.memory[0xc000] == 0x99:
                    break
            else:
                raise AssertionError(f'{stem}: species {species:#x} did not return PC={boy.register_file.PC:04x} SP={boy.register_file.SP:04x} bank={boy.memory[syms["hLoadedROMBank"][1]]:02x}')
            assert boy.register_file.SP == 0xdff0, 'unbalanced stack'
            assert boy.memory[syms['hLoadedROMBank'][1]] == 0x1c, 'bank not restored'
            assert bytes(boy.memory[0x4000:0x4010]) == rom[0x70000:0x70010], 'hardware bank not restored'
            start = syms['sSpriteBuffer1'][1]
            actual = bytes(boy.memory[start:start + 2 * 7 * 7 * 8])
            assert actual == expected(pic, temp), f'{stem}: {pic}: decompression mismatch'

        try:
            for png, front, back, dex in manifest():
                species = dexes.index(dex) + 1
                call(species, 11, ROOT / png.replace('.png', '.pic'))
                # The back filename need not match the base-stat filename (Mr. Mime).
                source = (ROOT / 'gfx/pics.asm').read_text() + (ROOT / 'data/pokemon/mew.asm').read_text()
                path = re.search(rf'{back}::\s+INCBIN "([^"]+)"', source)[1]
                call(species, 13, ROOT / path)
            for species, path in ((0xb6, 'gfx/pokemon/front/fossilkabutops.pic'),
                                  (0xb7, 'gfx/pokemon/front/fossilaerodactyl.pic'),
                                  (0xb8, 'gfx/battle/ghost.pic')):
                call(species, 11, ROOT / path)
        finally:
            boy.stop(save=False)
    print(f'{stem}: 151 fronts + 151 backs + 3 special pictures passed; bank and stack restored')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, help='pristine .gbc/.sym build directory')
    parser.add_argument('roms', nargs='*', default=['pokered', 'pokeblue'])
    args = parser.parse_args()
    deps = set()
    for source in ('gfx/pics.asm', 'main.asm'):
        deps.update(subprocess.check_output(
            [str(ROOT / 'tools/scan_includes'), source], cwd=ROOT, text=True).split())
    assert all(png.replace('.png', '.pic') in deps for png, *_ in manifest()), \
        'front pictures must remain visible to the make dependency scanner'
    for stem in args.roms:
        if args.baseline:
            check_preserved(stem, args.baseline)
        check_rom(stem)
