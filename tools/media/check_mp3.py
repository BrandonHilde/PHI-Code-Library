#!/usr/bin/env python3
"""medialib's MP3 decoder against Apple's (macOS's afconvert): the samples, the length, the alignment.

    python3 tools/media/check_mp3.py FILE.mp3 OURS.raw

OURS.raw is medialib's output, 16-bit stereo little-endian (MdMedia.ReadAudio's, one after the
other). Apple's decoder makes the reference (afconvert -f WAVE -d LEI16); both drop the encoder's
delay and padding that LAME's tag gives. It prints the offset at which they line up best (0 when
the gapless trimming agrees), the signal-to-noise ratio and the largest difference.
"""
import sys, struct, math, subprocess, tempfile, os
mp3, ours_path = sys.argv[1], sys.argv[2]
ref_path = os.path.join(tempfile.mkdtemp(), 'ref.wav')
subprocess.run(['afconvert', '-f', 'WAVE', '-d', 'LEI16', mp3, ref_path], check=True)
b = open(ref_path, 'rb').read()
i = 12; ch = 2; data = b''
while i < len(b):
    cid = b[i:i+4]; size = struct.unpack('<I', b[i+4:i+8])[0]
    if cid == b'fmt ': ch = struct.unpack('<H', b[i+10:i+12])[0]
    if cid == b'data': data = b[i+8:i+8+size]
    i += 8 + size + (size & 1)
ref = struct.unpack('<%dh' % (len(data) // 2), data)
if ch == 1:
    ref = [v for v in ref for _ in (0, 1)]
raw = open(ours_path, 'rb').read()
ours = struct.unpack('<%dh' % (len(raw) // 2), raw)
r0, o0 = ref[0::2], ours[0::2]
def score(off):
    s = n = 0
    for k in range(0, min(len(r0), len(o0) - off), 13):
        if 0 <= k + off < len(o0):
            s += (r0[k] - o0[k + off]) ** 2; n += 1
    return s / max(n, 1)
best = min(range(-2400, 2401), key=score)
sig = err = worst = n = 0
for k in range(len(r0)):
    j = k + best
    if 0 <= j < len(o0):
        for c in range(2):
            a, o = ref[k * 2 + c], ours[j * 2 + c]
            sig += a * a; err += (a - o) ** 2; worst = max(worst, abs(a - o)); n += 1
print('%s: offset %d; %d samples compared; SNR %.1f dB; largest difference %d; Apple %d frames, medialib %d'
      % (os.path.basename(mp3), best, n, 10 * math.log10(sig / max(err, 1e-9)), worst, len(r0), len(o0)))
