# Conventions

The rules every library here follows.

## What this repo is

A set of code libraries that other PHI projects pull from. It only makes `.philib` files. Which systems
those hold is up to PHI's compiler, and which systems a program runs on is up to the project building it.
So nothing here chooses a target: no `--target` in the build, and no code or tests written for one system.

## Entry point

The main file is `NAME.phi`, holding `phi.NameLib:Library` with a `VERSION` const and a `Start` method.
Nothing else runs at program start, so there's no code in a class's body.

## Names

A library exposes everything it declares, and a program can't include two classes with the same name.
So every top-level class, struct, enum and interface starts with the library's prefix, and each README
says which names are its API.

Add each new prefix here. It must not collide with a standard library name such as `Font`, `Draw`,
`Bytes`, `Text`, `Stream` or `Map`: a library class called `Font` breaks any program that also uses
`gfx.font`.

| Library | Entry class | Prefixes |
|---|---|---|
| corelib | `CoreLib` | `Core` |
| imagelib | `ImageLib` | `Img` |
| fontlib | `FontLib` | `Fnt` |
| weblib | `Weblib` | `Wl`, `Dom`, `Html`, `Css`, `Js`, `Page` |

`Cores` is already a standard library class, so don't use that exact name in corelib.

## Bytes in, data out

A library opens no files or sockets and creates no windows. It takes bytes and gives back data, and
anything else goes through hooks the project using it fills in.

## Failures

Public entry points catch everything and return a failure with a message, so a bad file can't take the
program down. That includes stack overflow, which PHI reports as `ErrorKind.STACK`.

## Hostile input

Images, fonts and web pages come from strangers.

- PHI doesn't check raw pointer access, so reads go through `CoreReader` or `(p as u8[n])`, which do.
- Every size from a file is checked for overflow and against a limit before anything is allocated.
- Each library has limits its user can change, such as maximum pixels, to stop decompression bombs.
- Every loop driven by a file has a bound, so a bad file can't hang the program.

## Size and speed

- A library's methods that nothing calls are left out of a program, but **its class variables and text
  always go in**. Big tables are built on the heap on first use, or loaded from a file.
- **Calls into a library are never inlined,** so APIs work on whole rows, glyphs and images, not one pixel
  at a time.
- Locals are limited to 4,096 bytes per method and fixed arrays to 16,384 elements, so large buffers go on
  the heap.
- PHI's generated code is simple: floating point on the x87, no register allocation, and `when` is a chain
  of compares. Pixel and glyph code prefers integer or fixed-point math and lookup tables.

## Threads

Assume one thread at a time unless a library's README says otherwise.

## Code that can go anywhere

Library source doesn't assume where it will end up, so PHI's compiler can take it wherever a project needs.

- **Nothing tied to one system:** no system-specific modules, outside functions, system calls or ports.
  Those belong in the project using the library, reached through hooks.
- **Only general standard library modules,** such as `memory.mem` and `data.crc32`, and not `gui`, `drivers`,
  `net` or `host`. Clocks and randomness come from hooks.
- **No assembly by default.** It's only for a speedup a benchmark has proved, and it keeps a plain PHI
  version beside it. It stays in one clearly named module.
- **Any pointer size:** pointers are never held in an `int` or `u32`, and sizes in files are checked before
  they're used.
- **Any byte order:** multi-byte values in files are put together by `CoreReader`, one byte at a time.
  Never read file data by casting a `ptr<u8>` to a `ptr<u32>`.
- **Small stacks and small heaps:** walks over data of unknown depth use loops, not recursion, large
  buffers go on the heap, and `new` returning 0 is handled.

weblib doesn't fully meet these rules yet: [plan.md](../plan.md) lists what's left.

## Tests

**The principle:** during development we will use a light weight minimum necessary tests to move forward
quickly. Then when preparing for release we will do the full suite of tests. But until then we will be
efficient with our time.

So there are two tiers:

