# vectorlib

Shapes drawn smooth onto pixels: paths of lines, curves and arcs (and SVG's path data), placed by a
matrix, filled by either rule or outlined with joins, caps and dashes, in a color, a gradient or an
image, and kept within a box or another shape. It draws onto pixels the program gives it,
`0xAARRGGBB` with straight alpha (what imagelib gives and PHI's `gfx.draw` draws), and touches
nothing else. It depends on no other library here.

What it's for: SVG drawings and their gradients, clipping and transforms in a browser; a `<canvas>`;
smooth shapes in a paint program; round corners and shadows in a desktop.

```phi
use vectorlib;

call VectorLib.Start;
VgCanvas c;
call c.Start: pixels w h w;                          # the program's pixels, w by h, a row w apart
ptr<VgPath> p: (Vg.NewPath);
bln whole: (p.Svg: 'M10 10 h80 a20 20 0 0 1 0 40 h-80 z');
VgPaint fill;
call fill.Linear: 0 0 100 0;
call fill.Stop: 0.0 0xFFE5484D;
call fill.Stop: 1.0 0xFF2F6FE4;
call c.m.Rotate: (Vg.Radians: 10);
bln drew: (c.Fill: p fill Vg.NONZERO);
VgPaint ink;
call ink.Solid: 0xFF000000;
drew is (c.Stroke: p ink 2.0 Vg.ROUND Vg.ROUND 4.0);
call Vg.FreePath: p;
call c.Done;
```

## API

These names are the API. Everything else (`VgScan`, the canvas's working fields and helpers) is how
it works, and may change.

| Name | What it is |
|---|---|
| `VectorLib.Start` | Call once, before anything else. `VectorLib.VERSION` is 1 |
| `Vg.NewPath` →, `Vg.FreePath: p` | A path on the heap (0 if there's no memory), and giving it back |
| `VgPath` | `MoveTo: x y`, `LineTo`, `QuadTo: cx cy x y`, `CubicTo: c1x c1y c2x c2y x y`, `ArcTo: rx ry turn large sweep x y` (SVG's elliptical arc), `Arc: cx cy r a0 a1 ccw` (a canvas's), `Close`; whole shapes as parts of their own: `Rect: x y w h`, `RoundRect: x y w h rx ry`, `Ellipse: cx cy rx ry`, `Circle: cx cy r`; `Svg: d` → (SVG path data; false at an error, keeping what came before it, as browsers draw it), `Append: other`, `Clear`, `Empty` →; `failed` (memory ran out) |
| `VgMatrix` | `a b c d e f` as SVG's `matrix()`: `Identity`, `Set`, `Copy: m`, `Translate: x y`, `Scale: sx sy`, `Rotate: radians`, `Skew: ax ay`, `Multiply: m`, `Then: a b c d e f` (each acts before what's there, as SVG's and a canvas's do), `X: x y` →, `Y: x y` →, `Invert: into` →, `Scaling` → |
| `VgPaint` | `Solid: color`; `Linear: x0 y0 x1 y1`, `Radial: cx cy r` and `Focus: fx fy`, then `Stop: offset color` (16 at most); `Image: pixels w h stride` (a pattern, a pixel a unit); fields `spread` (`Vg.PAD`, `REPEAT`, `REFLECT`, and `NONE` for an image), `opacity` (0 to 1), `smooth` (an image's, bilinear), `m` (its own units in the drawing's: SVG's `gradientTransform`) |
| `VgCanvas` | `Start: pixels w h stride`, `Done`; `m` (the matrix), `alpha` (0 to 1), `tolerance` (0.05 px); `Fill: path paint rule` →, `Stroke: path paint width join cap limit` →, `SetDash: lengths n offset`, `Picture: image iw ih stride x y w h smooth` →; `ClipBox: x0 y0 x1 y1` (pixels), `ClipPath: path rule` →, `NoClip` |
| `Vg` | `NONZERO`, `EVEN_ODD`; joins `MITER`, `ROUND`, `BEVEL`; caps `BUTT`, `ROUND`, `SQUARE`; `PI`, `Radians: degrees` →, `Atan2: y x` →, `Tan` →, `Premultiply: color opacity` →, `Mix: a b w` → |

Each drawing call answers false when there's no memory; a shape with nothing to draw is true.

## How it draws

**Coverage, exactly.** A shape is cut into straight edges (a curve into as many as keep within
`tolerance` of a pixel of it, after the matrix). Each edge adds, to each pixel it passes through, the
part of the pixel's area to its right, signed by its direction (the accumulation font-rs uses, after
FreeType's). Summed along a row, that's how much of each pixel is inside: exact wherever no two edges
cross in one pixel. Nonzero takes that as at most 1; even-odd folds it every 2. Only the shape's box
(within the clip) is worked on.

**Outlines** are made into a shape first, as FreeType's stroker makes them: along one side of each
part, round its end cap, back along the other side; a closed part is its two sides, one each way. A
join is on the outside of each corner (a miter, cut to a bevel when it's longer than `limit` times
the width, as SVG has it; a bevel; or round), and the inside goes through the corner itself, so that
where the two sides overlap they overlap the same way round and the nonzero rule fills them once.
An outline is made in the drawing's own units, so the matrix shapes the line as it shapes the path.
Dashes cut the parts first, as SVG reads `stroke-dasharray` (an odd list read twice).

**Paint** is blended source-over, straight alpha both sides, so an opaque canvas stays opaque.
Gradients mix their stops premultiplied (CSS's way, and a canvas's: a color fading to clear doesn't go
gray), in a table of 256 steps. A radial gradient's focus is kept just inside its circle, as SVG keeps it.

**Clipping** by a shape keeps a byte for each pixel of the canvas: how much of it shows.

## Not done

Dashes on a curve are cut along its straight pieces (close, not exact). Patterns other than an image,
masks, filters, blend modes other than source-over, gradients mixed in another color space, text
(that's fontlib's), and a nested clip's saving and restoring (the program keeps its own) are later.

## How it's checked

```
pwsh ./build.ps1 vector -Test                                  # about 10 s
python3 -I tools/vector/check_svg.py PHI [--keep DIR]          # against Quartz (macOS)
```

| Test | What it proves |
|---|---|
| `test_vector` | Each part once: the area every shape covers (summed from its pixels' alpha) beside its true area; small shapes as pictures; gradients', images' and blending's exact pixels; clipping; SVG path data with each command, short forms, numbers like `1e1` and `.5.5`, and an error part way |
| `tests/use/test_vectorlib` | The compiled `vectorlib.philib` on its own |

**Areas (2026-11-20):** shapes of straight edges come within 5/255 of a pixel of their true area, or
exactly; curved ones about 1% under (a circle of radius 6: 112.2 pixels of 113.1), as each straight
piece cuts inside its curve by up to the tolerance. The same output on 32 and 64-bit Linux and macOS.

**Against Quartz (2026-11-20, macOS 27):** `check_svg.py` draws 15 scenes (fills by each rule, arcs
with each flag, each join and cap, outlined curves, dashes, a matrix, gradients, an outline painted
with a gradient) with vectorlib and with Quartz (CoreGraphics), its paths read independently in
Python. In every scene compared, at most 2 pixels in 4,096 differ by more than 64 (where two edges
cross in one pixel), and the mean difference is at most 1.2 of 255. Quartz has no repeating
gradients, so the one scene of a reflected gradient isn't compared. ImageMagick's own SVG renderer was
tried first and set aside: it repeats a padded gradient, tiles a radial one and cuts miters flat.
