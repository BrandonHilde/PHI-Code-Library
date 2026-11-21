#!/usr/bin/env python3
"""Has ImageMagick (libpng) read the PNG files imagelib's writer makes, and checks every pixel.

    python3 -I tools/image/check_png_writer.py [PHI]      PHI: the compiler (else $PHI_EXE)

Builds libs/image/test_encode.phi for this computer (macOS, 64-bit Linux or 64-bit Windows) with
fresh corelib and imagelib libraries, and runs it with a temporary folder, where it writes each of
its images as NAME.png beside its pixels as NAME.rgba. Each PNG is then read by ImageMagick
(`magick NAME.png -depth 8 rgba:-`), which must take it without a warning and give exactly the
pixels the image had, and `magick identify` says what kind of PNG it is. Leaves nothing behind.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    phi = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('PHI_EXE')
    if not phi:
        sys.exit('give the phi compiler, or set PHI_EXE')
    magick = shutil.which('magick') or shutil.which('convert')
    if not magick:
        sys.exit('ImageMagick is needed')
    host = {'darwin': 'macos', 'win32': 'windows64'}.get(sys.platform, 'linux64')
    work = tempfile.mkdtemp(prefix='check_png_', dir=os.path.expanduser('~'))
    try:
        env = dict(os.environ, NASMENV='-O1')
        for lib in ('core/corelib.phi', 'image/imagelib.phi'):
            subprocess.run([phi, 'build', os.path.join(ROOT, 'libs', lib), '--library', '-o', work],
                           check=True, stdout=subprocess.DEVNULL, env=env)
        shutil.copy(os.path.join(ROOT, 'libs', 'image', 'test_encode.phi'), work)
        subprocess.run([phi, 'build', os.path.join(work, 'test_encode.phi'), '--target', host, '-o', work],
                       check=True, stdout=subprocess.DEVNULL, env=env)
        exe = [p for p in (os.path.join(work, 'test_encode'), os.path.join(work, 'test_encode.exe')) if os.path.exists(p)][0]
        out = os.path.join(work, 'out')
        os.mkdir(out)
        subprocess.run([exe, out], check=True, stdout=subprocess.DEVNULL)
        bad = 0
        files = sorted(glob.glob(os.path.join(out, '*.png')))
        for png in files:
            name = os.path.basename(png)[:-4]
            with open(png[:-4] + '.rgba', 'rb') as f:
                want = f.read()
            read = subprocess.run([magick, png, '-depth', '8', 'rgba:-'], capture_output=True)
            kind = subprocess.run([magick, 'identify', '-format', '%[png:IHDR.color-type-orig] %[png:IHDR.bit-depth-orig]', png],
                                  capture_output=True, text=True).stdout.strip()
            verdict = 'the same'
            if read.returncode != 0 or read.stderr:
                verdict = 'REFUSED OR WARNED: ' + read.stderr.decode(errors='replace').strip()
            elif read.stdout != want:
                verdict = 'NOT THE SAME'
            if verdict != 'the same':
                bad += 1
            print(f'{name:20} color type, depth {kind:6} {os.path.getsize(png):>7} bytes: {verdict}')
        print(f'{len(files) - bad} of {len(files)} read by ImageMagick with every pixel the same')
        return 1 if bad or not files else 0
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
