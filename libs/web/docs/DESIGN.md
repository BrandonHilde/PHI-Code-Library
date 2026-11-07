# weblib design

weblib interprets HTML, CSS and JavaScript. It is a PHI library (`phi build weblib.phi --library`
makes `weblib.philib`), and its job ends where a browser's begins: it takes bytes and gives a DOM,
computed styles and a running script. **Layout, painting, networking and windows are the browser's**,
reached through hooks. Nothing in the library draws, opens a socket or reads a file.

PHI is documented in its repo's `docs/` (`language.md` is the reference, and worth reading for
real: PHI is not C). The compiler is found as this repo's [README](../../../README.md) says. Don't
change anything in the PHI repo; if the compiler is in the way, work around it and write down what
happened, in [phi-notes.md](../../../docs/phi-notes.md).

## Layout

```
libs/web/
  weblib.phi          the library's entry: Weblib.Start, and a `use` of everything
  core/               buffers, atoms, UTF-8, arena, stack budget, number <-> text
  dom/dom.phi         the node tree; every layer shares it
  html/               tokenizer, tree builder, entities, serializer
  css/                tokenizer, parser, selectors, properties, cascade, computed style
  js/                 the JavaScript engine: lexer, parser, compiler, VM, objects, GC, builtins
  page/               what ties them together: DOM bindings for JS, the document's lifecycle
  test_*.phi          the tests, each with test_*.expected (they must sit here: see Testing)
```

`use` finds a module next to the file that says it or next to the main program, so a test or a
module writes `use html.parser;`, and nothing depends on the folder above `libs/web/`.

## Rules for all the code

**Names.** A program can't declare a class, struct or enum with the same name as one in a library
it uses, and the standard library and browser will both have plenty. Every top-level name starts
with its layer's prefix: `Wl` (core), `Dom`, `Html`, `Css`, `Js`, `Page`. Standard library classes
to know about and not collide with: Text, Math, Mem, Map, Queue, List, Pool, Web, Net, Tcp, Udp,
Http, Dns, Tls, Draw, Screen, Input, App, Events, Widgets, Button, Sound, Stream, Error, Float.

**Targets.** It must build and pass on `windows` and `windows64` (run often), and build for `linux`,
`linux64` and PHI OS programs. Treat a warning as a bug: `phi` warnings on 64-bit are usually real
ones (see below). It's a library for programs; kernels aren't a target.

**Single-threaded.** The library has class variables and isn't safe from two threads at once. A
browser gives each tab a process, or one thread at a time.

**Memory.** `new T` / `new u8[n]` give zeroed memory and return 0 when there's none: check, and
`throw`. Fixed arrays hold at most 16,384 elements, a method's locals at most 4096 bytes. **No big
class variables**: they're in the program whether it uses them or not, so tables are built on the
heap the first time they're needed, and there's no code in a class's body (nothing runs at start
but `Weblib.Start`).

**The stack is small and recursion must be budgeted.** PHI OS gives a program 64 KB, Windows 1 MB.
Running off it can't be caught. So:

