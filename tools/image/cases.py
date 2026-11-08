"""The cases file that each of imagelib's format tests reads, written for make_bmp_tests.py,
make_png_tests.py and make_jpeg_tests.py.

The format of cases.bin (every number little-endian):

    u32 count, then for each:
      u8 group, u8 kind, u8 name length, name,
      u32 max_pixels (0: the default),
      kind 0, a file:      u8 path length, path (from libs/image)
      kind 1, bytes:       u32 length, bytes
      kind 2, a cut:       u32 case, u32 length       (the first length bytes of an earlier case)
      kind 3, changes:     u32 case, u16 count, then count of: u32 offset, u8 value
      u8 ok; if ok: u32 width, u32 height, u32 CRC-32 of the pixels (each as 4 bytes, B G R A,
      top row first); if not: u8 length, the reason

Groups 2 and 3 are always cut and fuzz cases, which cases.txt sums up by the case they come from.
"""
import os
import struct
import zlib

CUT, FUZZ = 2, 3


def as_rgba(w, h, px):
    import numpy as np
    a = np.array(px, dtype=np.uint32).reshape(h, w)
    return np.stack([(a >> 16) & 255, (a >> 8) & 255, a & 255, a >> 24], axis=2).astype(np.uint8)


class Cases:
    def __init__(self, decode, max_pixels, out, maker, group_names):
        self.decode = decode            # the rules: decode(data, max_pixels) -> (ok, result)
        self.max_pixels = max_pixels    # the default limit
        self.out = out                  # the folder cases.bin and cases.txt go in
        self.maker = maker              # the script's name, for cases.txt
        self.group_names = group_names
        self.list = []                  # (group, kind, name, max_pixels, payload, data, verdict)

    def add(self, group, kind, name, data, max_pixels=0, payload=None):
        ok, result = self.decode(data, max_pixels or self.max_pixels)
        self.list.append((group, kind, name, max_pixels, payload, data, (ok, result)))
        return len(self.list) - 1

    def write(self):
        out = bytearray(struct.pack('<I', len(self.list)))
        lines = ['# made by tools/image/%s: what imagelib must make of each case in cases.bin' % self.maker,
                 '# (the cut and fuzz cases are summed up by the case they come from, at the end)']
        summary = {}
        for group, kind, name, max_pixels, payload, data, (ok, result) in self.list:
            nb = name.encode()
            out += struct.pack('<BBB', group, kind, len(nb)) + nb + struct.pack('<I', max_pixels)
            if kind == 0:
                p = payload.encode()
                out += struct.pack('<B', len(p)) + p
            elif kind == 1:
                out += struct.pack('<I', len(data)) + data
            elif kind == 2:
                out += struct.pack('<II', *payload)
            else:
                source, changes = payload
                out += struct.pack('<IH', source, len(changes))
                for at, v in changes:
                    out += struct.pack('<IB', at, v)
            if ok:
                w, h, px = result
                crc = zlib.crc32(struct.pack('<%dI' % len(px), *px))
                out += struct.pack('<BIII', 1, w, h, crc)
                verdict = 'ok, %d by %d' % (w, h)
            else:
                rb = result.encode()
                out += struct.pack('<BB', 0, len(rb)) + rb
                verdict = 'refused: ' + result
            if group in (CUT, FUZZ):
                key = (self.group_names[group], self.list[payload[0]][2])
                tally = summary.setdefault(key, [0, 0])
                tally[0 if ok else 1] += 1
            else:
                lines.append('%-5s %-40s %7d bytes  %s' % (self.group_names[group], name, len(data), verdict))
        for (group, source), (good, bad) in summary.items():
            lines.append('%-5s %-40s %4d ok, %4d refused' % (group, source, good, bad))
        with open(os.path.join(self.out, 'cases.bin'), 'wb') as f:
            f.write(out)
        with open(os.path.join(self.out, 'cases.txt'), 'w', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')
        return len(out)

    def summary(self):
        groups = {}
        for group, _, _, _, _, _, (ok, _) in self.list:
            g = groups.setdefault(self.group_names[group], [0, 0])
            g[0 if ok else 1] += 1
        return ', '.join('%s %d ok, %d refused' % (k, v[0], v[1]) for k, v in groups.items())
