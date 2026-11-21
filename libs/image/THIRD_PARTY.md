# What came from elsewhere

imagelib's code is its own: nothing in it was copied from another project, and nothing from GPL code.
What did come from elsewhere is test data, which keeps its own license, and one file of fixed data.

## Data built into programs

| Where | What | From | License |
|---|---|---|---|
| `imagelib/vp8tables.phi` | Lossy WebP's fixed tables: VP8's coefficient probabilities and their update probabilities, its 4x4 intra modes' probabilities, and its quantizer steps (RFC 6386, 13.4, 13.5, 12.3, 14.1) | Read out of libwebp's compiled library (1.6) by `tools/image/vp8_tables.py`, and checked against the RFC's values | libwebp's BSD 3-clause license (<https://chromium.googlesource.com/webm/libwebp/+/refs/heads/main/COPYING>); the same tables are in RFC 6386, whose code is under a BSD license too |

A program that reads lossy WebP carries these tables, so its notices should include libwebp's.

`tests/webp/` is made by `tools/image/make_webp_tests.py`, with libwebp's encoder and decoder through
ImageMagick, from images the script makes.

## Test data

Read by the tests, never built into a program.

| Where | What | From | License |
|---|---|---|---|
| `tests/bmp/bmpsuite/` | BMP Suite 2.8's image files, less `q/rgb24prof.bmp` and `q/rgb24prof2.bmp` | Jason Summers, <https://entropymine.com/jason/bmpsuite/> | Public domain: the suite's readme says its image files "are in the public domain (except for the embedded ICC profiles)". The two files with embedded profiles are left out. Its generator, which is GPLv3, isn't here, and nothing was copied from it |

| `tests/png/pngsuite/` | PngSuite 2017jul19's image files, with its `PngSuite.README` and `PngSuite.LICENSE` | Willem van Schaik, <http://www.schaik.com/pngsuite/> | Its own: "Permission to use, copy, modify and distribute these images for any purpose and without fee is hereby granted." (`PngSuite.LICENSE`, beside them) |

The rest of `tests/bmp/` and `tests/png/`, and all of `tests/jpeg/` and `tests/gif/` (`cases.bin`,
`cases.txt`, `release.bin`, `release.txt`), is made by `tools/image/make_bmp_tests.py`, `make_png_tests.py`,
`make_jpeg_tests.py` and `make_gif_tests.py`, from the suites' files and files they write themselves. Some of
the GIF files are written by Pillow and ImageMagick, from images made by the script. Some of the JPEG files are written by libjpeg-turbo, through Pillow and
ImageMagick, from images made by the script; the files are the script's output, and nothing of
libjpeg-turbo's is in them but its encoding.

## Used to check, not kept here

- **BMP Suite's reference images** (its `html/*.png`), which `make_bmp_tests.py --bmpsuite DIR` compares
  against, from a copy of the suite that isn't committed.
- **Pillow**, which `make_bmp_tests.py`, `make_png_tests.py`, `make_gif_tests.py` and `make_scale_tests.py`
  compare against. `Img.Scale` gives the pixels Pillow's `Image.resize` gives; nothing of Pillow's code is in
  it, and nothing was copied from it: the rules follow what its resampling does, worked out in integers.
- **The GIF test suite** (`test-suite` in <https://github.com/robert-ancell/pygif>, CC-BY-SA 4.0), which
  `make_gif_tests.py --gifsuite DIR` compares against, from a copy that isn't committed. Nothing of it is
  here.
- **ImageMagick** (`magick`, which reads PNG with libpng and JPEG with libjpeg-turbo), which
  `make_png_tests.py` and `make_jpeg_tests.py` compare against. Nothing of libpng's or libjpeg-turbo's is
  in imagelib, and nothing was copied from either: the JPEG decoder follows libjpeg-turbo's arithmetic (its
  IDCT's constants, its upsampling filter and its color tables) from what those algorithms are, so that
  the pixels match, and the tests prove that they do.
