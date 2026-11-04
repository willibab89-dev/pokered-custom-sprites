#!/usr/bin/env python3
"""Package an existing emulator gallery without running an emulator or build.

Requires Pillow. Input: results.json and the previously captured PNG screens.
Output: index.html with 151 embedded thumbnails, on-demand screens, and an offline ZIP.
"""
import argparse
import base64
import io
import json
from pathlib import Path
import shutil
import zipfile

from PIL import Image

HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>151 Pokémon — lightweight sprite gallery</title>
<style>
:root{font:16px system-ui,sans-serif;color:#202924;background:#f4f6f2;color-scheme:light}
*{box-sizing:border-box}body{margin:0}header,main,footer{max-width:1120px;margin:auto;padding:20px}
h1{font-size:26px;margin:0 0 8px}p{line-height:1.5;margin:8px 0;color:#4e5c52}
.controls,.pagination,.viewer-controls{display:flex;align-items:center;flex-wrap:wrap;gap:12px;margin:16px 0}
input,select,button{font:inherit}input,select{padding:8px;border:1px solid #a6b3a8;border-radius:5px;background:white}
button{cursor:pointer;border:1px solid #a6b3a8;border-radius:5px;padding:8px 14px;background:white;color:inherit}
button:hover{background:#e6ede5}button:disabled{opacity:.45;cursor:default}
:focus-visible{outline:3px solid #286e45;outline-offset:3px}input[type=search]{width:min(330px,100%)}
main{padding-top:0}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(145px,1fr));gap:12px}
.card{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:5px;min-height:184px;padding:14px 6px;border-color:#d2dbd0;background:#fff}
.card img{width:112px;height:112px;image-rendering:pixelated;object-fit:contain;background:white}
.number{font-size:12px;color:#647267}.name{font-weight:600}.status{font-size:14px;color:#4e5c52}
dialog{border:1px solid #a6b3a8;border-radius:10px;padding:20px;width:min(610px,calc(100% - 24px));max-height:95vh;overflow:auto}
dialog::backdrop{background:#17251cb3}.dialog-heading{display:flex;justify-content:space-between;gap:12px;align-items:center}
h2{font-size:22px;margin:0}.viewer-controls label{display:flex;align-items:center;gap:8px}
#screen{min-height:288px;display:flex;justify-content:center;align-items:center;background:white;margin:16px 0}
#screen img{width:320px;height:288px;max-width:100%;object-fit:contain;image-rendering:pixelated}
.viewer-nav{display:flex;justify-content:space-between;gap:12px}footer{font-size:13px;border-top:1px solid #d2dbd0}
[hidden]{display:none!important}@media(max-width:400px){header,main,footer{padding:14px}.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.card img{width:100px;height:100px}}
</style></head><body>
<header><h1>151 Pokémon</h1><p>Captured in-game sprites, in Pokédex order. Select a Pokémon to load a full screenshot.</p>
<div class="controls"><label for="search">Find</label><input id="search" type="search" placeholder="Name or Pokédex number" autocomplete="off">
<label for="page-size">Per page</label><select id="page-size"><option value="24">24</option><option value="48">48</option></select></div>
<nav class="pagination" aria-label="Gallery pages"><button id="previous" type="button">Previous</button><span id="page-label"></span><button id="next" type="button">Next</button><span id="status" class="status" role="status" aria-live="polite"></span></nav>
</header><main><div id="grid" class="grid"></div><p id="empty" hidden>No Pokémon match your search.</p></main>
<footer>All 151 thumbnails are embedded in this HTML. Only the current page is displayed. Full screenshots load after selection.
Thumbnails work from the HTML alone. For full screenshots offline, extract the complete ZIP and open index.html, keeping its assets folder beside it. No server or Internet connection is needed.</footer>
<dialog id="viewer" aria-labelledby="viewer-title"><div class="dialog-heading"><h2 id="viewer-title"></h2><button id="close" type="button" aria-label="Close screenshot">Close</button></div>
<div class="viewer-controls"><label>Game <select id="game"><option value="pokered">Red</option><option value="pokeblue">Blue</option></select></label>
<label>Screen <select id="context"><option value="wild">Wild battle</option><option value="trainer">Trainer battle</option><option value="pokedex">Pokédex</option></select></label></div>
<div id="screen"></div><p id="caption" class="status" role="status" aria-live="polite"></p>
<div class="viewer-nav"><button id="previous-pokemon" type="button">Previous Pokémon</button><button id="next-pokemon" type="button">Next Pokémon</button></div></dialog>
<script id="pokemon-data" type="application/json">__POKEMON_DATA__</script>
<script>
'use strict';
const pokemon=JSON.parse(document.getElementById('pokemon-data').textContent);
const $=id=>document.getElementById(id);
const normalize=value=>value.normalize('NFKD').replace(/[̀-ͯ]/g,'').toLowerCase().replace(/[^a-z0-9♀♂]/g,'');
let filtered=pokemon,page=0,pageSize=24,selected=null,searchTimer;
function drawPage(){
 const pages=Math.max(1,Math.ceil(filtered.length/pageSize));page=Math.max(0,Math.min(page,pages-1));
 const start=page*pageSize,items=filtered.slice(start,start+pageSize),fragment=document.createDocumentFragment();
 for(const item of items){
  const card=document.createElement('button');card.type='button';card.className='card';card.dataset.dex=item.dex;
  card.setAttribute('aria-label',`View #${String(item.dex).padStart(3,'0')} ${item.name}`);
  const number=document.createElement('span');number.className='number';number.textContent='#'+String(item.dex).padStart(3,'0');
  const image=document.createElement('img');image.loading='lazy';image.decoding='async';image.width=56;image.height=56;image.alt='';image.src=item.thumbnail;
  const name=document.createElement('span');name.className='name';name.textContent=item.name;
  card.append(number,image,name);card.addEventListener('click',()=>openPokemon(item));fragment.append(card);
 }
 $('grid').replaceChildren(fragment);$('empty').hidden=filtered.length!==0;
 $('previous').disabled=page===0;$('next').disabled=page>=pages-1;
 $('page-label').textContent=`Page ${page+1} of ${pages}`;
 $('status').textContent=filtered.length?`${start+1}–${Math.min(start+pageSize,filtered.length)} of ${filtered.length} Pokémon`:'0 Pokémon';
}
function filter(){
 const query=normalize($('search').value);
 filtered=pokemon.filter(item=>!query||(/^\d+$/.test(query)?item.dex===Number(query):normalize(item.name+' '+item.slug).includes(query)));
 page=0;drawPage();
}
function showScreenshot(){
 if(!selected)return;
 const game=$('game').value,context=$('context').value,item=selected;
 $('viewer-title').textContent=`#${String(item.dex).padStart(3,'0')} ${item.name}`;
 $('caption').textContent='Loading screenshot…';
 const image=document.createElement('img');image.width=160;image.height=144;image.decoding='async';
 image.alt=`${item.name} — ${game==='pokered'?'Red':'Blue'}, ${context==='pokedex'?'Pokédex':context+' battle'}`;
 image.addEventListener('load',()=>{if($('screen').firstChild===image)$('caption').textContent=image.alt+' · original 160×144 capture, displayed at 2×';});
 image.addEventListener('error',()=>{if($('screen').firstChild===image)$('caption').textContent='Screenshot unavailable. Extract the entire ZIP, including its assets folder.';});
 // This is the only point where a full screenshot URL becomes an image source.
 image.src=item.screens[game][context];$('screen').replaceChildren(image);
 const index=filtered.indexOf(item);$('previous-pokemon').disabled=index<=0;$('next-pokemon').disabled=index<0||index>=filtered.length-1;
}
function openPokemon(item){selected=item;showScreenshot();if(!$('viewer').open)$('viewer').showModal();}
function stepPokemon(offset){const index=filtered.indexOf(selected)+offset;if(index>=0&&index<filtered.length)openPokemon(filtered[index]);}
$('search').addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(filter,100);});
$('page-size').addEventListener('change',()=>{pageSize=Number($('page-size').value);page=0;drawPage();});
$('previous').addEventListener('click',()=>{page--;drawPage();});$('next').addEventListener('click',()=>{page++;drawPage();});
$('close').addEventListener('click',()=>$('viewer').close());
$('viewer').addEventListener('close',()=>{$('screen').replaceChildren();$('caption').textContent='';selected=null;});
for(const id of ['game','context'])$(id).addEventListener('change',showScreenshot);
$('previous-pokemon').addEventListener('click',()=>stepPokemon(-1));$('next-pokemon').addEventListener('click',()=>stepPokemon(1));
drawPage();
</script></body></html>
'''


def package(source, output):
    source, output = source.resolve(), output.resolve()
    if source == output:
        raise ValueError('Use a separate output directory to preserve the original gallery')
    data = json.loads((source / 'results.json').read_text())
    rows = data['cases']
    screen_dir = output / 'assets/screens'
    screen_dir.mkdir(parents=True, exist_ok=True)
    friendly = {'nidoranf': 'Nidoran♀', 'nidoranm': 'Nidoran♂',
                'mr.mime': 'Mr. Mime', 'farfetchd': 'Farfetch’d'}
    entries, files, thumbnail_bytes = [], [], 0
    for dex in range(1, 152):
        captures = [r for r in rows if r['dex'] == dex]
        assert len(captures) == 6, f'#{dex}: expected six existing captures'
        representative = next(r for r in captures if r['rom'] == 'pokered' and r['context'] == 'wild')
        slug = representative['pokemon']
        name = friendly.get(slug, slug.capitalize())
        screens = {game: {} for game in ('pokered', 'pokeblue')}
        for row in captures:
            original = (source / row['file']).resolve()
            original.relative_to(source)  # reject paths outside the capture directory
            assert original.is_file() and original.suffix.lower() == '.png'
            relative = f'assets/screens/{original.name}'
            shutil.copyfile(original, output / relative)
            files.append(relative)
            screens[row['rom']][row['context']] = relative
        with Image.open(source / representative['file']) as image:
            crop = image.crop(representative['front_crop']).convert('RGB')
            assert crop.size == (56, 56)
            encoded_png = io.BytesIO()
            crop.save(encoded_png, format='PNG', optimize=True)
        png_bytes = encoded_png.getvalue()
        thumbnail_bytes += len(png_bytes)
        thumbnail = 'data:image/png;base64,' + base64.b64encode(png_bytes).decode('ascii')
        assert all(set(views) == {'wild', 'trainer', 'pokedex'} for views in screens.values())
        entries.append(dict(dex=dex, name=name, slug=slug, thumbnail=thumbnail, screens=screens))
    encoded = json.dumps(entries, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    (output / 'index.html').write_text(HTML.replace('__POKEMON_DATA__', encoded))
    (output / 'README.txt').write_text(
        'Extract the complete ZIP and open index.html in a modern browser.\n'
        'All 151 thumbnails are embedded; index.html alone displays the thumbnail gallery.\n'
        'For full screenshots, keep the assets folder beside index.html. No server or Internet is needed.\n'
        '24 thumbnails per page by default; full screenshots load only on selection.\n'
        'Images come from existing emulator captures. No ROMs were rebuilt or modified.\n')
    files += ['index.html', 'README.txt']
    stats = dict(pokemon=151, thumbnails=151, screenshots=906, initial_page_size=24,
                 html_bytes=(output / 'index.html').stat().st_size,
                 thumbnail_bytes=thumbnail_bytes, thumbnails_embedded=True,
                 offline=True, source_commit=data.get('source_commit'))
    (output / 'package.json').write_text(json.dumps(stats, indent=2))
    files.append('package.json')
    with zipfile.ZipFile(output / 'lightweight-gallery.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in files:
            archive.write(output / name, name)
    print(json.dumps(stats, indent=2))
    print(f'Gallery: {output / "index.html"}\nOffline ZIP: {output / "lightweight-gallery.zip"}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='existing capture gallery directory')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    package(args.source, args.output)
