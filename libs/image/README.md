# imagelib

Image files in, pixels out. Whatever the file, the pixels are 32-bit `0xAARRGGBB` with straight (not
premultiplied) alpha, a row at a time from the top. It reads BMP, PNG and JPEG (baseline and progressive) so
far; GIF is next
([plan.md](../../plan.md#phase-3-image-library)). It uses [corelib](../core), so a program using it
has `corelib.philib` beside `imagelib.philib`.

```phi
use imagelib;

call ImageLib.Start;
ptr<ImgImage> image: (Img.Decode: bytes length);        # finds the format from the bytes
if image is 0
	log 'bad image: ' Img.error '\n';
	return;
;;
call Draw.Blit: 10 10 image.w image.h image.pixels image.w;   # when it's opaque
call Img.Free: image;
```

## API

These names are the API. Everything else the library declares (`ImgBmp`, `ImgBmpTables`, `ImgPng`,
`ImgPngTables`, `ImgJpeg`, `ImgJpegTables`, and `Img`'s `New`, `Limit`, `Done`, `DonePng` and `DoneJpeg`) is
how it works, and may change.

| Name | What it is |
|---|---|
| `ImageLib.Start` | Call once, before anything else. It starts corelib too. `ImageLib.VERSION` is 1 |
| `ImgImage` | A struct: `w`, `h` (`int`), and `pixels`, a `ptr<u32>` to `w * h` of them |
| `Img.Decode: data length` → | A `ptr<ImgImage>` from a file in any format imagelib reads, or 0 with the reason in `Img.error` |
| `Img.DecodeBmp: data length` → | The same, for a BMP file |
| `Img.DecodePng: data length` → | The same, for a PNG file |
| `Img.DecodeJpeg: data length` → | The same, for a JPEG file |
| `Img.Format: data length` → | Which format the bytes are in, from their first few: `Img.BMP`, `Img.PNG`, `Img.JPEG`, or `Img.UNKNOWN` |
| `Img.Free: image` | Gives back an image's memory (0 does nothing) |
| `Img.BlendRow: dest src count` | Draws `count` pixels of `src` over `dest`, which is taken as opaque: each color becomes `(src * alpha + dest * (255 - alpha)) / 255`, rounded, and `dest`'s top byte stays as it was |
| `Img.max_pixels` | The most pixels an image may have. 0, as it starts, means `Img.DEFAULT_MAX_PIXELS` (16,777,216: 4096 by 4096, 64 MB of pixels) |

**A bad file** gives 0 and a reason, never a crash or a hang. **Sizes are checked first:** a file that
says it's bigger than `max_pixels` is refused before any memory is taken for it, so a small file can't
claim gigabytes, and one whose pixels would run past its end is refused before they're read. A PNG's
image data is inflated with its exact size as the limit, so it can't inflate to more.

**One thread at a time:** `Img.error` and `Img.max_pixels` are shared.

## BMP

Every header size BMP has (12 and 16-byte OS/2, 40, 52, 56, 64, 108 and 124), palettes of 1, 2, 4 and
8 bits, 16, 24 and 32-bit pixels with bit fields of any shape (alpha too, and `BI_ALPHABITFIELDS`), RLE8
and RLE4, and images stored either way up.

Where readers differ, it does what BMP Suite calls correct, which is what the browsers do:

- **Pixels RLE skips over** (with a delta, or an early end of line or of the image) are transparent.
- **A channel of n bits** becomes 8 by scaling, `round(v * 255 / (2^n - 1))`, so a 5-bit channel's top
  value is 255, not 248.
- **Alpha only comes from an alpha mask**, in a header of 56 bytes or more, or `BI_ALPHABITFIELDS`. The
  unused bits of 16 and 32-bit pixels without one are ignored, so those images are opaque.
- **An index past the end of the palette** is opaque black.
- **Lenient where it's harmless:** the file size and image size fields are ignored, as is the planes
  field; the last row may be missing its padding; a palette may be shorter or longer than its bit depth
  (only the first 2^bits count).

**Not done:** 64-bit pixels, Huffman 1D, RLE24, embedded JPEG and PNG (they're refused, saying so), and
color profiles (ignored). **Refused as invalid:** RLE stored top-down, bit fields on 8 or 24-bit pixels,
RLE with the wrong bit depth, masks that aren't one run of bits or are wider than the pixel, and pixels
that start inside the headers.

## PNG

Every color type and bit depth PNG has (gray at 1, 2, 4, 8 and 16 bits, RGB at 8 and 16, palettes of 1,
2, 4 and 8 bits, gray with alpha and RGBA at 8 and 16), interlaced (Adam7) or not, all five filters, and
tRNS transparency of each kind. Gamma, color profiles, `sBIT` and the rest are ignored, so the pixels are
the samples the file holds, as Pillow and ImageMagick also give them.

Where the standard leaves a choice, it does what libpng does, which is what the browsers do:

- **A sample of n bits** becomes 8 by scaling, `round(v * 255 / (2^n - 1))`, as for BMP. So 16-bit samples
  are rounded, not cut to their top byte (which can be 1 lower).
- **tRNS** makes a gray or RGB color transparent when it matches all 16 bits of the sample, before any
  scaling, and the pixel keeps its color.
- **Ancillary chunks that are wrong are ignored:** one with a bad CRC, a tRNS of the wrong length, a second
  one, one after the image data, or one in a palette image before the palette (or longer than it), and a
  PLTE in a gray image. Unknown ancillary chunks are skipped, so APNG's frames after the first are too.
- **Lenient where libpng gives up:** a palette index past the end of the palette is opaque black, as BMP's
  is.

**It shows what it can,** as Pillow and the browsers do:

- **The image is done at the end of the IDATs,** so nothing after them is read: no IEND is needed, and a
  chunk after them that's wrong in any way (a bad CRC, an unknown critical chunk, a late PLTE) is no matter.
- **Image data past what the image needs is ignored.**
- **Image data that ends too soon** (the file cut short, inside an IDAT or before the next, or a zlib stream
  that stops early or has no Adler-32) gives the rows that came whole, and the rest of the image is
  transparent: as a browser shows such a file, and as Pillow gives it with `LOAD_TRUNCATED_IMAGES`. For an
  interlaced image, that's the passes that came whole and the rows of the next.

The image data is inflated with corelib's `ZlibUpTo`, which stops at the image's size and keeps what it made
when the data ends.

**Refused** is what libpng refuses: what PNG doesn't have (color types, bit depths, methods, filter types),
chunks whose names aren't letters, a missing or doubled PLTE in a palette image, an IDAT whose CRC is wrong,
unknown critical chunks before the image data (such as Apple's `CgBI`), image data that's damaged, and a file
with no IDAT. **Not done:** APNG's other frames.

## JPEG

Baseline and extended sequential JPEG (SOF0 and SOF1) with Huffman coding and 8-bit samples: gray, or three
components, which are YCbCr unless the file says RGB. Any sampling factors that divide evenly (4:4:4, 4:2:2,
4:2:0, 4:4:0, 4:1:1 and the rest, chroma at a higher resolution than luma too), interleaved scans or one
component a scan, and restart markers.

It gives the **same pixels as libjpeg-turbo**, not merely close ones, damaged files included, because it
decodes as libjpeg-turbo does by default, step for step:

- **The integer IDCT,** libjpeg's "islow", as its C code works it out: its 13-bit constants, its two passes, its
  shortcuts for columns and rows with no AC terms, 64-bit intermediates with a 32-bit work array between the
  passes, and a 16-bit quantization table. A block whose dequantized coefficients are all within 1,173 can't
  overflow 32 bits, so it's done in 32 (as nearly every block of a good file is), and any other in 64.
- **"Fancy" upsampling,** the triangle filter, for chroma at half width, half height or both, with the edges
  repeated; plain repeating for other ratios, and for a component 2 samples across or fewer.
- **YCbCr to RGB** by libjpeg's fixed-point tables.
- **The color space** chosen as libjpeg chooses it: a JFIF marker means YCbCr; otherwise an Adobe marker's
  transform says (0 is RGB); otherwise component IDs R, G and B mean RGB.

- **What it does with a damaged file,** which is to show what it can, as libjpeg does:
  - entropy-coded data that runs out (at a marker, or the end of the file) reads as zero bits, and once a bit
    that isn't there has been used, the MCUs up to the next restart marker are left at zero, which is gray;
  - a code that isn't in its Huffman table takes 17 bits and is 0, and a run of coefficients past the end of a
    block puts its coefficient last;
  - restart markers out of order are resynced by libjpeg's rules (`jpeg_resync_to_restart`);
  - what isn't a marker between segments is skipped, as are restart and TEM markers outside a scan, DNL, and
    APPn or COM segments too short to be one;
  - past the end of the file come EOI markers, again and again, as libjpeg's source managers give them, so a
    file cut short anywhere is read as libjpeg reads it (the file is copied with them after it);
  - a scan that says it isn't sequential is read as if it were;
  - with no Huffman table defined, tables 0 and 1 are the standard ones (from the JPEG standard's Annex K, as
    motion-JPEG frames expect).

Coefficients are kept in 16 bits, as libjpeg keeps them. A file whose first scan has every component goes in
one pass, each block straight to samples, and is done when that scan is (libjpeg finds what comes after too
late to change its pixels). Any other keeps every component's coefficients until the end, as libjpeg does, so
a component in no scan comes out gray, and one in two has the second's coefficients written over the first's;
that takes 2 bytes a sample more while it's read. EXIF orientation isn't applied, and color profiles are
ignored.

**Progressive JPEG** (SOF2) is read as libjpeg's `jdphuff.c` reads it: DC scans first and refined, AC bands
of one component first (with their end-of-band runs) and refined, each scan's band and bits checked as
libjpeg checks them, every coefficient kept until the end of the file, and the same recovery from damage. A
progressive file has no standard Huffman tables to fall back on, as in libjpeg. **Not done yet:** when a
progressive file's scans stop before its low AC coefficients have all come (a file cut short, say), libjpeg
smooths each block from its neighbors' DC values, and imagelib shows the blocks as they are. Such a file's
pixels aren't compared with libjpeg's; every other is.

**Refused** is only what libjpeg refuses: headers and tables that are wrong, and a file with no image in it.
**Not done** (refused, saying so): lossless, hierarchical and arithmetic coding, 12-bit samples, and four
components (CMYK).

## How it's checked

From the repo's root:

```
pwsh ./build.ps1 image -Test                         # (or .\build.ps1 image -Test on Windows)
python3 -P tools/image/make_bmp_tests.py --bmpsuite DIR    # remakes tests/bmp/cases.bin (it's committed)
python3 -P tools/image/make_png_tests.py                   # remakes tests/png/cases.bin
python3 -P tools/image/make_jpeg_tests.py                  # remakes tests/jpeg/cases.bin
pwsh ./build.ps1 image -Test -Release                      # and the release tests too
python3 -P tools/image/make_png_tests.py --release         # (and the others): remakes release.bin
```

**Two tiers,** as [the conventions](../../docs/conventions.md#tests) say: during development, light, quick
tests; the full suite when preparing a release. The everyday tests (`test_*`, in `cases.bin`) are each
format's outside suite and the cases made for each feature and each kind of error, a few sizes of each, and a
few of every other kind: two good files cut at 7 lengths each and 40 fuzzed files per format, all checked
against the outside decoders, and a short run of each crash fuzzer. All of imagelib's everyday tests, built
and run, take about 20 seconds. The release tests (`release_*`, in `release.bin`) are the full suite: every
size, good files cut short at many lengths, thousands of fuzzed files, and the crash fuzzers' full runs. The release figures below are from their last run (2026-11-08).

Each format's rules are written plainly in Python, in [tools/image](../../tools/image), and checked against
outside evidence before any case is written; imagelib follows them check for check.

**BMP:** the rules are [bmp_reference.py](../../tools/image/bmp_reference.py), and `make_bmp_tests.py` checks
them against BMP Suite's reference images and Pillow before it writes any case: it stops at any difference that isn't listed with its reason. Each case's expected result is then
the rules', and imagelib must give the same size and pixels, or refuse for the same reason. (`DIR` is
BMP Suite 2.8 unpacked, for its reference images. Without it, the script checks against Pillow alone.
`-P` rather than `-I`, since Pillow is usually in the user's site-packages.)

**PNG:** the rules are [png_reference.py](../../tools/image/png_reference.py), and `make_png_tests.py` checks
them against PngSuite (its broken files are named so) and two decoders that share no code: ImageMagick,
which reads PNG with libpng, and Pillow. Every pixel must be what libpng gives, at 16 bits and rounded the
same way, and every file the rules refuse must be refused by libpng too. That goes for the files cut short and
fuzzed as well. libpng refuses a file whose image data ends too soon, which the rules read as far as it goes,
so then a cut file's rows must be the rows of the image it was cut from. A fuzzed one must be what Pillow
gives, reading as far as it goes (`LOAD_TRUNCATED_IMAGES`), on every pixel the rules made, apart from where
Pillow always differs (16-bit samples, tRNS). A file whose IDATs are followed by a broken chunk, which libpng
and Pillow both give up on, must be what libpng gives with an IEND there instead. Images of more than a
million pixels (fuzzed headers claim up to the limit) aren't compared, to keep the checking's memory small.
Every ImageMagick run has limits on its memory, its address space and its time. It needs `magick` on the
path; `--pngsuite DIR` copies PngSuite-2017jul19 in from `DIR` first.

**JPEG:** the rules are [jpeg_reference.py](../../tools/image/jpeg_reference.py). There's no free JPEG test
suite, so `make_jpeg_tests.py` makes its files: with libjpeg-turbo itself, through Pillow and ImageMagick,
and with a small baseline encoder of its own for what those can't write. Every file the rules read must
give exactly the pixels libjpeg-turbo gives, and every file the rules refuse libjpeg must refuse too, unless
it's a kind not read yet: the files made, and every one cut short and every fuzzed one too, as they're
damaged files of every kind. libjpeg-turbo is the system's copy, through ImageMagick, with
`JSIMD_FORCENONE=1`: its C code, the reference its SIMD is tested against. The two give the same pixels for
every block of a good file, but on the garbage blocks of a damaged one the SIMD IDCT saturates where the C one
wraps. Where ImageMagick itself gives up (after a thousand of libjpeg's warnings, as when a segment runs past
the end of the file and its source manager gives an EOI and a warning for every 2 bytes skipped), Pillow's
copy of libjpeg-turbo is asked instead. Pillow is counted too.

| Test | What it proves |
|---|---|
| `test_bmp` | The decoder against the rules, on the everyday cases in [tests/bmp](tests/bmp) (listed in `cases.txt`): BMP Suite's files, and files made for what it doesn't cover |
| `release_bmp` | The same on the release cases (`release.bin`): the made files at every width, good files cut short at many lengths, and files with bytes changed |
| `test_bmp_fuzz`, `release_bmp_fuzz` | The crash fuzzer, in `fuzz_bmp.phi`: a short run every day (2,000 random changes, one file's header bytes, a little noise), and the full run for release. The full run: 100,000 random changes to good files, every value of each of the first 160 bytes of ten of them, troublesome numbers in every header field, and noise. All must come back, with an image within the limit or a reason |
| `test_png` | The same for PNG, on the everyday cases in [tests/png](tests/png): PngSuite's files, and files made for what it doesn't cover (every color type and depth at 4 sizes, interlaced and not, every filter, tRNS and PLTE of each kind, chunks in each wrong place, image data that's damaged, short or too long) |
| `release_png` | The same on the release cases: the made files at 13 sizes, good files cut short, and files with bytes changed, most with their CRCs mended so the change reaches what it was aimed at |
| `test_png_fuzz`, `release_png_fuzz` | The crash fuzzer, in `fuzz_png.phi`: a short run every day (2,000 random changes, one file's header bytes, a little noise), and the full run for release. The full run: 100,000 random changes to good files (three in four with their CRCs mended), every value of each of the first 64 bytes of eight, troublesome numbers in every field of the first 100 bytes, and 30,000 files made from noise: random pixel data of about the right size in stored blocks with the right Adler-32, so that it reaches the filters and the pixels. All must come back, with an image within the limit or a reason |
| `test_jpeg` | The same for JPEG, on the everyday cases in [tests/jpeg](tests/jpeg): files written by libjpeg-turbo (a few sizes, and many qualities and subsamplings, optimized tables, restart markers, RGB), and files made by the encoder for the rest (every sampling layout, one component a scan, scans of two, restart intervals of every length, 16-bit and redefined tables, each way of naming the color space, markers in every wrong place, and damaged entropy-coded data) |
| `release_jpeg` | The same on the release cases: more sizes, good files cut short, and files with bytes changed |
| `test_jpeg_fuzz`, `release_jpeg_fuzz` | The crash fuzzer, in `fuzz_jpeg.phi`: a short run every day (2,000 random changes, one file's header bytes, a little noise), and the full run for release. The full run: 100,000 random changes to good files, every value of each of the first 200 bytes of six, troublesome numbers in every 16-bit field of the first 400 bytes, and 30,000 good headers followed by noise, so that random coefficients reach the IDCT (the 64-bit path too). All must come back, with an image within the limit or a reason. Its limit is 2048 by 2048, so that no image is refused for memory in 32 bits and read in 64 |
| `test_image` | The API: finding the format, the limit, the reasons, freeing, and `BlendRow` against values worked out in Python |
| `tests/use/test_imagelib` | The compiled `imagelib.philib` on its own, with corelib reached through it (its reader for BMP, its inflate for PNG, and its bit reader for JPEG) |

### BMP: the rules, against outside evidence (2026-11-08)

| Against | Result |
|---|---|
| BMP Suite's reference images, for the 68 files that have one (in PNG) | 59 the same, pixel for pixel; 4 within 1 (channels wider than 8 bits, where no rule, shifting or rounding, matches all four); 1 the same but for the reference being stretched to square pixels (`pal8nonsquare`); 4 refused: Huffman 1D, embedded PNG, RLE24 and 64-bit |
| Pillow 11.1, on the 61 BMP Suite files it reads | 43 the same; 5 within 1 (Pillow widens 5 and 6-bit channels by shifting); 12 differ as noted below; 1 read by Pillow but refused here (`b/rletopdown`) |
| Pillow 11.1, on the 390 files made here | 170 the same; 40 within 1; 37 refused by both; 3 refused here but read by Pillow (bit fields on 24-bit pixels, RLE8 on 4-bit ones, pixels starting inside the headers); 140 Pillow can't judge (it doesn't read 2-bit, most bit-field layouts, 16 and 52-byte headers, alpha in 16 bits, or RLE4 correctly) |

**Where Pillow differs:** it makes RLE's skipped pixels palette color 0 rather than transparent, it
ignores a 16-bit image's alpha mask, and Pillow 11.1 draws every other pixel of an RLE4 run in color 0
(BMP Suite's `g/pal4rle` shows it).

### BMP: imagelib, against the rules (2026-11-08, as 32 and 64-bit Linux programs)

| Cases | Result |
|---|---|
| BMP Suite 2.8: 89 of its 91 files (the two with embedded color profiles are left out) | 89 of 89 as the rules say: 76 read, 13 refused |
| Made here | 390 of 390: 338 read, 52 refused |
| Good files cut short | 4,789 of 4,789: 4,782 refused, and 7 read, which lost only the last row's padding |
| Files with a few bytes changed | 4,000 of 4,000 (2,050 read, 1,950 refused) |
| Fuzzing: 100,000 random changes, 409,600 header bytes, 13,650 troublesome numbers, 3,010 noise | No crash or hang, and every image within the limit |

**Speed,** for a 2048 by 2048 image as a 64-bit Linux program (32-bit is about the same), with Pillow
11.1 decoding and converting to RGBA for comparison:

| Pixels | imagelib | Pillow |
|---|---|---|
| 24-bit | 9 ms | 15 ms |
| 32-bit bit fields, with alpha | 17 ms | 13 ms |
| 16-bit 565 | 9 ms | 19 ms |
| 8-bit palette | 6 ms | 3 ms |
| 1-bit palette | 12 ms | 3 ms |
| RLE8 | 6 ms | 73 ms |

32-bit pixels whose channels are all 8 bits (nearly all of them) skip the scaling, and a 16-bit image
of 65,536 pixels or more works out each of the 65,536 values once.

### PNG: the rules, against outside evidence (2026-11-08)

| Against | Result |
|---|---|
| PngSuite (2017jul19), its 176 files | All as it says: 162 read, and its 14 broken ones refused |
| ImageMagick 7 (libpng), on PngSuite | 162 of 162 the same, pixel for pixel at 16 bits; the 14 broken ones refused by both |
| ImageMagick, on the 531 files made here | 476 the same, pixel for pixel (image data that's too long, and a late PLTE, among them); 44 refused by both; 8 read where libpng refuses (image data that ends too soon, and a palette index past the end of the palette), each the same as Pillow gives; 2 refused for the pixel limit; 1 of more than a million pixels, not compared |
| The 2,226 good files cut short | 1,554 read, each one's rows the rows of the image it was cut from (Pillow gives the same on 1,155, within 1 on 335 of 16 bits, and differs on 40, on the last row it gives, which it shows before the row is all there, or with a 16-bit tRNS); 672 refused by both (cut before the image data) |
| The 4,000 fuzzed files | 282 the same as libpng; 3,522 refused by both; 154 that libpng refuses, as Pillow gives them (140 the same, 12 within 1, 1 differing with a tRNS, 1 with nothing whole, where Pillow gives up too) and 20 more of 16-bit gray, which Pillow clips; 5 whose IDATs are followed by a broken chunk, 4 of them the same as libpng with an IEND there, and 1 within 1 of Pillow then; 17 of more than a million pixels, not compared |
| Pillow 11.1, on PngSuite | 130 the same; 18 within 1 (16-bit color); 13 differ (16-bit gray); 1 differs (`tbbn0g04`, a 4-bit gray image's tRNS); 13 of the 14 broken ones refused, and `xcsn0g01` read, though its IDAT's CRC is wrong |
| Pillow 11.1, on the files made here | 343 the same; 82 within 1; 44 differ, for the reasons below; 37 refused by both; 2 refused for the pixel limit, which Pillow doesn't have (it reads one, and refuses the other); 19 refused here but read by Pillow, which checks less (a missing, short, doubled or late PLTE; IHDR not first, or doubled, or too long; an unknown critical chunk; image data short, too long or without its check; no IEND); 4 read here but refused by Pillow (a tRNS of the wrong length, or a bad CRC on an ancillary chunk, which libpng ignores; and APNG's chunks) |

**Where Pillow differs:** it cuts 16-bit samples to their top byte rather than rounding (within 1, except
where it turns an alpha of 1 into 0); it clips 16-bit gray to 255 rather than scaling it; it compares a gray
image's tRNS color against the scaled sample when there are fewer than 8 bits, so it doesn't match; and it
uses a tRNS that libpng ignores (one longer than the palette, a second one, or one after the image data or
before the palette).

### PNG: imagelib, against the rules (2026-11-08, as 32 and 64-bit Linux programs)

| Cases | Result |
|---|---|
| PngSuite | 176 of 176 as the rules say: 162 read, 14 refused |
| Made here | 531 of 531: 485 read, 46 refused |
| Good files cut short | 2,226 of 2,226: 1,554 read, 672 refused |
| Files with a few bytes changed | 4,000 of 4,000 (478 read, 3,522 refused) |
| Fuzzing: 100,000 random changes, 131,072 values of the first 64 bytes, 14,952 troublesome numbers, 30,000 files from noise | No crash or hang, and every image within the limit |

**Speed,** for 2048 by 2048 images saved by Pillow (a gradient with noise, so each is a few MB), as a 64-bit
Linux program (32-bit is about the same), with Pillow 11.1 decoding and converting to RGBA for comparison.
Most of the time is corelib's inflate, which is about 3 times slower than zlib's on this data; the rest is
unfiltering and making the pixels:

| Pixels | imagelib | of which inflate | Pillow |
|---|---|---|---|
| RGB, 8 bits | 139 ms | 88 ms | 43 ms |
| RGBA, 8 bits | 190 ms | 126 ms | 56 ms |
| RGBA, 8 bits, interlaced | 202 ms | 132 ms | 68 ms |
| Gray, 8 bits | 51 ms | 29 ms | 18 ms |
| Gray, 16 bits | 100 ms | 63 ms | 33 ms |
| Palette, 8 bits | 42 ms | 30 ms | 13 ms |
| Gray, 1 bit | 22 ms | 5 ms | 6 ms |

### JPEG: the rules, against outside evidence (2026-11-08)

| Against libjpeg-turbo 3.1.3's C code (through ImageMagick 7.1) | Result |
|---|---|
| The 124 files written by libjpeg-turbo | 121 the same, pixel for pixel; 3 not read yet (progressive, CMYK, arithmetic coding) |
| The 261 files made by the encoder | 212 the same, pixel for pixel, 15 of them damaged ones libjpeg warns about; 44 refused by both; 3 not read yet (12-bit, four components, arithmetic); 2 for the pixel limit |
| 3,050 good files cut short | 894 the same, pixel for pixel; 2,156 refused by both (cut before the image data) |
| 4,000 files with a few bytes changed | 2,226 the same, pixel for pixel; 1,771 refused by both; 3 where ImageMagick gives up, 2 of them the same as Pillow's libjpeg-turbo, and 1 where Pillow stops short too (a COM segment that claims 63,731 bytes, past the end of the file, after two of three scans) |
| 40,000 more fuzzed files, with another seed, run once | 22,263 the same, pixel for pixel (8,009 of them with libjpeg warning); 17,652 refused by both; 9 not read yet, as libjpeg does (a precision byte changed to 12); 76 where ImageMagick gives up, 65 of them the same as Pillow's libjpeg-turbo, and 11 where Pillow stops short too (several scans and a segment past the end, or a JFIF segment too short for Pillow's own reading) |

Pillow 11.1, with its own copy of libjpeg-turbo, gives the same pixels on every good file both read. It
refuses 2 that libjpeg reads (a JFIF or Adobe segment too short to be one, which Pillow's own reading of the
markers trips on), and stops short on damaged files where its source manager suspends rather than giving EOI.

### JPEG: imagelib, against the rules (2026-11-08, as 32 and 64-bit Linux programs)

| Cases | Result |
|---|---|
| Written by libjpeg-turbo | 124 of 124 as the rules say: 121 read, 3 refused |
| Made by the encoder | 261 of 261: 212 read, 49 refused |
| Good files cut short | 3,050 of 3,050: 894 read, 2,156 refused |
| Files with a few bytes changed | 4,000 of 4,000 (2,229 read, 1,771 refused); and the 40,000 more with another seed, run once: 40,000 of 40,000 as a 64-bit program, and 39,998 as a 32-bit one, whose 128 MB heap couldn't fit 2 images of over 4 million pixels beside that run's 96 MB of cases |
| Fuzzing: 100,000 random changes, 307,200 values of the first 200 bytes, 41,059 troublesome numbers, 29,548 headers followed by noise, with a limit of 2048 by 2048 | No crash or hang, and every image within the limit |

**Speed,** for a 2048 by 2048 photo (GNOME's Adwaita background, scaled, with a little noise added), saved
by Pillow at quality 85, with Pillow decoding and converting to RGBA for comparison. libjpeg-turbo uses SIMD
for the IDCT, the upsampling and the color conversion, where this is plain PHI:

| Kind | imagelib, 64-bit | imagelib, 32-bit | Pillow |
|---|---|---|---|
| 4:2:0 | 162 ms | 126 ms | 22 ms |
| 4:2:0, quality 95 | 210 ms | 164 ms | 20 ms |
| 4:4:4 | 250 ms | 190 ms | 17 ms |
| Gray | 91 ms | 72 ms | 7 ms |
