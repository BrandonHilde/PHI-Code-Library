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

A program with `weblib.philib` beside it says `use weblib;` and needs none of the source. Use a `.philib` built by the same build of `phi`. weblib uses vectorlib (for `<canvas>`), so `vectorlib.philib` goes beside it too, and a program that names vectorlib's types (as a `PageHost` that draws a canvas's text does) says `use vectorlib;` as well.

## What's in it

| Layer | Folder | What it does |
|---|---|---|
| Core | `core/` | byte buffers, interned names, UTF-8, a small-block allocator, a stack budget, correct number-to-text and back |
| DOM | `dom/` | the node tree every layer shares |
| HTML | `html/` | the WHATWG parsing algorithm in full, a serializer, `document.write` and incremental parsing |
| CSS | `css/` | parsing, selectors up to `:has()`, the cascade, `@media`, `@supports`, `@layer`, `var()`, `calc()`, 285 longhand properties, typed computed values |
| JavaScript | `js/` | a bytecode VM with a precise garbage collector, and the standard library |
| Page | `page/` | the DOM as JS sees it, events, timers, `fetch`, `<canvas>`, and the document's lifecycle |

**JavaScript** is ES2020 and some of what's come since: classes with private fields, generators, async functions, destructuring, optional chaining, `Proxy`, `Reflect`, `Map` and `Set` with the new set operations, `WeakRef`, typed arrays, `RegExp` with lookbehind and named groups, `Date` and `JSON`; and since 2026-11-21, `BigInt` (with `BigInt64Array`, `BigUint64Array` and DataView's BigInt methods), modules (`<script type=module>`, `import`/`export`, `import()` from any script, `import.meta`, top-level `await`, and since 2026-11-22 import maps), and:

- **RegExp**: every Unicode property ECMAScript names in `\p{...}` (general categories, scripts and their extensions, the binary properties, and with the `v` flag the emoji properties of strings), from Unicode 17's character database (`tools/web/js_gen_props.py` makes `js/uniprops.phi`, 88 KB); the `v` flag's classes (nested, `&&`, `--`, `\q{...}`); `(?i:...)` and the other modifiers; the same group name in separate alternatives; `RegExp.escape`.
- **Iterator** and its helpers (`map`, `filter`, `take`, `drop`, `flatMap`, `reduce`, `toArray`, `forEach`, `some`, `every`, `find`), `Iterator.from` and `concat`, and from the proposals test262 has, `zip`, `zipKeyed`, `includes`, `join`, `chunks` and `windows`.
- **Buffers**: resizable `ArrayBuffer`s and growable `SharedArrayBuffer`s, `transfer` and detaching, immutable buffers (`transferToImmutable`, `sliceToImmutable`), typed arrays and DataViews that track a buffer's length, `Float16Array` and `Math.f16round`, `toSorted`, `toReversed` and `with`, `Atomics` (one thread: `wait` doesn't block, `waitAsync` is woken by `notify`), and `Uint8Array`'s base64 and hex.
- **Resources**: `using` and `await using` (in blocks, functions, modules and `for` heads), `DisposableStack`, `AsyncDisposableStack`, `SuppressedError`, `Symbol.dispose`; and `Array.fromAsync` and `Error.isError`.

The newer builtins that are mostly choosing among options are JavaScript (`js/builtins/iterator.js`, `typedarray.js`, `extras.js`, made into PHI by `tools/web/js_to_phi.py`), loaded the first time one of them is called (`js/builtins/lazy.phi`), so a page that never uses them pays nothing; what scripts see are natives with the builtins' own names, lengths and identity.

