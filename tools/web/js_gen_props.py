#!/usr/bin/env python3
"""Writes libs/web/js/uniprops.phi: the Unicode properties RegExp's \\p{...} can name, from Unicode's own
character database.

    python3 tools/web/js_gen_props.py [UCD folder]

The folder (libs/web/build/ucd17 when none is given) is Unicode's UCD.zip unpacked, with emoji-sequences.txt
and emoji-zwj-sequences.txt in its emoji folder as well:

    https://www.unicode.org/Public/17.0.0/ucd/UCD.zip
    https://www.unicode.org/Public/17.0.0/emoji/emoji-sequences.txt (and emoji-zwj-sequences.txt)

Use the version test262 is generated from (its property-escapes tests say which). What it makes:

  data     every set of code points, each as a count of ranges and then, for each range, how far it starts
           past the last one's end and how long it is less one, all as LEB128 numbers
  sets     where each set starts in data: the 30 general categories, then each script, then each script's
           extensions, then the binary properties, then the code points of the properties of strings
  gc_mask  for each general category's name, which of the 30 it is made of, as bits
  names    the names: a kind, the name's length, the name, and a number two bytes long, low first.
           Kinds: 1 a binary property (its set), 2 a general category (its gc_mask), 3 a script (its number),
           4 a property of strings (its number), 5 what can stand before = (0 gc, 1 script, 2 extensions)
  strings  for each property of strings, where its strings start in string_data: a count, then each string
           as how many code points it shares with the string before, how many follow, and those, all LEB128
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UCD = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'libs', 'web', 'build', 'ucd17')
OUT = os.path.join(ROOT, 'libs', 'web', 'js', 'uniprops.phi')

LEAVES = ['Cc', 'Cf', 'Cn', 'Co', 'Cs', 'Ll', 'Lm', 'Lo', 'Lt', 'Lu', 'Mc', 'Me', 'Mn', 'Nd', 'Nl', 'No',
          'Pc', 'Pd', 'Pe', 'Pf', 'Pi', 'Po', 'Ps', 'Sc', 'Sk', 'Sm', 'So', 'Zl', 'Zp', 'Zs']

# ECMAScript's table of binary properties, and where each one's data is
BINARY = {
    'PropList.txt': ['ASCII_Hex_Digit', 'Bidi_Control', 'Dash', 'Deprecated', 'Diacritic', 'Extender',
                     'Hex_Digit', 'IDS_Binary_Operator', 'IDS_Trinary_Operator', 'Ideographic', 'Join_Control',
                     'Logical_Order_Exception', 'Noncharacter_Code_Point', 'Pattern_Syntax',
                     'Pattern_White_Space', 'Quotation_Mark', 'Radical', 'Regional_Indicator',
                     'Sentence_Terminal', 'Soft_Dotted', 'Terminal_Punctuation', 'Unified_Ideograph',
                     'Variation_Selector', 'White_Space'],
    'DerivedCoreProperties.txt': ['Alphabetic', 'Case_Ignorable', 'Cased', 'Changes_When_Casefolded',
                                  'Changes_When_Casemapped', 'Changes_When_Lowercased',
                                  'Changes_When_Titlecased', 'Changes_When_Uppercased',
                                  'Default_Ignorable_Code_Point', 'Grapheme_Base', 'Grapheme_Extend',
                                  'ID_Continue', 'ID_Start', 'Lowercase', 'Math', 'Uppercase', 'XID_Continue',
                                  'XID_Start'],
    'DerivedNormalizationProps.txt': ['Changes_When_NFKC_Casefolded'],
    'emoji/emoji-data.txt': ['Emoji', 'Emoji_Component', 'Emoji_Modifier', 'Emoji_Modifier_Base',
                             'Emoji_Presentation', 'Extended_Pictographic'],
    'extracted/DerivedBinaryProperties.txt': ['Bidi_Mirrored'],
}

STRING_PROPS = ['Basic_Emoji', 'Emoji_Keycap_Sequence', 'RGI_Emoji_Modifier_Sequence', 'RGI_Emoji_Flag_Sequence',
                'RGI_Emoji_Tag_Sequence', 'RGI_Emoji_ZWJ_Sequence', 'RGI_Emoji']


def path(name):
    return os.path.join(UCD, name)


def lines(name):
    for line in open(path(name), encoding='utf-8'):
        line = line.split('#', 1)[0].strip()
        if line:
            yield [f.strip() for f in line.split(';')]


def span(text):
    if '..' in text:
        a, b = text.split('..')
        return int(a, 16), int(b, 16)
    return int(text, 16), int(text, 16)


def ranges(points):
    out = []
    for cp in sorted(points):
        if out and out[-1][1] + 1 == cp:
            out[-1][1] = cp
        else:
            out.append([cp, cp])
    return out


def leb(n, out):
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return


def categories():
    gc = {}
    first = None
    for f in lines('UnicodeData.txt'):
        cp = int(f[0], 16)
        if f[1].endswith(', First>'):
            first = cp
            continue
        if f[1].endswith(', Last>'):
            for c in range(first, cp + 1):
                gc[c] = f[2]
            continue
        gc[cp] = f[2]
    for cp in range(0x110000):
        gc.setdefault(cp, 'Cn')
    return gc


def scripts(gc):
    sc = {}
    for f in lines('Scripts.txt'):
        a, b = span(f[0])
        for c in range(a, b + 1):
            sc[c] = f[1]
    long_name = {}
    aliases = {}
    for f in lines('PropertyValueAliases.txt'):
        if f[0] == 'sc':
            long_name[f[1]] = f[2]
            aliases[f[2]] = f[1:]
    by_short = {s: l for s, l in long_name.items()}
    scx = {}
    for f in lines('ScriptExtensions.txt'):
        a, b = span(f[0])
        for c in range(a, b + 1):
            scx[c] = [by_short[s] for s in f[1].split()]
    names = sorted(aliases)
    sets = {n: set() for n in names}
    ext = {n: set() for n in names}
    for cp in range(0x110000):
        s = sc.get(cp, 'Unknown')
        sets[s].add(cp)
        for e in scx.get(cp, [s]):
            ext[e].add(cp)
    return names, aliases, sets, ext


def binary(gc):
    found = {}
    for name, props in BINARY.items():
        want = set(props)
        for f in lines(name):
            if f[1] in want:
                a, b = span(f[0])
                found.setdefault(f[1], set()).update(range(a, b + 1))
    found['ASCII'] = set(range(0x80))
    found['Any'] = set(range(0x110000))
    found['Assigned'] = {cp for cp in range(0x110000) if gc[cp] != 'Cn'}
    aliases = {'ASCII': ['ASCII'], 'Any': ['Any'], 'Assigned': ['Assigned']}
    for f in lines('PropertyAliases.txt'):
        if f[1] in found:
            aliases[f[1]] = f
    for name in found:
        assert name in aliases, name
        assert found[name], name
    return found, aliases


def string_props():
    points = {p: set() for p in STRING_PROPS}
    strings = {p: set() for p in STRING_PROPS}
    for name in ('emoji/emoji-sequences.txt', 'emoji/emoji-zwj-sequences.txt'):
        for f in lines(name):
            prop = f[1]
            if '..' in f[0]:
                a, b = span(f[0])
                cps = [(c,) for c in range(a, b + 1)]
            else:
                cps = [tuple(int(x, 16) for x in f[0].split())]
            for seq in cps:
                for p in (prop, 'RGI_Emoji'):
                    if len(seq) == 1:
                        points[p].add(seq[0])
                    else:
                        strings[p].add(seq)
    return points, strings


def gc_names():
    out = []
    for f in lines('PropertyValueAliases.txt'):
        if f[0] == 'gc':
            out.append(f[1:])
    return out


def main():
    gc = categories()
    script_names, script_aliases, sc_sets, scx_sets = scripts(gc)
    bin_sets, bin_aliases = binary(gc)
    str_points, str_strings = string_props()

    all_sets = []
    for leaf in LEAVES:
        all_sets.append({cp for cp, g in gc.items() if g == leaf})
    for n in script_names:
        all_sets.append(sc_sets[n])
    for n in script_names:
        all_sets.append(scx_sets[n])
    bin_order = sorted(bin_sets)
    for n in bin_order:
        all_sets.append(bin_sets[n])
    for n in STRING_PROPS:
        all_sets.append(str_points[n])

    data = []
    offsets = []
    for s in all_sets:
        offsets.append(len(data))
        rs = ranges(s)
        leb(len(rs), data)
        end = 0
        for lo, hi in rs:
            leb(lo - end, data)
            leb(hi - lo, data)
            end = hi + 1

    sc_base = len(LEAVES)
    bin_base = sc_base + 2 * len(script_names)
    str_base = bin_base + len(bin_order)

    names = []

    def name(kind, text, number):
        b = text.encode('ascii')
        names.extend([kind, len(b)] + list(b) + [number & 0xFF, number >> 8])

    for i, n in enumerate(bin_order):
        for a in dict.fromkeys(bin_aliases[n]):
            name(1, a, bin_base + i)
    masks = []
    for row in gc_names():
        members = [row[0]] if row[0] in LEAVES else None
        if members is None:
            members = [l for l in LEAVES if l.startswith(row[0])] if row[0] != 'LC' else ['Ll', 'Lt', 'Lu']
        mask = 0
        for m in members:
            mask |= 1 << LEAVES.index(m)
        for a in dict.fromkeys(row):
            name(2, a, len(masks))
        masks.append(mask)
    for i, n in enumerate(script_names):
        for a in dict.fromkeys(script_aliases[n]):
            name(3, a, i)
    for i, n in enumerate(STRING_PROPS):
        name(4, n, i)
    for i, group in enumerate([['General_Category', 'gc'], ['Script', 'sc'], ['Script_Extensions', 'scx']]):
        for a in group:
            name(5, a, i)

    str_data = []
    str_offsets = []
    for n in STRING_PROPS:
        str_offsets.append(len(str_data))
        seqs = sorted(str_strings[n])
        leb(len(seqs), str_data)
        last = ()
        for seq in seqs:
            same = 0
            while same < len(seq) - 1 and same < len(last) and seq[same] == last[same]:
                same += 1
            leb(same, str_data)
            leb(len(seq) - same, str_data)
            for c in seq[same:]:
                leb(c, str_data)
            last = seq

    version = open(path('Scripts.txt'), encoding='utf-8').readline().strip('# \n').replace('Scripts-', '').replace('.txt', '')

    def table(kind, label, values, per_line):
        out = ['\t%s %s:' % (kind, label)]
        for i in range(0, len(values), per_line):
            out.append('\t\t' + ' '.join(str(v) for v in values[i:i + per_line]))
        out[-1] += ';'
        return out

    text = ['# Made by tools/web/js_gen_props.py from Unicode %s\'s character database: run that to make it again.' % version,
            '# What each table holds is told at the start of that script.',
            '',
            'phi.JsUniProps:Library',
            '{',
            '\tconst u32 SCRIPT_SETS: %d;' % sc_base,
            '\tconst u32 SCRIPTS: %d;' % len(script_names),
            '\tconst u32 STRING_SETS: %d;' % str_base,
            '']
    text += table('u32', 'sets', offsets, 16)
    text += table('u32', 'gc_mask', masks, 8)
    text += table('u32', 'strings', str_offsets, 8)
    text += table('u8', 'names', names, 32)
    text += table('u8', 'data', data, 32)
    text += table('u8', 'string_data', str_data, 32)
    text += ['}', '']
    open(OUT, 'w', newline='\n').write('\n'.join(text))
    print('%s: Unicode %s, %d sets, %d bytes of sets, %d of strings, %d of names'
          % (OUT, version, len(all_sets), len(data), len(str_data), len(names)))


main()
