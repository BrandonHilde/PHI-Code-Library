#!/usr/bin/env python3
"""Make an H.264 test stream and its reference pictures with a browser's WebCodecs: frames drawn by
a script (moving shapes and gradients, the same every time), encoded by the browser's VideoEncoder,
then decoded by its VideoDecoder, each picture's CRCs written as medialib's test prints them.

    python3 tools/media/make_h264_test.py OUT.h264 CODEC [W H FRAMES BITRATE ACCEL]
        # CODEC: avc1.42001f (Baseline: CAVLC), avc1.4d001f (Main), avc1.64001f (High)
        # ACCEL: prefer-software (OpenH264 in Chromium, Baseline only) or prefer-hardware

OUT.h264 is the stream as Annex B (start codes); OUT.h264.crcs the decoded pictures' CRCs ("frame N
crc Y/UV": the visible Y plane, then U and V one after the other) in the order shown. The browser's
own log (standard error) carries the page's answers; Brave or Chrome, headless."""
import sys, os, base64, json, subprocess, tempfile, time

out = sys.argv[1]
codec = sys.argv[2]
w = int(sys.argv[3]) if len(sys.argv) > 3 else 320
h = int(sys.argv[4]) if len(sys.argv) > 4 else 240
frames = int(sys.argv[5]) if len(sys.argv) > 5 else 30
bitrate = int(sys.argv[6]) if len(sys.argv) > 6 else 400000
accel = sys.argv[7] if len(sys.argv) > 7 else 'prefer-software'

html = '''<html><body><canvas id=c width=%(w)d height=%(h)d></canvas><script>
const W = %(w)d, H = %(h)d, N = %(n)d;
const cv = document.getElementById('c'), g = cv.getContext('2d');
function draw(k) {
  const grd = g.createLinearGradient(0, 0, W, H);
  grd.addColorStop(0, 'hsl(' + (k * 7) %% 360 + ',70%%,50%%)'); grd.addColorStop(1, 'hsl(' + (k * 7 + 180) %% 360 + ',60%%,30%%)');
  g.fillStyle = grd; g.fillRect(0, 0, W, H);
  for (let i = 0; i < 12; i++) {
    g.fillStyle = 'hsl(' + (i * 30) + ',80%%,' + (40 + (i %% 3) * 15) + '%%)';
    const x = (i * 53 + k * (3 + i %% 4)) %% W, y = (i * 37 + k * (2 + i %% 3)) %% H;
    g.beginPath(); g.arc(x, y, 10 + i * 3, 0, 7); g.fill();
  }
  g.fillStyle = '#fff'; g.font = '28px sans-serif'; g.fillText('frame ' + k, 10 + k, 40);
  for (let y = 0; y < 40; y++) for (let x = 0; x < 60; x++) {
    const v = ((x * 31 + y * 17 + k * 13) * 2654435761 >>> 0) %% 256;
    g.fillStyle = 'rgb(' + v + ',' + (255 - v) + ',' + ((v * 3) %% 256) + ')'; g.fillRect(W - 70 + x, H - 50 + y, 1, 1);
  }
}
const chunks = [];
function crc32(a) { let c, t = crc32.t; if (!t) { t = crc32.t = []; for (let n = 0; n < 256; n++) { c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } }
  c = 0xFFFFFFFF; for (let i = 0; i < a.length; i++) c = t[(c ^ a[i]) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; }
function b64(a) { let s = ''; for (let i = 0; i < a.length; i += 32768) s += String.fromCharCode.apply(null, a.subarray(i, i + 32768)); return btoa(s); }
async function run() {
  const enc = new VideoEncoder({ output: (c) => { const b = new Uint8Array(c.byteLength); c.copyTo(b); chunks.push([c.type === 'key', b]); },
                                 error: (e) => console.log('RESULT error ' + e) });
  const cfg = { codec: '%(codec)s', width: W, height: H, bitrate: %(br)d, framerate: 30, avc: { format: 'annexb' }, hardwareAcceleration: '%(accel)s', latencyMode: 'quality' };
  const sup = await VideoEncoder.isConfigSupported(cfg);
  if (!sup.supported) { console.log('RESULT error unsupported'); return; }
  enc.configure(cfg);
  for (let k = 0; k < N; k++) {
    draw(k);
    const f = new VideoFrame(cv, { timestamp: k * 33333 });
    enc.encode(f, { keyFrame: k === 0 }); f.close();
  }
  await enc.flush();
  const out = [];
  const dec = new VideoDecoder({ output: async (f) => {
      const w = f.visibleRect.width, h = f.visibleRect.height;
      const buf = new Uint8Array(f.allocationSize()); const layout = await f.copyTo(buf);
      const y = new Uint8Array(w * h);
      for (let r = 0; r < h; r++) y.set(buf.subarray(layout[0].offset + r * layout[0].stride, layout[0].offset + r * layout[0].stride + w), r * w);
      const cw = (w + 1) >> 1, ch = (h + 1) >> 1; const uv = new Uint8Array(cw * ch * 2);
      for (let r = 0; r < ch; r++) {
        uv.set(buf.subarray(layout[1].offset + r * layout[1].stride, layout[1].offset + r * layout[1].stride + cw), r * cw);
        uv.set(buf.subarray(layout[2].offset + r * layout[2].stride, layout[2].offset + r * layout[2].stride + cw), cw * ch + r * cw);
      }
      out.push(crc32(y) + '/' + crc32(uv)); f.close();
    }, error: (e) => console.log('RESULT error decode ' + e) });
  dec.configure({ codec: '%(codec)s', hardwareAcceleration: 'prefer-software' });
  let ts = 0, total = 0;
  for (const [key, b] of chunks) { dec.decode(new EncodedVideoChunk({ type: key ? 'key' : 'delta', timestamp: ts, data: b })); ts += 33333; total += b.length; }
  await dec.flush();
  const all = new Uint8Array(total); let o = 0; for (const [, b] of chunks) { all.set(b, o); o += b.length; }
  console.log('RESULT ' + JSON.stringify({ stream: b64(all), crcs: out }));
}
run().catch((e) => console.log('RESULT error ' + e));
</script></body></html>''' % {'w': w, 'h': h, 'n': frames, 'codec': codec, 'br': bitrate, 'accel': accel}
d = tempfile.mkdtemp()
page = os.path.join(d, 'p.html'); open(page, 'w').write(html)
browser = os.environ.get('REF_BROWSER')
for c in [browser, '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']:
    if c and os.path.exists(c):
        browser = c
        break
p = subprocess.Popen([browser, '--headless', '--no-first-run', '--user-data-dir=' + d + '/prof',
                      '--allow-file-access-from-files', '--enable-logging=stderr', '--v=0', 'file://' + page],
                     stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
result = None; began = time.time()
while time.time() - began < 120:
    line = p.stderr.readline()
    if not line:
        break
    if 'RESULT ' in line:
        result = line.split('RESULT ', 1)[1]
        break
p.kill()
if result is None or result.startswith('error'):
    print('failed:', result); sys.exit(1)
result = result[:result.rindex('}') + 1]
r = json.loads(result)
open(out, 'wb').write(base64.b64decode(r['stream']))
with open(out + '.crcs', 'w') as f:
    for i, c in enumerate(r['crcs']): f.write('frame %d crc %s\n' % (i, c))
print('%s: %d bytes, %d pictures' % (out, os.path.getsize(out), len(r['crcs'])))
