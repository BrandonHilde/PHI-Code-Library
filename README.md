# PHI Code Library

Libraries written in [PHI](https://github.com/BrandonHilde/PHI). Each one builds to a `.philib`, which
a PHI program includes with a single `use` and needs none of its source. The library's code goes inside
the program, so there's nothing extra to ship.

## Libraries

| Library | What it does | Status |
|---|---|---|
| `weblib` | HTML, CSS and JavaScript: bytes in; DOM, computed styles and running scripts out | Moved here, in [libs/web](libs/web) |
| `imagelib` | Image files in, pixels out | Reads BMP, PNG, JPEG (baseline and progressive), GIF (animations too) and WebP (lossless and lossy, exactly as libwebp), writes PNG, and scales, in [libs/image](libs/image) |
| `fontlib` | Font files in; metrics and smooth glyph bitmaps out | Reads TrueType, CFF (`.otf`), WOFF and WOFF2 fonts (faces, outlines, metrics, characters), makes FreeType's glyph bitmaps, and measures, kerns and draws text, in [libs/font](libs/font) |
| `corelib` | Checked byte reading; inflate, deflate and Brotli; shared by `imagelib` and `fontlib` | Built and tested, in [libs/core](libs/core) |
| `vectorlib` | Shapes drawn smooth onto pixels: paths, SVG path data, transforms, gradients, outlines, dashes, clipping | Built and tested, in [libs/vector](libs/vector); checked against Quartz |
| `encodinglib` | Text in the web's encodings made UTF-8, and an HTML page's encoding found as browsers find it | Built and tested, in [libs/encoding](libs/encoding): UTF-8, UTF-16 and the 28 single-byte encodings |
| `netlib` | HTTP/1.1 messages for a client (requests, answers, gzip, deflate and Brotli bodies), cookies as browsers keep them, and TLS 1.2 for servers without 1.3 | Built and tested, in [libs/net](libs/net): checked against OpenSSL's server, and in PHI OS's browser |
| `editlib` | Text being edited: the caret, selecting, moving by words and lines, undo and redo, finding | Built and tested, in [libs/edit](libs/edit); PHI OS's text fields and Notes use it |

[plan.md](plan.md) has the roadmap. None has had its first release yet.

## Building

You need PHI's compiler, built with `dotnet build PHI.sln` (the .NET 10 SDK), and NASM. `build.ps1` looks
for the compiler in a `PHI` folder next to this one, or at the path in the `PHI_EXE` environment variable.

```
.\build.ps1                every library, into dist/
.\build.ps1 image          one library and what it depends on
.\build.ps1 -Test          and run the tests
```

On Linux, the same script runs in PowerShell 7 (`dotnet tool install --global PowerShell` installs it
without root): `pwsh ./build.ps1 -Test`.

This repo only makes `.philib` files. Which systems they hold is up to PHI's compiler, and which systems a
program runs on is up to the project building it.

A `.philib` only loads with the build of `phi` that made it, so rebuild after updating the compiler. For
that reason they're never committed.

## Using a library

Put the `.philib` beside your program, along with those of any libraries it depends on:

```phi
use imagelib;
```

## License

[Apache License 2.0](LICENSE). Programs built with these libraries contain their code, so if you
distribute one, include [LICENSE](LICENSE) and [NOTICE](NOTICE) with it. Programs contain code from PHI's
standard library too, so include [PHI's NOTICE](https://github.com/BrandonHilde/PHI/blob/main/NOTICE) as
well.

## Contributing

[docs/conventions.md](docs/conventions.md) has the rules every library follows, and how to add one.