**Modules** (2026-11-21): the compiler makes a module a function whose parameters are the namespaces it imports from, so an import is a live binding (a read of the other module's namespace) and assigning one is a TypeError; its own exports are getters on its namespace, defined as it starts, and reading one before then is a ReferenceError. `js/modules.phi` keeps the modules by address, asks its host for each (`JsModules.load` and `resolve`), and runs a graph imports first; `page/pmodules.phi` fetches them as SCRIPT requests and runs a page's module scripts in document order once it's parsed, before `DOMContentLoaded`, as the HTML standard has it. A `nomodule` script doesn't run. Not yet: link-time errors for importing a name a module doesn't export (it reads undefined), JSON modules, import maps, the namespace object's own rules (its keys come in the order they were defined, not sorted, and its properties are getters), and a module with top-level `await` doesn't hold up the ones that import it.

**The DOM** covers `Node`, `Element`, `Document` and collections that stay up to date, `innerHTML`, `classList`, `dataset`, `style`, `getComputedStyle`, selectors, capture and bubble events, `CustomEvent`, timers, `requestAnimationFrame`, `fetch`, `XMLHttpRequest`, `localStorage`, `location` and `navigator`.

**The time and randomness are the host's.** The library asks nothing of the system it runs on, so a browser gives it a clock and a seed: `Js.SetClockHook: hook` (a `method<:f64>` giving the time in milliseconds since 1970 began, UTC), which `Date` reads, and `Js.SetRandomSeed: seed` (a `u64`, from its clock, say), which seeds `Math.random`. Without them, `Date`'s now is 0, the start of 1970, and every run's `Math.random` gives the same numbers.

## How it's checked

From the repo's root:

```
.\build.ps1 web -Test -Only test_css                # the everyday tests, in three groups of under 3 minutes:
.\build.ps1 web -Test -Only test_html,test_page,test_core,test_weblib
.\build.ps1 web -Test -Only test_js                 # (15 programs, and the compiled test in tests/use)
.\build.ps1 web -Test -Release -Timeout 600         # and the release ones too: release_css_perf, release_html_perf,
                                                    # release_js_bench and release_js_limits (speed and the edges)
python tools/web/fetch_test262.py                   # test262, once (it isn't in git)
python tools/web/js_test262.py language --depth 2   # after building test_js262 (its docstring says how)
```

As [the conventions](../../docs/conventions.md#tests) say, during development the tests are light, and the
full suite waits for release: the four that check speed and the edges of the stack and heap run only with
`-Release` (2026-11-10: the everyday tests together take over 3 minutes, so they run in three groups of about 90 to 100 seconds each, most of it building weblib).
All 19 test programs pass as `windows` and `windows64` programs (2026-11-06). As Linux programs
(2026-11-07, their first run), all pass on `linux` and `linux64`, once PHI gave 32-bit Linux
programs the same 128 MB default heap limit as the other systems (see
[phi-notes.md](../../docs/phi-notes.md)). As macOS programs (Apple Silicon, 2026-11-22, the first time weblib
built for it: its x87 routines for `Math.log`, `exp`, `tan`, `atan2` and `**` have ARM versions that
call the Mac's own C library), all pass too; PHI OS's browser runs on a Mac with it (`mac.sh` there). Where an outside test suite exists, it's the measure. The
figures are the same on Windows and Linux, except for `built-ins`, which was counted differently:

| Suite | Result |
|---|---|
| html5lib / WPT tree construction | 14,792 of 14,792 runs |
| html5lib tokenizer | 14,084 of 14,084 runs |
| CSS parsing tests | 8,331 of 8,338 |
| test262, `language`, modules included (Linux, 2026-11-21, evening) | 22,613 of 23,832 (94.9%), no crashes |
| test262, `built-ins`, all of it (Linux, 2026-11-21, evening) | 18,519 of 23,861 (77.6%), no crashes |
| test262, `built-ins` without `Temporal`'s 4,613 (none of which pass) | 18,519 of 19,248 (96.2%) |
| (that morning, before RegExp's properties, the iterator helpers, the new buffers and `using`) | `language` 22,484 (94.3%); `built-ins` 15,366 (64.4%) |
| test262, `intl402` without Temporal's 2,029 (Linux, 2026-11-21) | 1,140 of 1,353 (84.3%), no crashes |
| (before BigInt and modules, 2026-11-07: `language` without its 817 module tests, and `built-ins`) | 21,487 of 23,015 (93.4%); 14,577 of 23,848 (61.1%) |
| test262, `built-ins`, without the families that weren't built on 2026-11-07 (`Temporal`, `Atomics`, `SharedArrayBuffer`, `BigInt`, `ShadowRealm`, the disposable stacks, `SuppressedError`, `Iterator`) | 14,561 of 17,702 (82.3%), then |

(On Windows, 2026-11-06, `built-ins` without the families not built then was 14,351 of 17,398, 82.5%;
which families those were wasn't written down. `Intl` is in test262's `intl402`, not `built-ins`. Most of
its failures there are tests of other locales' formats, of calendars and numbering systems other than
Gregorian and Latin digits, and of Temporal's objects.)

Most of the test262 failures are things deliberately not here (see below): `Temporal`, `with` (298 tests outside its own folder use it), realms (181), `ShadowRealm`, decorators and `accessor` fields, and `Atomics` tests that need other agents (112). Whole families are at or near 100%: `Reflect`, `parseInt`, `Number`, `Object`, `String`, `Date`, `RegExp` (98.6%), `TypedArray` (99.7%), `Iterator` (99.7%), `ArrayBuffer`, `DataView`, `Uint8Array`.

Every JS fixture also runs with a garbage collection at every safepoint, which is how missing roots are found, and the HTML, CSS and JS parsers are fuzzed with fixed seeds. `test_page` runs a whole page, normally and under that stress, and insists the two come out the same. `test_canvas` draws on a canvas from a page (rectangles, transforms, a circle, a gradient, a stroke, `putImageData`, `Path2D`, a clip, text and pictures from a pretend browser, `toDataURL`) and checks the pixels through `getImageData`, with the values a browser gives.

**Observers** (2026-11-21): `MutationObserver` is the DOM standard's (records' `previousSibling` and `nextSibling` are always null); `IntersectionObserver` reports every target wholly in view, once, as a browser that shows the whole page and scrolls it itself would want; `ResizeObserver` reports each target's size once. They're `page/observers.js`, run in every page (`tools/web/make_observers.py` makes `observersjs.phi` from it), with the DOM's `on_mutation` hook telling it of changes while anything observes.

**Custom elements and shadow DOM** (2026-11-22): `customElements.define` and its registry (`get`, `getName`, `whenDefined`, `upgrade`), `HTMLElement` as a constructor a class extends, upgrades of elements the parser or `innerHTML` made earlier, and the `connectedCallback`, `disconnectedCallback` and `attributeChangedCallback` reactions, run as the HTML standard runs them: after each DOM method (`JsVm.after_native`) and between the parser's tokens; `:defined`; `attachInternals` (kept, said to nothing). Shadow trees: `attachShadow`, `ShadowRoot`, slots (`assignedNodes`, `assignedElements`, `assignedSlot`, fallback content), declarative shadow DOM (`<template shadowrootmode>`), events across them (`composed`, `event.target` retargeted, `composedPath`), and styles scoped to them (a shadow tree's sheets for what's in it; `:host`, `:host()`, `:host-context()` and `::slotted()`, which give way to the outside's rules; inheritance through the flat tree). A browser lays out the flat tree with `Dom.FlatFirst` and `FlatNext`. They're `page/elements.js` and `.phi`, `page/shadow.phi`, and the DOM's shadow links (`dom/dom.phi`). Constructable stylesheets (`new CSSStyleSheet`, `replaceSync`, `insertRule`) and `adoptedStyleSheets`, the document's and shadow roots': each sheet is parsed once, however many trees adopt it. Not kept: customized built-ins (`extends`) and `::part`.

**The platform's everyday classes** (2026-11-22, `page/platform.js`, run in every page): `URL` and `URLSearchParams` (the URL standard's parser; hosts aren't made punycode), `TextEncoder` and `TextDecoder` (UTF-8, UTF-16, Latin-1), `DOMException`, `AbortController` and `AbortSignal`, `Blob`, `File`, `FileReader`, `FormData`, `Headers`, `Request` and `Response` (`fetch` takes and gives them), the event classes pages construct (`PointerEvent`, `ErrorEvent` and the rest; no `TouchEvent`, which would say this is a touch screen), `DOMRect`, `DOMPoint`, a 2D `DOMMatrix`, `CSS.supports` and `CSS.escape`, `PerformanceObserver` (told nothing), `requestIdleCallback`, `structuredClone`, `MessageChannel` and `postMessage`, `crypto.getRandomValues` and `randomUUID` (from PHI's `crypto.random`), and in `page/elements.js`, `TreeWalker`, `NodeIterator`, `NodeFilter`, `Range` and `Selection` (nothing is ever selected), `document.implementation` and `DOMParser`. `tools/web/make_page_js.py` makes their `*js.phi`.

**Intl** (2026-11-21) is ECMA-402 with one locale, English as the United States writes it: any locale a page asks for is checked and tidied as the standard has it, then formats as `en-US` (or `en`) does, as a browser with only English would. All of it is there but Temporal's parts: `Collator`, `NumberFormat` (every style and notation, the rounding options, ranges), `PluralRules`, `DateTimeFormat` (with the IANA time zones), `RelativeTimeFormat`, `ListFormat`, `DisplayNames` (common names), `Locale` (a short table of likely subtags), `Segmenter` (graphemes, words and sentences by simple rules, with no dictionary for Chinese or Japanese) and `DurationFormat`, with `toLocaleString` on numbers, BigInts, dates and arrays, `localeCompare` and the locale case changes using them. It is JavaScript, `js/builtins/intl.js`, and big (about 136 KB), so a runtime starts without it: `Intl` is an empty object marked lazy until something looks inside it, and the locale methods load it on their first call (about 0.2 s and 20 MB, once, on emulated 64-bit Linux). `tools/web/make_intl.py` makes `intljs.phi` from it and `intl_data.js`, which holds each time zone's rule now (from the IANA database's compiled files, whose last line is that rule) and how Latin letters with marks come apart (for sorting). A zone's rule now is used for every date, so times long ago in a zone whose rules have changed can be an hour or so out. Checked against Node.js, which agrees except where ICU writes narrow or thin spaces (before AM and PM, around a range's dash) and this a plain one.

**Cookies** are the browser's (`PageHost.cookies` and `set_cookie`, which PHI OS answers from netlib's jar); a host without them gives a page what it set in this session.

**`<canvas>`** (2026-11-21, `page/canvas.phi`): its 2D context, drawn with vectorlib onto pixels the canvas keeps (`0xAARRGGBB`, straight alpha), which a browser paints where layout put it (`PageCanvas.Of: node` gives them, and `PageCanvas.changes` goes up whenever a script draws). Paths (lines, curves, `arc`, `arcTo`, `ellipse`, `rect`, `roundRect`), `Path2D` (with SVG path data), fill by either rule, stroke with joins, caps and dashes, `clip`, transforms, `save` and `restore`, solid colors, linear and radial gradients and patterns, `globalAlpha`, `drawImage` (another canvas, or an `<img>`), `getImageData`, `putImageData`, `ImageData`, `fillText`, `strokeText`, `measureText`, `isPointInPath` and `toDataURL`. Text and other pictures are the browser's: `PageHost.canvas_text` gives a string's outlines in a CSS font, `image_pixels` an `<img>`'s pixels, and `encode_png` a PNG for `toDataURL`. A path made on the context is placed by the transform when each point is added, as the standard has it. Not done: shadows, filters, compositing other than `source-over` (the setting is kept), a radial gradient's starting circle (its center is the focus), conic gradients (drawn with their first color), and `isPointInStroke` (false).

## What it doesn't do yet

- **JavaScript:** no `with`, and direct `eval` runs as global code. `Intl` has only English (above). `String.normalize` returns text as it is. No `Temporal`, no `ShadowRealm`, and no `Error.prototype.stack` accessor (an error has a `stack` of its own, as in browsers now).
- **CSS:** no nesting, no `@container`, `@property` or `@counter-style`. Animations and transitions are parsed and kept, but don't run. `ex` and `ch` are 0.5em. Colours are 8-bit sRGB. Logical properties assume left-to-right text.
- **HTML:** input is always read as UTF-8, with no `<meta charset>` or encoding sniffing.
- **DOM:** no customized built-in elements or `::part`; no WebGL, streams, WebSocket or workers; `Range` doesn't take content out or copy it, and nothing is ever selected. `Date`'s local time is one fixed offset (`JsDate.tz_minutes`), UTC until a browser sets it, with no daylight saving (`Intl.DateTimeFormat` knows the named zones' rules). `localStorage` lasts as long as the page. `attributes` is a snapshot, not live.
- **Nodes aren't freed until their document is.** A long-lived page that makes and drops many nodes keeps growing until it's left.
- **PHI OS is a separate project.** The library builds for it, but it's only tested on Windows. Its 64 KB program stack would limit how deeply scripts can nest.

## Finding your way around

- [docs/DESIGN.md](docs/DESIGN.md): how it's built, the rules for all the code, and **the traps PHI has for this kind of work**. Read that list before changing anything.
- [docs/JS-INTERNALS.md](docs/JS-INTERNALS.md): how to write natives, host objects and bindings for the JS engine.
- `jsrun.phi`: runs a `.js` file through the engine, for trying things out.
- [`tools/web/`](../../tools/web): the generators for the entity, CSS, Unicode and case tables, and the test262 runner. test262 is 217 MB of test data that only that runner uses, so it isn't in git: `fetch_test262.py` there fetches it, at the commit the results above are from.
- [THIRD_PARTY.md](THIRD_PARTY.md): the test data and tables that came from elsewhere, and their licenses.
