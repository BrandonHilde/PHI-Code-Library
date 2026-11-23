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
3. ~~**A jump table for a dense `when`.**~~ **Done in PHI (`1c0c750`, 2026-11-10):** a `when` on a number
   whose values are constants close together (5 or more, the table no more than three entries a value)
   is one jump through a table, in 32- and 64-bit code. weblib's JS VM was what showed the need: with it
   and a 64-bit value copied in one load and store, `release_js_bench run` went from 13.7 s to 10.9 s as
   a 64-bit Linux program.

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
**Fixed by 1.0:** `phi test --help` prints the usage (checked 2026-11-21).

**A `u32` index is sign-extended in 64-bit code** (2026-11-08). `p:i`, with `p` a pointer and `i` a
`u32`, comes out as `movsxd rax, eax` before the add (seen in corelib's inflate, in
`build/test_inflate.linux64/program.asm`), so an index of 2^31 or more reaches below `p` instead of
past it. Nothing here meets it yet, as corelib and imagelib hold every size under 2 GB, but a `u32`
index ought to be zero-extended.

**Fixed in PHI (`1c0c750`, 2026-11-10):** a `u32` index through a pointer is zero-extended
(`mov eax, eax`), and an `int` index keeps its sign (`movsxd rax, eax`), so a negative one still
reaches before the pointer. Checked 2026-11-11 in the code for `p:(i * 3 + 1)` with `i` a `u32` and
an `int`.


## PHI 1.0 (2026-11-20)

From here the libraries are built and tested with the released compiler, `phi 1.0.0 (9aeb805)`, and
PHI isn't changed from this work: what's found is written here for PHI to take up.

**A kernel that uses any compiled library gets a line table for all of itself.** PHI OS's kernel went
from 352 KB to 504 KB when its text field started using `editlib.philib`, and editlib's own code is
about 15 KB of that. The rest is `phi_lines`, the table that lets an error name its line: in the x86
code generator, `Catches` is true for a 32-bit unit with any compiled library
(`unit.CompiledLibraries.Count > 0`), and `MarksLines` follows it, so every line of the kernel is
marked, not only the library's. A program always has the table, so only kernels see the jump. It's
within the kernel's limit (about 1 MB) and its errors now say their line, so PHI OS lives with it; a
kernel with less room would want the library's lines alone marked, or a switch.

**Tests slower than their limit under emulation aren't failures of the code.** On a Mac, the 64-bit
Linux runs go through Lima's x86 emulation: imagelib's `test_png_fuzz` printed exactly its expected
output and was still cut off at 300 s. Give the emulated runs a longer `-Timeout` before reading a
timeout as a bug.

**A method's result reads a variable declared again after a block that had one of the same name as
another class's (or fails to build).** Found writing imagelib's VP8 decoder, 2026-11-20, in 1.0 on ARM
and x86 alike:

```phi
phi.T:Program
{
	int v: 7;
	log (Foo.F: 1) '\n';          # 17: F's [end: ...] took T's v, not its own (3)
	exit 0;
}

phi.Foo:Library
{
	[F: int a: 0;]
		if a > 5
			int v: 1;               # a v inside a block
			return v + 100;
		;;
		int v: 3;                   # and another at the method's level, after it
		int w: v + 10;              # statements see this one: w is 13
	[end: v + 10]                   # the result doesn't: 17, T's v plus 10
}
```

