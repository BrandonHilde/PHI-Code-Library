# PHI Code Library: plan

A collection of libraries written in [PHI](../PHI), each of which builds to a `.philib` that any PHI
program can include with a single `use`. The first three are a **Web Library**, an **Image Library**
and a **Font Library**, and more will follow.

Written 2026-11-06. Status (2026-11-08): Phases 0 and 2 are done, and so is Phase 1's move (commit
`2e9743f`): weblib builds here, and all its tests pass from here (38 of 38 runs as Linux programs,
and the compiled test). Phase 1's tidying is left. Phase 3 is under way: imagelib reads BMP, PNG and
baseline JPEG (milestones 3.1 to 3.3), and its compiled test uses corelib through the chain.

| Library | File | What it does | Starts from |
|---|---|---|---|
| Web | `weblib.philib` | HTML, CSS and JavaScript: bytes in; DOM, computed styles and running scripts out | Existing work in `C:\labs\AI\browse` |
| Image | `imagelib.philib` | Image files in, pixels out | Nothing |
| Font | `fontlib.philib` | Font files in; metrics and smooth glyph bitmaps out | Nothing |
| Core | `corelib.philib` | Shared by Image and Font: checked byte reading and inflate | Nothing |

## Goals

1. **One line to use.** A program says `use imagelib;` and has everything, with no source and nothing
   to ship beside the finished program.
2. **Safe with hostile files.** Images, fonts and web pages come from strangers, so a bad file gives
   an error, never a crash or a hang.
3. **Measured against outside evidence.** Each library is checked against an outside test suite or a
   reference implementation wherever one exists, and its pass rate is reported as it stands.
4. **Easy to add to.** A new library follows one checklist and needs no changes to the others.
5. **Reusable by any PHI project.** This repo only makes `.philib` files. Build targets are handled by
   PHI's compiler and chosen by the project using a library, so nothing here picks one, and library code
   stays free of anything tied to one system.

**Not goals:** build targets, applications of any kind (the test browser stays its own project and uses
weblib like anyone else), changes to the PHI compiler from this repo, and matching FreeType or Chromium
feature for feature.

## What we're building on

### Findings

Each of these was checked on 2026-11-06, with PHI at commit `2753446` or `7fc1c6e`, which differ only in license files.

| Finding | How it was checked | What it means here |
|---|---|---|
| `weblib` builds on the current compiler: 45 s, 22.7 MB with `NASMENV=-O1` and no `--target` | Built a scratch copy | The move starts from something that builds. **Its tests haven't been run on this compiler**, and that's the first job in Phase 1 |
| `use` has no include path and can't go up a folder | `PhiCompiler.Resolve` | A library in another folder can't be reached by path, so the build must copy `.philib` files around |
| A library's dependencies must be beside it when it's built | Test: `mid` failed until `base.philib` was next to `mid.phi` | The build does this, in dependency order |
| A program needs every library it reaches, not only those it names | Test: a program with only `mid.philib` failed | Apps get the full set of dependencies copied beside them |
| `use dist.mid;` works when `dist/` is inside the program's folder | Test | Available if an app prefers a subfolder |
| A class named `Font` in a library breaks any program that also uses `gfx.font` | Test: a build error | Every class name needs a prefix |
| `weblib` has x87 assembly in `asm.` and `x64.` versions, in JS math and floating-point setup | Searched the source | It's the known exception to keeping library code free of anything tied to one CPU |
| A `.philib` only loads with the build of `phi` that made it | `CompiledLibrary.Load` | Never commit a `.philib`. Every compiler rebuild means rebuilding them all |
| Source beats compiled in the same folder | `PhiCompiler.Resolve` | A test beside a library's source tests the source, not the `.philib` |
| The standard library has no inflate, PNG or font-file code. `Draw.Blit` copies opaque pixels | Searched `lib/phi`, read `gfx/draw.phi` | Image and Font start from nothing, and alpha blending is ours to write |
| `C:\labs\AI\browse` isn't a git repo | `git status` | There's no history to keep, so a plain copy loses nothing |
| PHI's standard library is compiled into programs | `language.md`, `PhiCompiler` | A program using these libraries carries the license terms of both repos, so PHI moved to Apache-2.0 as well |

### Rules from the PHI documentation

- A library's methods that nothing calls are left out of a program, but **its class variables and
  text always go in**. Big tables must be built on the heap on first use, or loaded from a file.
