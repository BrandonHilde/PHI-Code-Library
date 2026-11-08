# imagelib

Image files in, pixels out. Whatever the file, the pixels are 32-bit `0xAARRGGBB` with straight (not
premultiplied) alpha, a row at a time from the top. It reads BMP and PNG so far; JPEG and GIF are next
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
`ImgPngTables`, and `Img`'s `New`, `Limit`, `Done` and `DonePng`) is how it works, and may change.

| Name | What it is |
|---|---|
| `ImageLib.Start` | Call once, before anything else. It starts corelib too. `ImageLib.VERSION` is 1 |
| `ImgImage` | A struct: `w`, `h` (`int`), and `pixels`, a `ptr<u32>` to `w * h` of them |
| `Img.Decode: data length` → | A `ptr<ImgImage>` from a file in any format imagelib reads, or 0 with the reason in `Img.error` |
| `Img.DecodeBmp: data length` → | The same, for a BMP file |
| `Img.DecodePng: data length` → | The same, for a PNG file |
| `Img.Format: data length` → | Which format the bytes are in, from their first few: `Img.BMP`, `Img.PNG`, or `Img.UNKNOWN` |
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

**Stricter than libpng,** where it would show something after a warning: the file must run through IEND,
the image data must be exactly what the image needs (no more, and no less), and every critical chunk's CRC
must match. **Refused as invalid:** what PNG doesn't have (color types, bit depths, methods, filter types),
chunks whose names aren't letters, a missing or late PLTE in a palette image, IDATs that aren't one after
another, unknown critical chunks (such as Apple's `CgBI`), and image data that's damaged, cut short, or the
wrong size. **Not done:** APNG's other frames, and showing an image that's cut short (it's refused).

## How it's checked

From the repo's root:

```
pwsh ./build.ps1 image -Test                         # (or .\build.ps1 image -Test on Windows)
python3 -P tools/image/make_bmp_tests.py --bmpsuite DIR    # remakes tests/bmp/ (it's committed)
python3 -P tools/image/make_png_tests.py                   # remakes tests/png/ (it's committed)
```

Each format's rules are written plainly in Python, in [tools/image](../../tools/image), and checked against
outside evidence before any case is written; imagelib follows them check for check.

**BMP:** the rules are [bmp_reference.py](../../tools/image/bmp_reference.py), and `make_bmp_tests.py` checks them against BMP Suite's reference images and Pillow before it writes any
case: it stops at any difference that isn't listed with its reason. Each case's expected result is then
the rules', and imagelib must give the same size and pixels, or refuse for the same reason. (`DIR` is
BMP Suite 2.8 unpacked, for its reference images. Without it, the script checks against Pillow alone.
`-P` rather than `-I`, since Pillow is usually in the user's site-packages.)

**PNG:** the rules are [png_reference.py](../../tools/image/png_reference.py), and `make_png_tests.py` checks
them against PngSuite (its broken files are named so) and two decoders that share no code: ImageMagick,
which reads PNG with libpng, and Pillow. Every pixel must be what libpng gives, at 16 bits and rounded the
same way, and every file the rules refuse must be refused by libpng too, except for the few listed where the
rules are stricter or more lenient. Pillow's differences are counted, and each has a reason below. It needs
`magick` on the path; `--pngsuite DIR` copies PngSuite-2017jul19 in from `DIR` first.

| Test | What it proves |
|---|---|
| `test_bmp` | The decoder against the rules, on the cases in [tests/bmp](tests/bmp) (listed in `cases.txt`): BMP Suite's files, files made for what it doesn't cover, good files cut short at many lengths, and files with bytes changed |
| `test_bmp_fuzz` | 100,000 random changes to good files, every value of each of the first 160 bytes of ten of them, troublesome numbers in every header field, and noise. All must come back, with an image within the limit or a reason |
| `test_png` | The same for PNG, on the cases in [tests/png](tests/png): PngSuite's files; files made for what it doesn't cover (every color type and depth at 13 sizes, interlaced and not, every filter, tRNS and PLTE of each kind, chunks in each wrong place, image data that's damaged, short or too long); good files cut short; and files with bytes changed, most with their CRCs mended so the change reaches what it was aimed at |
| `test_png_fuzz` | 100,000 random changes to good files (three in four with their CRCs mended), every value of each of the first 64 bytes of eight, troublesome numbers in every field of the first 100 bytes, and 30,000 files made from noise: random pixel data of about the right size in stored blocks with the right Adler-32, so that it reaches the filters and the pixels. All must come back, with an image within the limit or a reason |
| `test_image` | The API: finding the format, the limit, the reasons, freeing, and `BlendRow` against values worked out in Python |
| `tests/use/test_imagelib` | The compiled `imagelib.philib` on its own, with corelib reached through it (its reader for BMP, and its inflate for PNG) |

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
| ImageMagick, on the 531 files made here | 472 the same, pixel for pixel; 52 refused by both; 4 refused here where libpng warns and shows something (a PLTE after the image data, and image data that's too long, three ways); 1 read here where libpng gives up (a palette index past the end of the palette); 2 refused for the pixel limit |
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
| Made here | 531 of 531: 473 read, 58 refused |
| Good files cut short | 2,226 of 2,226 refused (the file must run through IEND) |
| Files with a few bytes changed | 4,000 of 4,000 (294 read, 3,706 refused); and 40,000 of 40,000 with another seed, run once |
| Fuzzing: 100,000 random changes, 131,072 values of the first 64 bytes, 14,952 troublesome numbers, 30,000 files from noise | No crash or hang, and every image within the limit |

**Speed,** for 2048 by 2048 images saved by Pillow (a gradient with noise, so each is a few MB), as a 64-bit
Linux program (32-bit is about the same), with Pillow 11.1 decoding and converting to RGBA for comparison.
Most of the time is corelib's inflate, which is about 6 times slower than zlib's; the rest is unfiltering
and making the pixels:

| Pixels | imagelib | of which inflate | Pillow |
|---|---|---|---|
| RGB, 8 bits | 269 ms | 224 ms | 43 ms |
| RGBA, 8 bits | 363 ms | 294 ms | 56 ms |
| RGBA, 8 bits, interlaced | 382 ms | 291 ms | 68 ms |
| Gray, 8 bits | 100 ms | 72 ms | 18 ms |
| Gray, 16 bits | 168 ms | 136 ms | 33 ms |
| Palette, 8 bits | 66 ms | 57 ms | 13 ms |
| Gray, 1 bit | 27 ms | 10 ms | 6 ms |
