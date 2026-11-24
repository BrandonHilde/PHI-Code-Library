#!/usr/bin/env python3
"""libvpx's pictures of a WebM's VP8 frames, for medialib's test: each shown frame's CRC-32s.

    python3 tools/media/vp8_reference.py libs/media/tests/media/flower.webm > libs/media/tests/media/flower.vp8.crcs

The video track's blocks (simple blocks or block groups, no lacing) go to Brave's (or Chrome's)
WebCodecs VideoDecoder, which is libvpx, in a headless browser; each frame's visible Y plane, then
its U and V planes one after the other (each half the size, rounded up), are CRC-32'd, written
"frame N crc Y/UV" as medialib's test prints them. The page reports through the console (read from
the browser's log on standard error): headless Chrome's --dump-dom with a virtual time budget
never lets the decoder finish."""
import sys, struct, base64, json, subprocess, os, zlib, tempfile
def vint(b, i, keep=False):
    first = b[i]; n = 1; mask = 0x80
    while n <= 8 and not (first & mask): n += 1; mask >>= 1
    v = first if keep else first & (mask - 1)
    for k in range(1, n): v = (v << 8) | b[i + k]
    return v, n
CONT = {0x18538067, 0x1F43B675, 0x1654AE6B, 0xAE, 0xA0}
def walk(b, i, end, out, track):
    while i < end:
        idv, n = vint(b, i, True); size, m = vint(b, i + n); body = i + n + m
        if size == (1 << (7 * m)) - 1: size = end - body
        if idv in CONT: walk(b, body, min(body + size, end), out, track)
        elif idv == 0xD7: track.setdefault('nums', []).append(int.from_bytes(b[body:body+size], 'big'))
        elif idv == 0x86: track.setdefault('codecs', []).append(b[body:body+size].decode())
        elif idv in (0xA3, 0xA1):
            t, tn = vint(b, body); flags = b[body + tn + 2]
            out.append((t, (flags & 0x80) != 0, b[body + tn + 3: body + size]))
        i = body + size
b = open(sys.argv[1], 'rb').read(); blocks = []; track = {}
walk(b, 0, len(b), blocks, track)
vnum = track['nums'][track['codecs'].index('V_VP8')]
frames = [(k, base64.b64encode(d).decode()) for t, k, d in blocks if t == vnum]
html = '''<html><body><pre id=o></pre><script>
const frames = %s;
const out = [];
function crc32(a) { let c, t = crc32.t; if (!t) { t = crc32.t = []; for (let n = 0; n < 256; n++) { c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } }
  c = 0xFFFFFFFF; for (let i = 0; i < a.length; i++) c = t[(c ^ a[i]) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; }
const dec = new VideoDecoder({ output: async (f) => {
    const w = f.visibleRect.width, h = f.visibleRect.height;
    const buf = new Uint8Array(f.allocationSize());
    const layout = await f.copyTo(buf); if (f.format !== 'I420') out.push('fmt-' + f.format);
    const y = new Uint8Array(w * h);
    for (let r = 0; r < h; r++) y.set(buf.subarray(layout[0].offset + r * layout[0].stride, layout[0].offset + r * layout[0].stride + w), r * w);
    const cw = (w + 1) >> 1, ch = (h + 1) >> 1;
    const uv = new Uint8Array(cw * ch * 2);
    for (let r = 0; r < ch; r++) {
      uv.set(buf.subarray(layout[1].offset + r * layout[1].stride, layout[1].offset + r * layout[1].stride + cw), r * cw);
      uv.set(buf.subarray(layout[2].offset + r * layout[2].stride, layout[2].offset + r * layout[2].stride + cw), cw * ch + r * cw);
    }
    out.push(crc32(y) + '/' + crc32(uv)); f.close();
  }, error: (e) => { out.push('error ' + e); } });
dec.configure({ codec: 'vp8' });
let ts = 0;
for (const [key, data] of frames) {
  const bin = Uint8Array.from(atob(data), c => c.charCodeAt(0));
  dec.decode(new EncodedVideoChunk({ type: key ? 'key' : 'delta', timestamp: ts, data: bin })); ts += 33333;
}
dec.flush().then(() => { console.log('CRCS ' + out.join(' ')); });
</script></body></html>''' % json.dumps(frames)
d = tempfile.mkdtemp()
page = os.path.join(d, 'p.html'); open(page, 'w').write(html)
brave = os.environ.get('REF_BROWSER')
for b in [brave, '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']:
    if b and os.path.exists(b):
        brave = b
        break
p = subprocess.Popen([brave, '--headless', '--disable-gpu', '--no-first-run', '--user-data-dir=' + d + '/prof',
                      '--allow-file-access-from-files', '--enable-logging=stderr', '--v=0', 'file://' + page],
                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
import time, select
crcs = None; began = time.time()
while time.time() - began < 90:
    line = p.stderr.readline()
    if not line:
        break
    if 'CRCS ' in line:
        crcs = line.split('CRCS ')[1].split('"')[0].split()
        break
p.kill()
if crcs is None:
    print('no result')
else:
    for i, c in enumerate(crcs): print('frame %d crc %s' % (i, c))
