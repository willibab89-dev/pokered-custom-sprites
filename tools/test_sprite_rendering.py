#!/usr/bin/env python3
"""Capture and pixel-check real battle/Pokedex rendering in PyBoy.

Optional dependencies: pyboy==2.6.1 Pillow==11.3.0
Diagnostic PNGs and fixed-bank placements exist only in a disposable source copy.
"""
import argparse
import hashlib
import html
import io
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageOps
from pyboy import PyBoy

from front_sprites import ROOT, manifest, symbols

CASES = (('bulbasaur', 40), ('nidorino', 48), ('venusaur', 56))
PALETTE = (255, 170, 85, 0)


def run(repo, *args):
    subprocess.run([str(a) for a in args], cwd=repo, check=True,
                   stdout=subprocess.DEVNULL)


def raster(repo, name):
    """Independent row-major pixel oracle, before the ROM's alignment stage."""
    with tempfile.TemporaryDirectory() as folder:
        raw = Path(folder) / 'sprite.2bpp'
        pic = repo / f'gfx/pokemon/front/{name}.pic'
        run(repo, repo / 'tools/pkmncompress', '-u', pic, raw)
        data = raw.read_bytes()
        width = (pic.read_bytes()[0] >> 4) * 8
        image = Image.new('RGB', (width, width), 'white')
        for tile in range((width // 8) ** 2):
            tx, ty = tile % (width // 8) * 8, tile // (width // 8) * 8
            for y in range(8):
                lo, hi = data[tile * 16 + y * 2:tile * 16 + y * 2 + 2]
                for x in range(8):
                    index = ((lo >> (7 - x)) & 1) | (((hi >> (7 - x)) & 1) << 1)
                    image.putpixel((tx + x, ty + y), (PALETTE[index],) * 3)
        return image


def aligned(image, flipped=False):
    # Original tile-aligned policy: 40 => (8,16), 48 => (8,8), 56 => (0,0).
    x, y = {40: (8, 16), 48: (8, 8), 56: (0, 0)}[image.width]
    result = Image.new('RGB', (56, 56), 'white')
    result.paste(image, (x, y))
    return ImageOps.mirror(result) if flipped else result


class Scenes:
    def __init__(self, repo, stem, temp):
        self.repo = repo
        self.syms = symbols(repo / f'{stem}.sym')
        empty = temp / 'empty.sym'
        empty.touch()
        self.boy = PyBoy(str(repo / f'{stem}.gbc'), window='null',
                         sound_emulated=False, symbols=str(empty), log_level='ERROR',
                         color_palette=(0xffffff, 0xaaaaaa, 0x555555, 0x000000))
        self.boy.set_emulation_speed(0)
        self.hits = {}
        for name in ('OverworldLoop', 'DisplayBattleMenu',
                     'ShowPokedexDataInternal.waitForButtonPress',
                     'LoadMonFrontSprite', 'LoadMonBackPic'):
            self.boy.hook_register(*self.syms[name], self.hit, name)
        self.boy.tick(600, False)
        # Use the game's existing intro-skip path, then normal initialization.
        self.write('wStatusFlags6', 2)
        self.jump('StartNewGameDebug', returning=False)
        self.wait('OverworldLoop', buttons=True)
        self.boy.tick(120, True)
        self.write('wStatusFlags6', self.read('wStatusFlags6') & ~2)
        self.write('wPartyCount', 0)
        self.write('wPartySpecies', 255)
        self.write('wCurPartySpecies', 1)  # Rhydon, unchanged player back picture
        self.write('wCurEnemyLevel', 20)
        self.write('wMonDataLocation', 16)  # player party, skip naming prompt
        self.call('AddPartyMon')
        nickname = [ord(c) - ord('A') + 0x80 for c in 'RHYDON'] + [0x50] * 5
        addr = self.syms['wPartyMon1Nick'][1]
        self.boy.memory[addr:addr + 11] = nickname
        self.base = io.BytesIO()
        self.boy.save_state(self.base)

    def hit(self, name):
        self.hits[name] = self.hits.get(name, 0) + 1

    def read(self, name):
        return self.boy.memory[self.syms[name][1]]

    def write(self, name, value):
        self.boy.memory[self.syms[name][1]] = value

    def jump(self, name, returning=True):
        bank, addr = self.syms[name]
        self.write('hLoadedROMBank', bank)
        self.boy.memory[0x2000] = bank
        # Frame boundaries can be inside an interrupt. Explicit EI avoids
        # inheriting IME=0 when redirecting execution. Leave LCD/VBlank active.
        code = ([0xfb, 0xcd, addr & 255, addr >> 8, 0x3e, 0x99,
                 0xea, 0x80, 0xdf, 0x18, 0xfe] if returning else
                [0xfb, 0x00, 0xc3, addr & 255, addr >> 8])
        self.boy.memory[0xdf00:0xdf00 + len(code)] = code
        self.boy.memory[0xdf80] = 0
        self.boy.register_file.SP = 0xdff0
        self.boy.register_file.PC = 0xdf00

    def call(self, name):
        self.jump(name)
        for _ in range(600):
            self.boy.tick(1, True)
            if self.boy.memory[0xdf80] == 0x99:
                return
        raise AssertionError(f'{name} did not return')

    def wait(self, name, buttons=False):
        for frame in range(3000):
            if buttons and frame % 16 == 0:
                self.boy.button('a', 3)
            self.boy.tick(1, True)
            if self.hits.get(name):
                return frame
        raise AssertionError(f'{name} not reached')

    def capture(self, species, context):
        self.base.seek(0)
        self.boy.load_state(self.base)
        self.hits.clear()
        if context in ('wild', 'trainer'):
            self.write('wCurEnemyLevel', 20)
            self.write('wBattleType', 0)
            if context == 'trainer':
                # In-memory test encounter: use the real Youngster battle flow,
                # replacing only this emulator's first trainer party definition.
                bank, addr = self.syms['YoungsterData']
                for i, value in enumerate((20, species, 0)):
                    self.boy.memory[bank, addr + i] = value
                self.write('wTrainerNo', 1)
            self.write('wCurOpponent', 201 if context == 'trainer' else species)
            self.jump('InitOpponent')
            frames = self.wait('DisplayBattleMenu', buttons=True)
            self.boy.button_release('a')
            self.boy.tick(12, True)
            assert self.read('wIsInBattle') == (2 if context == 'trainer' else 1)
            assert self.read('wEnemyMonSpecies') == species
            assert self.hits.get('LoadMonBackPic'), 'player back loading not exercised'
        else:
            self.write('wUpdateSpritesEnabled', 0)
            self.write('wIsInBattle', 0)
            self.call('LoadFontTilePatterns')
            self.call('LoadTextBoxTilePatterns')
            # Establish the menu's usual BG map/VBlank transfer prerequisites.
            self.boy.memory[0xff40] = 0xe3
            self.write('hAutoBGTransferEnabled', 1)
            addr = self.syms['hAutoBGTransferDest'][1]
            self.boy.memory[addr:addr + 2] = [0, 0x98]
            self.write('wPokedexNum', species)  # entry expects an internal ID
            self.write('wSpriteFlipped', 0)
            addr = self.syms['wPokedexOwned'][1]
            self.boy.memory[addr:addr + 19] = [0] * 19  # seen-only entry, no text paging
            self.jump('ShowPokedexData')
            frames = self.wait('ShowPokedexDataInternal.waitForButtonPress')
            self.boy.tick(16, True)
            assert self.read('wSpriteFlipped') == 0, 'flipped flag was not cleared'
        assert self.hits.get('LoadMonFrontSprite'), 'front loading not exercised'
        return self.boy.screen.image.convert('RGB').copy(), frames

    def close(self):
        self.boy.stop(save=False)


def fixture(repo):
    """Distinct corner markers and a solid border expose mirroring and clipping."""
    pics = repo / 'gfx/pics.asm'
    text = pics.read_text()
    labels = {Path(png).stem: front for png, front, *_ in manifest()}
    for name, size in CASES:
        image = Image.new('RGB', (size, size), 'white')
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, size - 1, size - 1), outline='black', width=1)
        draw.rectangle((2, 2, 9, 9), fill='black')
        draw.rectangle((size - 7, 2, size - 3, 6), fill=(85,) * 3)
        draw.rectangle((2, size - 6, 5, size - 3), fill=(170,) * 3)
        draw.line((size // 2, 12, size // 2, size - 4), fill='black', width=2)
        draw.line((12, size // 2, size - 4, size // 2), fill=(85,) * 3, width=3)
        image.save(repo / f'gfx/pokemon/front/{name}.png')
        label = labels[name]
        old = f'\tmon_frontpic {label}\n'
        assert text.count(old) == 1
        text = text.replace(old, f'\tPUSHS\nSECTION "Front sprite {label}", ROMX, BANK[$3f]\n{label}::\n')
    pics.write_text(text)


def suite(repo, variant, output, backs):
    order = (repo / 'data/pokemon/dex_order.asm').read_text().splitlines()
    dexes = [line.split()[1] for line in order if line.strip().startswith('db ')]
    records = []
    for stem in ('pokered', 'pokeblue'):
        rom = (repo / f'{stem}.gbc').read_bytes()
        assert len(rom) == 0x100000 and rom[0x148] == 5
        syms = symbols(repo / f'{stem}.sym')
        with tempfile.TemporaryDirectory() as folder:
            scenes = Scenes(repo, stem, Path(folder))
            try:
                for name, size in CASES:
                    png, front, _, dex = next(row for row in manifest()
                                              if Path(row[0]).stem == name)
                    bank, addr = syms[front]
                    if variant == 'diagnostic':
                        assert bank == 0x3f
                    source = raster(repo, name)
                    assert source.size == (size, size)
                    for context in ('wild', 'trainer', 'pokedex'):
                        image, frames = scenes.capture(dexes.index(dex) + 1, context)
                        scroll_x = scenes.boy.memory[0xff43]
                        scroll_y = scenes.boy.memory[0xff42]
                        x, y = (8, 8) if context == 'pokedex' else (96, 0)
                        box = (x - scroll_x, y - scroll_y, x + 56 - scroll_x, y + 56 - scroll_y)
                        expected = aligned(source, context == 'pokedex')
                        actual = image.crop(box)
                        filename = f'{variant}-{stem}-{name}-{context}.png'
                        image.save(output / filename)
                        if actual.tobytes() != expected.tobytes():
                            actual.save(output / f'FAILED-{filename}')
                            expected.save(output / f'EXPECTED-{filename}')
                            raise AssertionError(f'{filename}: rendered front differs from pixel oracle')
                        if context != 'pokedex':
                            back = image.crop((8, 40, 64, 96)).tobytes()
                            key = (stem, context)
                            if key in backs:
                                assert back == backs[key], f'{filename}: back rendering changed'
                            else:
                                backs[key] = back
                        records.append(dict(variant=variant, rom=stem, pokemon=name,
                                            size=size, context=context, bank=bank,
                                            address=addr, file=filename, frames=frames,
                                            front_crop=box, scroll=[scroll_x, scroll_y],
                                            front_pixels='passed', back_pixels=(
                                                'unchanged' if context != 'pokedex' else 'not applicable')))
                        print(f'PASS {filename}: {size}x{size}, bank {bank:02x}', flush=True)
            finally:
                scenes.close()
    return records


def gallery(output, records):
    for variant in ('stock', 'diagnostic'):
        for stem in ('pokered', 'pokeblue'):
            selected = [r for r in records if r['variant'] == variant and r['rom'] == stem]
            sheet = Image.new('RGB', (3 * 336, 3 * 324 + 32), '#eeeeee')
            draw = ImageDraw.Draw(sheet)
            draw.text((8, 8), f'{variant} / {stem} — actual emulator frames, nearest-neighbor 2x', fill='black')
            for i, row in enumerate(selected):
                x, y = (i % 3) * 336 + 8, (i // 3) * 324 + 32
                draw.text((x, y), f'{row["size"]}px {row["context"]} bank {row["bank"]:02x}', fill='black')
                image = Image.open(output / row['file'])
                sheet.paste(image.resize((320, 288), Image.Resampling.NEAREST), (x, y + 18))
            sheet.save(output / f'{variant}-{stem}-contact.png')
    content = ['<!doctype html><meta charset="utf-8"><title>Sprite rendering regression</title>',
               '<style>body{font:16px system-ui;max-width:1100px;margin:24px auto}img{max-width:100%;image-rendering:pixelated}</style>',
               '<h1>Sprite rendering regression</h1>',
               '<p>36 captured screens: 2 games × 3 dimensions × 3 contexts × stock/diagnostic. '
               'All 56×56 front-buffer pixels match the independent oracle. '
               'Diagnostic fronts are pinned to bank 3f in a disposable build. '
               'Player back crops remain identical. Encounters are set up through emulator memory; '
               'screens are rendered by the original game routines with LCD/VBlank active.</p>']
    for variant in ('stock', 'diagnostic'):
        for stem in ('pokered', 'pokeblue'):
            name = f'{variant}-{stem}-contact.png'
            content.append(f'<h2>{variant} / {stem}</h2><a href="{name}"><img src="{name}"></a>')
    content.append('<h2>Individual screenshots</h2><ul>')
    content.extend(f'<li><a href="{html.escape(r["file"])}">{html.escape(r["file"])}</a></li>' for r in records)
    content.append('</ul><p>Details: <a href="results.json">results.json</a></p>')
    (output / 'index.html').write_text('\n'.join(content))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rgbds', type=Path,
                        default=Path(shutil.which('rgbasm') or
                                     '/workspace/.toolchains/rgbds-1.0.4/rgbasm').parent)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # A failed rerun must not leave an old success report visible.
    for name in ('results.json', 'index.html'):
        (output / name).unlink(missing_ok=True)
    rgbds = args.rgbds.resolve()
    # Source hashes prove that temporary patterns never replace checkout artwork.
    originals = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in (ROOT / 'gfx/pokemon').rglob('*.png')}
    run(ROOT, 'make', '-j4', f'RGBDS={rgbds}/', 'red', 'blue')
    original_roms = {str(ROOT / f'{stem}.gbc'): hashlib.sha256(
        (ROOT / f'{stem}.gbc').read_bytes()).hexdigest() for stem in ('pokered', 'pokeblue')}
    backs = {}
    records = suite(ROOT, 'stock', output, backs)
    with tempfile.TemporaryDirectory(prefix='sprite-rendering-') as folder:
        repo = Path(folder)
        # Copy tracked inputs, including local edits; exclude .git and outputs.
        tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
        for name in filter(None, tracked):
            dest = repo / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, dest)
        fixture(repo)
        run(repo, 'make', '-j4', f'RGBDS={rgbds}/', 'red', 'blue')
        records += suite(repo, 'diagnostic', output, backs)
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest
               for p, digest in originals.items()), 'checkout artwork was modified'
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest
               for p, digest in original_roms.items()), 'checkout ROMs were modified'
    gallery(output, records)
    (output / 'results.json').write_text(json.dumps(dict(
        emulator=f'PyBoy {version("pyboy")}', pillow=version('Pillow'),
        source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        cases=records, screens_passed=len(records),
        original_artwork_unchanged=True, rom_size_bytes=0x100000,
        limitations=['Scripted emulator-memory encounter setup, not a manual playthrough',
                     'One representative player back visually checked; all backs covered by separate decompression tests',
                     'Seen-only Pokedex entries; description pagination not exercised',
                     'DMG rendering only; SGB hardware/palettes not covered']), indent=2))
    print(f'{len(records)} screens passed. Gallery: {output / "index.html"}')


if __name__ == '__main__':
    main()
