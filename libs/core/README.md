# corelib

What `imagelib` and `fontlib` both need: checked reading of bytes and bits, Adler-32, and inflating
DEFLATE, zlib and gzip data. It's small on purpose, and depends on no other library here.

```phi
use corelib;

call CoreLib.Start;
u32 size: 0;
ptr<u8> bytes: (CoreInflate.Zlib: data length 0 addr size);   # 0: the default limit, 64 MB
if bytes is 0
	log 'bad data: ' CoreInflate.error '\n';
	return;
;;
CoreReader r;
call r.Start: bytes size;
u32 width: (r.U32BE);
if r.failed ...                    # read past the end: every read after that gives 0
free bytes;
```

## API

These names are the API. Everything else the library declares (`CoreHuff`, `CoreInflater`, and
`CoreInflate`'s tables) is how it works, and may change.

| Name | What it is |
|---|---|
| `CoreLib.Start` | Call once, before anything else. `CoreLib.VERSION` is 1 |
| `CoreReader` | A struct reading bytes in memory: `Start: bytes length`; `U8`, `U16BE`, `U16LE`, `U24BE`, `U32BE`, `U32LE` → `u32`; `I8`, `I16BE`, `I16LE`, `I32BE`, `I32LE` → `int`; `Bytes: count` → where they are (0 if they aren't all there); `Skip: count`, `Seek: offset`, `Left` →; `pos`, `failed` |
| `CoreBits` | A struct reading bits: `Start: bytes length msb_first`; `Bits: n` → (n at most 24), `Bit` →, `Peek: n` →, `Drop: n`, `AlignByte`, `Release` (gives back whole bytes it's holding, so `pos` is the next unread byte); `failed` |
| `CoreAdler` | `Of: data length` → Adler-32, `Add: adler data length` → (carries on from an earlier one). CRC-32 is the standard library's `data.crc32` |
| `CoreInflate` | `Raw`, `Zlib`, `Gzip`, each `: data length limit size_out` → the output, or 0 with the reason in `CoreInflate.error`. `CoreInflate.used` is how many bytes of the input the stream took |
| `CoreInflate.ZlibUpTo: data length limit size_out` → | zlib data inflated up to `limit` bytes and no more, for a reader that knows how much it needs (as a PNG's image data is): it stops at the limit, with `CoreInflate.more` true if the stream had more to give, and when the data ends too soon it gives back what it made, with the reason in `error`. It fails (0) only when the stream is damaged before the limit |

**A read past the end** of a `CoreReader` or `CoreBits` gives 0 and sets `failed`, which stays set.
`CoreBits` reads zeros past the end without failing until one of them is used, so a decoder can look
further ahead than the data goes.

**Inflate** takes the whole input and gives back the whole output, on the heap, which the caller
frees with `free`. Its limit is the most the output may be (0 means 64 MB): going past it fails before
the memory is taken, so a small file can't claim gigabytes. A gzip input can be several members one
after another, as the format allows. Data after the end of the stream is left alone, and `used` says
where that is. A zlib stream with a preset dictionary is refused.

**What counts as damaged** is what zlib says: codes with more codes than there's room for, incomplete
codes (except a lone 1-bit code, which zlib allows), matches reaching before the start, codes DEFLATE
doesn't have, and checks that don't match. Like zlib's one-shot inflate, a zlib header's window size
isn't enforced.

**ZlibUpTo** gives what zlib gives of the same data when asked for at most `limit` bytes: every symbol
decoded whole before the data ends (a stored block as far as it goes), and nothing past the limit is
checked, except that a match just past it whose distance reaches before the start is damage (corelib checks
a match's distance before its room; zlib checks it once there's room, so asking zlib for one byte more is
how the test finds this out).

**One thread at a time:** `CoreInflate.error`, `used` and `more` are shared.

## How it's checked

From the repo's root:

```
pwsh ./build.ps1 core -Test                       # (or .\build.ps1 core -Test on Windows)
python3 -I tools/core/make_inflate_tests.py       # remakes tests/inflate/ (it's committed)
```

| Test | What it proves |
|---|---|
| `test_reader` | `CoreReader`, `CoreBits` and `CoreAdler`, on values worked out by hand and with Python |
| `test_inflate` | Inflate against zlib, on the cases in [tests/inflate](tests/inflate) (listed in `cases.txt`), and every good stream cut short |
| `test_inflate_upto` | `ZlibUpTo` against zlib, on the cases in `upto.bin`: every good zlib stream cut at many lengths, and whole with limits below, at and past its size, and the bad and fuzzed zlib streams. Each must give what zlib gives of it as far as it goes, by length and CRC-32, and say whether there's more past the limit, or be damaged where zlib finds it damaged |
| `release_inflate_fuzz` (release tier) | 100,000 random changes to good streams, every value of each of the first 48 bytes of one stream in each format, and noise. All of them must come back, with a result or a failure |
| `tests/use/test_corelib` | The compiled `corelib.philib`, on its own |

The reference is Python's zlib. `make_inflate_tests.py` makes the streams with it, at every level and
strategy, in each format, from text, random bytes, runs, zeros and a match 32 KB back, and writes
other streams a bit at a time for what zlib never makes (a lone distance code, codes 15 bits long) and
for each way a stream can be broken. Every case's expected result is zlib's own verdict.

| Suite (2026-11-07, as 32 and 64-bit Linux programs) | Result |
|---|---|
| Good streams, inflated byte for byte as zlib does | 160 of 160 |
| Broken streams, refused | 43 of 43 |
| Fuzz cases (small streams with bits changed), agreeing with zlib | 600 of 600 (230 good, 370 bad) |
| Good streams cut short, refused | 3,513 of 3,513 |
| `ZlibUpTo`, as zlib gives it (2026-11-08) | 2,689 of 2,689: 323 to the limit exactly, 353 with more past it, 2,008 shorter as the data ends first, 5 damaged |

**Speed** (2026-11-08, as a 64-bit Linux program, with Python's zlib on the same data for comparison):

| Data, 16 to 24 MB of output | corelib | zlib, in C |
|---|---|---|
| Text (PHI's docs and weblib's source) | 185 MB/s | 851 MB/s |
| Mostly long matches | 503 MB/s | 1,444 MB/s |
| A PNG's image data (2048 by 2048 RGBA, saved by Pillow) | 135 MB/s | 376 MB/s |

Most symbols are decoded by a fast path, as zlib's `inflate_fast` does: while 16 bytes of input are left
and the output has room for the longest match, the bits stay in the method's own variables and each code
is one look in a table. That made it 1.8 times faster on text and 2.3 times on image data. The last
bytes of the input, codes longer than 9 bits, and output near the limit go the slower way, one call per
step, and both check the same things in the same order, so they fail the same way.
