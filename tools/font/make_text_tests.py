"""Makes libs/font/tests/text/cases.bin (with cases.txt): the cases test_text runs fontlib's simple text
against, checked with the rules in text_reference.py, whose glyphs and advances must be HarfBuzz's (with
shaping turned off) on every case with one font.

    python3 -P tools/font/make_text_tests.py

The format (little-endian):

    u32 count, then for each:
      u8 name length, name, u8 font count, then for each font: u8 kind (0: a path, from libs/font, u8
      length then the path; 1: bytes, u32 length then the bytes), u32 ppem;
      u32 canvas width, height, u8 background (0 white, 1 noise, 2 transparent black), i32 x (64ths of
      a pixel), i32 y (pixels), u32 color, u32 text length, the text (UTF-8, perhaps malformed);
      then what fontlib must give: i32 its width (Measure), i32 the pen after Draw, u32 the CRC-32 of
      the canvas after it (each pixel as 4 bytes, little-endian)
"""
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import text_reference as X  # noqa: E402
import make_font_tests as M  # noqa: E402

OUT = os.path.join(M.LIB, 'tests', 'text')
SHAPING_OFF = {f: False for f in ('kern', 'liga', 'clig', 'calt', 'ccmp', 'locl', 'mark', 'mkmk', 'rlig',
                                  'rclt', 'dlig', 'frac', 'numr', 'dnom')}


def background(kind, w, h):
    if kind == 0:
        return [0xFFFFFFFF] * (w * h)
    if kind == 2:
        return [0] * (w * h)
    return [0xFF000000 | ((i * 0x9E3779B1 & 0xFFFFFFFF) >> 8) for i in range(w * h)]


def harfbuzz(data, ppem, text):
    import uharfbuzz as hb
    if not text:
        return []
    font = hb.Font(hb.Face(hb.Blob(data)))
    font.scale = (ppem * 64, ppem * 64)
    buf = hb.Buffer()
    buf.add_str(text.decode('utf-8', errors='replace'))
    buf.guess_segment_properties()
    buf.direction = 'ltr'
    hb.shape(font, buf, SHAPING_OFF)
    return [(i.codepoint, p.x_advance) for i, p in zip(buf.glyph_infos, buf.glyph_positions)]


def cases():
    liberation = open(os.path.join(M.FONTS, M.LIBERATION), 'rb').read()
    lib = (0, 'tests/fonts/' + M.LIBERATION, liberation)
    made = dict((n, d) for n, d, r in M.made_cases())
    squares = (1, None, made['cmap-format-4'])
    emoji = (1, None, made['cmap-format-12'])
    texts = {
        'ascii': b'Hello, world! 0123456789',
        'beyond-437': 'Ünïcödé — “quotes” ‘single’ € Ω≈ç√∫ ﬁ ½ ™ …'.encode(),
        'greek-cyrillic': 'Ελληνικά Кириллица ĂăĐđŁł'.encode(),
        'missing-glyphs': '日本語 ✓ ★'.encode(),
        'malformed-utf8': b'ok \xff \xc3 \xe2\x82 \xf0\x9f\x98 \xed\xa0\x80 \xc0\xaf end',
        'empty': b'',
    }
    out = []
    for name, text in texts.items():
        for ppem, bg in ((12, 0), (19, 1), (33, 2)):
            out.append(('%s-%d' % (name, ppem), [(lib, ppem)], 220, 48, bg, 3 * 64 + 17, 36, 0xFF203040, text))
    out.append(('half-transparent-color', [(lib, 16)], 200, 30, 1, 0, 22, 0x80C02010, texts['beyond-437']))
    out.append(('off-the-left', [(lib, 24)], 80, 40, 0, -50 * 64, 30, 0xFF000000, texts['ascii']))
    out.append(('off-the-right', [(lib, 24)], 80, 40, 0, 40 * 64, 30, 0xFF000000, texts['ascii']))
    out.append(('off-the-top', [(lib, 40)], 120, 30, 1, 64, 12, 0xFF0000FF, b'Tlgy'))
    out.append(('off-the-bottom', [(lib, 40)], 120, 30, 1, 64, 45, 0xFF0000FF, b'Tlgy'))
    out.append(('fallback-squares-then-liberation', [(squares, 14), (lib, 14)], 200, 30, 0, 64, 22, 0xFF000000,
                'AB ab Ω 日'.encode()))
    out.append(('fallback-liberation-then-emoji', [(lib, 14), (emoji, 20)], 200, 30, 0, 64, 22, 0xFF000000,
                'A \U0001F600 B \U00010010'.encode()))
    out.append(('fallback-none-has-it', [(squares, 14), (emoji, 14)], 120, 30, 0, 64, 22, 0xFF000000,
                '日本'.encode()))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    blob = bytearray()
    lines = ['# made by tools/font/make_text_tests.py: what fontlib must make of each run of text']
    all_cases = cases()
    blob += struct.pack('<I', len(all_cases))
    checked = 0
    for name, fonts, w, h, bg, x, y, color, text in all_cases:
        loaded = [X.Font(data, ppem) for (kind, path, data), ppem in fonts]
        if len(fonts) == 1:
            mine = [(g, a) for _, g, a in X.glyphs(loaded, text)]
            theirs = harfbuzz(fonts[0][0][2], fonts[0][1], text)
            if mine != theirs:
                sys.exit('%s: the glyphs and advances %s differ from HarfBuzz\'s %s' % (name, mine[:6], theirs[:6]))
            checked += 1
        width = X.measure(loaded, text)
        canvas = background(bg, w, h)
        pen = X.draw(loaded, text, canvas, w, h, x, y, color)
        crc = zlib.crc32(struct.pack('<%dI' % len(canvas), *canvas))
        nb = name.encode()
        blob += struct.pack('<B', len(nb)) + nb + struct.pack('<B', len(fonts))
        for (kind, path, data), ppem in fonts:
            if kind == 0:
                pb = path.encode()
                blob += struct.pack('<BB', 0, len(pb)) + pb
            else:
                blob += struct.pack('<BI', 1, len(data)) + data
            blob += struct.pack('<I', ppem)
        blob += struct.pack('<IIBiiII', w, h, bg, x, y, color, len(text)) + text
        blob += struct.pack('<iiI', width, pen, crc)
        lines.append('%-36s width %6d, pen %6d' % (name, width, pen))
    with open(os.path.join(OUT, 'cases.bin'), 'wb') as f:
        f.write(blob)
    with open(os.path.join(OUT, 'cases.txt'), 'w', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    print('cases.bin: %d cases, %d bytes; %d with one font the same as HarfBuzz' % (len(all_cases), len(blob), checked))


if __name__ == '__main__':
    main()
