#!/usr/bin/env python3
"""Makes encodinglib's test cases, with Python's codecs as the outside decoder.

    python3 -I tools/encoding/make_cases.py

Writes libs/encoding/tests/cases.bin and cases.txt: for every single-byte encoding, all 256 bytes
decoded; UTF-8 and UTF-16 with every kind of bad sequence the Encoding standard names; byte-order
marks; and labels. Each case's expected UTF-8 is Python's decoding with errors='replace' (which, for
UTF-8 and UTF-16, puts one U+FFFD where the standard does), less the three places make_tables.py
says WHATWG and Python differ, which take WHATWG's.

The format of cases.bin (little-endian): u32 count, then each: u8 label length, label, u32 length,
the bytes, u32 length, the UTF-8 expected.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_tables import SINGLE, table

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def expect_single(name, data):
    t = table(name, dict(SINGLE)[name])
    return ''.join(chr(b) if b < 0x80 else (chr(t[b - 0x80]) if t[b - 0x80] else '�') for b in data).encode('utf-8')


def main():
    cases = []
    every = bytes(range(256))
    for name, _ in SINGLE:
        cases.append((name, every, expect_single(name, every)))
    utf8 = [b'plain ascii', 'café φ € \U0001F600'.encode(), b'\x80', b'\xc3', b'\xc3(', b'\xe2\x82', b'\xe2\x82(', b'\xf0\x9f\x98',
            b'\xed\xa0\x80', b'\xc0\xaf', b'\xf4\x90\x80\x80', b'\xff\x80', b'\xe0\x80\xaf', b'a\xf1\x80\x80\xe1\x80\xc2b\x80c',
            b'\xef\xbb\xbfwith a byte-order mark']
    for data in utf8:
        if data.startswith(b'\xef\xbb\xbf'):
            want = data[3:].decode('utf-8', 'replace').encode()
        else:
            want = data.decode('utf-8', 'replace').encode()
        cases.append(('utf-8', data, want))
    utf16 = ['hello é中\U0001F600'.encode('utf-16-le'), b'\x00\xd8a\x00', b'\x00\xdc', b'\x3d\xd8\x00\xde', b'a\x00b',
             b'\x00\xd8']
    for data in utf16:
        cases.append(('utf-16le', data, data.decode('utf-16-le', 'replace').encode()))
        be = bytes(b for i in range(0, len(data) - 1, 2) for b in (data[i + 1], data[i])) + data[len(data) & ~1:]
        cases.append(('utf-16be', be, be.decode('utf-16-be', 'replace').encode()))
    cases.append(('utf-16le', b'\xfe\xff\x00a', 'a'.encode()))          # a byte-order mark overrides the label
    cases.append(('x-user-defined', b'a\x80\xff', ('a' + chr(0xF780) + chr(0xF7FF)).encode()))
    cases.append(('iso-2022-kr', b'anything', '�'.encode()))
    cases.append(('replacement', b'', b''))
    for label, name in (('  LATIN1\t', 'windows-1252'), ('ascii', 'windows-1252'), ('iso-8859-9', 'windows-1254'), ('KOI8', 'KOI8-R'),
                        ('cyrillic', 'ISO-8859-5'), ('tis-620', 'windows-874'), ('x-mac-ukrainian', 'x-mac-cyrillic')):
        cases.append((label, every, expect_single(name, every)))
    out = bytearray(struct.pack('<I', len(cases)))
    lines = []
    for label, data, want in cases:
        lb = label.encode()
        out += struct.pack('<B', len(lb)) + lb + struct.pack('<I', len(data)) + data + struct.pack('<I', len(want)) + want
        lines.append(f'{label!r:24} {len(data):4} bytes to {len(want):4}')
    os.makedirs(os.path.join(ROOT, 'libs', 'encoding', 'tests'), exist_ok=True)
    open(os.path.join(ROOT, 'libs', 'encoding', 'tests', 'cases.bin'), 'wb').write(out)
    open(os.path.join(ROOT, 'libs', 'encoding', 'tests', 'cases.txt'), 'w', newline='\n').write(
        '# made by tools/encoding/make_cases.py: each case, decoded by Python\n' + '\n'.join(lines) + '\n')
    print(len(cases), 'cases')


if __name__ == '__main__':
    main()