- **Calls into a library are never inlined**, so a call per pixel is slow. APIs work on whole rows,
  glyphs and images.
- A library exposes everything it declares, so helpers are public too. Prefixes keep them from
  clashing, and each library's README says which names are its API.
- Locals are limited to 4,096 bytes per method and fixed arrays to 16,384 elements, so large buffers
  go on the heap.
- The code generator is simple: floating point on the x87, no register allocation, and `when` is a
  chain of compares. Pixel and glyph code should prefer integer or fixed-point math and lookup tables.

## Repository layout

```
PHI-Code-Library/
  plan.md
  README.md               what's here, and how to build and use it
  LICENSE, NOTICE
  build.ps1               builds the libraries in dependency order, into dist/
  libraries.psd1          the list of libraries and what each one uses
  docs/
    conventions.md        the rules every library follows
    phi-notes.md          compiler problems we hit, and what we want from PHI
  libs/
    core/   corelib.phi   README.md  docs/  test_*.phi  tests/
    image/  imagelib.phi  README.md  docs/  test_*.phi  tests/
    font/   fontlib.phi   README.md  docs/  test_*.phi  tests/
    web/    weblib.phi    README.md  docs/  test_*.phi  tests/   (today's weblib folder)
  tools/                  table generators, test runners, reference-data scripts, check_build.ps1
  dist/                   build output, not committed
```

**Not committed:** `*.philib`, `dist/`, `build/`, `*.img`, `*.actual`, and test262.

### How a build works

Because of the findings above, `build.ps1` does the following for each library, in dependency order:

1. Copy the library's dependencies from `dist/` next to its main file (git ignores them).
2. Run `phi build NAME.phi --library -o dist`.

It finds the compiler through `PHI_EXE`, falling back to the path in the PHI repo, and sets
`NASMENV=-O1` for development builds (without it, weblib takes minutes rather than seconds).

```
.\build.ps1                        # every library
.\build.ps1 image                  # one library, and what it depends on
.\build.ps1 -Test                  # and run the tests
```

It never passes `--target`, so `phi` decides what each `.philib` holds. To use a library, a project puts
the `.philib` files for it and its dependencies beside its program, and builds for whatever it needs.

`tools/check_build.ps1` tests `build.ps1` itself on a throwaway chain, including that it fails when it
should. Run it after changing `build.ps1`, or when PHI changes how libraries work.

### How the libraries depend on each other

```
imagelib ──┐
           ├──> corelib
fontlib ───┘

weblib      (depends on none of them)
```

**weblib stays independent.** Its job ends at a DOM and computed styles, and drawing belongs to whoever
uses it. A browser project is where the libraries meet: it reads `<img>` from the DOM and hands the bytes
to imagelib, and reads `font-family` and hands text to fontlib.

**Why corelib exists.** PNG and WOFF both need inflate, and web fetches will want gzip too. Two
libraries can't both declare the same class, so code they share has to live in a library of its own.

weblib's own `Wl*` core stays where it is. Moving it would churn about 63,000 lines for no gain to
anyone using the library. If a later library wants `WlBuf` or `WlAtoms`, that's the time to move them.

## Conventions for every library

[docs/conventions.md](docs/conventions.md) has the rules: name prefixes, bytes in and data out, handling
hostile input, code that can go anywhere, the two kinds of test, what counts as done, and how to add a library.

## Testing while in development

