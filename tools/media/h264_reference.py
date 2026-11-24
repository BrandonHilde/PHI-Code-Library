#!/usr/bin/env python3
"""The pictures of an MP4's H.264 video as a browser's decoder makes them, for medialib's test.

    python3 tools/media/h264_reference.py FILE.mp4 > FILE.h264.crcs
    python3 tools/media/h264_reference.py FILE.mp4 --dump 0,5 DIR    (also frames 0 and 5 as DIR/ref.N.yuv)

The first video track's samples (with its avcC) go to Brave's (or Chrome's) WebCodecs VideoDecoder
in a headless browser; each frame, in the order shown, gets "frame N crc Y/UV" as medialib's test
prints them: a CRC-32 of the visible Y plane, then of the U and V planes one after the other. H.264
decoding is exact by its standard, so every conforming decoder gives these pictures. Dumped frames
are raw I420 (Y, then U, then V, visible size). The page reports through the console, read from the
browser's log on standard error."""
import sys, struct, base64, json, subprocess, os, tempfile, time

def boxes(b, i, end):
    while i + 8 <= end:
        size, = struct.unpack('>I', b[i:i+4]); t = b[i+4:i+8].decode('latin-1'); h = 8
        if size == 1: size, = struct.unpack('>Q', b[i+8:i+16]); h = 16
        elif size == 0: size = end - i
        yield t, i + h, i + size
        i += size

def find(b, i, end, path):
    for t, s, e in boxes(b, i, end):
        if t == path[0]:
            if len(path) == 1: return s, e
            r = find(b, s, e, path[1:])
            if r: return r
    return None

def video_track(b):
    moov = find(b, 0, len(b), ['moov'])
    for t, s, e in boxes(b, *moov):
        if t != 'trak': continue
        stbl = find(b, s, e, ['mdia', 'minf', 'stbl'])
        if not stbl: continue
        stsd = find(b, *stbl, ['stsd'])
        entry = stsd[0] + 8
        typ = b[entry+4:entry+8]
        if typ not in (b'avc1', b'avc3'): continue
        esize, = struct.unpack('>I', b[entry:entry+4])
        avcc = find(b, entry + 8 + 78, entry + esize, ['avcC'])
        return stbl, b[avcc[0]:avcc[1]]
    raise SystemExit('no H.264 track')

def samples(b, stbl):
    s, e = stbl
    def body(n):
        r = find(b, s, e, [n]); return r[0] if r else None
    p = body('stsz'); fixed, count = struct.unpack('>II', b[p+4:p+12])
    sizes = [fixed] * count if fixed else list(struct.unpack('>%dI' % count, b[p+12:p+12+4*count]))
    p = body('stco')
    if p is not None:
        n, = struct.unpack('>I', b[p+4:p+8]); offs = list(struct.unpack('>%dI' % n, b[p+8:p+8+4*n]))
    else:
        p = body('co64'); n, = struct.unpack('>I', b[p+4:p+8]); offs = list(struct.unpack('>%dQ' % n, b[p+8:p+8+8*n]))
    p = body('stsc'); n, = struct.unpack('>I', b[p+4:p+8])
    runs = [struct.unpack('>III', b[p+8+12*k:p+20+12*k]) for k in range(n)]
    p = body('stss'); keys = None
    if p is not None:
        n, = struct.unpack('>I', b[p+4:p+8]); keys = set(x - 1 for x in struct.unpack('>%dI' % n, b[p+8:p+8+4*n]))
    out = []; k = 0
    for c in range(len(offs)):
        per = None
        for first, spc, _ in runs:
            if first - 1 <= c: per = spc
        pos = offs[c]
        for _ in range(per):
            if k >= count: break
            out.append((keys is None or k in keys, b[pos:pos + sizes[k]])); pos += sizes[k]; k += 1
    return out

args = sys.argv[1:]
dump = set(); dump_dir = None
if '--dump' in args:
    i = args.index('--dump'); dump = set(int(x) for x in args[i+1].split(',')); dump_dir = args[i+2]; del args[i:i+3]
b = open(args[0], 'rb').read()
stbl, avcc = video_track(b)
codec = 'avc1.%02x%02x%02x' % (avcc[1], avcc[2], avcc[3])
frames = [(k, base64.b64encode(d).decode()) for k, d in samples(b, stbl)]
html = '''<html><body><script>
const frames = %s, dump = %s;
const desc = Uint8Array.from(atob("%s"), c => c.charCodeAt(0));
const out = [];
function crc32(a) { let c, t = crc32.t; if (!t) { t = crc32.t = []; for (let n = 0; n < 256; n++) { c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } }
  c = 0xFFFFFFFF; for (let i = 0; i < a.length; i++) c = t[(c ^ a[i]) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; }
function b64(a) { let s = ''; for (let i = 0; i < a.length; i += 32768) s += String.fromCharCode.apply(null, a.subarray(i, i + 32768)); return btoa(s); }
let n = 0;
const dec = new VideoDecoder({ output: async (f) => {
    const k = n++;
    const w = f.visibleRect.width, h = f.visibleRect.height, x0 = f.visibleRect.x, y0 = f.visibleRect.y;
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
    out[k] = crc32(y) + '/' + crc32(uv);
    if (dump.includes(k)) { const all = new Uint8Array(y.length + uv.length); all.set(y); all.set(uv, y.length); console.log('DUMP ' + k + ' ' + b64(all)); }
    f.close();
  }, error: (e) => { console.log('CRCS error ' + e); } });
dec.configure({ codec: '%s', description: desc, optimizeForLatency: false, hardwareAcceleration: 'prefer-software' });
let ts = 0;
for (const [key, data] of frames) {
  const bin = Uint8Array.from(atob(data), c => c.charCodeAt(0));
  dec.decode(new EncodedVideoChunk({ type: key ? 'key' : 'delta', timestamp: ts, data: bin })); ts += 33333;
}
dec.flush().then(() => { setTimeout(() => console.log('CRCS ' + out.join(' ')), 200); });
</script></body></html>''' % (json.dumps(frames), json.dumps(sorted(dump)), base64.b64encode(avcc).decode(), codec)
d = tempfile.mkdtemp()
page = os.path.join(d, 'p.html'); open(page, 'w').write(html)
browser = os.environ.get('REF_BROWSER')
for c in [browser, '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']:
    if c and os.path.exists(c):
        browser = c
        break
p = subprocess.Popen([browser, '--headless', '--disable-gpu', '--no-first-run', '--user-data-dir=' + d + '/prof',
                      '--allow-file-access-from-files', '--enable-logging=stderr', '--v=0', 'file://' + page],
                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
crcs = None; began = time.time()
while time.time() - began < 120:
    line = p.stderr.readline()
    if not line:
        break
    if 'DUMP ' in line:
        k, data = line.split('DUMP ')[1].split('"')[0].split()
        open(os.path.join(dump_dir, 'ref.%s.yuv' % k), 'wb').write(base64.b64decode(data))
    if 'CRCS ' in line:
        crcs = line.split('CRCS ')[1].split('"')[0].split()
        break
p.kill()
if crcs is None:
    print('no result'); sys.exit(1)
for i, c in enumerate(crcs): print('frame %d crc %s' % (i, c))