Only the `[end: ...]` expression is wrong; statements after the second declaration see it. Where no
other class has a variable of that name, the build stops instead: `'v' is declared only inside blocks
(if, else, while) that have ended here`. A warning (`'v' is a variable of T; write T.v to say so`)
came in one build of the decoder and not in the small case above. **Here:** the decoder names its
variables apart, and a scan of every `.phi` file in this repo and PHI OS for the pattern (a name
declared in a block, again at the method's level, then in `[end: ...]`) found no other. **For PHI:** a
silent wrong value, so a candidate for "something that demands a fix".

**Fixed in PHI (`977a988` and `09231a9`, its macos branch, not released):** `[end: ...]` sees the method's own variables as they are at its end, whether it's worked out from a call elsewhere or at the method's own first return (end_sees_own_locals).

**`net.tls13` offers no ALPN, so a client on it can't speak HTTP/2.** Its ClientHello's extensions are
fixed (server_name, the groups, key_share and the rest), and an extension a program wants to add, or a
server's EncryptedExtensions to read, has no way in. netlib has HTTP/2 now (`WireH2`), and its own TLS
1.2 client offers `h2` by ALPN, but PHI OS's browser tries `net.tls13` first, as it should, so it stays
on HTTP/1.1 with every server that speaks TLS 1.3. What would do: a list of ALPN names on the session
before the ClientHello is made (`application_layer_protocol_negotiation`, extension 16), and the name
the server chose, from its EncryptedExtensions, after the handshake (2026-11-21).

**Fixed in PHI (`be98582`, macos branch):** `Tls13.Client: s host 'h2 http/1.1'` (and Server, Tls.Connect, Secure.Accept/Connect) offer protocols; `s.protocol` is the one agreed.

**A shift is done in 32 bits whatever it's stored into, and a constant one that overflows is folded
without a word.** `u64 a: 1 << 42;` is 1024, as is `1 << n` with `n` 42: the shift is an `int`'s,
its count taken modulo 32, and only then made a `u64`. The constant is folded at build time to the
same 1024, where a build could tell it's wrong. And `u8` 200 `<< 24` is an `int`, so it comes out
-939524096: stored in an `int` that's silent, and stored in a `u32` it stops the program ("a negative
number can't be a u32"). Two of weblib's were met this way on 2026-11-21: `Float16Array`'s rounding,
which shifted a `1` by up to 42 (wrong numbers, found by test262), and canvas's `putImageData`, which
built a pixel from four `u8`s (a stopped program). **Here:** a `u64` one is shifted (`u64 one: 1;`),
and a byte is made a `u32` before its shift. **For PHI:** an error for a constant shift past its
width, and a warning when a shift's count may reach 32 in an `int` that's then widened, as the
silent wrong value is the dangerous half (2026-11-21, checked in 1.0 on macOS arm64).

**Fixed in PHI (`82fcd36`, macos branch):** a written count past the width is an error, and a 32-bit shift made 64 bits is warned about (fontlib's `truetype.phi` met the warning, and now writes the shift in 64 bits).

**A macOS program's window must be made on its first thread, and nothing says so.** PHI OS's browser
makes its window on a thread of its own, with a big stack. Built for macOS it built cleanly and
stopped as it opened, with AppKit's `NSInternalInconsistencyException` ("NSWindow should only be
instantiated on the main thread!"). Neither `window_macos.phi` nor the documentation of macOS programs
mentions it, and the same program runs on PHI OS, Linux and Windows. `gui.app` could stop with a PHI
error saying so when it's called on another thread, or the documentation could say it. Related and
smaller: `OS.ThreadStart` takes a method of no values on PHI OS, but on Linux, Windows and macOS the
method must take the one value it's given; that error is clear (2026-11-21).

**Fixed in PHI (`5fb03a7`, macos branch):** opening one off the first thread is a PHI error that says what to do, and can be caught.

**A macOS program is about ten times the size of the same program for x86.** PHI OS's browser built
for macOS is 41 MB (27 MB stripped); as a PHI OS program it's 3.7 MB, and as a 64-bit Linux program
(`render`, the same engine) 4.5 MB. Its `__TEXT` is 4.6 MB, so the code isn't the difference: it's
15.6 MB of `__DATA_CONST,__const` and 20 MB of `__LINKEDIT` (a `phi_line_N` symbol for each line).
Not looked into further; it runs (2026-11-22).

**PHI 1.0's floating-point maths stops at `Sin` and `Cos`, and the libraries have each filled the gap
their own way.** The builtins are `Float.Abs`, `Sqrt`, `Sin`, `Cos`, `Floor`, `Ceil`, `Round` and
`Trunc`; there's no log, exp, pow, tan, atan, atan2, asin or acos. So:

- weblib (JavaScript's `Math`) computes `log`, `log2`, `log10`, `log1p`, `exp`, `expm1`, `tan`, `atan2`
  and `**` in assembly: the x87's own instructions (`fyl2x`, `f2xm1`, `fptan`, `fpatan`) in 32- and
  64-bit x86 code, and since 2026-11-22 calls to the Mac's C library in ARM code (`libs/web/docs/DESIGN.md`,
  "Assembly: the x87"). That assembly is all that tied weblib to x86, and it means a result can
  differ in its last bit between an x86 build and a Mac one, and from browsers' (they use fdlibm).
- vectorlib has its own `Vg.Tan` (`Sin` over `Cos`) and `Vg.Atan2` in PHI, which canvas uses too.
- weblib also sets the x87's control word to double precision in assembly (`WlSetFpu`, `JsSetFpu`):
  a 32-bit program's `f64` arithmetic is done on the x87, which keeps 80 bits unless told otherwise,
  so a result could be rounded twice where JavaScript allows once. PHI has no way to say this itself.

**For PHI:** the rest of C's `<math.h>` as `Float.` builtins (`Log`, `Log2`, `Log10`, `Log1p`, `Exp`,
`Expm1`, `Pow`, `Tan`, `Atan`, `Atan2`, `Asin`, `Acos`, `Sinh`, `Cosh`, `Tanh`, `Cbrt`, `Hypot`), the
same to the bit on every system (fdlibm's algorithms, in PHI, would be), and `f64` arithmetic in 32-bit
programs rounded to double precision as a matter of course. Then weblib would need no assembly at
all, and vectorlib's own versions could go. Until then, porting fdlibm into a library here is the way
to the same results everywhere (2026-11-22).

**Fixed in PHI (`67981c8`, `8a00315`, `aed0acc`, macos branch):** `Float.Log`, `Log2`, `Log10`, `Log1p`, `Exp`, `Expm1`, `Pow`, `Tan`, `Atan`, `Atan2`, `Asin`, `Acos`, `Sinh`, `Cosh`, `Tanh`, `Cbrt`, `Hypot`, and `Sin` and `Cos`, are fdlibm's in PHI (`lang.float`, no `use`), the same to the bit on x86 and ARM; and x86 code's `f64` results keep an `f64`'s range (they kept the x87's). weblib's x87 routines and libm calls can go, and vectorlib's `Vg.Tan`/`Atan2` with them.

**A macOS program can't read the count of a local `atmost` array.** `str words[atmost 8];` in a method,
then `words.len`, stops a macOS build with `Args uses a NameExpr (Length, an atmost array's count
'words.len') ..., which macOS programs can't do yet`; the same file builds for every other system.
PHI OS's `render.phi` met it (2026-11-22) and keeps a count of its own. The message says exactly
what and where, so it's a gap in the ARM code generator rather than a trap.

**Fixed in PHI (`7b879f7`, macos branch).**


**Keywords are reserved by design, not a problem to fix.** `method`, `into`, `at`, `out`, `end`,
`each` and the rest can't name a field, a variable or a parameter, and an earlier version of this
note asked for contextual keywords. That was a misreading: a keyword always means what it is, never
also a variable, so a reader identifies it at once — one word, one meaning, which matters most in a
low-level language (the user, 2026-11-22). The compiler names the word and suggests another
(`'end' is a keyword… try 'stop' or 'last'`); this library uses `verb`, `dest`, `at_` and the like.

**A PHI OS program's heap is a fixed 124 MB.** It's the range `0x40400000`–`0x47FFFFFF` whatever
the machine has (PHI's `docs/memory-map.md`), and `Heap.most_bytes` can't raise it. weblib meets it
on PHI OS with Wikipedia's Golden ratio article: 36 MB to load, past 116 MB with its pictures and
MathJax typesetting, and then "RangeError: Out of memory" from the JS engine (on the Mac the same
page is fine). For PHI: a heap that grows with the machine, or a way to ask for more. PHI OS
FINDINGS #36 (2026-11-22).

**Wanted, for later (the user's call, 2026-11-22):** the limit should be something the programmer
can optionally set with a function call, as `Heap.most_bytes` already is on Linux, macOS and
Windows: on PHI OS the call would have to reach the kernel, whose `proc.process` stops a heap at
`HEAP_LIMIT` (`0x48000000`, 124 MB above `USER_TOP`) for every program. YouTube in PHI OS's browser
meets it too (its scripts fail with "RangeError: Out of memory" at a 92 MB heap, 20 MB of it the
browser's cache of fetched scripts). Not to be worked round in PHI OS by copying `proc/process.phi`
next to `os.phi`: it waits for PHI.

**Fixed in PHI (`feb228a`, macos branch):** `call Heap.Limit: bytes;` sets it, up to what the machine has; the default stays 128 MB.
