# encodinglib

Text in the encodings the web uses, made UTF-8, as the WHATWG Encoding standard decodes it; and an HTML
page's encoding found as browsers find it (HTML's encoding sniffing). For a browser before it hands a page
to weblib (which reads UTF-8), and for anything that opens old text files. It depends on no other library.

```phi
use encodinglib;

call EncodingLib.Start;
int enc: (Enc.Sniff: page length charset charset_length);   # the server's charset label, or 0 0
u32 size: 0;
ptr<u8> utf8: (Enc.Decode: enc page length addr size);       # on the heap: free it
log (Enc.Name: enc) '\n';                                     # 'windows-1252', 'KOI8-R', ...
```

## API

These names are the API. `EncTables`, `EncAttr` and `Enc`'s other methods are how it works, and may change.

| Name | What it is |
|---|---|
| `EncodingLib.Start` | Call once, before anything else. `EncodingLib.VERSION` is 1 |
| `Enc.Label: text n` → | The encoding a label names (ASCII whitespace round it and letters' case don't matter), or -1 for none, or one this library doesn't decode. 190 labels |
| `Enc.Name: enc` → | Its name as the standard writes it (`str`); `none` for -1 |
| `Enc.Decode: enc data length size_out` → | The bytes as UTF-8, on the heap (the caller frees them), their count in `size_out`; 0 with the reason in `Enc.error`. A byte-order mark says the encoding instead and goes, as the standard's *decode* has it |
| `Enc.Sniff: data length transport n` → | An HTML page's encoding: a byte-order mark's; else the server's label (`transport`, n bytes; 0 0 for none); else what a `<meta>` in the first 1,024 bytes says (HTML's prescan, its steps followed: comments passed over, `charset`, `http-equiv` with `content`, UTF-16 taken as UTF-8 and x-user-defined as windows-1252); else windows-1252, as browsers have it for a page that says nothing |
| `Enc.Prescan: data length` → | What a `<meta>` in the first 1,024 bytes says, by HTML's prescan alone: -1 if nothing (for a program with a guess of its own to make where a page says nothing) |
| `Enc.Bom: data length` → | The encoding a byte-order mark says, its length in `Enc.bom`; -1 for none |
| `Enc.UTF8`, `UTF16BE`, `UTF16LE`, `WINDOWS_1252`, `X_USER_DEFINED`, `REPLACEMENT` | Some encodings' numbers |

**The encodings:** UTF-8 (a bad sequence one U+FFFD for each maximal part, as the standard says),
UTF-16BE and LE (surrogates paired, or U+FFFD), the 28 single-byte ones (IBM866, ISO-8859-2 to -16 but -9
and -11 and -12, ISO-8859-8-I, KOI8-R, KOI8-U, macintosh, windows-874, windows-1250 to -1258,
x-mac-cyrillic), x-user-defined, and replacement (the whole text one U+FFFD: what a few dangerous labels,
like `iso-2022-kr`, name). Labels for ISO-8859-1 and US-ASCII name windows-1252, and for ISO-8859-9
windows-1254, as the standard has them.

**Not yet:** the East Asian encodings (GBK and gb18030, Big5, EUC-JP, ISO-2022-JP, Shift_JIS, EUC-KR).
Their tables are tens of kilobytes each, and would come as files a program gives the library, as
corelib's Brotli dictionary does. Their labels give -1, and `Sniff` passes over a `<meta>` naming one.

## Where its tables come from

`tools/encoding/make_tables.py` makes `encodinglib/tables.phi` from Python's codecs for the single-byte
encodings, made to agree with WHATWG's indexes where they're known to differ: the windows-* encodings' bytes
0x80 to 0x9F that have no character are the C1 control of the same number; KOI8-U's 0xAE and 0xBE are
U+045E and U+040E; windows-1255's 0xCA is U+05BA. Anything else WHATWG maps and Python doesn't would decode
to U+FFFD here (none is known). The labels are the standard's.

## How it's checked

```
pwsh ./build.ps1 encoding -Test
python3 -I tools/encoding/make_cases.py      # remakes tests/cases.bin (it's committed)
```

| Test | What it proves |
|---|---|
| `test_encoding` | Every single-byte encoding's 256 bytes, UTF-8 with each kind of bad sequence, UTF-16 both ways with lone and paired surrogates, byte-order marks, x-user-defined, replacement, and labels with spaces and capitals: 66 cases, each decoded as Python's codecs decode it. And sniffing on 18 pages made here, each answer worked out by the HTML standard's steps |
| `tests/use/test_encodinglib` | The compiled `encodinglib.philib` on its own |

**2026-11-21:** 66 of 66 decoded as Python decodes them, and every page's encoding as the steps give it,
the same on 32 and 64-bit Linux and macOS.
