# What came from elsewhere

imagelib's code is its own: nothing in it was copied from another project, and nothing from GPL code.
What did come from elsewhere is test data, which keeps its own license.

## Test data

Read by the tests, never built into a program.

| Where | What | From | License |
|---|---|---|---|
| `tests/bmp/bmpsuite/` | BMP Suite 2.8's image files, less `q/rgb24prof.bmp` and `q/rgb24prof2.bmp` | Jason Summers, <https://entropymine.com/jason/bmpsuite/> | Public domain: the suite's readme says its image files "are in the public domain (except for the embedded ICC profiles)". The two files with embedded profiles are left out. Its generator, which is GPLv3, isn't here, and nothing was copied from it |

The rest of `tests/bmp/` (`cases.bin`, `cases.txt`) is made by `tools/image/make_bmp_tests.py`, from
BMP Suite's files and files it writes itself.

## Used to check, not kept here

- **BMP Suite's reference images** (its `html/*.png`), which `make_bmp_tests.py --bmpsuite DIR` compares
  against, from a copy of the suite that isn't committed.
- **Pillow**, which `make_bmp_tests.py` compares against.
