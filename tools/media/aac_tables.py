#!/usr/bin/env python3
"""Make libs/media/medialib/aactables.phi: AAC's Huffman codebooks (the 11 spectral ones and the
scalefactors'), as (length, index, code) words, from the PacketVideo AAC decoder (Apache 2.0) in
Android's source, which holds them in a layout of its own.

    python3 tools/media/aac_tables.py DIR      # DIR has decode_huff_cw_binary.cpp, hcbtables_binary.cpp, sfb.cpp
        # (android.googlesource.com/platform/frameworks/base, tag android-2.3.7_r1,
        #  media/libstagefright/codecs/aacdec)

Each of its decode functions reads N bits and, by ranges of their value, picks a word of its table
(index << 16 | length), or for its shortest code answers at once. This reads those functions' text
(nothing is compiled or run), does what each does for every one of the 2^N values, and so recovers
each codeword: then it checks each book is a whole prefix code of the size it should be.
"""
import re, sys, os
D = sys.argv[1]
src = open(os.path.join(D, 'decode_huff_cw_binary.cpp')).read()
tabsrc = open(os.path.join(D, 'hcbtables_binary.cpp')).read()
tabsrc = re.sub(r'/\*.*?\*/', '', tabsrc, flags=re.S)

def table(name):
    m = re.search(r'const\s+U?Int32\s+' + name + r'\s*\[\s*\d+\s*\]\s*=\s*\{(.*?)\};', tabsrc, re.S)
    assert m, name
    return [int(x, 0) for x in re.findall(r'0x[0-9a-fA-F]+|\d+', m.group(1))]

funcs = {}
for m in re.finditer(r'Int\s+(decode_huff_cw_tab\d+|decode_huff_scl)\s*\(\s*BITS\s*\*\s*pInputStream\s*\)\s*\{(.*?)\n\}', src, re.S):
    funcs[m.group(1)] = m.group(2)
assert len(funcs) == 12, sorted(funcs)

def emulate(name):
    body = funcs[name]
    n = int(re.search(r'(?:get17_n_lessbits|get9_n_lessbits|getbits)\s*\(\s*(\d+)', body).group(1))
    tab = table(re.search(r'tab\s*=\s*\*\s*\(\s*(\w+)\s*\+\s*tab\s*\)', body).group(1))
    # the chain: (shift, op, limit, action) where action is ('ret', used, idx) or ('tab', shift, sub, add)
    rules = []
    for m in re.finditer(r'(?:if|else if)\s*\(\s*\(\s*cw\s*>>\s*(\d+)\s*\)\s*(==|<=)\s*(\d+)\s*\)\s*\{(.*?)\}', body, re.S):
        shift, op, limit, act = int(m.group(1)), m.group(2), int(m.group(3)), m.group(4)
        r = re.search(r'usedBits\s*-=\s*\(\s*\d+\s*-\s*(\d+)\s*\).*?return\s+(\d+)', act, re.S)
        if r:
            rules.append((shift, op, limit, ('ret', int(r.group(1)), int(r.group(2)))))
        else:
            t = re.search(r'tab\s*=\s*\(\s*cw\s*>>\s*(\d+)\s*\)\s*-\s*(\d+)(?:\s*\+\s*(\d+))?', act)
            if not t:
                t2 = re.search(r'tab\s*=\s*\(\s*cw\s*>>\s*(\d+)\s*\)\s*;', act)
                rules.append((shift, op, limit, ('tab', int(t2.group(1)), 0, 0)))
            else:
                rules.append((shift, op, limit, ('tab', int(t.group(1)), int(t.group(2)), int(t.group(3) or 0))))
    last = re.search(r'else\s*\{\s*tab\s*=\s*cw\s*-\s*(\d+)\s*\+\s*(\d+)\s*;', body)
    codes = {}
    for cw in range(1 << n):
        done = None
        for shift, op, limit, act in rules:
            v = cw >> shift
            if (op == '==' and v == limit) or (op == '<=' and v <= limit):
                if act[0] == 'ret':
                    done = (act[2], act[1])
                else:
                    done = ('t', (cw >> act[1]) - act[2] + act[3])
                break
        if done is None:
            done = ('t', cw - int(last.group(1)) + int(last.group(2)))
        if done[0] == 't':
            w = tab[done[1]]
            idx, length = w >> 16, w & 0xFFFF
        else:
            idx, length = done
        code = cw >> (n - length)
        if idx in codes:
            assert codes[idx] == (code, length), (name, idx, codes[idx], code, length)
        codes[idx] = (code, length)
    return codes

SIZES = {1: 81, 2: 81, 3: 81, 4: 81, 5: 81, 6: 81, 7: 64, 8: 64, 9: 169, 10: 169, 11: 289}
books = {}
for b in range(1, 12):
    books[b] = emulate('decode_huff_cw_tab%d' % b)