Nothing here has been released: it's all in development. During development we will use a light weight
minimum necessary tests to move forward quickly. Then when preparing for release we will do the full suite
of tests. But until then we will be efficient with our time. `build.ps1 -Test` runs the everyday tests, and
`-Release` adds the full suite ([the conventions](docs/conventions.md#tests)). imagelib's tests were split
so on 2026-11-08 (about 1,000 decodes every day, where there had been 23,600, and a few of every kind:
cut, fuzzed, a short crash fuzz), and corelib's and weblib's on 2026-11-09. `build.ps1 image -Test`
(corelib and imagelib) takes about 20 seconds; `build.ps1 web -Test` about 3 minutes, nearly all of
it building weblib's 15 test programs, whose cases are already cheap to run. Tests go through
`build.ps1`, which sets `NASMENV=-O1`: without it, NASM takes about 2 minutes to assemble each
weblib test, rather than 1 second.

## Phases

### Phase 0: Foundation

- [x] Rebuild `phi.exe` from PHI's latest commit
- [x] Add the Apache-2.0 `LICENSE`, and a `NOTICE` with the project's name and copyright line
- [x] Add `README.md`, `.gitignore`, `.gitattributes`, `docs/conventions.md`, `docs/phi-notes.md`
- [x] Write `build.ps1`, and try it on a two-library chain (`tools/check_build.ps1`)

**Done when:** `.\build.ps1 -Test` builds and tests a throwaway chain from a clean checkout.
**Done 2026-11-06:** all 7 checks in `tools/check_build.ps1` went the right way.
**On Linux, 2026-11-07:** all 7 again, under `pwsh` 7.6 on Fedora 42, with PHI on .NET 10. `build.ps1`
and `check_build.ps1` now find `phi` without `.exe`, turn `libraries.psd1`'s `\` paths into `/` for
`phi`, and run the PowerShell they're in rather than `powershell`.

### Phase 1: Bring in the Web Library

Copy, don't move, and leave `C:\labs\AI\browse` alone until the new copy has proved itself.

`browse` turned up on the Linux computer as `../browse` on 2026-11-07, and the move was done from there.
It was removed from this computer afterwards; the owner keeps a backup of it on a drive.

**The move:**
- [x] Run weblib's tests in `browse` on the rebuilt compiler, and write down the results. PHI has
      changed since they last ran (text too long for a `str` is now an error, for one), so any new
      failures need to be known about before the move, not confused with it afterwards.
      **2026-11-07, on Linux, PHI on .NET 10, from a copy of `browse` (so it was left untouched):
      37 of 38 runs passed in 23 minutes.** These were the first runs as Linux programs (the old
      results are Windows'). The one failure, `test_js_limits (linux)`, is the 32-bit check that the
      heap running out is a `RangeError`: it assumes the heap stops at 128 MB, as a 32-bit Windows
      program's does, but a 32-bit Linux program's grows with `brk` and has no cap, so filling it
      took longer than the test's 600 s (see [phi-notes.md](docs/phi-notes.md)). PHI now lets a
      program set its heap's limit, 128 MB by default in 32-bit code, and the test passes
- [x] Check that nothing being brought in was copied from outside GPL code, and list what came
      from elsewhere and its license: [libs/web/THIRD_PARTY.md](libs/web/THIRD_PARTY.md). WPT's and
      Unicode's license texts weren't beside their data, and now are
- [x] Copy `weblib/` to `libs/web/`, along with its docs and the tools it needs (in `tools/web/`). The
      test browser stays out, as its own project, and so does `browser_roots.py`, which is its
- [x] Commit the small suites (html5lib, CSS parsing, JS fixtures, about 5 MB), with their licenses
- [x] Leave out test262 (217 MB): `tools/web/fetch_test262.py` fetches it at commit `d115437`, and
      `js_test262.py` says so when it's absent. `test_js262`'s self-test needed three of its harness
      files, which are kept with the self-test's own fixtures
- [x] Fix paths that assumed the old layout (the Python runners and generators, the README, DESIGN.md)
- [x] Add `weblib` to `libraries.psd1`
- [x] Give weblib's long tests the time they need: the tests' own time comments cover the four long
      ones, and `.\build.ps1 web -Test -Timeout 600` gives the rest what the README always used
- [x] Add the compiled-library tests in `tests/use/`: `test_weblib` parses, serializes and runs a
      script through `weblib.philib` alone

**Tidying, in commits of its own after the move passes:**
- [ ] Update `DESIGN.md`'s trap list. PHI has fixed several since it was written, including 5
      (`(F: x).field`), 23 (bare file names) and 24 (`not (s.Method: x)`)
- [ ] Add a dated note to the copy of `PHI_Assessment.md`, since many of its items have been fixed

**Done when:** all 19 test programs pass from the new location under plain `phi test`, and the suite
results match the baseline below (or differences are explained).
**2026-11-07:** from `libs/web`, through `.\build.ps1 web -Test -Timeout 600` in 24 minutes, the same 37
of 38 as the baseline, with the same one failure, and `tests/use` 2 of 2. All 19 pass on `linux64`.
Once PHI's heap limit was the program's to set (see the first item above): 38 of 38, in 4 minutes.
The outside suites, rerun on Linux the same day, are in the table below.

**Then, bringing weblib in line with [the conventions](docs/conventions.md)** (this doesn't hold up the
phases after it):
- [ ] Take `--target` and promises about particular systems out of its docs
- [ ] Move the use of `OS.Now` and `OS.GetTicks` (`Date`, and seeding `Math.random`) behind hooks
- [ ] List its x87 assembly, and write plain PHI versions where they're practical

| Suite | Last recorded (browse README, Windows) | Linux, 2026-11-07 |
|---|---|---|
| html5lib / WPT tree construction | 14,792 of 14,792 | the same (`test_html5lib.expected`) |
| html5lib tokenizer | 14,084 of 14,084 | the same |
| CSS parsing tests | 8,331 of 8,338 | the same (`test_css_syntax.expected`) |
| test262 `language` | 21,487 of 23,015 (93.4%), no crashes | the same, as a 64-bit program |
| test262 `built-ins` | 14,351 of 17,398 (82.5%) of the families built so far, no crashes | 14,577 of all 23,848 (61.1%), no crashes |

The old `built-ins` figure left out families that weren't built, but which ones wasn't written down,
so the Linux run counts all of them. Leaving out those at 0% because they aren't there (`Temporal`,
`Atomics`, `SharedArrayBuffer`, `BigInt`, `ShadowRealm`, `DisposableStack`, `AsyncDisposableStack`,
`SuppressedError`) and `Iterator` (2%) gives 14,561 of 17,702 (82.3%).

### Phase 2: Core Library

Small on purpose: only what Image and Font both need.

- [x] `CoreReader`: bounds-checked reads, big and little endian, with a sticky failure
- [x] `CoreBits`: a bit reader in either bit order
- [x] `CoreInflate`: DEFLATE, zlib and gzip framing, with a limit on output size
- [x] Adler-32 (CRC-32 already exists as `data.crc32`)

**Checked by:** streams from Python's `zlib` at every compression level, stored blocks and malformed
streams, and a fuzz test.

**Done when:** every reference stream inflates byte for byte, every malformed one fails cleanly, and
imagelib's first test uses `corelib.philib` through the chain.
**Done 2026-11-08:** imagelib's `tests/use/test_imagelib` builds against `imagelib.philib` and
`corelib.philib` alone, and reaches corelib through imagelib. **2026-11-07,** the rest: In [libs/core](libs/core): 160 of 160
reference streams inflate as zlib does, byte for byte; 43 of 43 broken ones and 3,513 of 3,513 cut
short are refused; zlib's verdict and corelib's agree on 600 of 600 fuzz cases; and 100,000 random
changes, every value of the first 48 bytes, and noise all come back without a crash. **2026-11-08:**
a fast path, like zlib's `inflate_fast`, took it from about 100 to 185 MB/s on text, and from 57 to
135 MB/s on PNG image data (zlib in C: 851 and 376).

### Phase 3: Image Library

Output is one format whatever the input: 32-bit straight-alpha `0xAARRGGBB` pixels. Fully opaque
images work directly with `Draw.Blit`, and `Img.BlendRow` covers the rest.

```phi
# the API, as built in 3.1
use imagelib;

call ImageLib.Start;
ptr<ImgImage> image: (Img.Decode: bytes length);        # finds the format from the bytes
if image is 0
	log 'bad image: ' Img.error '\n';
	return;
;;
call Draw.Blit: 10 10 image.w image.h image.pixels image.w;
call Img.Free: image;
```

| Milestone | Scope | Checked against |
|---|---|---|
| 3.1 BMP ✓ | Every header size, bit depths 1 to 32, bit fields, RLE8 and RLE4; the simplest format, to settle the API | BMP Suite's reference images, and Pillow |
| 3.2 PNG ✓ | All color types and depths, interlacing, gamma ignored at first | PngSuite: valid images match, broken ones fail cleanly |
| 3.3 JPEG baseline ✓ | Huffman, integer IDCT, chroma subsampling | Pillow/libjpeg within a small per-pixel tolerance, since decoders legally differ |
| 3.4 JPEG progressive ✓ | Common on the web | The same |
| 3.5 GIF ✓ | LZW, transparency, and animation frames with their timing | Pillow |
| 3.6 Scaling ✓ | Nearest and bilinear, working by rows | Pillow, within a tolerance |
| Later | WebP, then encoders (PNG first), SVG (shares fontlib's rasterizer), AVIF only if needed | |

Tests compare decoded pixels with reference data, so no viewer program is needed here.

**3.1, done 2026-11-08,** in [libs/image](libs/image). The rules are written plainly in Python
(`tools/image/bmp_reference.py`), checked against BMP Suite's reference images and Pillow, and every
difference is listed with its reason. Where those two disagree, the choice is BMP Suite's, which is
the browsers': RLE's skipped pixels are transparent, channels are scaled so their top value is 255,
and alpha comes only from an alpha mask. imagelib agrees with the rules on all 9,268 cases (BMP Suite's
89 files, 390 made here, 4,789 cut short, 4,000 changed) as 32 and 64-bit Linux programs, and comes
back from 526,260 fuzzed files without a crash. Not done: 64-bit pixels, Huffman 1D, RLE24 and
embedded JPEG and PNG (refused, saying so). A 2048 by 2048 image takes 6 to 17 ms. `Img.BlendRow`
is in, and `Img.max_pixels` is the limit, 4096 by 4096 by default.

**3.2, done 2026-11-08,** in [libs/image](libs/image), the same way: the rules are in
`tools/image/png_reference.py`, and ImageMagick (libpng) gives the same pixels as the rules, at 16 bits,
on all 162 of PngSuite's good files and the 472 good files made here, and refuses its 14 broken ones.
Pillow's differences are listed with their reasons. Where libpng only warns, the rules follow it for
ancillary chunks (ignored) and are stricter for the rest: the file must run through IEND, and the image
data must be exactly the image's size. imagelib agrees with the rules on all 6,933 cases (and 40,000
more fuzz cases with another seed), as 32 and 64-bit Linux programs, and comes back from 276,024 fuzzed
files without a crash. A 2048 by 2048 RGBA image took 363 ms, 294 of them corelib's inflate; with
inflate's fast path it takes 190 ms, 126 of them inflate (Pillow: 56 ms). Not done: APNG's other frames.

**3.2, made to show what it can, 2026-11-08,** as the owner asked: not stricter than libpng and
Pillow. The image is done at the end of its IDATs (no IEND needed), image data past what it needs is
ignored, and image data that ends too soon gives the rows that came whole, the rest transparent, as a
browser shows it. corelib's new `ZlibUpTo` inflates up to a limit and keeps what it made when the data
ends; it agrees with zlib on 2,689 of 2,689 cases. The 1,554 cut files now read show exactly the rows of
the images they were cut from, and every fuzzed one libpng refuses is what Pillow gives, reading as far
as it goes. imagelib agrees with the rules on all 6,933 cases.

**3.3, done 2026-11-08,** in [libs/image](libs/image). Better than the tolerance planned: the rules
(`tools/image/jpeg_reference.py`) decode as libjpeg-turbo does by default, step for step (its integer
IDCT as its C code works it out, its fancy upsampling, its color tables, and its recovery from damage),
so the pixels are the same as libjpeg-turbo's, exactly: on all 121 files libjpeg-turbo wrote, the 212
the script's own encoder wrote that libjpeg reads (every sampling layout that divides evenly, one
component a scan, restart intervals, 16-bit tables, each way of naming the color space, and damaged
ones), and the 894 cut short and 2,229 fuzzed that it reads. There's no free JPEG suite, so the script
makes its files. imagelib agrees with the rules on all 7,435 cases, as 32 and 64-bit Linux programs, and
comes back from 477,807 fuzzed files without a crash. As the owner asked, it isn't stricter than libjpeg:
a damaged or cut-short file shows what libjpeg shows. A 2048 by 2048 photo takes 162 ms at 4:2:0
(Pillow, with libjpeg-turbo's SIMD: 22 ms). Not done: progressive (3.4), CMYK, 12-bit, arithmetic
coding, EXIF orientation.

**3.4, done 2026-11-09,** in [libs/image](libs/image), tested the light way: progressive files written
by libjpeg-turbo (Pillow's standard progression, at several sizes and subsamplings, gray, with restart
markers, and ImageMagick's at 4:1:1), one made case for each kind of bad progression, and a few cut and
fuzzed. The rules follow libjpeg's `jdphuff.c` step for step, and libjpeg gives the same pixels on every
progressive file it reads, exactly; refused where it refuses. Not done: libjpeg's block smoothing of a
progressive image whose low AC coefficients haven't all come (a file cut short), which the tests count
and don't compare.

**EXIF orientation, done 2026-11-09,** for JPEG (APP1) and PNG (`eXIf`): read as Chrome reads it, applied
as Pillow's `exif_transpose` applies it, on by default (`Img.ignore_orientation` turns it off), and
`Img.orientation` says what it was. Every orientation, in both byte orders, matches ImageMagick's
`-auto-orient` and Pillow; three cases where Chrome and ImageMagick differ (a LONG value, the next APP1
after a bad TIFF header, an APP1 after the first scan) follow Chrome.

**3.5, done 2026-11-09,** in [libs/image](libs/image): GIF, still and animated, through
`Img.OpenAnimation` and `Img.NextFrame` (which open any format, a still image as one frame). The rules
(`tools/image/gif_reference.py`) follow the browsers where Pillow and ImageMagick differ from them: a
transparent canvas, the background color ignored, the screen grown for a first frame past its edge as
Chrome grows it, disposal 4 read as 3. Checked against Pillow, ImageMagick and the GIF test suite (63 of
75 files the same; the rest differ as listed), with every pixel the rules draw matching theirs. imagelib
agrees with the rules on all 161 everyday cases and the 5,536 release cases, as 32 and 64-bit programs, and
comes back from about 318,000 fuzzed files, every frame, without a crash.

**3.6, done 2026-11-09,** in [libs/image](libs/image): `Img.Scale`, nearest and bilinear, a row at a
time. Better than the tolerance planned: the rules (`tools/image/scale_reference.py`) give Pillow's pixels
exactly, nearest by Pillow's own running sum of doubles, bilinear (Pillow's triangle filter, premultiplied
alpha, across then down) with its weights worked out in exact integers. imagelib agrees on all 67 everyday
cases and the 1,707 release cases, as 32 and 64-bit programs. Phase 3's milestones are done; WebP and the
encoders are "later".

**Done when:** milestones 3.1 to 3.6 pass, PngSuite's results are in the README, every decoder has been
fuzzed, and a pixel bomb is refused before it allocates.

### Phase 4: Font Library

Glyph bitmaps are 8-bit coverage, ready to blend in any color. Text is UTF-8.

```phi
# proposed API
use fontlib;

call FontLib.Start;
ptr<FntFace> face: (Fnt.Load: bytes length);            # the caller keeps bytes alive
ptr<FntSized> sized: (Fnt.AtSize: face 16.0);
int width: (Fnt.Measure: sized text length);
call Fnt.Draw: sized pixels stride 10 30 text length color;
call Fnt.Free: face;
```

| Milestone | Scope | Checked against |
|---|---|---|
| 4.1 TrueType reading ✓ | Table directory, `head`, `hhea`, `hmtx`, `maxp`, `cmap`, `loca`, `glyf`, composite glyphs | FreeType's numbers (through `freetype-py`), for outlines and metrics |
| 4.2 Rasterizer | Anti-aliased coverage in fixed-point, with a glyph cache | FreeType's bitmaps, within a tolerance |
| 4.3 Simple text | UTF-8, advances, line metrics, measuring and drawing a run, fallback across faces | HarfBuzz advances, and reference bitmaps |
| 4.4 Kerning | `kern`, and pair adjustment in `GPOS` | FreeType/HarfBuzz advances |
| 4.5 OpenType CFF | `.otf` outlines | FreeType |
| 4.6 Web fonts | WOFF 1 (uses inflate) | Sample fonts, compared with the same font unpacked |
| Later | Ligatures (`GSUB`), WOFF2 (needs Brotli), variable fonts, color fonts, TrueType hinting | |

**Left out on purpose:** TrueType hinting (a bytecode VM that mostly matters at low resolution, and a
security risk) and complex scripts such as Arabic and Indic shaping, which are a project of their own.

**Brotli gets its own library when WOFF2 needs it.** Its dictionary is about 120 KB, and because a
library's data always goes in, it would otherwise land in every program using corelib.

**Finding fonts is the user's job.** fontlib takes bytes, so where fonts come from is up to the project
using it. Test fonts must have licenses that allow committing them, such as the OFL.

**A chance to help PHI:** PHI's own plan expects "a larger font loaded from a file" for text beyond
ASCII, and fontlib could provide it.

**4.1, done 2026-11-09,** in [libs/font](libs/font): the face, every glyph's outline and metrics, and
which glyph a character is. The rules (`tools/font/ttf_reference.py`) are FreeType's for the face, the
outlines and the metrics (unscaled, unhinted, composites included, and the shift of an outline to its
left side bearing), and HarfBuzz's for characters, as browsers look them up; HarfBuzz's cmap source was
read for what it does with damaged tables. Checked against freetype-py and uharfbuzz on Liberation Sans
(committed, OFL), 61 fonts made with fontTools, and cut and fuzzed ones: fontlib agrees on the 116
everyday cases and the 5,388 release cases, as 32 and 64-bit programs, and comes back from about 1.2
million fuzzed fonts without a crash. Not done: CFF (4.5), collections, and HarfBuzz's Arabic symbol
pages.

**Done when:** milestones 4.1 to 4.4 pass, a test draws Unicode text beyond code page 437 that matches its
reference, and every parser has been fuzzed.

### Phase 5 onward: Web Library features

Picked up when there's a reason to. Taken from weblib's list of what it doesn't do yet:

| Area | Missing | Note |
|---|---|---|
| HTML | Encoding sniffing, `<meta charset>` | Input is always read as UTF-8 today, which breaks older pages |
| JS | Modules, `BigInt`, `Intl`, `with`, direct `eval` | `BigInt` is most of what remains failing in test262's typed arrays |
| DOM | `MutationObserver`, `IntersectionObserver`, custom elements, shadow DOM | |
| Canvas | `<canvas>` | Becomes possible once Image and Font exist, through hooks |
| CSS | Nesting, `@container`, running animations and transitions | |
| Memory | Nodes aren't freed until their document is | Matters for long-lived pages |

## Order, and what can run at once

```
Phase 0 ──> Phase 1 (web)
       └──> Phase 2 (core) ──> Phase 3 (image)
                          └──> Phase 4 (font)
```

Phase 1 and Phase 2 are independent, as are Phases 3 and 4.

**Image comes before Font,** because BMP and PNG prove the library chain with little risk, whereas the
rasterizer is the harder job.

## Risks

| Risk | Effect | What we do |
|---|---|---|
| The compiler changes often and there's no release | Any `.philib` goes stale, and behavior can shift, as with the `str` change | Rebuild from source every time, never commit a `.philib`, and run tests after each compiler rebuild |
| Raw pointers aren't checked | A decoder bug can become silent memory corruption, and images and fonts are classic targets for this | Checked reads, fuzzing, limits, and the rule that sizes are checked first |
| Speed of generated code (a sieve ran about 1.8x slower than C#) | JPEG and glyph drawing may be slow on large inputs | Integer math, tables and whole-row APIs, plus a benchmark for each decoder. PHI's optimizing phase should help later |
| Every build makes every system `phi` builds for | weblib takes about 45 s and 22.7 MB, so the working loop is slower | Accepted, since targets are PHI's business. Build one library by name while working on it |
| No `use` include path | Copying `.philib` files around is a workaround | Keep it all inside `build.ps1`, and ask PHI for an include path or packages (below) |
| Code drifts toward one system | A project may find a library won't build or behave for its target | The rules under [Code that can go anywhere](docs/conventions.md#code-that-can-go-anywhere). weblib's x87 code is the known exception |

## What we'd ask of PHI

This repo doesn't change the PHI compiler, as weblib's design already says. Requests and problems go in
[docs/phi-notes.md](docs/phi-notes.md).

## Decisions needed

**`NOTICE` and weblib's tables.** `html/entities.phi` (from the HTML Standard's list, CC BY 4.0) and
`js/unicode.phi` and `js/casemap.phi` (from Unicode's data, Unicode License v3) are built into every
program that uses weblib. Whether `NOTICE` should name them is the owner's call
([libs/web/THIRD_PARTY.md](libs/web/THIRD_PARTY.md) lists them).

## Decisions made (2026-11-06)

| Decision | Choice |
|---|---|
| License | Apache-2.0 with a `NOTICE` file for this repo, PHI and its VS Code extension, because it clearly requires attribution, including in compiled programs. No exception waiving that for compiled output |
| Library names | `weblib`, `imagelib`, `fontlib`, `corelib` |
| Shared library | Keep `corelib`, rather than making Image and Font fully standalone |
| Order | Image before Font |
| Scope | This repo only makes `.philib` files for other PHI projects to use, with no applications in it |
| Targets | Not handled here. PHI's compiler handles them and the project using a library chooses, so this repo passes no `--target` and writes nothing for a particular system. It doesn't use PHI OS |
| `browse` after the move (2026-11-07) | Not needed here: the owner keeps it backed up on a drive, and the copy on the Linux computer was removed |
| A 32-bit program's heap (2026-11-07) | The program's to decide (`Heap.most_bytes` in PHI), 128 MB by default in 32-bit code on every system |
