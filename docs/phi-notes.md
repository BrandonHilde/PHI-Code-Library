# Notes for PHI

What this repo has run into with the PHI compiler, and what we'd ask for. Changes themselves belong in
the PHI repo.

## Requests

1. **An include path or packages for `use`.** `use` only looks next to the file, next to the main program,
   and in the standard library, and it can't go up a folder. So `build.ps1` copies `.philib` files beside
   everything that needs them. PHI's plan still lists packages as open, and this repo would be its first
   real user.
2. **A way to mark what's public in a library.** Everything a library declares is exposed, so helpers need
   prefixes too. PHI's plan says this can come later.
3. **A jump table for a dense `when`.** It matters to image and font decoding as well as to weblib's JS VM.
   It's already on PHI's optimizing list.

## Found on Linux (2026-11-07)

PHI's first run on a Linux computer (Fedora 42, a GNOME desktop on Wayland), after moving it to .NET 10.
Each is fixed in PHI, in commits `6858e27` to `457456d`.

| What | Why | Fix |
|---|---|---|
| Every `LanguageServerTests` test hung forever | Closing a pipe on Linux waits for a read on it to end; the test closed the end the server was reading | Close the write ends first, so each reader ends |
| Windows-only tests (`foreign_program`, `outside_functions_program`, `own_heap/bugs`) failed to build | A program that builds for no system *this computer* runs was forced onto the first one | Skip it when it builds for a system this computer can't run |
| `tls_host_client` and `tls_host_p384` expected suite 4865 | .NET's client is SChannel on Windows, OpenSSL on Linux; OpenSSL offers ChaCha20 before AES-128 | The tests check the suite is one PHI offers |
| Windows didn't open (6 tests) | XWayland, like most desktops' X servers, wants a cookie; PHI's X11 client sent none | `window_linux.phi` sends the display's MIT-MAGIC-COOKIE-1 from the Xauthority file |
| `sound_program` never finished | PipeWire keeps back a short end of a stream until it's drained; and the held count went wrong once it read past it | `sound_linux.phi` drains a stream that should have ended, and counts reading past as nothing held |
| Playing sound crashed `uresourced` (a desktop service) | PHI's PulseAudio client gave no `application.process.id`, which every client gives | It's given now (`sys.GetProcessId`, new) |

## A 32-bit Linux program's heap had no cap

A 32-bit Windows program's heap stopped at 128 MB (a fixed reserve in `lib/x86_32_windows/system.asm`),
and a PHI OS program's at 124 MB, but a 32-bit Linux program's grew with `brk` until Linux refused,
which can be gigabytes. weblib's `test_js_limits` fills the heap to check that running out is a
`RangeError`, and on 32-bit Linux that took longer than its 600 s. Found 2026-11-07.

**Fixed in PHI (`0b5f105`):** how far the heap grows is now the program's decision,
`Heap.most_bytes` in `memory/program_heap.phi`. The default (0) is 128 MB in 32-bit code on every
system, and the system's own limit in 64-bit. 32-bit Windows now reserves up to 1 GB of addresses
so a program can raise it (that part is assembled but not yet run on Windows). `test_js_limits`
passes on 32-bit Linux now, in seconds.

## Small problems

**A misleading message when a library doesn't build for a system.** Building a library that uses
`drivers.ata` reports this same text for every system, including 64-bit Windows and Linux:

```
not for 64-bit Windows: libs\mid\cbmid.phi:1:1: error: drivers.ata doesn't work in a 16-bit program (lib/phi/drivers/ata.phi:38: user programs can't use ports; only the kernel can talk to hardware)
```

The reason in brackets is right, but "16-bit program" isn't.

**`phi test --help` crashes** (2026-11-08). `phi test` takes `--help` as the file to test, and .NET's
unhandled `FileNotFoundException` comes out, with its stack trace, from `TestRunner.BuildTestLibraries`.
`phi` with no arguments prints the usage, so that's the way to see it for now.

**A `u32` index is sign-extended in 64-bit code** (2026-11-08). `p:i`, with `p` a pointer and `i` a
`u32`, comes out as `movsxd rax, eax` before the add (seen in corelib's inflate, in
`build/test_inflate.linux64/program.asm`), so an index of 2^31 or more reaches below `p` instead of
past it. Nothing here meets it yet, as corelib and imagelib hold every size under 2 GB, but a `u32`
index ought to be zero-extended.

