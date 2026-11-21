#!/usr/bin/env python3
"""Draws scenes with vectorlib and with macOS's own Quartz (CoreGraphics), and compares them.

    python3 -I tools/vector/check_svg.py [PHI] [--keep DIR]     PHI: the compiler (else $PHI_EXE)

macOS only: tools/vector/quartz.swift is built with swiftc. Each scene is written twice from one
description: in tools/vector/scene/scene.phi's line format for vectorlib, and for quartz.swift, whose
paths this script makes absolute itself (SVG's path data read here, its arcs made cubics by SVG's
own formulas, F.6), so the comparison is of filling, outlining, gradients and transforms. Quartz
has no repeating gradients, so a scene that repeats or reflects one is drawn by vectorlib alone.

Renderers smooth edges each their own way, so the two are compared loosely: how many pixels differ
by more than 64 in any channel (a pixel one has inside and the other outside), and the mean
difference. --keep DIR saves each scene side by side (vectorlib left, Quartz right), to look at.

(ImageMagick's own SVG renderer, MSVG, was tried first and isn't a reference: it repeats a padded
gradient, tiles a radial one, and cuts a miter join flat under its limit.)
"""
import os
import shutil
import subprocess
import sys
import math
import re
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# each scene: a list of (command, ...) in scene.phi's words
SCENES = {
    'triangle': [('color', 0xFFE5484D), ('path', 'M8 56 L32 6 L58 50 Z'), ('fill', 0)],
    'star, nonzero': [('color', 0xFF2F6FE4), ('path', 'M32 4 L50 58 L4 22 L60 22 L14 58 Z'), ('fill', 0)],
    'star, even-odd': [('color', 0xFF2F6FE4), ('path', 'M32 4 L50 58 L4 22 L60 22 L14 58 Z'), ('fill', 1)],
    'circle by arcs': [('color', 0xFF30A46C), ('path', 'M32 8 A24 24 0 0 1 32 56 A24 24 0 0 1 32 8 Z'), ('fill', 0)],
    'arc flags': [('color', 0xFF000000), ('path', 'M12 20 A12 8 0 0 0 36 20'), ('stroke', 2, 0, 0, 4),
                  ('color', 0xFFE5484D), ('path', 'M12 44 A12 8 0 1 1 36 44'), ('stroke', 2, 0, 0, 4),
                  ('color', 0xFF2F6FE4), ('path', 'M40 30 A10 18 30 0 1 58 50'), ('stroke', 2, 0, 0, 4)],
    'miter join': [('color', 0xFF000000), ('path', 'M8 56 L32 12 L56 56'), ('stroke', 8, 0, 0, 4)],
    'bevel join': [('color', 0xFF000000), ('path', 'M8 56 L32 12 L56 56'), ('stroke', 8, 2, 0, 4)],
    'round join and caps': [('color', 0xFF000000), ('path', 'M8 56 L32 12 L56 56'), ('stroke', 8, 1, 1, 4)],
    'caps': [('color', 0xFF000000), ('path', 'M16 12 L48 12'), ('stroke', 8, 0, 0, 4),
             ('path', 'M16 32 L48 32'), ('stroke', 8, 0, 1, 4), ('path', 'M16 52 L48 52'), ('stroke', 8, 0, 2, 4)],
    'curves outlined': [('color', 0xFF8E4EC6), ('path', 'M6 40 C6 4 58 4 58 40 Q32 70 6 40 Z'), ('stroke', 3, 1, 0, 4)],
    'dashed circle': [('dash', 0, 8, 4), ('color', 0xFFF08A24), ('path', 'M32 10 A22 22 0 1 1 31.99 10 Z'), ('stroke', 4, 0, 0, 4)],
    'turned and scaled': [('matrix', 0.866, 0.5, -0.75, 1.299, 32, 10), ('color', 0xFF12A594), ('path', 'M0 0 h24 v20 h-24 z'), ('fill', 0)],
    'linear gradient': [('linear', 8, 0, 56, 30, 0), ('stop', 0, 0xFFE5484D), ('stop', 0.5, 0xFFF5D90A), ('stop', 1, 0xFF2F6FE4),
                        ('path', 'M4 4 h56 v56 h-56 z'), ('fill', 0)],
    'gradient outline': [('linear', 0, 0, 64, 64, 0), ('stop', 0, 0xFF000000), ('stop', 1, 0xFF2F6FE4),
                         ('path', 'M10 10 L54 20 L20 54 Z'), ('stroke', 6, 1, 1, 4)],
    'reflected gradient': [('linear', 20, 0, 36, 0, 2), ('stop', 0, 0xFF000000), ('stop', 1, 0xFFFFFFFF),
                           ('path', 'M4 4 h56 v56 h-56 z'), ('fill', 0)],
    'radial gradient': [('radial', 32, 32, 26, 22, 24, 0), ('stop', 0, 0xFFFFFFFF), ('stop', 1, 0xFF2F6FE4),
                        ('path', 'M4 4 h56 v56 h-56 z'), ('fill', 0)],
}

