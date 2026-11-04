#!/usr/bin/env python3
"""Create patch-only release files from verified originals and custom builds.

Floating IPS creates BPS patches and applies them back to pristine inputs.
Only patches, checksums, a manifest, and instructions enter the output directory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
BASELINE_COMMIT = '0dbf95cd12f5b1511c62ce69efe283000f780a8f'
FLIPS_COMMIT = '359d414cff73b3e0400871d3c288a59b36564834'
ORIGINALS = {
    'pokered': {
        'version': 'Pokemon Red Version (USA, Europe) (SGB Enhanced)',
        'sha1': 'ea9bcae617fdf159b045185467ae58b2e4a48b9a',
        'sha256': '5ca7ba01642a3b27b0cc0b5349b52792795b62d3ed977e98a09390659af96b7b',
    },
    'pokeblue': {
        'version': 'Pokemon Blue Version (USA, Europe) (SGB Enhanced)',
        'sha1': 'd7037c83e1ae5b39bde3c30787637ba1d4c48ce2',
        'sha256': '2a951313c2640e8c2cb21f25d1db019ae6245d9c7121f754fa61afd7bee6452d',
    },
}


def checksums(data):
    return dict(bytes=len(data), sha1=hashlib.sha1(data).hexdigest(),
                sha256=hashlib.sha256(data).hexdigest(), crc32=f'{zlib.crc32(data):08X}')


def verify_original(stem, data):
    actual = checksums(data)
    if actual['bytes'] != 0x100000 or any(actual[key] != ORIGINALS[stem][key]
                                        for key in ('sha1', 'sha256')):
        raise ValueError(f'{stem}: original ROM does not match the required USA/Europe version; '
                         f'got SHA-1 {actual["sha1"]}')
    return actual


def build(originals, targets, flips, output):
    originals, targets, output = originals.resolve(), targets.resolve(), output.resolve()
    flips = flips.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Use a new or empty output directory for patch-only artifacts')
    # Verify both inputs before generating any distributable files.
    inputs = {}
    for stem in ORIGINALS:
        original = (originals / f'{stem}.gbc').read_bytes()
        target = (targets / f'{stem}.gbc').read_bytes()
        verified = verify_original(stem, original)
        if len(target) != 0x100000 or target[0x147:0x149] != original[0x147:0x149]:
            raise ValueError(f'{stem}: custom ROM must retain the original 1 MiB size and mapper')
        if target == original:
            raise ValueError(f'{stem}: target is unchanged; refusing to publish an empty modification')
        inputs[stem] = (original, target, verified)
    records = []
    with tempfile.TemporaryDirectory(prefix='bps-package-') as temp:
        temp = Path(temp)
        stage = temp / 'patches'
        stage.mkdir()
        for stem, (original, target, verified) in inputs.items():
            patch = stage / f'{stem}-custom-fronts.bps'
            restored = temp / f'{stem}-roundtrip.gbc'
            subprocess.run([str(flips), '--create', '--bps',
                            str(originals / f'{stem}.gbc'), str(targets / f'{stem}.gbc'),
                            str(patch)], check=True)
            data = patch.read_bytes()
            if data[:4] != b'BPS1':
                raise ValueError(f'{stem}: expected a BPS patch')
            # BPS trailer holds input, output, and patch CRCs (little endian).
            trailer = [int.from_bytes(data[i:i + 4], 'little')
                       for i in range(len(data) - 12, len(data), 4)]
            expected = [zlib.crc32(original), zlib.crc32(target), zlib.crc32(data[:-4])]
            if trailer != expected:
                raise ValueError(f'{stem}: BPS CRC validation failed')
            subprocess.run([str(flips), '--apply', str(patch),
                            str(originals / f'{stem}.gbc'), str(restored)], check=True)
            if restored.read_bytes() != target:
                raise ValueError(f'{stem}: applying the patch did not reproduce the custom ROM')
            records.append(dict(name=stem, original_version=ORIGINALS[stem]['version'],
                                original=verified, target=checksums(target),
                                patch=dict(filename=patch.name, **checksums(data)),
                                verification='applied patch matches custom ROM byte-for-byte'))
            print(f'{stem}: verified original, {len(data)}-byte BPS, exact round trip passed')
        manifest = dict(format='BPS', baseline_source_commit=BASELINE_COMMIT,
                        flips_source_commit=FLIPS_COMMIT, rgbds_version='1.0.4',
                        target_source_commit=subprocess.check_output(
                            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                        roms=records)
        (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        shutil.copyfile(ROOT / 'docs/bps-patches.md', stage / 'README-WINDOWS.md')
        sums = ''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n'
                       for p in sorted(stage.iterdir()))
        (stage / 'SHA256SUMS.txt').write_text(sums)
        expected_files = {'pokered-custom-fronts.bps', 'pokeblue-custom-fronts.bps',
                          'README-WINDOWS.md', 'manifest.json', 'SHA256SUMS.txt'}
        if {p.name for p in stage.iterdir()} != expected_files:
            raise ValueError('Unexpected file in patch-only package')
        output.mkdir(parents=True, exist_ok=True)
        for p in stage.iterdir():
            shutil.copyfile(p, output / p.name)
    print(f'Patch-only package: {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--originals', type=Path, required=True)
    parser.add_argument('--targets', type=Path, default=ROOT)
    parser.add_argument('--flips', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.originals, args.targets, args.flips, args.output)
