#!/usr/bin/env python3
"""Makes libs/net/netlib/hpacktables.phi: HPACK's static table and Huffman code (RFC 7541, Appendices A
and B), read from the RFC's own text.

    python3 tools/net/make_hpack_tables.py rfc7541.txt

(https://www.rfc-editor.org/rfc/rfc7541.txt.) The code is canonical: codes of each length follow one
another in the order of their symbols, which is what lets the decoder be a few small tables.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, 'libs', 'net', 'netlib', 'hpacktables.phi')

txt = open(sys.argv[1], encoding='utf-8').read()
codes = {}
for m in re.finditer(r"\((\s*\d+)\)\s+\|[01|]+\s+([0-9a-f]+)\s+\[\s*(\d+)\]", txt):
    codes[int(m.group(1))] = (int(m.group(2), 16), int(m.group(3)))
assert len(codes) == 257 and abs(sum(2.0 ** -b for c, b in codes.values()) - 1.0) < 1e-12

static = {}
for m in re.finditer(r"\|\s*(\d+)\s*\|\s*(:?[a-z0-9-]+)\s*\|\s*([^|]*?)\s*\|", txt):
    i = int(m.group(1))
    if 1 <= i <= 61 and i not in static:
        static[i] = (m.group(2), m.group(3))
assert len(static) == 61 and static[2] == (':method', 'GET')

# canonical: by length, then symbol, each code is the one before it plus one
order = sorted(range(257), key=lambda s: (codes[s][1], s))
code = 0
last_len = codes[order[0]][1]
first = [0] * 31
count = [0] * 31
offset = [0] * 31
for i, s in enumerate(order):
    c, b = codes[s]
    if i == 0:
        code = c
    else:
        code = (code + 1) << (b - last_len)
    assert code == c, s
    if count[b] == 0:
        first[b] = c
        offset[b] = i
    count[b] += 1
    last_len = b


def table(kind, name, values, per):
    lines = ['\t%s %s:' % (kind, name)]
    for i in range(0, len(values), per):
        lines.append('\t\t' + ' '.join(str(v) for v in values[i:i + per]))
    lines[-1] += ';'
    return lines


text = []
starts = []
for i in range(1, 62):
    n, v = static[i]
    starts.append(len(text))
    text.extend(n.encode() + b'\0' + v.encode() + b'\0')
out = ['# Made by tools/net/make_hpack_tables.py from RFC 7541: run that to make it again.',
       '# The static table: each entry its name and its value, each ending with a zero, and where each',
       '# starts. The Huffman code, canonical: for each length, the first code of that length, how many',
       '# there are and where they start in symbols (sorted by length, then symbol); and each symbol\'s',
       '# code and length, for encoding.',
       '',
       'phi.WireHpackTables:Library',
       '{']
out += table('u16', 'static_at', starts, 16)
out += table('u8', 'static_text', list(text), 32)
out += table('u32', 'first', first, 16)
out += table('u16', 'count', count, 16)
out += table('u16', 'offset', offset, 16)
out += table('u16', 'symbols', order, 16)
out += table('u32', 'code', [codes[s][0] for s in range(257)], 8)
out += table('u8', 'bits', [codes[s][1] for s in range(257)], 32)
out += ['}', '']
open(OUT, 'w', newline='\n').write('\n'.join(out))
print(OUT)
