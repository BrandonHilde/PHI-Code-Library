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
timeout as a bug. (2026-11-25: weblib's `test_css_fuzz` takes 59–60 s in Lima on both Linux targets,
right at the default 60 s, so it fails or passes by a second; its output is exact, and it passes with
`-Timeout 180`.)

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

**Fixed in PHI (`7f1e16e`, macos branch):** both were the line table: 24 bytes, a global symbol and a
loader fix-up for each of 348,000 lines. Now each object has its own table of 8-byte entries, offsets
from its code's start that the assembler works out: the browser is 9.6 MB (`__DATA_CONST` 2.8 MB,
`__LINKEDIT` 0.6 MB). The library ABI is 1.3, so `.philib`s are rebuilt.

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

## A method value's pointer result was an int (fixed in PHI, 2026-11-23)

`method<...: ptr<T>>` gave its result back as an `int` (every number did, and PHI counts a pointer
as a number), so in 64-bit code (macOS, 64-bit Linux and Windows) the pointer lost its top half and
the program stopped at its first use. weblib's `CssEngine.on_style` (page/anim.phi's hook for
transitions and animations) is one. Fixed on PHI's macos branch in `6cf41dc` (a pointer or method
value keeps its type; other numbers are still an int); weblib needs a PHI built from it. PHI OS
FINDINGS #45.

## cssText keeps shorthands and colour names (2026-11-26)

`style.cssText`, a rule's `style.cssText` and the style attribute written from them now give
shorthands back as Chrome does: when every longhand of `margin`, `border`, `font`, `background`,
`flex` and the like is set, they are written as the shorthand, the largest one first, and only
the longhands left over are written alone. A named colour stays its name (`color: red`, and
`style.color` is `red`), while `getComputedStyle` still gives `rgb(255, 0, 0)`. Checked against
Brave: 22 of 25 cases match. The three that don't are Chrome's own longhand order after
`font-kerning`, `background` with a `url()` (Chrome keeps it relative and writes `center center`)
and `outline`'s order.

## An image's natural size and the window's load wait for the picture (2026-11-26)

