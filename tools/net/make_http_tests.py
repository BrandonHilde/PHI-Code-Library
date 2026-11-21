#!/usr/bin/env python3
"""Makes libs/net/tests/http/bodies.bin for test_http: one page's text, and that text packed as a
server packs a body for each Content-Encoding netlib unpacks: gzip (Python's gzip), deflate as the
standard has it (zlib) and as some servers send it (bare DEFLATE), Brotli (the brotli tool, from
Google's library), and two codings one after the other. test_http unpacks each and compares.

    python3 tools/net/make_http_tests.py
"""
import gzip, os, shutil, struct, subprocess, zlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BROTLI = shutil.which('brotli', path='/opt/homebrew/bin:' + os.environ.get('PATH', ''))

words = ('the page body script style table header footer section article content navigation '
         'function return window document element').split()
lines = []
for i in range(400):
    lines.append('<p class="row-%d">%s %d</p>' % (i % 7, ' '.join(words[(i * 3 + k) % len(words)] for k in range(9)), i * i))
text = ('<!DOCTYPE html>\n<html><head><title>netlib</title></head><body>\n' + '\n'.join(lines) + '\n</body></html>\n').encode()

def raw(data):
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return c.compress(data) + c.flush()

brotli = subprocess.run([BROTLI, '-c', '-q', '11'], input=text, capture_output=True, check=True).stdout
items = [
    ('gzip', 'gzip', gzip.compress(text, 9)),
    ('x-gzip', 'x-gzip', gzip.compress(text, 1)),
    ('deflate (zlib)', 'deflate', zlib.compress(text, 9)),
    ('deflate (bare)', 'deflate', raw(text)),
    ('br', 'br', brotli),
    ('deflate then gzip', 'deflate, gzip', gzip.compress(zlib.compress(text))),
    ('identity', 'identity', text),
    ('gzip, cut short', 'gzip', gzip.compress(text)[:-40]),
]
folder = os.path.join(ROOT, 'libs', 'net', 'tests', 'http')
os.makedirs(folder, exist_ok=True)
with open(os.path.join(folder, 'bodies.bin'), 'wb') as f:
    f.write(struct.pack('<II', len(items), len(text)) + text)
    for name, coding, data in items:
        for t in (name.encode(), coding.encode()):
            f.write(bytes([len(t)]) + t)
        f.write(struct.pack('<I', len(data)) + data)
print('wrote', len(items), 'bodies of a', len(text), 'byte page')