books[0] = emulate('decode_huff_scl')
SIZES[0] = 121
for b, codes in books.items():
    assert sorted(codes) == list(range(SIZES[b])), (b, len(codes))
    kraft = sum(2.0 ** -l for c, l in codes.values())
    assert abs(kraft - 1.0) < 1e-12, (b, kraft)
    # prefix-free: no code is the start of another
    items = sorted((l, c) for c, l in codes.values())
    seen = set()
    for l, c in items:
        for k in range(1, l):
            assert (k, c >> (l - k)) not in seen, (b, 'prefix')
        seen.add((l, c))
out = ['# AAC\'s Huffman codebooks (ISO/IEC 14496-3), made by tools/media/aac_tables.py from the PacketVideo',
       '# AAC decoder\'s tables (Apache 2.0, in Android\'s source). Don\'t change them by hand.', '',
       'phi.MdAacTables:Library', '{',
       '\t# Book 0 is the scalefactors\' (index 0 to 120: a difference of index - 60), 1 to 11 the spectrum\'s.',
       '\t# Each code is length << 24 | index << 15 | ... no: length << 26 | index << 17 is too few bits for',
       '\t# codes of 19, so two words: book_len (bits) and book_code, by book_start:book + index.',
       '\tu16 book_start:']
starts = []; lens = []; cds = []
for b in range(12):
    starts.append(len(lens))
    for i in range(SIZES[b]):
        c, l = books[b][i]
        lens.append(l); cds.append(c)
out[-4:] = ['\t# Book 0 is the scalefactors\' (index 0 to 120: a difference of index - 60), 1 to 11 the spectrum\'s',
            '\t# (their indexes as the standard numbers them). Each code\'s length and bits, by book_start:book',
            '\t# plus its index.', '\tu16 book_start:']
out.append('\t\t' + ' '.join(str(s) for s in starts) + ';')
out.append('\tu8 book_size_hint: 0;')
out.pop()
out.append('\tu8 code_len:')
for k in range(0, len(lens), 32):
    out.append('\t\t' + ' '.join(str(x) for x in lens[k:k + 32]))
out[-1] += ';'
out.append('\tu32 code_bits:')
for k in range(0, len(cds), 16):
    out.append('\t\t' + ' '.join(str(x) for x in cds[k:k + 16]))
out[-1] += ';'
# the scalefactor bands' edges by sampling frequency index (0: 96000 ... 11: 8000), long then short:
# sfb.cpp has each table's band ends; the standard says which rate uses which
sfb = re.sub(r'/\*.*?\*/', '', open(os.path.join(D, 'sfb.cpp')).read(), flags=re.S)
def bands(name):
    m = re.search(r'const\s+Int16\s+' + name + r'\s*\[\s*\]\s*=\s*\{(.*?)\};', sfb, re.S)
    assert m, name
    return [0] + [int(x) for x in re.findall(r'\d+', m.group(1))]
LONG = ['96_1024', '96_1024', '64_1024', '48_1024', '48_1024', '32_1024', '24_1024', '24_1024', '16_1024', '16_1024', '16_1024', '8_1024']
SHORT = ['64_128', '64_128', '64_128', '48_128', '48_128', '48_128', '24_128', '24_128', '16_128', '16_128', '16_128', '8_128']
COUNTS = [(41, 12), (41, 12), (47, 12), (49, 14), (49, 14), (51, 14), (47, 15), (47, 15), (43, 15), (43, 15), (43, 15), (40, 15)]
longs = []; shorts = []; long_at = []; short_at = []
for i in range(12):
    lb = bands('sfb_' + LONG[i]); sb = bands('sfb_' + SHORT[i])
    assert len(lb) - 1 == COUNTS[i][0] and lb[-1] == 1024, (i, len(lb))
    assert len(sb) - 1 == COUNTS[i][1] and sb[-1] == 128, (i, len(sb))
    long_at.append(len(longs)); longs += lb
    short_at.append(len(shorts)); shorts += sb
out.append('\t# scalefactor bands: each sampling frequency index\'s edges (with 0 first), long (1024) then short (128)')
out.append('\tu8 long_count: ' + ' '.join(str(c[0]) for c in COUNTS) + ';')
out.append('\tu8 short_count: ' + ' '.join(str(c[1]) for c in COUNTS) + ';')
out.append('\tu16 long_at: ' + ' '.join(str(x) for x in long_at) + ';')
out.append('\tu16 short_at: ' + ' '.join(str(x) for x in short_at) + ';')
out.append('\tu16 long_edges:')
for k in range(0, len(longs), 26):
    out.append('\t\t' + ' '.join(str(x) for x in longs[k:k + 26]))
out[-1] += ';'
out.append('\tu8 short_edges:')
for k in range(0, len(shorts), 32):
    out.append('\t\t' + ' '.join(str(x) for x in shorts[k:k + 32]))
out[-1] += ';'
out.append('}')
dest = os.path.join(os.path.dirname(__file__), '..', '..', 'libs', 'media', 'medialib', 'aactables.phi')
open(dest, 'w').write('\n'.join(out) + '\n')
print('wrote', os.path.normpath(dest), ':', len(lens), 'codes in 12 books; longest', max(lens))