| Tier | Files | What's in it | Run by |
|---|---|---|---|
| Everyday | `test_*.phi` | The least that shows each feature works: an outside suite's files, and one or a few made cases for each feature and each kind of error. A few of every kind of test the release tier has, too (a few files cut short, a few dozen fuzzed, a short run of the crash fuzzer), so that no kind goes unrun, but not thousands covering the same thing. Quick to run, and quick to remake | `.\build.ps1 -Test` |
| Release | `release_*.phi` | The full suite: every size, files cut short at many lengths, thousands of fuzzed files checked against outside decoders, crash fuzzers of hundreds of thousands, stress runs with other seeds | `.\build.ps1 -Test -Release`, when preparing a library for release |

We still want a few of each required test, but thousands of them covering the same issues is a waste for
early development builds. Nothing has been released yet, so the release tier waits. A new feature gets everyday tests. Its edge cases,
fuzzing and stress go in the release tier, or wait until release is near. Don't run the release tier as part
of everyday work, and don't make or run release sets for new code until release is near either.

**Nothing runs over 3 minutes during development:** no test run, no case generator, no check. A run that
would take longer is split into separate quicker ones, or made smaller. `build.ps1` runs one library at a
time (`.\build.ps1 font -Test`), and `-Only` runs the test programs whose names start with given prefixes,
for a library whose everyday tests together take longer:

| Library | Everyday run | Time (2026-11-10) |
|---|---|---|
| corelib | `.\build.ps1 core -Test` | about 5 s |
| imagelib | `.\build.ps1 image -Test` | about 30 s |
| fontlib | `.\build.ps1 font -Test` | about 15 s |
| weblib | `.\build.ps1 web -Test -Only test_css` | about 90 s |
| | `.\build.ps1 web -Test -Only test_html,test_page,test_core,test_weblib` | about 100 s |
| | `.\build.ps1 web -Test -Only test_js` | about 90 s |

(Each weblib group builds weblib first, which is most of its time.) A prefix no program has fails the run,
rather than passing with nothing tested.

Each library's tests are of two kinds:

| Kind | Where | What it proves |
|---|---|---|
| Internal | `test_*.phi`, beside the source | The source works. These can reach the library's modules |
| Compiled | `tests/use/test_*.phi` | The `.philib` works alone. A test beside the source can't show this, because source beats compiled in the same folder |

Each is a `phi.Name:Program` that ends in `exit 0;`, with a `.expected` file holding what it must print.
`.\build.ps1 -Test` runs them with plain `phi test`, which decides what they run on. It copies the `.philib`
files in first, so use it rather than `phi test` for the first run in that folder.

**Writing expected output:**
- Test output must be ASCII. `phi test` decodes it by the console's code page, so anything else passes or
  fails depending on the shell.
- Save a `.expected` only after reading it, since a file nobody checked proves nothing.
- Don't save one through PowerShell's `>`, which re-encodes it.

**Fuzzing and outside evidence.** Parsers and decoders are fuzzed with fixed seeds, so a failure can be
repeated: in the release tier. Each library is measured against an outside suite or a reference
implementation where one exists, and its README reports the result as it stands.

**Memory.** Test generators keep only what they need of each case (its size and a CRC, not its pixels), and
outside decoders run with limits on their memory and time (`tools/image/cases.py`'s `run_magick`). Run one
heavy job at a time.

**Warnings** fail the build, because `phi`'s warnings are usually real problems.

## Done

A milestone is done when its tests pass, and any outside-suite results are written in the library's README.

## License

The repo is Apache-2.0. Code is never copied in from GPL sources, because Apache-2.0 code can't take in GPL
code. Third-party test data and tables keep their own licenses, listed where they're committed.

## Adding a library

1. Choose its name and prefix, and add them to the table above.
2. Create `libs/FOLDER/` with `NAME.phi`, a README, and at least one test of each kind.
3. Add it to [libraries.psd1](../libraries.psd1), after everything it uses.
4. Name the outside suite or reference implementation that will measure it.
5. Give it a section in [plan.md](../plan.md).

## When PHI gets in the way

This repo doesn't change the PHI compiler. Work around the problem, and write it down in
[phi-notes.md](phi-notes.md).
