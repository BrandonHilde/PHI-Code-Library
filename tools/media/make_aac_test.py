#!/usr/bin/env python3
"""Make libs/media/tests/media/plucks.m4a and plucks.ref.raw: an AAC clip for medialib's test, and
Apple's decoding of it (macOS's afconvert both ways).

    python3 tools/media/make_aac_test.py

Two seconds of five plucked notes (sharp attacks: short windows and TNS), a burst of hiss and a click,
spread across two channels, made here (so the clip is this repository's own), encoded at 64 kbit/s
(which Apple's encoder makes 32000 Hz), then decoded back to 16-bit stereo as the reference.
"""
import struct, math, random, subprocess, os, tempfile
here = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'libs', 'media', 'tests', 'media')
rate = 44100; n = int(rate * 2.0); random.seed(7)
L = [0.0] * n; R = [0.0] * n
for t0, f, pan in [(0.0, 220.0, 0.9), (0.35, 277.18, 0.8), (0.7, 329.63, 0.8), (1.05, 440.0, 0.7), (1.4, 554.37, 0.6)]:
    s = int(t0 * rate)
    for i in range(s, min(n, s + int(0.9 * rate))):
        t = (i - s) / rate; env = math.exp(-4 * t) * (1 - math.exp(-400 * t))
        v = 0.3 * env * (math.sin(2 * math.pi * f * t) + 0.4 * math.sin(4 * math.pi * f * t) + 0.2 * math.sin(6 * math.pi * f * t))
        L[i] += v * pan; R[i] += v * (1.2 - pan)
for i in range(int(0.9 * rate), int(1.2 * rate)):
    v = 0.15 * random.uniform(-1, 1) * math.sin(math.pi * (i - 0.9 * rate) / (0.3 * rate))
    L[i] += v; R[i] += v * 0.5
for i in range(int(1.7 * rate), int(1.7 * rate) + 30):
    L[i] += 0.6 * (-1) ** i; R[i] -= 0.6 * (-1) ** i
clip = lambda x: max(-32768, min(32767, int(x * 32767)))
data = b''.join(struct.pack('<hh', clip(a), clip(b)) for a, b in zip(L, R))
d = tempfile.mkdtemp()
wav = os.path.join(d, 'plucks.wav')
open(wav, 'wb').write(b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVEfmt ' + struct.pack('<IHHIIHH', 16, 1, 2, rate, rate * 4, 4, 16) + b'data' + struct.pack('<I', len(data)) + data)
m4a = os.path.join(here, 'plucks.m4a')
subprocess.run(['afconvert', '-f', 'm4af', '-d', 'aac', '-b', '64000', wav, m4a], check=True)
ref = os.path.join(d, 'ref.wav')
subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16', m4a, ref], check=True)
b = open(ref, 'rb').read(); i = b.index(b'data')
open(os.path.join(here, 'plucks.ref.raw'), 'wb').write(b[i + 8:])
print('wrote plucks.m4a and plucks.ref.raw')
