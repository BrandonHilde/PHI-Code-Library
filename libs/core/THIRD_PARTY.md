# What came from elsewhere

corelib's code is its own: nothing in it was copied from another project, and nothing from GPL code.
Some of its fixed data came from elsewhere, as did some test data.

## Data built into programs

| Where | What | From | License |
|---|---|---|---|
| `corelib/brotlitables.phi` | Brotli's 121 dictionary-word transforms, its literal context lookup table, and its block-length ranges (RFC 7932, appendix B, 7.1 and 6) | Read out of the Brotli library's own (`libbrotlicommon` 1.2.1) by `tools/core/brotli_tables.py` | MIT, below |

A program that uses `CoreBrotli` carries these tables, so its notices should include Brotli's.

## Data a program gives corelib

| Where | What | From | License |
|---|---|---|---|
| `brotli/dictionary.bin` | Brotli's static dictionary, 122,784 bytes (RFC 7932, appendix A) | The same, by `BrotliGetDictionary` | MIT, below |

## Test data

`tests/inflate/` is made by `tools/core/make_inflate_tests.py` with Python's zlib, and
`tests/brotli/` by `tools/core/make_brotli_tests.py` with the `brotli` command, from this repository's
own text and data the scripts make.

## Brotli's license

```
Copyright (c) 2009, 2010, 2013-2016 by the Brotli Authors.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```
