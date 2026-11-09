# fontlib

Fonts in; metrics, outlines and smooth glyph bitmaps out. So far it reads TrueType fonts: the face, each
glyph's outline and metrics, in font units, and which glyph a character is; and it makes glyphs' bitmaps
at a size, exactly as FreeType makes them ([plan.md](../../plan.md#phase-4-font-library), milestones 4.1
and 4.2). It uses [corelib](../core), so a program
using it has both `fontlib.philib` and `corelib.philib` beside it.

```phi
use fontlib;

call FontLib.Start;
ptr<FntFace> face: (Fnt.Load: bytes length);        # the bytes must stay as they are until Fnt.Free
if face is 0
	log 'bad font: ' Fnt.error '\n';
	return;
;;
ptr<FntOutline> o: (Fnt.NewOutline);
if (Fnt.Outline: face (Fnt.GlyphOf: face 0x41) o)   # 'A'
	# o.points points at o.x, o.y (o.on: 1 on the curve, 0 a quadratic control point),
	# in o.contours contours, each ending at o.ends:k; o.advance
;;
call Fnt.FreeOutline: o;

ptr<FntSize> size: (Fnt.AtSize: face 16);           # 16 pixels per em
ptr<FntBitmap> b: (Fnt.Bitmap: size (Fnt.GlyphOf: face 0x41));
if b is not 0
	# b.width by b.height bytes of coverage at b.pixels, top row first, b.left right of the pen and
	# b.top above the baseline; then move the pen b.advance / 64 pixels
;;
call Fnt.FreeSize: size;                            # its bitmaps too
call Fnt.Free: face;
```

## API

These names are the API. Everything else the library declares (`FntTrueType`, `FntFrame`,
`FntMacRoman`, `FntRaster`, `FntCell`, `FntSize`'s `scale`, `cache`, `outline` and `raster`, and
`Fnt`'s `Grow`, `Release`, `ReleasePoints`, `Done`, `Failed`, `DivFix`, `Make` and `FreeBitmap`) is how it
works, and may change.

| Name | What it is |
|---|---|
| `FontLib.Start` | Call once, before anything else. It starts corelib too. `FontLib.VERSION` is 1 |
| `FntFace` | A struct: `glyph_count` (`u32`), and in font units (`int`): `units_per_em`, `ascender`, `descender` (negative), `height` (baseline to baseline) and `max_advance` |
| `Fnt.Load: data length` → | A `ptr<FntFace>`, or 0 with the reason in `Fnt.error`. `data` must stay as it is until `Fnt.Free` |
| `Fnt.Free: face` | Gives back a face's memory (0 does nothing); not its bytes, which are the caller's |
| `Fnt.GlyphOf: face code` → | The glyph for a Unicode code point, as HarfBuzz finds it, or 0 if the font has none |
| `Fnt.Advance: face glyph` → | The glyph's advance from `hmtx`, in font units, as text is laid out with it (HarfBuzz's) |
| `FntOutline` | A struct: `points`, `contours` (`u32`), `advance` (`int`, FreeType's: the glyph's, or a component's that says so), and `x`, `y` (`ptr<int>`), `on` (`ptr<u8>`) and `ends` (`ptr<u32>`) |
| `Fnt.NewOutline` → | An outline to load glyphs into, again and again; its arrays grow as they need to |
| `Fnt.Outline: face glyph outline` → | Loads a glyph's outline: true, or false with the reason in `Fnt.error`, and the outline empty |
| `Fnt.FreeOutline: outline` | Gives back an outline's memory (0 does nothing) |
| `Fnt.MOST_POINTS`, `Fnt.MOST_CONTOURS` | 32,767 each: the most one outline may have, as in FreeType |
| `Fnt.AtSize: face ppem` → | A `ptr<FntSize>`: the font at `ppem` pixels per em (1 to 16,384), or 0 with the reason in `Fnt.error`. The face must stay until `FreeSize` |
| `FntSize` | A struct: `face`, `ppem`, and the line in 64ths of a pixel, rounded to whole pixels as FreeType rounds them: `ascender` (up), `descender` (down), `height` and `max_advance` |
| `Fnt.Bitmap: size glyph` → | A `ptr<FntBitmap>`, the glyph at that size, made the first time it's asked for and kept by the size (not to be freed); or 0 with the reason in `Fnt.error` |
| `FntBitmap` | A struct: `width` by `height` bytes of coverage (0 to 255) at `pixels`, a row at a time from the top (`pixels` is 0 when there are none); `left` (pixels right of the pen), `top` (pixels above the baseline), and `advance` (64ths of a pixel) |
| `Fnt.FreeSize: size` | Gives back a size's memory and its bitmaps (0 does nothing) |
| `Fnt.MOST_BITMAP_PIXELS` | 1,048,576: the most pixels a glyph's bitmap may have, so that a damaged font's glyph can't ask for gigabytes |
| `Fnt.error` | Why the last call failed |

**A bad font** gives 0 or false and a reason, never a crash or a hang. **One thread at a time:**
`Fnt.error` is shared.

## TrueType

Two references decide what fontlib makes of a font, as they decide what browsers show:

- **The face, the outlines and the metrics are FreeType's** (2.13, unscaled and unhinted): its reading
  of the table directory (an entry past the end of the file is left out, and `hmtx` is clipped to it);
  the tables it needs (`head`, `hhea` and `hmtx`, `loca`; no `maxp` is no glyphs, and no `glyf` is no
  outlines); its checks on each glyph; its composites (each kind of offset and transform, matching
  points, `USE_MY_METRICS`, a scaled offset by its own fixed-point length, and a glyph that contains
  itself refused, however deep they nest); its limit of 32,767 points; and the shift it gives an
  unhinted outline so that its left edge is at the left side bearing. The line is `hhea`'s, or OS/2's
  typo metrics when its `USE_TYPO_METRICS` bit says so, or OS/2's when `hhea` has none.
- **Which glyph a character is: HarfBuzz's** (15.0), which is how browsers look a character up: its own
  reading of the directory and of `cmap`, its choice of subtable (symbol first, then (3,10), (0,6),
  (0,4), (3,1), (0,3) and the rest of Unicode's, then Mac Roman, then any other Mac one), formats 0, 4,
  6, 10, 12 and 13, and its fallbacks: a symbol font's U+F000 to U+F0FF also at U+0000 to U+00FF, Mac
  Roman through its table, and only ASCII for other Mac encodings. A subtable HarfBuzz's sanitizer fails
  leaves the font with no characters, as it does in HarfBuzz.

Coordinates are kept to 32 bits, where FreeType keeps 64: only a composite nested past any real font's
depth could tell them apart. **Not done yet:** CFF outlines (OpenType `.otf`, milestone 4.5), font
collections, and the Arabic code pages of HarfBuzz's symbol fallback (a symbol font whose OS/2 names
one maps nothing there).

## Bitmaps

A glyph's bitmap is FreeType's, exactly, as its smooth rasterizer makes it unhinted
(`FT_LOAD_NO_HINTING`, `FT_RENDER_MODE_NORMAL`), which is how browsers draw text on Linux:

- **The size:** the scale is `FT_DivFix(ppem * 64, units_per_em)`, and the glyph is loaded scaled as
  FreeType loads it: each simple glyph's points as they're read, then composites' transforms and scaled
  offsets, then the shift to the left side bearing. The advance is the scaled phantom points' difference.
- **The bitmap** is the outline's control box rounded out to whole pixels.
- **Coverage,** as ftgrays.c works it out: the outline read as `FT_Outline_Decompose` reads it; lines
  walked cell by cell in 256ths of a pixel (dividing by a reciprocal, as FreeType does on 64-bit systems);
  each quadratic curve split into 2^n lines by forward differences in 32.32 fixed point; each row swept
  from the left, by the non-zero winding rule. The cells kept are only those the outline crosses, so the
  memory is the outline's length, not its area.

**Not done:** hinting (left out on purpose, as the plan says), and the 4 times oversampling FreeType gives
a glyph that says its contours overlap (none of the fonts tested does).

## How it's checked

From the repo's root:

```
pwsh ./build.ps1 font -Test                       # (or .\build.ps1 font -Test on Windows)
python3 -P tools/font/make_font_tests.py          # remakes tests/ttf/cases.bin (it's committed)
python3 -P tools/font/make_raster_tests.py        # remakes tests/raster/cases.bin
pwsh ./build.ps1 font -Test -Release              # and the release tests too
python3 -P tools/font/make_font_tests.py --release
```

The rules are written plainly in Python, in [ttf_reference.py](../../tools/font/ttf_reference.py), and
`make_font_tests.py` checks them against freetype-py (FreeType 2.13.2) for the face and every glyph's
points, flags, contours and advance, and against uharfbuzz (HarfBuzz 15.0) for the glyph of every code
point to U+FFFF and every 16th to U+2FFFF. It stops at any difference. fontlib follows the rules check
for check. The fonts: Liberation Sans (in [tests/fonts](tests/fonts), OFL), 61 made with fontTools (each
feature and each kind of damage), and fonts cut short and fuzzed. A case's verdict is its face and two
CRC-32s: over every glyph, and over those characters' glyphs.

| Cases (2026-11-09, as 32 and 64-bit Linux programs) | Result |
|---|---|
| Everyday: Liberation Sans, the 61 made, 14 cut short, 40 fuzzed | 116 of 116 as the rules say, which are FreeType's and HarfBuzz's |
| Release: the same, 1,326 cut short and 4,000 fuzzed | 5,388 of 5,388 (3,805 read, 1,583 refused) |
| Fuzzing, every glyph (up to 3,000) of: 100,000 random changes, 1,024,000 values of the first 200 bytes, 119,100 troublesome numbers in the first 400 | No crash or hang, every outline within FreeType's limits |

**Bitmaps:** [raster_reference.py](../../tools/font/raster_reference.py) gives FreeType's bitmaps exactly,
and `make_raster_tests.py` stops if it doesn't, on any glyph: its advance, its bitmap's box, or any
pixel. A case is a font at a size, and its verdict the size's line and one CRC-32 over every glyph.

| Cases (2026-11-10, as 32 and 64-bit Linux programs) | Result |
|---|---|
| Everyday: Liberation Sans at 12 and 19 pixels, each made font at 12, 16 fuzzed at 5, 12 or 30 | 55 of 55 as the rules say, which are FreeType's, 5,422 glyphs |
