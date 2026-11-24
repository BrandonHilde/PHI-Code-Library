#!/usr/bin/env python3
"""Make libs/media/medialib/mp3tables.phi, the MP3 decoder's fixed tables, from PDMP3's source.

    python3 tools/media/mp3_tables.py PATH/TO/pdmp3.c

PDMP3 (Krister Lagerstrom, public domain: the Unlicense; github.com/technosaurus/PDMP3) holds the
tables of ISO/IEC 11172-3 as the ISO reference decoder had them: the Huffman code trees and the
synthesis window. This reads its text (it isn't compiled or run), walks each tree into its code
words, and writes them out as (length, value, code) words, from which the decoder builds its own
lookup tables when it starts. The synthesis window's 512 values are whole multiples of 1/65536 (the
standard prints them to 9 places); they're written as those whole numbers, and that's checked.
"""
import re, sys, os

src = open(sys.argv[1], encoding='latin1').read()
# (comments first: the tables' own have braces in them)
src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
src = re.sub(r'//[^\n]*', '', src)

def array_text(name):
    m = re.search(name + r'\s*\[[^\]]*\]\s*=\s*\{', src)
    if not m:
        raise SystemExit('no ' + name)
    i = m.end(); depth = 1; j = i
    while depth:
        if src[j] == '{': depth += 1
        elif src[j] == '}': depth -= 1
        j += 1
    body = src[i:j - 1]
    body = re.sub(r'//[^\n]*', '', body)
    body = re.sub(r'/\*.*?\*/', '', body, flags=re.S)
    return body

huff = [int(x, 16) for x in re.findall(r'0x[0-9a-fA-F]+', array_text('g_huffman_table'))]

# g_huffman_main: {g_huffman_table +OFFSET, TREELEN, LINBITS}
main = []
for m in re.finditer(r'\{\s*(NULL|g_huffman_table\s*(?:\+\s*(\d+))?)\s*,\s*(\d+)\s*,\s*(\d+)\s*\}', array_text('g_huffman_main')):
    if m.group(1) == 'NULL':
        main.append(None)
    else:
        main.append((int(m.group(2) or 0), int(m.group(3)), int(m.group(4))))
assert len(main) == 34, len(main)

def walk(offset, treelen):
    """every code word of a tree: (bits, length, x, y), as PDMP3's Huffman_Decode reads it"""
    out = []
    def go(point, code, length):
        if length > 24:
            raise SystemExit('tree too deep')
        e = huff[offset + point]
        if e & 0xff00 == 0:
            out.append((code, length, (e >> 4) & 15, e & 15))
            return
        # left (a 0 bit)
        p = point
        while (huff[offset + p] >> 8) >= 250:
            p += huff[offset + p] >> 8
        p += huff[offset + p] >> 8
        go(p, code << 1, length + 1)
        p = point
        while (huff[offset + p] & 0xff) >= 250:
            p += huff[offset + p] & 0xff
        p += huff[offset + p] & 0xff
        go(p, (code << 1) | 1, length + 1)
    go(0, 0, 0)
    return out

tables = {}
for t in list(range(1, 16)) + [16, 24, 32]:
    if main[t] is None:
        continue
    off, tl, lb = main[t]
    words = walk(off, tl)
    # a proper prefix code: the lengths fill the tree exactly (Kraft)
    total = sum(2.0 ** -w[1] for w in words)
    assert abs(total - 1.0) < 1e-9, (t, total)
    tables[t] = words

# count1 table B is four bits a value, each the value's complement (PDMP3 points its own elsewhere)
tables[33] = [(15 - v, 4, 0, v) for v in range(16)]
# what each table must hold: x and y below 16 (2, 3, 4 ... of each), and 16 for the count1 tables
SIZES = {1: 2, 2: 3, 3: 3, 5: 4, 6: 4, 7: 6, 8: 6, 9: 6, 10: 8, 11: 8, 12: 8, 13: 16, 15: 16, 16: 16, 24: 16}
for t, n in SIZES.items():
    assert len(tables[t]) == n * n, (t, len(tables[t]))
    assert sorted((x, y) for _, _, x, y in tables[t]) == [(x, y) for x in range(n) for y in range(n)], t
for t in (32, 33):
    assert sorted(y for _, _, x, y in tables[t]) == list(range(16)), t

linbits = [0] * 32
for t in range(32):
    if main[t] is not None:
        linbits[t] = main[t][2]

d = [float(x) for x in re.findall(r'-?\d+\.\d+', array_text('g_synth_dtbl'))]
assert len(d) == 512, len(d)
dw = []
for v in d:
    k = round(v * 65536)
    assert abs(k / 65536 - v) < 6e-9, v
    dw.append(k)

out = []
w = out.append
w('# MP3\'s fixed tables (ISO/IEC 11172-3), made by tools/media/mp3_tables.py from PDMP3\'s source (public')
w('# domain), which has them as the ISO reference decoder did. Don\'t change them by hand.')
w('')
w('phi.MdMp3Tables:Library')
w('{')
w('\t# The Huffman codes: for tables 1 to 15, 16 (17 to 23 too, with more linbits), 24 (25 to 31) and the')
w('\t# count1 tables A (32) and B (33), each code as length << 27 | x << 23 | y << 19 | bits. Where')
w('\t# each table\'s codes start in it, and how many: by table number, 0 for none')
starts = [0] * 34; counts = [0] * 34
flat = []
for t in sorted(tables):
    starts[t] = len(flat); counts[t] = len(tables[t])
    for code, length, x, y in tables[t]:
        assert length < 32 and code < (1 << 19)
        flat.append((length << 27) | (x << 23) | (y << 19) | code)
def rows(values, per=12):
    lines = []
    for i in range(0, len(values), per):
        lines.append('\t\t' + ' '.join(str(v) for v in values[i:i + per]))
    return lines
w('\tu16 code_start:')
out.extend(rows(starts, 17)); out[-1] += ';'
w('\tu16 code_count:')
out.extend(rows(counts, 17)); out[-1] += ';'
w('\tu32 codes:')
out.extend(rows(flat, 8)); out[-1] += ';'
w('\t# each big_values table\'s linbits, 0 to 31')
w('\tu8 linbits:')
out.extend(rows(linbits, 16)); out[-1] += ';'
w('\t# the synthesis window D[i], times 65536 (the standard\'s values are whole multiples of 1/65536)')
w('\tint window:')
out.extend(rows(dw, 16)); out[-1] += ';'
w('}')
dest = os.path.join(os.path.dirname(__file__), '..', '..', 'libs', 'media', 'medialib', 'mp3tables.phi')
os.makedirs(os.path.dirname(dest), exist_ok=True)
open(dest, 'w').write('\n'.join(out) + '\n')
print('wrote', os.path.normpath(dest), ':', len(flat), 'codes in', len(tables), 'tables; window', min(dw), 'to', max(dw))
