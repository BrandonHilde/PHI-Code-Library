#!/usr/bin/env python3
"""Makes the cases corelib's Brotli decoder is tested against, with Brotli's own encoder.

    python3 -I tools/core/make_brotli_tests.py

Writes libs/core/tests/brotli/cases.bin and cases.txt. Each case is a stream the `brotli` command
made (it's Google's encoder) at a quality from 0 to 11 and a window from 10 to 24 bits, of English
and HTML (which the encoder packs with words from the static dictionary and their transforms),
source code, noise, zeros, and nothing; with the size and CRC-32 of what it must decode to. Then a
few of every kind of damage: streams cut short and with bytes changed (fixed seed), which must come
back without a crash.

The format of cases.bin (little-endian): u32 count, then each: u8 kind (0 good, 1 damaged),
u8 name length, name, u32 length, the stream; for a good one u32 size, u32 CRC-32.
"""
import os
import random
import struct
import subprocess
import tempfile
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'libs', 'core', 'tests', 'brotli')


def compress(data, quality, window):
    with tempfile.TemporaryDirectory(dir=os.path.expanduser('~')) as d:
        a, b = os.path.join(d, 'in'), os.path.join(d, 'out.br')
        with open(a, 'wb') as f:
            f.write(data)
        subprocess.run(['brotli', '-q', str(quality), '-w', str(window), '-f', '-o', b, a], check=True)
        with open(b, 'rb') as f:
            return f.read()


def main():
    os.makedirs(OUT, exist_ok=True)
    rnd = random.Random(20261120)
    sources = {}
    text = b''
    for name in ('README.md', 'plan.md', 'docs/conventions.md'):
        with open(os.path.join(ROOT, name), 'rb') as f:
            text += f.read()
    sources['english'] = text[:16000]
    html = b''.join(b'<div class="item"><a href="/page/%d.html">Read the article about %s</a><p>Published %d. The %s of the %s.</p></div>\n'
                    % (i, rnd.choice([b'weather', b'history', b'science', b'music']), 2000 + i % 25,
                       rnd.choice([b'story', b'end', b'start']), rnd.choice([b'year', b'world', b'city'])) for i in range(120))
    sources['html'] = b'<!DOCTYPE html><html><head><title>News</title></head><body>' + html + b'</body></html>'
    with open(os.path.join(ROOT, 'libs', 'core', 'corelib', 'inflate.phi'), 'rb') as f:
        sources['source code'] = f.read()[:12000]
    sources['noise'] = bytes(rnd.getrandbits(8) for _ in range(4000))
    sources['zeros'] = bytes(50000)
    sources['one byte'] = b'x'
    sources['nothing'] = b''
    cases = []
    for name, data in sources.items():
        for q in ((0, 1, 5, 9, 11) if name in ('english', 'html') else (0, 5, 11)):
            for w in ((10, 16, 22) if name in ('english', 'html') else (22,)):
                cases.append((0, f'{name}, q{q} w{w}', compress(data, q, w), data))
    rnd2 = random.Random(7)
    damaged = []
    for kind, name, stream, data in cases[::4]:
        for cut in sorted({1, 3, len(stream) // 2, len(stream) - 1}):
            if 0 < cut < len(stream):
                damaged.append((1, f'{name}, cut to {cut}', stream[:cut], None))
        for k in range(4):
            b = bytearray(stream)
            for _ in range(rnd2.randint(1, 3)):
                b[rnd2.randrange(len(b))] = rnd2.randrange(256)
            damaged.append((1, f'{name}, changed {k}', bytes(b), None))
    cases += damaged
    out = bytearray(struct.pack('<I', len(cases)))
    lines = ['# made by tools/core/make_brotli_tests.py: each case, and what it must decode to']
    for kind, name, stream, data in cases:
        nb = name.encode()
        out += struct.pack('<BB', kind, len(nb)) + nb + struct.pack('<I', len(stream)) + stream
        if kind == 0:
            out += struct.pack('<II', len(data), zlib.crc32(data))
            lines.append(f'{name:36} {len(stream):7} bytes, to {len(data):7}')
        else:
            lines.append(f'{name:36} {len(stream):7} bytes, damaged')
    with open(os.path.join(OUT, 'cases.bin'), 'wb') as f:
        f.write(out)
    with open(os.path.join(OUT, 'cases.txt'), 'w', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    print(len(cases), 'cases,', len(out), 'bytes')


if __name__ == '__main__':
    main()
