# JS engine internals: how to build on it

This is for someone who knows PHI and has never seen this engine, and is about to write builtins
(`Math`, `JSON`, `Map`, `RegExp`, `Date` ...) or DOM bindings. Everything here is exercised by a test:
the worked example at the end is real code in `weblib/test_js.phi` (`JsDocExample`), run by
`tests/js/api_example.js`.

## The map

| File (under `weblib/js/`) | What's in it | Class to call |
|---|---|---|
| `js.phi` | the front door, and the `use` of everything | `Js` |
| `value.phi` | NaN-boxed values | `JsV` |
| `jsstring.phi` | strings, ropes, interning, UTF-16 indexes | `JsStrs` |
| `jsobject.phi` | properties, elements, descriptors, hooks | `JsObjs` |
| `ops.phi` | ToString, ToNumber, equality ...; errors | `JsOps`, `JsErr` |
| `gc.phi` | the collector | `JsGc` (use `Js.Mark` etc.) |
| `vm.phi` | the bytecode loop, calls | `JsVm` |
| `jslexer.phi jsparser.phi scope.phi compiler.phi opcodes.phi` | source to bytecode | `Js.Compile` |
| `runtime.phi` | a runtime; the atoms, symbols and prototypes it knows by name | `JsRt` |
| `builtins/*.phi` | one file per builtin family | |

Beyond the first ones, `builtins/` has `arrayx` and `stringx` (the rest of Array and String), `math`, `json`, `globals` (`parseInt`, the URI functions, what's left of Object and Number), `collections` (Map, Set and the weak ones), `regexp`, `date`, `proxy` (and Reflect), `typed` (ArrayBuffer, typed arrays, DataView) and `iter` (`JsIter.Each`: a native's way through any iterable, closing it on an error). `casemap.phi` is generated.

**Adding a builtin family:** write `js/builtins/math.phi` with a `phi.JsMath:Library` that has an `[Init]`,
add `use js.builtins.math;` to `js/js.phi`, and `call JsMath.Init;` to `JsBuiltins.Init` in
`js/builtins/core.phi`. Nothing runs at program start, and a builtin's tables go on the heap.