`img.naturalWidth`, `naturalHeight` and `complete` were 0, 0 and true whatever the picture, and the
window's `load` fired without waiting for images. `PageHost` now has a `picture` hook
(`method<ptr<Page> ptr<DomNode> ptr<int>: int>`): the host says 0 (it knows nothing), 1 (coming),
2 (here; the two ints are its width and height) or 3 (can't be had). `naturalWidth` and
`naturalHeight` are the size only at 2, and `complete` is false only at 1. With no hook, an image
whose IMAGE request is still waiting counts as coming. Settle's wait for the window's `load` now
counts an image's request unless the host has no hook or the image is `loading="lazy"`; FETCH
requests are not waited for (as in Chrome). A host that answers IMAGE with 200 at once still works
as before. PHI OS FINDINGS #50 has the browser side.

## An <img>'s width, complete and decode() straight after a src (2026-11-26)

An `<img>` given a src asks for its picture once the running script is done (`Page.RunJobs`), so
just after `img.src = ...` nothing said it was coming and `complete` was true; now a src waiting
to be asked for counts as coming. `img.decode()` resolved at once; now when the picture is in, and
it's an EncodingError with no src or a picture that couldn't be had. `img.width` and `height` are
Chrome's: the size it's drawn at inside its padding and border (from `PageHost.box`); not drawn,
the attribute, else the picture's own size once it's in. `new Image()` that's never put in the
document did already ask for its picture. Checked against Brave; PHI OS FINDINGS #51.

## The mouse: Page.Pointer and Page.Wheel (2026-11-26)

The host tells the page about the mouse with `Page.Pointer: page node kind x y button buttons
clicks` (kind `POINTER_MOVE`, `POINTER_DOWN` or `POINTER_UP`; x, y in the window's CSS pixels;
button 0 main, 1 middle, 2 other; buttons as `MouseEvent.buttons`) and `Page.Wheel: page node x y
dx dy buttons` (false if a handler canceled it, so the host doesn't scroll). Pointer and mouse
events come in Chrome's order, `:hover` and `:active` follow (`CssSel.ST_HOVER`, `ST_ACTIVE`), and
the click is still the host's to send with `Page.Click`, after the up. Listeners take `passive`
(Chrome's default for wheel and touch listeners on the window, document, html and body).
`el.attributes` has each attribute by name too, and the event handler properties are Chrome's
lists. The CSS engine counts the styles an Update changed (`CssEngine.changed`): a hover change
that changes none puts the document's version back. test_pointer; PHI OS FINDINGS #52.

## Clicks and the focus: Page.Click, Page.ClickTarget, Page.MoveFocus (2026-11-27)

`Page.Click: page node x y detail button` now takes the click count (`detail`, 2 for a double
click's second, which then also fires `dblclick`) and the button (0 a `click`, which takes a
link's default action; 1 or 2 an `auxclick`, which doesn't); both are PointerEvents, as Chrome
makes them. Where it goes is the host's to ask: `Page.ClickTarget: pressed_on node` is the
nearest element holding both what the button went down on and what it came up on (0 for none,
then no click). `Page.Pointer`'s down moves the focus when its mousedown isn't canceled, and the
other button's down fires `contextmenu` (as on the Mac); its result is false if either was
canceled (the host then doesn't start choosing text). `Page.MoveFocus: page n by_mouse` is how
the focus moves, for `focus()` and `blur()` too (`Page.Focusable` says what can have it):
blur and focusout, then focus and focusin, FocusEvents with relatedTarget, the focus nowhere
during the blur. `:focus-visible` (`CssSel.ST_FOCUS_VISIBLE`) follows Chrome's rule (in
`MoveFocus`). `Page.Focused: page` is what has it, 0 once it's out of the document. Not yet: the
blur Chrome fires as a focused element is taken out (it would run a handler in the middle of
`Dom.Remove`). test_focus; PHI OS FINDINGS #53.

## The keyboard: Page.Key, Page.KeyUp, Page.KeyDefault, Page.TypeInto (2026-11-27)

A key now reaches the page as Chrome sends it. `Page.Key: page key code key_code char_code ctrl
shift alt meta` fires keydown at what has the focus (the body when nothing does), then keypress
for a key that types (`char_code` not 0, no ctrl, alt or meta); false if either was canceled,
and then the key does nothing more. `Page.KeyUp` fires keyup at what has the focus by then (after
a Tab, where it went). The host names the key (PHI OS has `brw/keys.phi` for that, a US
keyboard). `Page.KeyDefault: page key shift` is what a key the page let be does: Tab and shift Tab
move the focus along (`Page.TabFocus`; positive tabindex first, then tree order, from where the
last click was), Enter follows a focused link, presses a button or sends the field's form
(`Page.ImplicitSubmit`, the standard's implicit submission), and a space pressed on a button,
checkbox or radio button clicks it when it comes up. `Page.TypeInto: page n text` types into a
field: beforeinput (cancelable), the value, then input, InputEvents with insertText or
deleteContentBackward and data; a field typed into fires change as the focus leaves it
(`Page.Commit`, before the blur). `Page.Click` on a checkbox or radio button now changes it first,
puts it back if the click is canceled, then fires input and change.

Unexpected: Chrome sends no keypress for Enter on a link, though it does for Enter on a button and
in a field. It follows the link as keydown's default and marks the key handled, which stops the
keypress; a button and a field act on the keypress instead. `Page.Key` leaves out that one
keypress. Brave's log of the same steps is test_keys; PHI OS FINDINGS #54.

## The Referer: WireReferrer (netlib), Page.policy and PageRequest.policy (weblib) (2026-11-27)

netlib's `WireReferrer.For: from to policy target max` is the Referer a request to `to` made at
`from` has, by the W3C's Referrer Policy (0, the default, is strict-origin-when-cross-origin);
`WireReferrer.Header`, `Meta` and `Policy` read a policy from a Referrer-Policy header (the last
name in it that is one), a `<meta name=referrer>` (with the old names) and an attribute. weblib
can't use netlib, so `PageReferrer.Parse` reads the names again with the same numbers. A page has
`policy` (`Page.SetPolicy` from its header; each `<meta name=referrer>` as it comes in or changes,
through `Page.Mutated`) and `referrer` (`Page.SetReferrer`, document.referrer). Each request's
policy is fixed as it's made (`PageRequest.policy`: the element's referrerpolicy, fetch's
referrerPolicy, or the page's then), as is an `<img>`'s picture's (`Page.PicturePolicy`, kept in
four of its flag bits, as the browser fetches pictures later); `Page.nav_policy` is a link's or
the page's while `host.navigate` or `host.post` runs (`rel=noreferrer` wins over `referrerpolicy`).
Unexpected: a meta's content changes reach `Mutated` before the new value is in place, so
they're taken before the next request (`MetaPolicies`), as `<img>` src changes are. Checked
against Brave: test_page_referrer, netlib's test_referrer; PHI OS FINDINGS #55.

## Fetch Metadata: WireMetadata (netlib) (2026-11-27)

netlib's `WireMetadata.Lines: to dest mode site user target max` writes a request's
`Sec-Fetch-Site`, `-Mode`, `-User` (navigations the user made only) and `-Dest` lines, in
Chrome's order, and nothing for an address that isn't potentially trustworthy (WireReferrer's
`Trustworthy`: https, localhost, 127.x.x.x, ::1), as the W3C's Fetch Metadata Request Headers say.
`WireMetadata.Site: from to` is where a request comes from (`none` when nothing asked: an address
typed; `same-origin`; `same-site`, the same scheme and registrable domain by `WireCookies.SameSite`;
`cross-site`, and always from something with no origin), and `Worse` keeps the worst along a
redirect chain. weblib has nothing of it: what a page's request is for is the host's to say
(PHI OS's `brw/meta.phi`, from `PageRequest.kind` and the element). netlib's test_metadata; PHI OS
FINDINGS #56.

## A field's caret: Page.Edit, PageBind.Selection, platform.js's selection (2026-11-27)

A text field's selection is kept on its element as `%ss`, `%se` and `%sd` (UTF-16 units and
`none`/`forward`/`backward`), as `%value` is: platform.js's `selectionStart` and the rest read and
set them, and so do `PageBind.Selection`/`SetSelection` for the page's typing. `Page.Edit` makes
every change a user does (text, Backspace, Delete, a line break, paste, cut: beforeinput, the
value, the caret after it, input); `Page.TypeInto` and `LineBreak` are it. `Page.KeyDefault` takes
the caret keys and Delete in a field (`MoveCaret`). The host draws and clicks in characters
(`FieldCaret`, `PlaceCaret`, `SelectAllIn`, `SelectedText`). Unexpected: `platformjs.phi` is made
from `platform.js` (tools/web/make_page_js.py); an edit of the made file alone is lost the next
time it's made, as the Referer's nearly was. test_page_caret, checked against Brave; PHI OS
FINDINGS #57.

## The clipboard's events: Page.Clipboard, platform.js's DataTransfer (2026-11-27)

`Page.Clipboard: p kind text put` makes the copy, cut or paste a key makes into a trusted
ClipboardEvent (through platform.js's hidden `%clipboardEvent`, whose DataTransfer is text only
and read-only for paste) at what has the focus, or the body, and says what the browser does next:
`CLIP_GO` (copy or paste as it does), `CLIP_SET` (what the page set, in put, is what's copied),
`CLIP_CANCELED`. Every class platform.js's `eventClass` makes has its own Symbol.toStringTag now
(they all said `[object Event]`). test_page_clipboard; PHI OS FINDINGS #58.

## phi test passed a test that didn't compile, on a Mac without Linux (2026-11-27)

A program that builds for none of the systems a computer runs is run on the first anyway, so
its build fails and says why; the first had to be an x86 one, so on this Mac without
PHI_LINUX_RUN a test that didn't compile ran nowhere and `phi test` said "0/0 passed" and
succeeded (build.ps1 then said the run passed). Found when a new test with a type error passed.
Fixed on PHI's macos branch (8ed6973): an arm64 host when there's no other. Runs with Lima were
never fooled (its Linux is the first x86 system).
