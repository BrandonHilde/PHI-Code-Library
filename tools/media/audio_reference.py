#!/usr/bin/env python3
"""A WebM's or Ogg's sound decoded by Brave's (or Chrome's) WebCodecs AudioDecoder, as 16-bit stereo.

    python3 tools/media/audio_reference.py FILE.webm|FILE.ogg OUT.raw

The first sound track's codec private data (Vorbis's three headers, Xiph-laced, or Opus's head) is
the decoder's description, and each frame of its blocks (laced ones split) a chunk. What comes out
is written 16-bit little-endian, left then right (one channel to both), the browser's floats times
32768, rounded and clamped. For checking medialib's decoders: compare by signal-to-noise, since a
float decoder's numbers aren't a fixed-point one's.
"""
import sys, os, json, base64, subprocess, tempfile, time, struct
def vint(b, i, keep=False):
    first = b[i]; n = 1; mask = 0x80
    while n <= 8 and not (first & mask): n += 1; mask >>= 1
    v = first if keep else first & (mask - 1)
    for k in range(1, n): v = (v << 8) | b[i + k]
    return v, n
CONT = {0x18538067, 0x1F43B675, 0x1654AE6B, 0xA0, 0xE1}
tracks = []
blocks = []
def walk(b, i, end):
    while i < end:
        idv, n = vint(b, i, True); size, m = vint(b, i + n); body = i + n + m
        if size == (1 << (7 * m)) - 1: size = end - body
        if idv == 0xAE:
            t = {}
            walk_track(b, body, body + size, t)
            tracks.append(t)
        elif idv in CONT: walk(b, body, min(body + size, end))
        elif idv in (0xA3, 0xA1): blocks.append(b[body:body + size])
        i = body + size
def walk_track(b, i, end, t):
    while i < end:
        idv, n = vint(b, i, True); size, m = vint(b, i + n); body = i + n + m
        v = b[body:body + size]
        if idv == 0xD7: t['num'] = int.from_bytes(v, 'big')
        elif idv == 0x86: t['codec'] = v.decode()
        elif idv == 0x63A2: t['priv'] = v
        elif idv == 0xE1: walk_track(b, body, body + size, t)
        elif idv == 0xB5: t['rate'] = struct.unpack('>f' if size == 4 else '>d', v)[0]
        elif idv == 0x9F: t['ch'] = int.from_bytes(v, 'big')
        i = body + size
