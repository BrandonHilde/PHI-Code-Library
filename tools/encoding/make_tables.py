#!/usr/bin/env python3
"""Writes libs/encoding/encodinglib/tables.phi: the WHATWG Encoding standard's single-byte encodings
(bytes 0x80 to 0xFF of each, as Unicode code points) and its labels.

    python3 -I tools/encoding/make_tables.py

The single-byte tables are Python's codecs for them, made to agree with WHATWG's indexes where they're
known to differ: windows-* map bytes 0x80 to 0x9F that have no character to the C1 control of the same
number, as WHATWG's indexes do; KOI8-U's 0xAE and 0xBE are U+045E and U+040E (WHATWG's is KOI8-RU's);
windows-1255's 0xCA is U+05BA. Anything else WHATWG maps that Python doesn't stays without a character
(decoded as U+FFFD). The labels are WHATWG's, as they're listed in the standard (encoding.spec.whatwg.org).
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# (WHATWG name, Python codec), in the order the library numbers them, from 4
SINGLE = [('IBM866', 'cp866'), ('ISO-8859-2', 'iso8859_2'), ('ISO-8859-3', 'iso8859_3'), ('ISO-8859-4', 'iso8859_4'),
          ('ISO-8859-5', 'iso8859_5'), ('ISO-8859-6', 'iso8859_6'), ('ISO-8859-7', 'iso8859_7'), ('ISO-8859-8', 'iso8859_8'),
          ('ISO-8859-8-I', 'iso8859_8'), ('ISO-8859-10', 'iso8859_10'), ('ISO-8859-13', 'iso8859_13'), ('ISO-8859-14', 'iso8859_14'),
          ('ISO-8859-15', 'iso8859_15'), ('ISO-8859-16', 'iso8859_16'), ('KOI8-R', 'koi8_r'), ('KOI8-U', 'koi8_u'),
          ('macintosh', 'mac_roman'), ('windows-874', 'cp874'), ('windows-1250', 'cp1250'), ('windows-1251', 'cp1251'),
          ('windows-1252', 'cp1252'), ('windows-1253', 'cp1253'), ('windows-1254', 'cp1254'), ('windows-1255', 'cp1255'),
          ('windows-1256', 'cp1256'), ('windows-1257', 'cp1257'), ('windows-1258', 'cp1258'), ('x-mac-cyrillic', 'mac_cyrillic')]
# the library's own numbers for the rest
OTHER = ['UTF-8', 'UTF-16BE', 'UTF-16LE', 'x-user-defined']
LABELS = {
    'UTF-8': 'unicode-1-1-utf-8 unicode11utf8 unicode20utf8 utf-8 utf8 x-unicode20utf8',
    'IBM866': '866 cp866 csibm866 ibm866',
    'ISO-8859-2': 'csisolatin2 iso-8859-2 iso-ir-101 iso8859-2 iso88592 iso_8859-2 iso_8859-2:1987 l2 latin2',
    'ISO-8859-3': 'csisolatin3 iso-8859-3 iso-ir-109 iso8859-3 iso88593 iso_8859-3 iso_8859-3:1988 l3 latin3',
    'ISO-8859-4': 'csisolatin4 iso-8859-4 iso-ir-110 iso8859-4 iso88594 iso_8859-4 iso_8859-4:1988 l4 latin4',
    'ISO-8859-5': 'csisolatincyrillic cyrillic iso-8859-5 iso-ir-144 iso8859-5 iso88595 iso_8859-5 iso_8859-5:1988',
    'ISO-8859-6': 'arabic asmo-708 csiso88596e csiso88596i csisolatinarabic ecma-114 iso-8859-6 iso-8859-6-e iso-8859-6-i iso-ir-127 iso8859-6 iso88596 iso_8859-6 iso_8859-6:1987',
    'ISO-8859-7': 'csisolatingreek ecma-118 elot_928 greek greek8 iso-8859-7 iso-ir-126 iso8859-7 iso88597 iso_8859-7 iso_8859-7:1987 sun_eu_greek',
    'ISO-8859-8': 'csiso88598e csisolatinhebrew hebrew iso-8859-8 iso-8859-8-e iso-ir-138 iso8859-8 iso88598 iso_8859-8 iso_8859-8:1988 visual',
    'ISO-8859-8-I': 'csiso88598i iso-8859-8-i logical',
    'ISO-8859-10': 'csisolatin6 iso-8859-10 iso-ir-157 iso8859-10 iso885910 l6 latin6',
    'ISO-8859-13': 'iso-8859-13 iso8859-13 iso885913',
    'ISO-8859-14': 'iso-8859-14 iso8859-14 iso885914',
    'ISO-8859-15': 'csisolatin9 iso-8859-15 iso8859-15 iso885915 iso_8859-15 l9',
    'ISO-8859-16': 'iso-8859-16',
    'KOI8-R': 'cskoi8r koi koi8 koi8-r koi8_r',
    'KOI8-U': 'koi8-ru koi8-u',
    'macintosh': 'csmacintosh mac macintosh x-mac-roman',
    'windows-874': 'dos-874 iso-8859-11 iso8859-11 iso885911 tis-620 windows-874',
    'windows-1250': 'cp1250 windows-1250 x-cp1250',
    'windows-1251': 'cp1251 windows-1251 x-cp1251',
    'windows-1252': 'ansi_x3.4-1968 ascii cp1252 cp819 csisolatin1 ibm819 iso-8859-1 iso-ir-100 iso8859-1 iso88591 iso_8859-1 iso_8859-1:1987 l1 latin1 us-ascii windows-1252 x-cp1252',
    'windows-1253': 'cp1253 windows-1253 x-cp1253',
    'windows-1254': 'cp1254 csisolatin5 iso-8859-9 iso-ir-148 iso8859-9 iso88599 iso_8859-9 iso_8859-9:1989 l5 latin5 windows-1254 x-cp1254',
    'windows-1255': 'cp1255 windows-1255 x-cp1255',
    'windows-1256': 'cp1256 windows-1256 x-cp1256',
    'windows-1257': 'cp1257 windows-1257 x-cp1257',
    'windows-1258': 'cp1258 windows-1258 x-cp1258',
    'x-mac-cyrillic': 'x-mac-cyrillic x-mac-ukrainian',
    'UTF-16BE': 'unicodefffe utf-16be',
    'UTF-16LE': 'csunicode iso-10646-ucs-2 ucs-2 unicode unicodefeff utf-16 utf-16le',
    'x-user-defined': 'x-user-defined',
    'replacement': 'csiso2022kr hz-gb-2312 iso-2022-cn iso-2022-cn-ext iso-2022-kr replacement',
}


def table(name, codec):
    out = []
    for b in range(0x80, 0x100):
        try:
            cp = ord(bytes([b]).decode(codec))
        except UnicodeDecodeError:
            cp = 0
        if cp == 0 and name.startswith('windows-') and b < 0xA0:
            cp = b
        out.append(cp)
    if name == 'KOI8-U':
        out[0xAE - 0x80], out[0xBE - 0x80] = 0x045E, 0x040E
    if name == 'windows-1255':
        out[0xCA - 0x80] = 0x05BA
    return out


def main():
    numbers = {'replacement': 0, 'UTF-8': 1, 'UTF-16BE': 2, 'UTF-16LE': 3, 'x-user-defined': 4 + len(SINGLE)}
    for i, (name, _) in enumerate(SINGLE):
        numbers[name] = 4 + i
    rows = []
    for name, codec in SINGLE:
        t = table(name, codec)
        rows.append('\t\t' + ' '.join(str(v) for v in t[:64]))
        rows.append('\t\t' + ' '.join(str(v) for v in t[64:]))
    labels = []
    for name, ls in LABELS.items():
        for l in ls.split():
            labels.append((l, numbers[name]))
    labels.sort()
    names = ['replacement', 'UTF-8', 'UTF-16BE', 'UTF-16LE'] + [n for n, _ in SINGLE] + ['x-user-defined']
    text = '''# The WHATWG Encoding standard's single-byte encodings and labels, made by
# tools/encoding/make_tables.py (which says where they come from). Don't change it by hand.

phi.EncTables:Library
{
	# each single-byte encoding's bytes 0x80 to 0xFF, as code points (0: no character), from encoding 4
	u16 single:
''' + '\n'.join(rows) + ''';
	# every label, sorted, and the encoding it names
	str labels: ''' + ' '.join("'" + l + "'" for l, _ in labels) + ''';
	u8 label_to: ''' + ' '.join(str(n) for _, n in labels) + ''';
	# each encoding's name, by number
	str names: ''' + ' '.join("'" + n + "'" for n in names) + ''';
}
'''
    path = os.path.join(ROOT, 'libs', 'encoding', 'encodinglib', 'tables.phi')
    with open(path, 'w', newline='\n') as f:
        f.write(text)
    print('wrote', path, len(labels), 'labels,', len(SINGLE), 'single-byte encodings')


if __name__ == '__main__':
    main()