JOINS = ['miter', 'round', 'bevel']
CAPS = ['butt', 'round', 'square']
SPREADS = ['pad', 'repeat', 'reflect']


def scene_text(cmds):
    out = ['size 64 64']
    for c in cmds:
        k = c[0]
        if k in ('color',):
            out.append(f'color 0x{c[1]:08X}')
        elif k == 'stop':
            out.append(f'stop {c[1]} 0x{c[2]:08X}')
        else:
            out.append(k + ' ' + ' '.join(str(v) for v in c[1:]))
    return '\n'.join(out) + '\n'


def rgb(c):
    return f'#{c & 0xFFFFFF:06x}', ((c >> 24) & 255) / 255


def svg_path(d):
    """SVG path data as absolute M, L, C and Z steps, quadratics and arcs as cubics."""
    tokens = re.findall(r'[A-Za-z]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?', d)
    out, i = [], 0
    x = y = sx = sy = 0.0
    last_c = last_q = None
    cmd = None

    def num():
        nonlocal i
        v = float(tokens[i]); i += 1
        return v
    while i < len(tokens):
        if re.match(r'[A-Za-z]', tokens[i]):
            cmd = tokens[i]; i += 1
            if cmd in 'Zz':
                out.append(('Z',)); x, y = sx, sy; last_c = last_q = None
                continue
        rel = cmd.islower()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        c = cmd.upper()
        if c == 'M':
            x, y = ox + num(), oy + num(); sx, sy = x, y
            out.append(('M', x, y)); cmd = 'l' if rel else 'L'; last_c = last_q = None
        elif c == 'L':
            x, y = ox + num(), oy + num(); out.append(('L', x, y)); last_c = last_q = None
        elif c == 'H':
            x = ox + num(); out.append(('L', x, y)); last_c = last_q = None
        elif c == 'V':
            y = oy + num(); out.append(('L', x, y)); last_c = last_q = None
        elif c in 'CS':
            if c == 'C':
                x1, y1 = ox + num(), oy + num()
            else:
                x1, y1 = (2 * x - last_c[0], 2 * y - last_c[1]) if last_c else (x, y)
            x2, y2, ex, ey = ox + num(), oy + num(), ox + num(), oy + num()
            out.append(('C', x1, y1, x2, y2, ex, ey)); last_c = (x2, y2); last_q = None; x, y = ex, ey
        elif c in 'QT':
            if c == 'Q':
                qx, qy = ox + num(), oy + num()
            else:
                qx, qy = (2 * x - last_q[0], 2 * y - last_q[1]) if last_q else (x, y)
            ex, ey = ox + num(), oy + num()
            out.append(('C', x + 2 / 3 * (qx - x), y + 2 / 3 * (qy - y), ex + 2 / 3 * (qx - ex), ey + 2 / 3 * (qy - ey), ex, ey))
            last_q = (qx, qy); last_c = None; x, y = ex, ey
        elif c == 'A':
            rx, ry, rot, large, sweep = abs(num()), abs(num()), num(), num() != 0, num() != 0
            ex, ey = ox + num(), oy + num()
            out.extend(arc(x, y, rx, ry, rot, large, sweep, ex, ey)); x, y = ex, ey; last_c = last_q = None
    return out


def arc(x1, y1, rx, ry, rot, large, sweep, x2, y2):
    """SVG 1.1, F.6.5 and F.6.6: endpoints to center, then cubics of a quarter turn at most."""
    if (x1, y1) == (x2, y2):
        return []
    if rx == 0 or ry == 0:
        return [('L', x2, y2)]
    phi = math.radians(rot)
    cp, sp = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(num, 0) / den) * (-1 if large == sweep else 1)
    cxp, cyp = co * rx * y1p / ry, -co * ry * x1p / rx
    cx, cy = cp * cxp - sp * cyp + (x1 + x2) / 2, sp * cxp + cp * cyp + (y1 + y2) / 2

    def angle(ux, uy, vx, vy):
        a = math.acos(max(-1, min(1, (ux * vx + uy * vy) / (math.hypot(ux, uy) * math.hypot(vx, vy)))))
        return -a if ux * vy - uy * vx < 0 else a
    t1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dt = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    n = max(1, math.ceil(abs(dt) / (math.pi / 2) - 1e-9))
    step = dt / n
    k = 4 / 3 * math.tan(step / 4)
    out = []

    def pt(t, ox=0.0, oy=0.0):
        ex, ey = rx * math.cos(t) + ox, ry * math.sin(t) + oy
        return cp * ex - sp * ey + cx, sp * ex + cp * ey + cy
    for i in range(n):
        a, b = t1 + i * step, t1 + (i + 1) * step
        c1 = (cp * (rx * math.cos(a) - k * rx * math.sin(a)) - sp * (ry * math.sin(a) + k * ry * math.cos(a)) + cx,
              sp * (rx * math.cos(a) - k * rx * math.sin(a)) + cp * (ry * math.sin(a) + k * ry * math.cos(a)) + cy)
        c2 = (cp * (rx * math.cos(b) + k * rx * math.sin(b)) - sp * (ry * math.sin(b) - k * ry * math.cos(b)) + cx,
              sp * (rx * math.cos(b) + k * rx * math.sin(b)) + cp * (ry * math.sin(b) - k * ry * math.cos(b)) + cy)
        e = pt(b)
        out.append(('C',) + c1 + c2 + e)
    out[-1] = out[-1][:5] + (x2, y2)
    return out


