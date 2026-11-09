# What came from elsewhere

fontlib's code is its own: nothing in it was copied from another project, and nothing from GPL code.
What did come from elsewhere is test data, which keeps its own license.

## Test data

Read by the tests, never built into a program.

| Where | What | From | License |
|---|---|---|---|
| `tests/fonts/LiberationSans-Regular.ttf` | Liberation Sans 2.1, unchanged | Red Hat, <https://github.com/liberationfonts/liberation-fonts> (from Fedora's `liberation-sans-fonts`) | SIL Open Font License 1.1, with Reserved Font Name "Liberation": its text is beside it, in `LiberationSans.LICENSE`. The font is unchanged, so the reserved name doesn't come into it |

The rest of `tests/` (`cases.bin`, `cases.txt`, `release.bin`, `release.txt`) is made by
`tools/font/make_font_tests.py`, from Liberation Sans and fonts it makes with fontTools.

## Used to check, not kept here

- **FreeType** (through freetype-py, which brings FreeType 2.13.2), whose faces, outlines and metrics the
  rules are checked against.
- **HarfBuzz** (through uharfbuzz, which brings HarfBuzz 15.0), whose characters' glyphs the rules are
  checked against. Its `src/hb-ot-cmap-table.hh` (MIT) was read to learn what it does with damaged
  `cmap` tables, and the rules say it in their own words; nothing of it is in fontlib but the Mac Roman
  table's values, which are Apple's character set (as Python's `mac_roman` codec has it).
- **fontTools**, which makes the test fonts.