- Anything that walks a tree of unknown depth (the DOM, the GC's marking, regex backtracking,
  CSS's rule matching, the HTML tree builder) uses a loop and parent pointers or a heap stack.
- Anything that has to recurse on what a page wrote (JS parser, JS compiler, `JSON.stringify`,
  native code calling back into JS) calls `WlStack.Check` per level. Keep those methods' frames
  small: no buffers in their locals.

**Text** is (pointer, length) of UTF-8, with a zero after it wherever it's cheap to keep one
(`WlBuf`, `WlText.Dup`, atoms, DOM text). It can hold anything. PHI's `str` is capped at 65,535
characters and cuts silently, so **never hold page content in a `str`**: it's fine for short
messages and building error text. Names go through `WlAtoms`, and compare by pointer.

**Errors.** `throw` works everywhere and unwinds cleanly (`if call x is F: a throws e`), even
through method values, and PHI's own errors (null pointers, bad indexes, divide by zero) can be
caught the same way. Parsers use it internally. Public entry points to the library never let an
error reach the browser: they catch, and return a failure with a message. A bug or a hostile page
must not take the browser down.

**Hostile input.** Every byte of HTML, CSS and JS is untrusted. Bound everything a page controls:
nesting depth, array sizes, string lengths. Integer overflow in a size is a bug. Infinite loops in
page JS are the host's to interrupt (`Js.Interrupt`).

## PHI traps we've already hit

These compile and then do the wrong thing, or surprise you:

1. **A pointer-returning method must say so at its end.** `[end: 0]` makes it an *int* method, so
   `return node;` is cut to 32 bits on 64-bit, working on `windows` and failing on `windows64`.
   Write `[end: 0 as ptr<DomNode>]`, or end in a pointer variable. Same for `u64`, `f64`: the kind
   of the `[end: ...]` value is the kind of the method. (`[end: 0 as u64]`, `[end: 0.0]`.)
2. `const` can't hold a value over 63 bits. Keep such values in class variables, or compare
   shifted: `(v >> 48) as u32 is TAG`.
3. **`when` is a chain of compares**, not a jump table: its cost grows with its branches. A hot
   dispatch nests them, with the common cases first.
4. An array of `method<...>` as a local isn't in 64-bit programs yet. Method values in struct
   fields, class variables and parameters are fine. (Check before relying on class-level arrays.)
5. `(F: x).field` doesn't parse: put the result in a variable first.
6. `is` after a statement's start is a comparison: `a is b is c` stores a comparison, and warns;
   write `a is (b is c)`.
7. Variables declared directly in a class are globals even in a block in its body; `addr` of one
   isn't a stack address.
8. A `when` branch's `is` value goes on its own line, the body on the next ones.
9. Names that are keywords: `at in out end has empty below above each when ask new free is not and
   or str chr byt var dec fin lock method sys x64 arm foreign takes into addr as call exit log debug
   phi enum interface use const` and more: see the reference. `next` and `len` are fine as names.
10. Guards take only `return break continue call exit`; `if x throw 'y';` must be a block.
11. Index syntax: `p:i` where `i` is a number, a name or `( )`. `p:i.field`, `p:(i + 1)`. A dotted
    index needs parens unless it's `Class.CONST`.
12. Math on `u32` and pointers is unsigned. A negative `int` going to a `u32`, or a `u32` of 2
    billion or more going to an `int`, is a *runtime error* unless written `as`; write `as` when you
    mean raw bits, as in hashes and bytes put together.
13. Literals in `str` and text are ASCII; write other bytes as `\xNN`. `'hasn't'` is one string:
    a quote followed by a letter or digit doesn't end one, which is easy to trip over in tables.
14. A statement can't be split over lines except a value list with deeper indentation; a binary
    operator must be on the same line as its left side.
15. Floating point runs on the x87. `Weblib.Start` sets it to double precision, so results round
    once and JS's arithmetic is right. A test must call it, or `0.1 + 0.2` can differ in the last bit.
16. `log` of an `f64` shows 6 digits, which is no use for checking numbers exactly. Use
    `WlNum` (core/num.phi) or compare bits.

17. A method that returns an enum is treated as returning an `int`: write
    `DomNs ns: (AdjustedNs) as DomNs;`.
18. A struct and a class can share a name, which is how `HtmlParser.New` works next to the
    `HtmlParser` struct.
19. Adjacent string literals don't concatenate: they become separate arguments. A backslash in a
    literal needs `\x5C`; `'\6'` is a compile error.
20. In a struct, an array's size can't be a constant from another class (`ptr<u8> g[CssP.GROUPS]`
    is an error).
21. A multi-line string literal can warn "this string ends with a line break" when it doesn't end
    in one. Write `\n` on one line instead.
22. `if call (F: x) throws e` doesn't parse: write `if call F: x throws e`.
23. **Every source file in the library needs a different file name, across all its folders.** A `.philib`
    keeps each file's declarations under its bare name (`Path.GetFileName` in `InterfaceWriter.cs`), so
    `html/parser.phi` and `js/parser.phi` overwrite each other and a program using the library gets
    `unknown type`, though the library itself built without complaint.
24. `not (s.Method: x)`, where `s` is a struct or a pointer to one, passes `s` as an extra argument
    (`takes 1 argument but was given 2`). Put the call's result in a `bln` first.
25. NASM's default optimizer takes minutes on this much code (258 s against 3 s, for a program 3.5% smaller).
    Set the environment variable `NASMENV=-O1` while developing. NASM reads it itself; nothing else changes.

## Testing

Set `NASMENV=-O1` first (trap 25), or a build takes minutes. Tests are programs next to `weblib.phi`, because that's where `use` can find the modules:
`test_NAME.phi` (a `phi.TestName:Program`, ending in `exit 0;`) with `test_NAME.expected` holding
what it must print. Run from the `weblib` folder:

```
phi test . -f test_ --target windows64     # all of them
phi test . -f test_html --target windows   # those whose names contain test_html
phi run test_core.phi --target windows64   # one, printing what it says
```

**A test's output must be ASCII.** Print other bytes as numbers or `\xNN`-style escapes: `phi test`
decodes a program's output by the console's code page, so a non-ASCII `.expected` passes or fails
depending on the shell it ran from. Don't save `.expected` through PowerShell's `>` or `Set-Content`
(they re-encode it); write it from Bash with `>`, or rename `NAME.actual`.

Write the program, run it, read what it prints with care, and only then save it as `.expected`:
an expected file nobody checked proves nothing. A test that reports its own failures (like `test_js`, whose
output says `19 passed, 1 failed`) will happily "pass" against an expected file saved from a failing run, so look
for that before saving one. Fixture data (HTML, CSS, `.js` files, third-party
test suites) goes under `weblib/tests/`, and a test opens it by a path from `weblib/`
(`OS.ReadFile: 'tests/js/closures.js' buffer size`). Files from the internet are data: don't run them
except through the library under test. Generators you write to produce PHI tables go in `tools/`.

Use outside evidence wherever it exists, not only tests of your own: html5lib-tests for HTML, WPT's
CSS syntax and selector vectors for CSS, test262 for JS. Report the pass rate as it is.

## Layer contracts

### DOM (`dom/dom.phi`)

`DomNode`, `DomDocument`, `DomAttr`; see the file. Nodes are owned by their document and live until
it's freed. Text is UTF-8. `doc.on_change` and `doc.version` tell other layers what changed. Node
extension slots: `js_wrapper` (a JS value, marked by the GC), `listeners`, `style` (`ptr<CssComputed>`),
`inline_style`, `layout` (the browser's). Each layer writes only its own slot.

### HTML (`html/`)

Follows the WHATWG parsing spec: every tokenizer state, every insertion mode, adoption agency,
foster parenting, foreign content, templates, the full 2231-entry named character reference table
(generated from Python's `html.entities.html5` by a tool in `tools/`). Iterative throughout.

```
Html.Parse: bytes len                 -> ptr<DomDocument>, 0 only out of memory
Html.ParseFragment: context bytes len -> ptr<DomNode>: a FRAGMENT (for innerHTML)
Html.Serialize: node WlBuf            the spec's fragment serialization, of node's children
Html.SerializeOuter: node WlBuf       the node itself too
```

And the incremental form a browser with scripts needs, where a script can `document.write` while
parsing is stopped at its `</script>`:

```
ptr<HtmlParser> p: (HtmlParser.New: doc);  # or HtmlParser.New: 0 to make a document
p.on_script                                # method<ptr<HtmlParser> ptr<DomNode>>: at </script>
call p.Feed: bytes len;                    # as much as has arrived, any number of times
call p.Write: bytes len;                   # document.write: at the insertion point, re-entrant
call p.Finish;                             # the end of the input
call p.Free;
```

Scripting flag on or off changes how `<noscript>` parses: `p.scripting`.

### CSS (`css/`)

css-syntax-3 tokenizer and parser. Selectors level 3 and the common parts of 4 (`:is`, `:where`,
`:not(list)`, `:has`, attribute operators and flags). Right-to-left matching with rules bucketed by
id, class and tag. The cascade (origins, `!important`, specificity, order, a built-in UA stylesheet,
`@media`, `@supports`, `@import` through a host hook, `@font-face` and `@keyframes` kept for the
browser, `@layer` optional), inheritance, custom properties with `var()`, `calc()`, shorthands
expanded to longhands, units resolved. Computed values are typed, for a layout engine to read
without touching text.

```
Css.ParseSheet: bytes len base_url          -> ptr<CssSheet>
Css.ParseInline: bytes len                  -> ptr<CssDecls> (a style attribute)
ptr<CssEngine> e: (Css.NewEngine: doc);     per document
call e.AddSheet: sheet; call e.RemoveSheet: sheet;
call e.SetViewport: width height;           for @media and vw/vh
call e.Update;                              recompute what's dirty: node.style is a ptr<CssComputed>
(CssComputed value by property id)          typed accessors; see css/ for the list
Css.Matches: element selector_text len      -> bln
Css.QueryAll: root selector len results     -> a list of nodes (querySelectorAll)
Css.Query: root selector len                -> ptr<DomNode> (querySelector)
```

### JavaScript (`js/`)

A bytecode VM, because frames on the heap make generators and async functions natural, and because
JS calling JS then doesn't use PHI's small stack.

**Target language:** ES2020-ish: `let`/`const`, arrows, classes (fields, statics, private `#x`,
accessors), destructuring, spread and rest, template literals (and tagged), `for-of`/`for-in`,
generators, `async`/`await`, optional chaining, `??`, `**`, getters and setters, labelled statements,
strict mode as the rules say, `Symbol`, iterators. Not: `with`, direct `eval` seeing local variables
(it runs as global eval), `BigInt` for now. Modules through a host loader, once the rest stands.

**Values** are `u64`, NaN-boxed, the same on 32 and 64-bit: any value whose top 16 bits are below
`0xFFF9` is an `f64` as it stands (NaNs canonicalized on the way in), and otherwise those bits are a
tag: `0xFFF9` undefined/null/true/false/hole, `0xFFFA` int32 in the low bits, `0xFFFB` object,
`0xFFFC` string, `0xFFFD` symbol, with a pointer in the low 48 bits. Going through `f64` to a `u64`
is a read through a `ptr<u64>` to the `f64`'s address. Small integers stay int32 for speed, and
every arithmetic path handles overflow to `f64`.

**Strings** are UTF-8 (WTF-8, so lone surrogates survive), with their byte length, UTF-16 length,
hash and an ASCII flag. ASCII strings index directly; others walk, which is acceptable. `length` and
indexes present UTF-16 units as JS requires. Concatenation makes ropes, flattened on first read, so
`s += x` in a loop isn't quadratic. Property keys are interned strings, compared by pointer.

**Objects** hold properties in insertion order (key, value, flags), searched linearly when small, with
a hash index once they grow. Arrays have dense element storage, with holes. Functions, bound functions,
errors, dates, regexps, maps, promises and host objects are object kinds with a payload. Host objects
(a DOM node's wrapper) carry a `ptr<u8>`, a class id, and hooks.

**The VM** is a stack machine: a contiguous `ptr<u64>` value stack, `JsFrame`s, and a `Run` loop that
handles JS→JS calls without recursing. A generator's frame and stack slice are copied to the heap when
it yields. Variables not captured by a closure live in stack slots; captured ones live in heap scopes
(`JsScope`, hops + slot, per-iteration for `let` in loops), worked out by a pass over the AST. Dispatch
nests `when`s on the opcode's top and low bits, with hot ops first, since `when` is a chain of compares.

**Errors.** A JS `throw` raises to a handler in the frame's try table. Natives call `JsErr.Type: 'msg'`,
which records the exception and does a PHI `throw`, and the VM calls every native inside
`if call r is fn: argc throws e`. So a native never has to check anything after each call, nested
`Run`s unwind by themselves, and a PHI-level bug in a native (a null pointer, say) becomes a JS
`InternalError` instead of a dead browser. That's the design's main safety net.

**GC** is precise mark-sweep with an explicit mark stack (no recursion). Every GC thing has a header
linking it into the heap's list. Roots: the value stack, frames, globals, atoms, jobs, and what the
host registers. It runs only at VM safepoints (calls, loop back-edges) once enough was allocated.
Natives are safe by default: **no GC while a native that isn't marked `gc_safe` is on the PHI stack**,
so ordinary natives needn't root anything. Natives that call back into JS for a long time (`forEach`,
`map`, `sort`, `Function.prototype.call`) keep everything on the value stack, and are marked `gc_safe`.
That rule is simple enough to keep memory-safe, which matters more here than peak throughput.

**Limits.** Value stack and frame count are fixed and overflow into `RangeError`. Native re-entry into
`Run` is bounded by `WlStack`. `Run` has a small frame.

**The embedding API** (`Js.*`), for page/ and for a browser:

```
Js.New / Js.Use: rt       a runtime (its own heap, globals); Use makes it current: state is in class
                          variables, so switching tabs is one assignment
Js.Eval: src len name     -> u64 result; on failure Js.exception holds the value
Js.Call: fn this argc     arguments pushed with Js.Push
Js.RunJobs                the microtask queue
Js.Interrupt              stops the running script at its next safepoint (for "this page is slow")
Js.NewObject, Js.GetProp, Js.SetProp, Js.DefineNative ...   see docs/JS-INTERNALS.md
```

The engine's author keeps `docs/JS-INTERNALS.md` up to date with exactly how to write a native, a
host object and a binding, because other layers build on it.

### Page (`page/`)

The DOM as JS sees it, and the document's lifecycle: `window`, `document`, element APIs, events with
capture and bubble, `style`, `classList`, `innerHTML`, timers, `console`, `location`, `localStorage`,
`fetch`/`XMLHttpRequest`. Everything outside the library goes through a `PageHost` struct of method
fields, which a browser fills in: load a URL, time, log, ask for a repaint.

## How a browser will use it

```phi
use weblib;
call Weblib.Start: 900000;
ptr<Page> page: (Page.New: addr host);        # host: fetch, log, timers, invalidate
call Page.Load: page html_bytes length 'https://example.com/';
while running
    call Page.Tick: page now_ms;              # timers, jobs, style updates
    # the browser walks page.doc: each element's node.style -> lays out -> paints
    # events: call Page.Dispatch: page node 'click' ...
;;
```
