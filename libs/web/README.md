# weblib

A library, written in [PHI](https://github.com/BrandonHilde/PHI), that interprets HTML, CSS and JavaScript, for building a web browser. It takes bytes and gives a DOM, computed styles and running scripts. **Layout, painting, networking and windows are the browser's**, and it reaches them through a small set of hooks, so the library itself opens no files and no sockets.

A simple working browser built on it is kept as a project of its own, outside this repo.

```phi
use weblib;

PageHost host;
host.load is addr Load;                      # fetch a URL, then call Page.Delivered with the bytes
host.logger is addr Console;                 # console.log, and scripts' uncaught errors
host.navigate is addr GoTo;                  # a link was clicked, or location.href was set

call Weblib.Start: 900000;                   # how much of the stack may be recursed through
ptr<Page> page: (Page.New: addr host 1024.0 768.0);
call Page.Load: page html length 'https://example.com/';

while running
    call Page.Tick: page now_ms;             # timers and promise jobs
    call Page.UpdateStyle: page;             # computed styles for whatever changed
    # lay out and paint page.doc: every element's (Css.StyleOf: node) has typed getters
    call Page.Frame: page now_ms;            # requestAnimationFrame
;;
call Page.Free: page;
```

## Building

From the repo's root, as its [README](../../README.md) says:

```
.\build.ps1 web                              # dist/weblib.philib, for every system (22 MB)
.\build.ps1 web -Test                        # and its tests
```

`build.ps1` sets `NASMENV=-O1`, which assembles 80 times quicker for a program 3.5% bigger.

A program with `weblib.philib` beside it says `use weblib;` and needs none of the source. Use a `.philib` built by the same build of `phi`.

## What's in it

| Layer | Folder | What it does |
|---|---|---|
| Core | `core/` | byte buffers, interned names, UTF-8, a small-block allocator, a stack budget, correct number-to-text and back |
| DOM | `dom/` | the node tree every layer shares |
| HTML | `html/` | the WHATWG parsing algorithm in full, a serializer, `document.write` and incremental parsing |
| CSS | `css/` | parsing, selectors up to `:has()`, the cascade, `@media`, `@supports`, `@layer`, `var()`, `calc()`, 285 longhand properties, typed computed values |
| JavaScript | `js/` | a bytecode VM with a precise garbage collector, and the standard library |
| Page | `page/` | the DOM as JS sees it, events, timers, `fetch`, and the document's lifecycle |

**JavaScript** is ES2020 and some of what's come since: classes with private fields, generators, async functions, destructuring, optional chaining, `Proxy`, `Reflect`, `Map` and `Set` with the new set operations, `WeakRef`, typed arrays, `RegExp` with lookbehind and named groups, `Date` and `JSON`.

**The DOM** covers `Node`, `Element`, `Document` and collections that stay up to date, `innerHTML`, `classList`, `dataset`, `style`, `getComputedStyle`, selectors, capture and bubble events, `CustomEvent`, timers, `requestAnimationFrame`, `fetch`, `XMLHttpRequest`, `localStorage`, `location` and `navigator`.

## How it's checked

From the repo's root:

```
.\build.ps1 web -Test -Timeout 600                  # the 19 test programs, and the compiled test in tests/use
python tools/web/fetch_test262.py                   # test262, once (it isn't in git)
python tools/web/js_test262.py language --depth 2   # after building test_js262 (its docstring says how)
```

All 19 test programs pass as `windows` and `windows64` programs (2026-11-06). As Linux programs
(2026-11-07, their first run), all pass on `linux` and `linux64`, once PHI gave 32-bit Linux
programs the same 128 MB default heap limit as the other systems (see
[phi-notes.md](../../docs/phi-notes.md)). Where an outside test suite exists, it's the measure. The
figures are the same on Windows and Linux, except for `built-ins`, which was counted differently:

| Suite | Result |
|---|---|
| html5lib / WPT tree construction | 14,792 of 14,792 runs |
| html5lib tokenizer | 14,084 of 14,084 runs |
| CSS parsing tests | 8,331 of 8,338 |
| test262, `language` | 21,487 of 23,015 (93.4%), no crashes |
| test262, `built-ins`, all of it (Linux, 2026-11-07) | 14,577 of 23,848 (61.1%), no crashes |
| test262, `built-ins`, without the families that aren't built (`Temporal`, `Atomics`, `SharedArrayBuffer`, `BigInt`, `ShadowRealm`, the disposable stacks, `SuppressedError`, `Iterator`) | 14,561 of 17,702 (82.3%) |

(On Windows, 2026-11-06, `built-ins` without the families not built then was 14,351 of 17,398, 82.5%;
which families those were wasn't written down. `Intl` is in test262's `intl402`, not `built-ins`.)

Most of the test262 failures are things deliberately not here (see below), and whole families are at or near 100%: `Reflect`, `parseInt`, `Number`, `Object`, `String`, `Date`.

Every JS fixture also runs with a garbage collection at every safepoint, which is how missing roots are found, and the HTML, CSS and JS parsers are fuzzed with fixed seeds. `test_page` runs a whole page, normally and under that stress, and insists the two come out the same.

## What it doesn't do yet

- **JavaScript:** no `BigInt` (which alone is most of the remaining test262 failures in typed arrays), no `with`, no modules or dynamic `import()`, and direct `eval` runs as global code. No `Intl`. `String.normalize` returns text as it is. `\p{...}` knows the general categories but not scripts. No resizable or detached buffers, no `SharedArrayBuffer`, and the `v` regex flag is read as `u`, without its set notation.
- **CSS:** no nesting, no `@container`, `@property` or `@counter-style`. Animations and transitions are parsed and kept, but don't run. `ex` and `ch` are 0.5em. Colours are 8-bit sRGB. Logical properties assume left-to-right text.
- **HTML:** input is always read as UTF-8, with no `<meta charset>` or encoding sniffing. No declarative shadow DOM.
- **DOM:** no shadow DOM at all, no `MutationObserver`, `IntersectionObserver` or custom elements, no `<canvas>`, no `Range` or `Selection`. `<script type=module>` doesn't run. Time zones are one fixed offset (`JsDate.tz_minutes`), UTC until a browser sets it, with no daylight saving. `localStorage` lasts as long as the page. `attributes` is a snapshot, not live.
- **Nodes aren't freed until their document is.** A long-lived page that makes and drops many nodes keeps growing until it's left.
- **PHI OS is a separate project.** The library builds for it, but it's only tested on Windows. Its 64 KB program stack would limit how deeply scripts can nest.

## Finding your way around

- [docs/DESIGN.md](docs/DESIGN.md): how it's built, the rules for all the code, and **the traps PHI has for this kind of work**. Read that list before changing anything.
- [docs/JS-INTERNALS.md](docs/JS-INTERNALS.md): how to write natives, host objects and bindings for the JS engine.
- `jsrun.phi`: runs a `.js` file through the engine, for trying things out.
- [`tools/web/`](../../tools/web): the generators for the entity, CSS, Unicode and case tables, and the test262 runner. test262 is 217 MB of test data that only that runner uses, so it isn't in git: `fetch_test262.py` there fetches it, at the commit the results above are from.
- [THIRD_PARTY.md](THIRD_PARTY.md): the test data and tables that came from elsewhere, and their licenses.
