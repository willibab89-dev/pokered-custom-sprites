#!/usr/bin/env python3
"""Capture and pixel-check all 151 fronts in both games and all three scenes.

Requires pyboy==2.6.1 Pillow==11.3.0. Uses existing emulator scene setup;
does not replace artwork, modify ROMs, or require a save file.
"""
import argparse
import hashlib
import html
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

from PIL import Image, ImageDraw

from front_sprites import ROOT, manifest, symbols
from test_sprite_rendering import Scenes, aligned, raster, run

CONTEXTS = ('wild', 'trainer', 'pokedex')
ROMS = ('pokered', 'pokeblue')


def overview(output, records):
    """Paginate real screen crops into readable, numbered overview sheets."""
    pages = []
    for stem in ROMS:
        by_dex = {r['dex']: r for r in records
                  if r['rom'] == stem and r['context'] == 'wild'}
        for page, start in enumerate(range(1, 152, 28), 1):
            numbers = list(range(start, min(start + 28, 152)))
            sheet = Image.new('RGB', (7 * 240, ((len(numbers) + 6) // 7) * 156 + 40), '#eeeeee')
            draw = ImageDraw.Draw(sheet)
            draw.text((8, 10), f'{stem}: #{numbers[0]:03d}-#{numbers[-1]:03d} | battle / Pokedex | actual screen crops, 2x', fill='black')
            for i, dex in enumerate(numbers):
                row = by_dex[dex]
                x, y = (i % 7) * 240 + 8, (i // 7) * 156 + 40
                draw.text((x, y), f'#{dex:03d} {row["pokemon"]} ({row["size"]}px)', fill='black')
                for j, context in enumerate(('wild', 'pokedex')):
                    capture = next(r for r in records
                                   if r['rom'] == stem and r['dex'] == dex and r['context'] == context)
                    with Image.open(output / capture['file']) as image:
                        crop = image.crop(capture['front_crop'])
                    sheet.paste(crop.resize((112, 112), Image.Resampling.NEAREST), (x + j * 116, y + 18))
                    draw.text((x + j * 116, y + 132), 'battle' if j == 0 else 'Pokedex', fill='#444444')
            filename = f'{stem}-overview-{page:02d}.png'
            sheet.save(output / filename)
            pages.append(filename)
    return pages


def web_gallery(output, records, pages):
    content = ['''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>All 151 Pokemon: in-game sprite gallery</title>
<style>
body{font:16px system-ui;margin:0;background:#f2f2ef;color:#222}
header,main,footer{max-width:1280px;margin:auto;padding:20px}
header{position:sticky;top:0;background:#f2f2eff5;z-index:1;border-bottom:1px solid #ccc}
h1{font-size:24px;margin:0 0 10px}p{line-height:1.45}
label{display:inline-block;margin:4px 14px 4px 0}input,select{font:inherit;padding:5px}
main{display:grid;grid-template-columns:repeat(auto-fit,minmax(500px,1fr));gap:18px}
article{background:white;border:1px solid #ccc;border-radius:8px;padding:12px}
h2{font-size:18px;margin:0 0 10px}.screens{display:flex;flex-wrap:wrap;gap:8px}
figure{margin:0}img{width:160px;height:144px;image-rendering:pixelated;display:block}
figcaption{font-size:12px;margin:4px 0 10px}a{color:#174c81}
[hidden]{display:none!important}footer a{display:inline-block;margin:5px 12px 5px 0}
@media(max-width:550px){main{display:block}article{margin-bottom:15px}.screens{justify-content:center}}
</style><header><h1>All 151 Pokemon: in-game sprite gallery</h1>
<p>906 emulator screenshots: Red and Blue, wild battle, trainer battle, and Pokedex.
Every front-buffer pixel passed comparison with the source artwork. Click a screen
to inspect its original 160x144 image.</p>
<label>Find <input id="search" type="search" placeholder="Name or Pokedex number"></label>
<label>Game <select id="game"><option value="pokered">Red</option><option value="pokeblue">Blue</option><option value="all">Both</option></select></label>
<label>Screen <select id="context"><option value="all">All screens</option><option value="wild">Wild battle</option><option value="trainer">Trainer battle</option><option value="pokedex">Pokedex</option></select></label>
<span id="count"></span></header><main>''']
    for dex in range(1, 152):
        rows = [r for r in records if r['dex'] == dex]
        first = rows[0]
        name = html.escape(first['pokemon'])
        content.append(f'<article data-search="{dex:03d} {dex} {name}"><h2>#{dex:03d} {name} <small>{first["size"]}x{first["size"]}</small></h2><div class="screens">')
        for row in rows:
            file = html.escape(row['file'])
            title = ('Red' if row['rom'] == 'pokered' else 'Blue') + ' / ' + row['context']
            content.append(f'<figure data-game="{row["rom"]}" data-context="{row["context"]}"><a href="{file}"><img loading="lazy" src="{file}" alt="{name}, {title}"></a><figcaption>{title}</figcaption></figure>')
        content.append('</div></article>')
    content.append('''</main><footer><h2>Overview sheets</h2><p>Numbered battle/Pokedex crops, enlarged 2x without smoothing.</p>''')
    content.extend(f'<a href="{page}">{page}</a>' for page in pages)
    content.append('''<h2>Test scope</h2><p>Encounters are scripted in emulator memory.
The game executes its original loading, alignment, flipping, VRAM-transfer and
screen routines with LCD/VBlank enabled. Captures stop at the battle fight menu
or a seen-only Pokedex entry. This does not test battle turns, status screens,
owned-entry descriptions or SGB palettes. The displayed Rhydon back crop is
checked for consistency throughout.</p><p><a href="results.json">Machine-readable results</a>
<a href="sprite-gallery.zip">Download gallery</a></p></footer>
<script>
const search=document.querySelector('#search'),game=document.querySelector('#game'),context=document.querySelector('#context');
function filter(){let count=0;for(const card of document.querySelectorAll('article')){
card.hidden=!card.dataset.search.includes(search.value.trim().toLowerCase());if(!card.hidden)count++;
for(const image of card.querySelectorAll('figure'))image.hidden=(game.value!=='all'&&image.dataset.game!==game.value)||(context.value!=='all'&&image.dataset.context!==context.value);
}document.querySelector('#count').textContent=count+' Pokemon';}
for(const control of [search,game,context])control.addEventListener('input',filter);filter();
</script></html>''')
    (output / 'index.html').write_text('\n'.join(content))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rgbds', type=Path, default=Path(shutil.which('rgbasm') or
                        '/workspace/.toolchains/rgbds-1.0.4/rgbasm').parent)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for name in ('index.html', 'results.json', 'sprite-gallery.zip'):
        (output / name).unlink(missing_ok=True)
    run(ROOT, 'make', '-j4', f'RGBDS={args.rgbds.resolve()}/', 'red', 'blue')
    rows = manifest()
    art_hashes = {png: hashlib.sha256((ROOT / png).read_bytes()).hexdigest() for png, *_ in rows}
    order = (ROOT / 'data/pokemon/dex_order.asm').read_text().splitlines()
    dexes = [line.split()[1] for line in order if line.strip().startswith('db ')]
    records, backs, rom_hashes = [], {}, {}
    for stem in ROMS:
        rom = (ROOT / f'{stem}.gbc').read_bytes()
        assert len(rom) == 0x100000 and rom[0x148] == 5
        rom_hashes[stem] = hashlib.sha256(rom).hexdigest()
        syms = symbols(ROOT / f'{stem}.sym')
        with tempfile.TemporaryDirectory() as folder:
            scenes = Scenes(ROOT, stem, Path(folder))
            try:
                for dex, (png, front, _, dex_name) in enumerate(rows, 1):
                    name = Path(png).stem
                    source = raster(ROOT, name)
                    assert source.width == source.height and source.width in (40, 48, 56)
                    for context in CONTEXTS:
                        image, frames = scenes.capture(dexes.index(dex_name) + 1, context)
                        sx, sy = scenes.boy.memory[0xff43], scenes.boy.memory[0xff42]
                        x, y = (8, 8) if context == 'pokedex' else (96, 0)
                        box = (x - sx, y - sy, x + 56 - sx, y + 56 - sy)
                        filename = f'{stem}-{dex:03d}-{name}-{context}.png'
                        image.save(output / filename)
                        expected = aligned(source, context == 'pokedex')
                        actual = image.crop(box)
                        if actual.tobytes() != expected.tobytes():
                            expected.save(output / f'EXPECTED-{filename}')
                            actual.save(output / f'FAILED-{filename}')
                            raise AssertionError(f'{filename}: pixel comparison failed')
                        if context != 'pokedex':
                            back = image.crop((8, 40, 64, 96)).tobytes()
                            key = (stem, context)
                            if key in backs:
                                assert back == backs[key], f'{filename}: player back changed'
                            else:
                                backs[key] = back
                        bank, addr = syms[front]
                        records.append(dict(dex=dex, pokemon=name, size=source.width,
                                            rom=stem, context=context, file=filename,
                                            bank=bank, address=addr, front_crop=box,
                                            frames=frames, pixel_check='passed'))
                    print(f'{stem}: #{dex:03d} {name}: wild / trainer / Pokedex passed', flush=True)
            finally:
                scenes.close()
    assert len(records) == 906
    assert all(hashlib.sha256((ROOT / png).read_bytes()).hexdigest() == digest
               for png, digest in art_hashes.items()), 'source artwork changed'
    assert all(hashlib.sha256((ROOT / f'{stem}.gbc').read_bytes()).hexdigest() == digest
               for stem, digest in rom_hashes.items()), 'production ROM changed'
    pages = overview(output, records)
    web_gallery(output, records, pages)
    report = dict(screens_passed=len(records), species=151, games=list(ROMS),
                  contexts=list(CONTEXTS), emulator=f'PyBoy {version("pyboy")}',
                  source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  rom_sha256=rom_hashes, source_artwork_unchanged=True,
                  rom_size_bytes=0x100000, player_back_consistent=True, cases=records)
    (output / 'results.json').write_text(json.dumps(report, indent=2))
    with zipfile.ZipFile(output / 'sprite-gallery.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for filename in [r['file'] for r in records] + pages + ['index.html', 'results.json']:
            archive.write(output / filename, filename)
    print(f'906 screenshots passed. Gallery: {output / "index.html"}', flush=True)


if __name__ == '__main__':
    main()