def frames_of(blk):
    t, tn = vint(blk, 0); p = tn + 2; flags = blk[p]; p += 1
    lacing = (flags >> 1) & 3
    if lacing == 0: return t, [blk[p:]]
    count = blk[p] + 1; p += 1; sizes = []
    if lacing == 1:
        for _ in range(count - 1):
            s = 0
            while True:
                x = blk[p]; p += 1; s += x
                if x < 255: break
            sizes.append(s)
    elif lacing == 3:
        first, n = vint(blk, p); p += n; sizes.append(first); last = first
        for _ in range(count - 2):
            raw, n = vint(blk, p); p += n
            last = last + raw - ((1 << (7 * n - 1)) - 1); sizes.append(last)
    else:
        sizes = [(len(blk) - p) // count] * (count - 1)
    out = []
    for s in sizes: out.append(blk[p:p + s]); p += s
    out.append(blk[p:])
    return t, out
def ogg_packets(b):
    """the first stream's packets (Ogg pages put back together)"""
    packets = []; cur = b''; serial = None; i = 0
    while i + 27 <= len(b) and b[i:i+4] == b'OggS':
        segs = b[i + 26]; lace = b[i + 27:i + 27 + segs]; body = i + 27 + segs
        page_serial = struct.unpack('<I', b[i + 14:i + 18])[0]
        if serial is None: serial = page_serial
        at = body
        for L in lace:
            if page_serial == serial:
                cur += b[at:at + L]
                if L < 255: packets.append(cur); cur = b''
            at += L
        i = body + sum(lace)
    return packets
def xiph_lace(heads):
    out = bytes([len(heads) - 1])
    for h in heads[:-1]:
        n = len(h)
        while n >= 255: out += b'\xff'; n -= 255
        out += bytes([n])
    return out + b''.join(heads)
b = open(sys.argv[1], 'rb').read()
if b[:4] == b'OggS':
    pk = ogg_packets(b)
    ident = pk[0]
    audio = {'priv': xiph_lace(pk[:3]), 'ch': ident[11], 'rate': struct.unpack('<I', ident[12:16])[0]}
    codec = 'vorbis'
    chunks = [base64.b64encode(f).decode() for f in pk[3:]]
else:
    walk(b, 0, len(b))
    audio = [t for t in tracks if t.get('codec', '').startswith('A_')][0]
    codec = {'A_VORBIS': 'vorbis', 'A_OPUS': 'opus'}[audio['codec']]
    chunks = []
    for blk in blocks:
        t, fr = frames_of(blk)
        if t == audio['num']:
            chunks += [base64.b64encode(f).decode() for f in fr]
html = '''<html><body><script>
const chunks = %s; const desc = Uint8Array.from(atob("%s"), c => c.charCodeAt(0));
const out = [];
const dec = new AudioDecoder({ output: (a) => {
    const n = a.numberOfFrames, ch = a.numberOfChannels;
    const l = new Float32Array(n), r = new Float32Array(n);
    a.copyTo(l, { planeIndex: 0, format: 'f32-planar' });
    if (ch > 1) a.copyTo(r, { planeIndex: 1, format: 'f32-planar' }); else r.set(l);
    const s = new Int16Array(n * 2);
    for (let i = 0; i < n; i++) {
      s[2*i] = Math.max(-32768, Math.min(32767, Math.round(l[i] * 32768)));
      s[2*i+1] = Math.max(-32768, Math.min(32767, Math.round(r[i] * 32768)));
    }
    out.push(s); a.close();
  }, error: (e) => console.log('PCMERR ' + e) });
dec.configure({ codec: '%s', sampleRate: %d, numberOfChannels: %d, description: desc });
let ts = 0;
for (const c of chunks) { dec.decode(new EncodedAudioChunk({ type: 'key', timestamp: ts, data: Uint8Array.from(atob(c), x => x.charCodeAt(0)) })); ts += 1000; }
dec.flush().then(() => {
  let total = 0; for (const s of out) total += s.length;
  const all = new Int16Array(total); let at = 0; for (const s of out) { all.set(s, at); at += s.length; }
  const bytes = new Uint8Array(all.buffer); let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  const b64 = btoa(bin);
  for (let i = 0; i < b64.length; i += 60000) console.log('PCM ' + (i / 60000) + ' ' + b64.slice(i, i + 60000));
  console.log('PCMEND ' + total / 2);
});
</script></body></html>''' % (json.dumps(chunks), base64.b64encode(audio.get('priv', b'')).decode(), codec, int(audio['rate']), audio.get('ch', 2))
d = tempfile.mkdtemp(); page = os.path.join(d, 'p.html'); open(page, 'w').write(html)
browser = os.environ.get('REF_BROWSER')
for c in [browser, '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']:
    if c and os.path.exists(c):
        browser = c; break
p = subprocess.Popen([browser, '--headless', '--disable-gpu', '--no-first-run', '--user-data-dir=' + d + '/prof',
                      '--allow-file-access-from-files', '--enable-logging=stderr', '--v=0', 'file://' + page],
                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
parts = {}; frames = None; began = time.time()
while time.time() - began < 90:
    line = p.stderr.readline()
    if not line: break
    if 'PCMERR' in line: print(line.strip()); break
    if '"PCM ' in line:
        body = line.split('"PCM ', 1)[1].split('"', 1)[0]
        k, data = body.split(' ', 1); parts[int(k)] = data
    if 'PCMEND' in line:
        frames = int(line.split('PCMEND ')[1].split('"')[0]); break
p.kill()
if frames is None: sys.exit('no answer from the browser')
raw = base64.b64decode(''.join(parts[k] for k in sorted(parts)))
open(sys.argv[2], 'wb').write(raw)
print('%s: %d frames of %s at %d Hz' % (os.path.basename(sys.argv[1]), frames, codec, int(audio['rate'])))