`JsRt.A` holds interned names (`JsRt.A.length`), `JsRt.S` the well-known symbols (`JsRt.S.iterator`),
`JsRt.P` prototypes (`JsRt.P.array`). `JsProtoSet` in `runtime.phi` already has fields for `regexp`, `date`,
`map`, `set`, `weakmap`, `weakset`, `weakref`, `arraybuffer`, `dataview`, `proxy_ctor`, marked by the
collector; add more there freely (it's nothing but pointers). A prototype you keep in a class variable
of your own is **not** a root and must also be reachable some other way.

## Values

A value is a `u64`. Test and convert with `JsV`:

```phi
JsV.UNDEF  JsV.NULL  JsV.TRUE  JsV.FALSE  JsV.HOLE  JsV.NAN       # class variables, not consts
(JsV.IsObj: v) (JsV.IsStr: v) (JsV.IsSym: v) (JsV.IsNum: v) (JsV.IsInt: v) (JsV.IsBool: v) (JsV.IsNil: v)
(JsV.AsObj: v) -> ptr<JsObj>     (JsV.AsStr: v) -> ptr<JsStr>     (JsV.AsSym: v) -> ptr<JsSym>
(JsV.AsNum: v) -> f64 of a number value, int or double     (JsV.AsInt: v) -> int of an int value
(JsV.Obj: p) (JsV.Str: p) (JsV.Sym: p) (JsV.Int: i) (JsV.Uint: u) (JsV.Bool: b)
(JsV.Num: x)     an f64 as a value, an int if it is one: use this for results
```

**Don't compare values with `is` to test JS equality**: an int and a double can be the same number, and
two strings the same text. `(JsOps.StrictEq: a b)`, `(JsOps.LooseEq: a b)`, `(JsOps.SameValue: a b)`,
`(JsOps.SameValueZero: a b)`. Comparing against `JsV.UNDEF` and friends with `is` is right.

`JsV.HOLE` marks an array hole and an uninitialized `let`. It must never reach JS code.

Conversions, each of which may run JS and may throw: `(JsOps.ToNumber: v)` f64, `(JsOps.ToStr: v)`
ptr<JsStr>, `(JsOps.ToBool: v)` (never runs JS), `(JsOps.ToObject: v)`, `(JsOps.ToPrimitive: v JsOps.HINT_STRING)`,
`(JsOps.ToInt32: v)`, `(JsOps.ToUint32: v)`, `(JsOps.ToInteger: v)` f64, `(JsOps.ToLength: v)` f64,
`(JsOps.RelativeIndex: v len default)` for slice-like arguments, `(JsOps.IsCallable: v)`,
`(JsOps.IsConstructor: v)`, `(JsOps.IsArray: v)`, `(JsOps.TypeOf: v)`, `(JsOps.InstanceOf: v c)`,
`(JsOps.ProtoFromCtor: new_target fallback)`, `(JsOps.Species: o fallback)`, `(JsOps.GetMethod: v key)`.

## Strings

A `ptr<JsStr>` is WTF-8 with a UTF-16 length. It may be a rope: **call `(JsStrs.Flat: s)` before touching
`s.data`** (`s.bytes` and `s.len` are always right).

```phi
(Js.NewString: bytes n)         # a value, from any bytes: bad UTF-8 becomes U+FFFD
(Js.NewStringZ: 'text')
(JsStrs.New: bytes n)           # ptr<JsStr>, from bytes known to be good WTF-8
(JsStrs.FromBuf: addr buf)      # the same from a WlBuf
call Js.TextOf: v addr buf;     # adds the text of a value (ToString) to a WlBuf

s.len                           # UTF-16 units
(JsStrs.UnitAt: s i)            # the unit at i, which must be in range
(JsStrs.CodeAt: s i)            # the code point there; JsStrs.units_taken says how many units
(JsStrs.Slice: s from upto)     # by units; splits surrogate pairs correctly
(JsStrs.IndexOf: s needle from) (JsStrs.Compare: a b) (JsStrs.Eq: a b) (JsStrs.EqZ: s 'text')
(JsStrs.Concat: a b)            # a rope if it's long
(JsStrs.FromUnit: u) (JsStrs.FromCode: cp)
call JsStrs.BufAddUnit: addr buf u;   # one UTF-16 unit to a WlBuf, joining surrogate pairs as it should
(JsStrs.InternZ: 'name') (JsStrs.Intern: bytes n) (JsStrs.InternStr: s)     # the interned one
(JsOps.IsSpace: cp)  call JsOps.Trim: s;  (then JsOps.trim_start and JsOps.trim_len, in bytes)
```

ASCII strings (`(s.flags & JsStrs.F_ASCII) is not 0`) index directly; others walk from a remembered place,
so going along a string in order is linear. Numbers: `WlNum` (`core/num.phi`) has `ToText`, `ToRadix`,
`ToFixed`, `ToExponential`, `ToPrecision`, `Parse`, `ParseRadix`; `(JsOps.NumToStr: x)`, `(JsOps.StrToNum: s)`.

Never hold page text in a PHI `str`: it's cut at 65,535 characters. Error messages built with `(...)` are fine.

## A native function

It takes a pointer to its arguments and how many there are. They're on the value stack. Its `[end: ...]`
must be a `u64` expression (`JsV.UNDEF` will do), so that it's the right kind of method.

```phi
[Sum: ptr<u64> args: 0; int argc: 0;]
    f64 total: 0.0;
    while int i: 0; i < argc; i++;
        total is total + (JsOps.ToNumber: args:i);
    ;;
[end: (JsV.Num: total)]
```

```phi
call Js.DefineNative: JsRt.r.global 'sum' addr Sum 2;       # 2: its `length`
```

- `(Js.Arg: args argc i)` is argument `i`, or undefined if there aren't that many.
- `(Js.This: args)` is `this`, which is `args:(-1)`. It's whatever it was called with: check it.
- `(Js.CalleeOf: args)` is the `ptr<JsNativeFn>` being called. One native can serve many functions through
  its `f.magic` (a u32), and keep values in `f.data` and `f.data2`, which the collector marks. Closures:
  `(JsObjs.NewNative: addr Fn 'name' nargs false)`, set `f.data`.
- `(Js.NewTarget)` is `new.target`, or undefined when not called with `new`. **Read it first thing**, before
  anything that could call JS. For `new` to work the function needs `f.o.flags | JsObjs.F_CTOR`:
  `Js.DefineClass` does that.

A method returning `u64` must return one on every path: `return JsV.UNDEF;`, not `return;`.

## Errors

```phi
call JsErr.Type: 'message';          # also Range, Reference, Syntax, Eval, Uri, Internal
call JsErr.Type: ('bad value ' n);   # with values in it, as a short str
call JsErr.Throw: value;             # throws any value
(JsErr.Make: JsRt.P.type_error 'message')    # an Error object, not thrown; it has a stack
```

Those never come back: they record the exception and do a PHI `throw`. There's nothing to check after any
call that might have thrown, in natives or helpers. Unwinding goes straight to the JS handler. Write
`[end: JsV.UNDEF]` after one anyway, as the compiler wants a result.

**A PHI error is a JS error too.** A plain `throw 'text'`, a null pointer, a bad index or a division by zero in
a native all become a JS `InternalError`; out of memory a `RangeError`. `throw 'too much recursion'`
(`WlStack.Check`) becomes a `RangeError`. So a bug in a native doesn't bring the browser down.

**Catching** is rarer, and has a form, because more than the PHI stack has to be put back:

```phi
JsTryState t;
call Js.TryBegin: addr t;
u64 r: 0;
if call r is Js.CallThrowing: f JsV.UNDEF 0 throws err
    u64 thrown: (Js.TryCatch: addr t err);    # the exception, cleared; the value stack as it was
    # ... do something with it
;;
```

`Js.TryCatch` rethrows an interrupt rather than handing it over, so `Js.Interrupt` can't be swallowed.

## Objects and arrays

```phi
ptr<JsObj> o: (Js.NewObject);
ptr<JsObj> p: (Js.NewObjectWith: proto);          # 0 for no prototype
ptr<JsObj> a: (Js.NewArray: room);
call Js.ArrayPush: a v;                           # a real array only
a.length                                          # an array's length (u32)
```

### Properties

By name, on any value (these follow prototypes, call getters and setters, and may run JS):

```phi
u64 v: (Js.GetProp: x 'name');       call Js.SetProp: x 'name' v;      # SetProp throws if it fails
u64 w: (Js.GetKey: x key_value);     call Js.SetKey: x key_value v;    # any JS value as the key
u64 e: (Js.GetIndex: x 3);           call Js.SetIndex: x 3 v;
(Js.HasProp: o 'name')   (Js.Delete: o 'name')
call Js.Define: o 'name' v JsObjs.WC;              # no setters run; flags are the property's
```

Flags: `JsObjs.W`, `E`, `C`, together `WEC`, and `WC` for what builtin methods and `constructor` have.

Underneath, `JsObjs` takes a **key value**: `(JsObjs.KeyOf: v)` turns any JS value into one (it may run JS: an
object's `toString`), and `(JsObjs.KeyZ: 'name')` makes one from text. A key value is an int-tagged u32 for an
array index up to 2^32-2 (`(JsObjs.IsIndexKey: k)`, then `k as u32`), a string value of an interned non-index
string, or a symbol value. It's for handing to these, not a JS value: `(JsObjs.KeyToValue: k)` is what JS sees.

```phi
(JsObjs.Get: o k receiver)   (JsObjs.Set: o k v receiver) -> bln   (JsObjs.Has: o k)   (JsObjs.Delete: o k) -> bln
(JsObjs.GetV: anything k)    (JsObjs.SetV: anything k v) -> bln
(JsObjs.GetAtom: o key_ptr receiver)     # with a JsRt.A.name as ptr<u8>, or a symbol: the quick way
(JsObjs.GetIndex: o u32 receiver)
(JsObjs.CreateData: o k v) -> bln        # CreateDataProperty: define, no setters
(JsObjs.GetOwn: o k addr desc) -> bln    # a JsDesc: desc.value, .getter, .setter, .flags
(JsObjs.DefineOwn: o k addr desc) -> bln # ValidateAndApply; set .flags from W E C and H_W H_E H_C H_VALUE H_GET H_SET
(JsObjs.OwnKeys: o) -> array of strings and symbols, in JS's order (index ascending, strings, symbols)
(JsObjs.ForInKeys: o)  (JsObjs.ProtoOf: o)  (JsObjs.SetProtoOf: o p) -> bln
(JsObjs.IsExtensible: o)  (JsObjs.PreventExtensions: o)
```

`(JsObjs.GetOwn: ...)` and friends go through hooks; `o.props` and `o.elems` are for the engine's own files.

### Array elements, quickly

Dense elements are in `o.elems`, `o.elem_len` of them; a hole is `JsV.HOLE`. Index keys that are far apart, or have
attributes other than WEC, live in the property table instead and the object has `JsObjs.F_SPARSE`, so a loop
must go `(JsObjs.GetIndex: o i v)` unless it has checked `o.kind is JsGc.K_ARRAY` and the flag isn't set. A
page can set `length` to 4 billion in one statement: **a builtin must not loop to `length` without thought**. For
a sparse array, go by `JsObjs.OwnKeys` where the result can't tell the difference. A loop that can run for a long
time calls `call Js.Checkpoint;` on each round: `Js.Interrupt` and the poll hook then work there too, and if the native is
`gc_safe` it's a safepoint, so it may collect there (a native that isn't, never does).

## Calling JS

From a native, for a function value `f`:

```phi
u64 r: (JsVm.Call0: f this_value);
u64 r: (JsVm.Call1: f this_value a);       # also Call2, Call3
call Js.Push: a;  call Js.Push: b;
u64 r: (Js.CallThrowing: f this_value 2);  # any number of arguments; they've been pushed
call Js.Push: a;
u64 o: (Js.Construct: f 1);                # new f(a)
```

An exception from the callee carries on up through you, which is usually what you want. `Js.Call` is the same
for a **host** at the top level: it catches everything, and sets `Js.failed` and `Js.exception`.

Each native-to-JS call is another `Run` on the PHI stack, budgeted by `WlStack`: too deep is a `RangeError`, and
nothing you need to check for.

### The collector, and `gc_safe`

The collector runs **only at VM safepoints** (function entries and loop back-edges), never during an allocation. So:

- **Allocating never collects.** A native can make as many objects as it likes and hold them in locals.
- **A native defined with `Js.DefineNative` is not `gc_safe`.** While it's on the PHI stack the collector doesn't
  run at all, even in JS it calls. Such a native needs no rooting. This is the right choice for almost
  everything, including anything that calls JS only briefly (`toString`, a getter, one callback).
- **A native that can call JS for a long time** (`forEach`, `map`, `sort`, `replace` with a function, `Function.prototype.call`)
  should be `gc_safe`, or a page's whole run could pass with no collection: `Js.DefineNativeSafe`. Then **across any
  call that can run JS**, whatever it holds must be reachable from something the collector sees:

  1. its own arguments and `this`: they're on the stack already;
  2. what it pushes with `Js.Push` (nothing pops it until the native returns: the VM resets the stack then);
  3. anything reachable from those.

  ```phi
  ptr<JsObj> list: (Js.NewArray: 3);
  call Js.Push: (JsV.Obj: list);            # now it's safe in a local too
  while int i: 0; i < 3; i++;
      call Js.Push: x;
      call Js.ArrayPush: list (Js.CallThrowing: f JsV.UNDEF 1);
  ;;
  ```

  **Push it before the first `Js.Checkpoint`, not just before the first call.** In a `gc_safe` native a checkpoint can collect, so a new array that's only in a local dies there. That's how `toSorted` once freed its own copy; only GC stress caught it.

  A pointer into the stack stays good: **the stack never moves**. The result of a call is unrooted only until the
  next call that can run JS. Conversions count as running JS (`JsOps.ToStr` of an object), and so does anything
  that may reach a getter.

If in doubt, leave it not `gc_safe`: that can only cost memory for a while, not safety. Test with GC stress, below.

**Values a native keeps after it returns** (in a class variable, a struct on the heap, a DOM node) aren't seen by the
collector unless you say so:

- `call Js.AddRoot: addr slot;` marks that `u64` slot in every collection, until `Js.RemoveRoot`.
- `call Js.AddRootFn: addr Fn;` runs `Fn` in every collection; it calls `Js.Mark: v` for each value it holds. This
  is the way for a document's nodes: walk them and mark each `node.js_wrapper`.
- Inside an object: a `trace` hook (below), or the object's own properties.

A host at the top level holds the same way: a value from `Js.Eval` is safe in a local only until JS next runs.

## A builtin class

```phi
ptr<JsObj> proto: (Js.NewObject);
JsRt.P.date is proto;                                              # if the engine should know it
ptr<JsNativeFn> c: (Js.DefineClass: 'Date' addr Construct 7 proto);    # on the global, linked both ways
call Js.DefineNative: proto 'getTime' addr GetTime 0;
call Js.DefineGetter: proto 'size' addr SizeGet 0;                  # 0: no setter
call Js.DefineSymbolNative: proto JsRt.S.iterator '[Symbol.iterator]' addr Values 0;
call Js.DefineSymbolGetter: c as ptr<JsObj> JsRt.S.species '[Symbol.species]' addr Species 0;
call Js.DefineNative: c as ptr<JsObj> 'now' addr Now 0;             # a static
```

The constructor gets its prototype from `new.target`, so that `class X extends Date` works:

```phi
u64 nt: (Js.NewTarget);
if not (JsV.IsObj: nt)
    call JsErr.Type: 'Date needs new';      # or do what the spec says for a plain call
;;
ptr<JsObj> o: (JsObjs.NewHost: date_class (JsOps.ProtoFromCtor: nt JsRt.P.date) data);
```

## Objects with a payload, and hooks

A kind of object is a `JsClass`: make it once, in a class variable (it isn't per runtime, and isn't a GC thing).

```phi
if date_class is 0
    date_class is (JsObjs.NewClass: 'Date');     # the name's what Object.prototype.toString says
    date_class.finalize is addr FreeDate;
;;
ptr<JsObj> o: (JsObjs.NewHost: date_class proto payload);
```

`o.data` is your `ptr<u8>` payload; `o.cls` tells you it's yours; `o.slot` is one value the collector marks for you.
Always check `o.cls` before trusting `o.data` of a `this`: a page can call any method on anything.

Every hook is optional, and set before the first `NewHost`:

| Hook | Signature | When | Result |
|---|---|---|---|
| `trace` | `[H: ptr<JsObj> o;]` | each collection it's alive | call `Js.Mark: v` for each value in the payload |
| `finalize` | `[H: ptr<JsObj> o;]` | it's being freed | free the payload. Don't allocate, or touch other objects |
| `get` | `[H: ptr<JsObj> o; u64 key; u64 recv; ptr<u64> out;]` | a property read | 1 answered, in `out:0`; 0 not mine |
| `set` | `[H: ptr<JsObj> o; u64 key; u64 v; u64 recv;]` | a write | 1 done; -1 refused; 0 not mine |
| `has_key` | `[H: ptr<JsObj> o; u64 key;]` | `in` | 1 yes; -1 no; 0 not mine |
| `del` | `[H: ptr<JsObj> o; u64 key;]` | `delete` | 1 done; -1 refused; 0 not mine |
| `keys` | `[H: ptr<JsObj> o; ptr<JsObj> list;]` | own keys | add every own key to `list` with `Js.ArrayPush`, as strings and symbols, ordinary ones too |
| `get_own` | `[H: ptr<JsObj> o; u64 key; ptr<JsDesc> d;]` | [[GetOwnProperty]] | 1 filled in; -1 no such; 0 not mine |
| `define` | `[H: ptr<JsObj> o; u64 key; ptr<JsDesc> d;]` | [[DefineOwnProperty]] | 1 ok; -1 refused; 0 not mine |
| `call_fn` | `[H: ptr<JsObj> o; ptr<u64> args; int argc;]` returns u64 | it's called | the result; `this` is `args:(-1)` |
| `construct` | `[H: ptr<JsObj> o; ptr<u64> args; int argc; u64 nt;]` returns u64 | `new` | the object |
| `get_proto`, `set_proto`, `is_extensible`, `prevent_ext` | see `struct.JsClass` | | for Proxy |
| `ephemeron` | `[H: ptr<JsObj> o;]` returns int | during marking | `Js.Mark` the value of each key `Js.IsMarked`; how many it marked |
| `weak_clear` | `[H: ptr<JsObj> o;]` | marking's done | drop what `(Js.IsMarked: v)` says is dead |

`key` is a key value. "Not mine" carries on as for any object. Having any exotic hook makes every property
access on the object take the slow path; it's not a cost on anything else. A hook that throws, throws to JS.

**A live collection** (`nodeList[3]`, `nodeList.length`) needs `get`, `get_own` and `keys`, and `has_key`, `set` and `del` to
be right about it. **Proxy** is all of them, plus `call_fn` and `construct` where the target has them (and a Proxy
checks its invariants itself). **WeakRef** has `weak_clear`, with the target kept in the payload (not `o.slot`,
which would keep it alive). **WeakMap** has `ephemeron` and `weak_clear`. Both are in the example.

## Regular expressions, and other hooks for later

Hooks on the runtime (`JsRt.r`):

| Field | Set it to | Meaning |
|---|---|---|
| `regexp_hook` | `[H: ptr<JsStr> pattern; ptr<JsStr> flags;]` returning u64 | what a regex literal evaluates to, each time it's reached. Without it a literal throws `SyntaxError` when reached |
| `regexp_check_hook` | `[H: ptr<JsStr> pattern; ptr<JsStr> flags;]` | called when a literal is compiled; `JsErr.Syntax` it if it's bad, as the spec's early errors want. The lexer has already checked that the flags are `dgimsuy`, each once |
| `console_hook` | `[H: ptr<u8> text; u32 n;]` | `console.log` and friends, one line of text (WTF-8, without a newline) |
| `reject_hook` | `[H: u64 promise; u64 reason; int kind;]` | 0 rejected with no handler, 1 handled later |
| `poll_hook` (`Js.SetPollHook: addr F every`) | `[F]` returning bln | asked every `every` safepoints; true stops the script, as `Js.Interrupt` does |

`call JsPromises.EnqueueCall: fn arg;` queues a job (`queueMicrotask`). `(JsPromises.PromiseResolve: ctor v)` and the rest of
`builtins/promise.phi` are there to call: a promise is `o.kind is JsGc.K_PROMISE`, as a `ptr<JsPromiseObj>`.

## The embedding API

```phi
call Weblib.Start: 900000;                 # the stack budget (48000 is the default) and the x87's precision
ptr<JsRuntime> rt: (Js.New);               # makes it current
rt.console_hook is addr Print;
call Js.Use: rt;                           # switches current; not while JS is running
u64 r: (Js.Eval: source length 'name.js');
if Js.failed
    # Js.exception is what was thrown
;;
call Js.Push: a;
u64 r2: (Js.Call: fn this_value 1);        # the same on failure
call Js.RunJobs;                           # the microtask queue, until it's empty. A job's exception sets Js.failed.
call Js.Interrupt;                         # stops the running script at its next safepoint; no catch sees it
call Js.Free: rt;
```

`Js.Eval` can't let an error out: compile errors, exceptions and bugs in natives all come back as `Js.failed`.

`(Js.Compile: source length 'name' false)` gives a `ptr<JsCode>` without running it (it throws on a syntax error:
`JsErr` style), and `(Js.RunCode: code)` runs it, for those who want parse errors and run errors apart. A
`JsCode` is a GC thing and nothing holds it until it runs: run it before anything else can.

## Memory for cells, properties and elements

These come from `WlAlloc` (`core/alloc.phi`), not `new`: `(WlAlloc.Alloc: size)` and `call WlAlloc.Free: p size`, the same size both ways. PHI's own heap searches a list of freed blocks, which gets slow when many have nearly the same size, as a JS heap's do. Anything of 512 bytes or less has its own slabs, so it takes one step either way.

The collector can't run during an allocation, so the heap must never fill between collections: `JsGc.Collect` leaves at most half the room there is before the next one, by `heap_ceiling` (100 MB on 32-bit, where the heap is 128 MB). If `new` ever does fail, `JsGc.HeapFull` lowers the ceiling to what was in use, and the script sees a `RangeError`.

## Limits

- The value stack is 2 MB (262,144 values) and frames 8,000 deep, per runtime; past those a `RangeError`.
- A native's re-entry into JS is limited by the `WlStack` budget: about 1,900 levels of JS -> native -> JS at 900 KB, and
  100 at 48 KB. **A native that recurses** on what a page wrote calls `WlStack.Check` per level, and keeps its frame small.
- What stays alive after a collection is limited to 1.5 GB (`Js.SetMemoryLimit: bytes`): past that, a `RangeError` at the next
  safepoint. Running out for real (a 32-bit PHI program on Windows has a 128 MB heap) is the same error: made ahead of
  time, so it can always be thrown. A native's `new` that returns 0 should `throw 'out of memory...'` with that wording.
- Strings are at most 512 MB; a dense array 64 million elements; arguments to `apply` or a spread call, 200,000.
- Pointer arithmetic in PHI goes through 32 bits, even on 64-bit: don't build an allocation over 2 GB.

## GC stress

`call Js.SetStress: true;` (after `Js.New`) collects at every safepoint: every function call and loop back-edge. A
missing root shows up at once rather than one day in the field, usually as a value that's changed or
an access violation that comes back as an `InternalError`. `test_js` runs every fixture both ways and insists on identical
output. Anything `gc_safe` must have a fixture that goes through it, with allocation and a call in the
middle: `gc()` is there for tests to ask for one at a chosen point (`Js.Collect`, which does nothing
while a non-`gc_safe` native is running).

## Adding a test

A fixture is `libs/web/tests/js/NAME.js`, with what it must log in `NAME.out` (as `console.log` writes it, one line a call,
and non-ASCII as `\uXXXX`). `test_js` finds it by itself and runs it normally and under stress. An uncaught
exception is written as `UNCAUGHT` and its text.

```
cd libs/web
phi build test_js.phi                         # it says where it put the program
PROGRAM NAME                                  # one fixture: prints what it logs. READ IT WITH CARE.
PROGRAM NAME > tests/js/NAME.out              # from Bash, never PowerShell: it re-encodes
phi test . -f test_js
```

Natives only tests need go in `JsTestHost` in `test_js.phi`. A new `test_*.phi` needs `use js.js;`, `call Js.Start: 900000;` first thing (the stack budget and the x87's precision, what `Weblib.Start` does for the engine; with `use weblib;` it would compile all of HTML and CSS too, and take minutes), and a `.expected`.
Output must be ASCII. Builtin tests want a loop's iterations in the hundreds, not millions: stress makes each one
a whole collection.

## test262

The suite is under `libs/web/tests/test262/` (`tools/web/fetch_test262.py` fetches it) (a sparse checkout: `harness` and `test/language`; for builtins, go there
and run `git sparse-checkout add test/built-ins`). Files in it are data: they only ever run through the engine.

```
cd libs/web
phi build test_js262.phi
cd ../..
python3 tools/web/js_test262.py language/expressions language/statements --fails fails.txt
python3 tools/web/js_test262.py built-ins/Math --depth 3 --causes 30
```

It prints pass, fail and crash per folder (`--depth` how many levels), then failures counted by cause, each with one
example; `--fails` lists them all. A test is run strict and sloppy unless its `flags` say otherwise, with `includes`,
`negative` and `async` honoured; modules are skipped and counted; a crash costs one test. `build/test_js262/test_js262.exe
LISTFILE` runs a list of paths by itself. `tests/js/shim262.js` is loaded first in every test: it stands in for
builtins not written yet, each only if missing, so as builtins arrive it fades away, and **a builtin's own tests must
not be read as passing because of it**: it can be deleted, and then every missing builtin shows up by cause.

## Worked example

The whole of it is `JsDocExample` in `weblib/test_js.phi`, driven by `tests/js/api_example.js`: `sum`, `makeList`, `shapeOf`,
`callTwice`, `callCatching`, a `Counter` class with a payload and a `trace` hook, a `Live` collection with hooks, a `Weak`
reference and an `Ephemeron` table. Here's the heart of it:

```phi
struct.JsCounterData
{
    u64 label;            # a JS value this host object holds: its trace hook marks it
    f64 count;
}

phi.JsDocExample:Library
{
    ptr<JsClass> counter_class: 0;
    ptr<JsObj> counter_proto: 0;

    [Install]
        if counter_class is 0
            counter_class is (JsObjs.NewClass: 'Counter');
            counter_class.trace is addr TraceCounter;
            counter_class.finalize is addr FreeCounter;
        ;;
        counter_proto is (Js.NewObject);
        call Js.DefineClass: 'Counter' addr CounterCtor 1 counter_proto;
        call Js.DefineNative: counter_proto 'add' addr CounterAdd 1;
        call Js.DefineNativeSafe: counter_proto 'each' addr CounterEach 1;
        call Js.DefineGetter: counter_proto 'value' addr CounterGet addr CounterSet;
    [end]

    [CounterCtor: ptr<u64> args: 0; int argc: 0;]
        u64 nt: (Js.NewTarget);
        if not (JsV.IsObj: nt)
            call JsErr.Type: 'Counter needs new';
        ;;
        ptr<JsCounterData> d: new JsCounterData;
        if d is 0
            throw 'out of memory';
        ;;
        d.label is JsV.UNDEF;
        d.count is (JsOps.ToNumber: (Js.Arg: args argc 0));
        ptr<JsObj> proto: (JsOps.ProtoFromCtor: nt counter_proto);
        ptr<JsObj> o: (JsObjs.NewHost: counter_class proto d as ptr<u8>);
    [end: (JsV.Obj: o)]

    # `this`, checked to be a Counter
    [ThisCounter: ptr<u64> args: 0;]
        u64 t: (Js.This: args);
        if (JsV.IsObj: t)
            ptr<JsObj> o: (JsV.AsObj: t);
            if o.cls is counter_class
                return o.data as ptr<JsCounterData>;
            ;;
        ;;
        call JsErr.Type: 'not a Counter';
    [end: 0 as ptr<JsCounterData>]

    [TraceCounter: ptr<JsObj> o: 0;]
        ptr<JsCounterData> d: o.data as ptr<JsCounterData>;
        call Js.Mark: d.label;
    [end]

    [FreeCounter: ptr<JsObj> o: 0;]
        free o.data;
    [end]

    [CounterAdd: ptr<u64> args: 0; int argc: 0;]
        ptr<JsCounterData> d: (ThisCounter: args);
        if argc > 0
            if not (JsV.IsNum: args:0)
                call JsErr.Type: 'add needs a number';
            ;;
            d.count is d.count + (JsV.AsNum: args:0);
        ;;
    [end: (JsV.Num: d.count)]

    # gc_safe: calls f(count, i) three times; the array it builds stays reachable on the stack
    [CounterEach: ptr<u64> args: 0; int argc: 0;]
        ptr<JsCounterData> d: (ThisCounter: args);
        u64 f: (Js.Arg: args argc 0);
        ptr<JsObj> list: (Js.NewArray: 3);
        call Js.Push: (JsV.Obj: list);
        while int i: 0; i < 3; i++;
            call Js.Push: (JsV.Num: d.count);
            call Js.Push: (JsV.Int: i);
            call Js.ArrayPush: list (Js.CallThrowing: f JsV.UNDEF 2);
        ;;
    [end: (JsV.Obj: list)]
}
```

(`CounterEach` reads `d` after JS has run, and that's fine: `this` is on the stack, so the object and its payload stay alive.)

## PHI traps met here

On top of the list in `DESIGN.md`:

- An `int` shifted by a `u32` is an unsigned shift: `a >> (b & 31)` with `b` a `u32` loses the sign. `(b & 31) as int`.
- A method whose `[end: ...]` is a call to itself has its kind guessed as `int`: end in a typed local.
- Numbers on the x87: `0.0 - x` isn't `-x` when `x` is 0. `x * -1.0` is.
- A class variable declared with a string literal after the class's own `exit 0;` is never set: only what can be
  done when the program is built (numbers) is. Set it in code.
- `ptr + n` adds bytes: `sp + 8`, not `sp + 1`.
- `(F: x).field` doesn't parse, and neither does `(expr):i`: put it in a variable first.
- In a Bash heredoc, a doubled backslash may reach the file as one (it's the tool, not PHI).
