#!/usr/bin/env python3
"""Has zlib read back what corelib's deflate makes, and says how its sizes compare with zlib's own.

    python3 -I tools/core/check_deflate.py [PHI]       PHI: the compiler (else $PHI_EXE)

Builds tools/core/pack/pack.phi for this computer (macOS, 64-bit Linux or 64-bit Windows) with a fresh corelib.philib, packs each input at
levels 0, 1, 6 and 9 in each framing, and unpacks each with Python's zlib (zlib.decompress, with
the window bits for bare DEFLATE, zlib and gzip). Every one must give back its input exactly. The
inputs: noise, zeros, text made of words, the repo's own source and documents, and PNG pictures'
image data as it is before it's packed (from tests in libs/image), which is what imagelib's PNG
writer gives it.

It prints each input's size, corelib's size beside zlib's at each level, and whether every one came
back. It writes into a temporary folder and leaves nothing behind.
"""
import os
import random
import shutil
import subprocess
import sys
import tempfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEVELS = (0, 1, 6, 9)
WBITS = {0: -15, 1: 15, 2: 31}


def inputs():
    rnd = random.Random(20261120)
    yield 'noise', bytes(rnd.getrandbits(8) for _ in range(200_000))
    yield 'zeros', bytes(500_000)
    words = [b'the ', b'quick ', b'brown ', b'fox ', b'jumps ', b'over ', b'lazy ', b'dog\n']
    yield 'words', b''.join(rnd.choice(words) for _ in range(40_000))
    src = b''
    for folder, _, names in os.walk(os.path.join(ROOT, 'libs', 'core')):
        for n in sorted(names):
            if n.endswith('.phi') or n.endswith('.md'):
                with open(os.path.join(folder, n), 'rb') as f:
                    src += f.read()
    yield 'corelib source', src
    with open(os.path.join(ROOT, 'libs', 'web', 'html', 'entities.phi'), 'rb') as f:
        yield 'weblib entities.phi', f.read()
    # a picture's rows, each with PNG's filter byte 0 before it: a drawing in a few colors
    rows = bytearray()
    for y in range(400):
        rows.append(0)
        for x in range(640):
            c = 3
            if (x - 320) ** 2 + (y - 200) ** 2 < 120 * 120:
                c = 9
            if 40 < x < 200 and 50 < y < 140:
                c = 4
            rows.append(c)
    yield 'a drawing in 16 colors', bytes(rows)
    photo = bytearray()
    for y in range(240):
        photo.append(1)
        for x in range(320 * 3):
            photo.append((x * 7 + y * 3 + rnd.getrandbits(3)) & 255)
    yield 'a photo-like picture', bytes(photo)


def main():
    phi = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('PHI_EXE')
    if not phi:
        sys.exit('give the phi compiler, or set PHI_EXE')
    work = tempfile.mkdtemp(prefix='check_deflate_', dir=os.path.expanduser('~'))
    try:
        shutil.copy(os.path.join(ROOT, 'tools', 'core', 'pack', 'pack.phi'), work)
        subprocess.run([phi, 'build', os.path.join(ROOT, 'libs', 'core', 'corelib.phi'), '--library',
                        '-o', work], check=True, stdout=subprocess.DEVNULL)
        host = {'darwin': 'macos', 'win32': 'windows64'}.get(sys.platform, 'linux64')
        subprocess.run([phi, 'build', os.path.join(work, 'pack.phi'), '--target', host, '-o', work], check=True,
                       stdout=subprocess.DEVNULL, env=dict(os.environ, NASMENV='-O1'))
        pack = [os.path.join(work, n) for n in ('pack', 'pack.exe') if os.path.exists(os.path.join(work, n))][0]
        bad = 0
        print(f'{"input":26} {"bytes":>8}  ' + '  '.join(f'{"level " + str(l):>17}' for l in LEVELS))
        for name, data in inputs():
            source = os.path.join(work, 'in.bin')
            with open(source, 'wb') as f:
                f.write(data)
            cells = []
            for level in LEVELS:
                sizes = []
                for frame in (0, 1, 2):
                    out = os.path.join(work, 'out.bin')
                    subprocess.run([pack, source, out, str(level), str(frame)], check=True)
                    with open(out, 'rb') as f:
                        packed = f.read()
                    try:
                        back = zlib.decompress(packed, WBITS[frame])
                    except zlib.error as e:
                        back = None
                        print(f'  {name}, level {level}, frame {frame}: zlib refused it: {e}')
                    if back != data:
                        bad += 1
                        print(f'  {name}, level {level}, frame {frame}: NOT THE SAME')
                    if frame == 1:
                        sizes.append(len(packed))
                ours = sizes[0]
                theirs = len(zlib.compress(data, level))
                cells.append(f'{ours:>8} / {theirs:<8}')
            print(f'{name:26} {len(data):>8}  ' + '  '.join(cells))
        print('(each: corelib / zlib, in zlib framing)')
        print('every one read back by zlib exactly' if bad == 0 else f'{bad} WRONG')
        return 1 if bad else 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