def scene_quartz(cmds):
    out = ['size 64 64']
    for c in cmds:
        k = c[0]
        if k == 'color':
            out.append(f'color 0x{c[1]:08X}')
        elif k == 'stop':
            out.append(f'stop {c[1]} 0x{c[2]:08X}')
        elif k == 'path':
            out.append('path')
            for step in svg_path(c[1]):
                out.append(' '.join([step[0]] + [repr(float(v)) for v in step[1:]]))
        else:
            out.append(k + ' ' + ' '.join(str(v) for v in c[1:]))
    return '\n'.join(out) + '\n'


def repeats(cmds):
    return any((c[0] == 'linear' and c[5] != 0) or (c[0] == 'radial' and c[6] != 0) for c in cmds)


def main():
    args = sys.argv[1:]
    keep = None
    if '--keep' in args:
        i = args.index('--keep')
        keep = args[i + 1]
        del args[i:i + 2]
        os.makedirs(keep, exist_ok=True)
    phi = args[0] if args else os.environ.get('PHI_EXE')
    if not phi:
        sys.exit('give the phi compiler, or set PHI_EXE')
    magick = shutil.which('magick')
    if sys.platform != 'darwin':
        sys.exit('this compares with Quartz, which is macOS\'s')
    host = {'darwin': 'macos', 'win32': 'windows64'}.get(sys.platform, 'linux64')
    work = tempfile.mkdtemp(prefix='check_svg_', dir=os.path.expanduser('~'))
    try:
        subprocess.run([phi, 'build', os.path.join(ROOT, 'libs', 'vector', 'vectorlib.phi'), '--library', '-o', work],
                       check=True, stdout=subprocess.DEVNULL)
        shutil.copy(os.path.join(ROOT, 'tools', 'vector', 'scene', 'scene.phi'), work)
        subprocess.run([phi, 'build', os.path.join(work, 'scene.phi'), '--target', host, '-o', work],
                       check=True, stdout=subprocess.DEVNULL)
        exe = os.path.join(work, 'scene')
        quartz = os.path.join(work, 'quartz')
        subprocess.run(['swiftc', '-O', os.path.join(ROOT, 'tools', 'vector', 'quartz.swift'), '-o', quartz], check=True)
        print(f'{"scene":24} {"pixels off by > 64":>20} {"mean difference":>16}')
        for name, cmds in SCENES.items():
            sc, qsc, mine, theirs = (os.path.join(work, n) for n in ('s.txt', 'q.txt', 'mine.rgba', 'theirs.rgba'))
            with open(sc, 'w') as f:
                f.write(scene_text(cmds))
            subprocess.run([exe, sc, mine], check=True)
            if repeats(cmds):
                print(f'{name:24} (Quartz has no repeating gradients: not compared)')
                continue
            with open(qsc, 'w') as f:
                f.write(scene_quartz(cmds))
            subprocess.run([quartz, qsc, theirs], check=True)
            a = open(mine, 'rb').read()
            b = open(theirs, 'rb').read()
            if len(a) != len(b):
                print(f'{name:24} sizes differ ({len(a)} and {len(b)} bytes)')
                continue
            off = 0
            total = 0
            for i in range(0, len(a), 4):
                d = max(abs(a[i + j] - b[i + j]) for j in range(3))
                total += d
                if d > 64:
                    off += 1
            print(f'{name:24} {off:>20} {total / (len(a) // 4):>16.2f}')
            if keep and magick:
                out = os.path.join(keep, name.replace(' ', '_').replace(',', '') + '.png')
                subprocess.run([magick, '-size', '64x64', '-depth', '8', 'rgba:' + mine, '-size', '64x64', '-depth', '8',
                                'rgba:' + theirs, '+append', '-scale', '400%', out], check=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    main()
