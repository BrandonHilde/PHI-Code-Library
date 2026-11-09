# fontlib

Fonts in; metrics, outlines and (later) smooth glyph bitmaps out. So far it reads TrueType fonts: the
face, each glyph's outline and metrics, in font units, and which glyph a character is
([plan.md](../../plan.md#phase-4-font-library), milestone 4.1). It uses [corelib](../core), so a program
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
call Fnt.Free: face;
```

## API

These names are the API. Everything else the library declares (`FntTrueType`, `FntFrame`,
`FntMacRoman`, and `Fnt`'s `Grow`, `Release`, `ReleasePoints`, `Done` and `Failed`) is how it works,
and may change.

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

## How it's checked

From the repo's root:

```
pwsh ./build.ps1 font -Test                       # (or .\build.ps1 font -Test on Windows)
python3 -P tools/font/make_font_tests.py          # remakes tests/ttf/cases.bin (it's committed)
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
