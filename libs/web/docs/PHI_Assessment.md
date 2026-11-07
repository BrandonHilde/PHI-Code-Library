# PHI assessment

November 2026. Based on building weblib, a library of HTML, CSS and JavaScript engines written in PHI, and a simple test browser on top of it, plus small test programs compiled with the current compiler. Written by Claude, the AI that wrote that code. File paths below are relative to the PHI repo.

## Verdict

**PHI is good, and it's further along than its age and size would suggest, but it isn't yet a comfortable language for large programs that handle hostile input.**

The core design is sound. It has carried about 55,000 hand-written lines of HTML, CSS and JavaScript engine without falling over, and I have no miscompile on record. What holds it back is mostly fixable: a few grammar holes, return types declared in the wrong place, fixed limits, and a code generator that doesn't try very hard. The one deep problem is safety. "Optional memory safety" doesn't reach the pointer-heavy code where it matters most.

I'd pick PHI today for kernels, drivers, tools and small programs that should be readable all the way down to the machine code. For a browser engine, I'd only pick it with the first group of changes below made.

## What this is based on

| Evidence | Result |
|---|---|
| weblib | About 55,000 hand-written lines, 4,400 generated |
| Outside test suites | html5lib 14,792/14,792 and 14,084/14,084, CSS 8,331/8,338, test262 language 93.4%, built-ins 82.5%, 0 crashes |
| Standard library in real use | The browser fetched GitHub, Wikipedia and Google through PHI's own TLS and HTTP |
| Re-tests | The behaviours in the appendix, checked on `windows64` when this was written |

**What this doesn't cover.** I only wrote Windows programs. I didn't exercise kernels, PHI OS, threads, 16-bit code or ARM, and those are PHI's home ground, so this assessment is probably harder on the language than one written from there. I also barely used owned objects or interfaces. I'm an AI, so I can't judge how PHI feels to learn, or how fast a person gets used to it.

## Against PHI's own goals

| Goal (from the README) | Assessment |
|---|---|
| Direct access to ASM | **Met.** Assembly blocks work, and ports and interrupts are part of the language. |
| Optional memory safety | **Partly met.** Arrays and CPU faults are well handled, but pointers are never checked, and large programs are mostly pointers. |
| Syntax efficiency | **Mixed.** Short and clean for small code. In long argument lists it saves commas at the cost of readability. |
| Compile to ASM, then binary | **Met, and a real strength.** Each source line appears above the code it produced. NASM's default optimizer is the main cost. |
| C compatibility | Planned, not assessed. |

## What's good

- **Errors are the best feature.** `throw`, PHI's own errors and CPU faults all go through the same `if call ... throws e`, with a line number. A null pointer inside a guarded call reports `an empty object or a null pointer was used on line 9`, and the program carries on. weblib's JS engine uses this as its safety net: a bug in a built-in function becomes a JS `InternalError` instead of a dead browser. Few low-level languages offer this.
- **Compiler messages are unusually helpful.** They tell you what to write instead:
  - `'at' is a keyword and can't be a variable name; try 'pos' or 'offset'`
  - `'x -1' is two arguments, x and -1; to subtract, write x - 1, or write (-1) if two are meant`
  - `comparisons can't be chained; use parentheses, like (a < b) is false, or 'and'`
- **You can see what it does.** The `.asm` output with source lines above it made performance questions quick to answer. There's no hidden runtime to reason about.
- **Sensible fixes to C.** Bitwise operators bind tighter than comparisons, there's no `when` fall-through, enums are real types with a warning for missed cases, a negative number going into a `u32` is a runtime error unless you write `as`, and array indexes are checked.
- **The tools come with it.** `phi test`, `phi check`, the language server, compiled libraries and a `.pdb` on Windows, with no build system to set up.
- **The standard library goes surprisingly deep.** TLS 1.3 and its cryptography, networking, graphics and windows are all written in PHI, and the browser uses them on real sites. The only change HTTPS needed was loading more root certificates.
- **The documentation is serious.** `language.md` is complete enough that weblib was written from it, though the shorter guide for C programmers has drifted out of date.

## What's bad

### Safety stops where large programs begin
Pointers are never checked, and writing `unsafe` doesn't change that. weblib has about 220 lines with `new` and 190 with `free`, and only one with `unsafe`, because most of its data is reached through pointers, which `unsafe` has no effect on. In my re-tests, writing to `p:100` of a 4-byte allocation and reading a freed pointer both ran silently. A use-after-free in weblib's `toSorted` was found by a GC stress mode I wrote, not by anything in the language.

### Stack overflow can't be caught
Runaway recursion inside `if call ... throws` kills the process with no message (exit code `0xC00000FD`). Everything else is caught, so this is the one hole in the best feature. For code that handles hostile input it's serious: weblib has to carry its own stack budget (`WlStack.Check`) through every recursive path.

### Return types are in the wrong place
A method's return type is inferred from its `[end: ...]`, at the bottom. You can't see what a method returns from its header, and `[end: 0]` makes it an `int`. That caused a whole class of bugs in this project: pointers cut to 32 bits, working on `windows` and failing on `windows64`. The compiler now warns, which helps, but the program still builds. weblib has 39 `[end: 0 as ptr<...>]` lines that exist only to work around this.

### Argument lists are hard to read
Space-separated arguments are fine until one is an expression. This is a real line from the test browser's layout code:

```phi
call Add: RECT x y + h - bb w bb (s.BorderBottomColor) n;
```

That's seven arguments, and you have to count to find out. It's also why `x -1` and `x - 1` mean different things. The compiler's warning is a good patch on a problem the grammar created.

### Grammar holes that cost real time
- `(F: x).field` doesn't parse.
- `not (s.Method: x)` passes `s` as an extra argument. The result is two misleading messages, about a 32-bit pointer and about the wrong number of arguments, for code that's correct.
- An expression can't continue on the next line, even inside parentheses.
- There are 81 reserved words, including ordinary names such as `at`, `in`, `out`, `end`, `log`, `lock` and `into`.

### Text and containers are weak
- `str` silently cuts text at 65,535 characters, and at its size if declared `str s: [3]`. Losing data silently is the wrong default, so weblib had to ban `str` for page content.
- There are no generics. `Map` only maps `u32` to `u32`, and its own comments say to keep a pointer's place in a table because a pointer won't fit in 64-bit code. weblib wrote its own containers.
- Method values can't carry data, and there are no closures. State goes through class variables, which is part of why weblib has a `Page.current` and can't run on two threads at once.
- String literals can't contain non-ASCII characters, which is awkward for anything that handles text.

### The generated code is simple
This is the inner loop of a sieve, with both variables already local:

```nasm
mov rax, qword [rbp - 12]
push rax
mov eax, dword [rbp - 28]
movsxd rax, eax
pop rbx
add rbx, rax
```

- There's no register allocation here, and a push and pop to add two numbers. Some small optimizations do exist, such as `add dword [mem], eax` and loop tests moved to the bottom.
- The same sieve took **642 ms in PHI and 353 ms in C#** with JIT and bounds checks. That's about 1.8×, from one benchmark that spends much of its time on memory, so branch-heavy code may well show a larger gap. There's no C compiler on this machine, so I have no C figure.
- `when` is a chain of compares, even for 8 consecutive integers. It matters for interpreters: weblib's VM had to nest `when`s by hand.
- Floating point on 64-bit still uses the x87, not SSE2. It also needed a precision fix in `Weblib.Start` to get JS arithmetic right.

### Fixed limits and small sharp edges
- `X509.MAX_ROOTS` is 16, so the browser has to retry HTTPS connections through its 118 root certificates in sets.
- Limits of 4,096 bytes of locals per method and 16,384 elements per fixed array.
- The heap's `FindFree` is a linear scan. A string test took 92 seconds until weblib added its own slab allocator, and then took 1 second.
- A `.philib` stores files by bare name (`Compiler/Phi.Compiler/Libraries/InterfaceWriter.cs:23`). `html/parser.phi` and `js/parser.phi` silently overwrite each other, and the error only appears later, in the program using the library.
- NASM's default optimizer took 258 s against 3 s with `-O1`, for a 3.5% smaller program, and nothing tells you this.
- An uncaught null pointer exited silently with `0xC0000005`, though the reference says it prints the error and ends with -1.
- `docs/phi-for-c-programmers.md` has gone stale in at least two places (see the appendix).

## What I'd change

In order of value for effort.

### Do first: small and high value

1. **Allow the return type in the header.** Interfaces already have this syntax, so it's an extension of the language, not something new. Then make a pointer narrowing to 32 bits an error unless `as` is written.
   ```phi
   # proposed; today this form only works in an interface
   [Make: : ptr<Node>]
       ...
   [end: node]
   ```
2. **Close the grammar holes.** Make `(F: x).field` and `not (s.M: x)` work, and let expressions continue on the next line inside parentheses.
3. **Catch stack overflow.** Give it a guard page and report it as an ordinary `ErrorKind`. If it can't be recovered on some target, at least print a message there, and do the same for the silent null pointer.
4. **Key `.philib` files by relative path.** About one line.
5. **Default to `-O1` for development builds**, and keep the full pass for release.
6. **Make `str` truncation visible.** Throw on overflow, and offer an explicit cut for the cases that want it.
7. **Fix the stale docs**, ideally by compiling their examples in `phi test`, as `patterns.md` already does.

### Do next: medium

8. **Add a jump table for dense `when`.** It's a contained change in the generator, and every interpreter and parser gains from it.
9. **Add `span<T>`, a checked pointer and length.** This is the most important single addition, because it moves safety to where the code actually is. Passing `span<u8>` instead of `ptr<u8>` with a separate `int` would have covered a large part of weblib, and it fits PHI's existing bounds errors.
   ```phi
   # proposed
   [Parse: span<u8> input;]
       chr c: input:i;      # checked, as an array is; unsafe turns it off
   [end]
   ```
10. **Allow optional commas in argument lists**, with a formatter that adds them when any argument is an expression. This keeps the clean look for `call Move: x y;` and makes the `layout.phi` line readable.
11. **Use SSE2 for floating point on 64-bit.** It removes the need for the x87 precision fix and is faster.
12. **Replace the heap's linear scan** with size-class free lists. Every program benefits, and libraries stop writing their own.
13. **Make the fixed limits growable where nothing needs them fixed**, starting with `MAX_ROOTS`.
14. **Make keywords contextual where the grammar allows it.** `at`, `in`, `out`, `log` and `into` could be usable names without ambiguity in most positions.

### Do later: large

15. **Register allocation.** Even a simple linear-scan allocator for locals should close much of the gap. Keep the source-line listing, since readability is one of PHI's selling points.
16. **Simple generics** for containers, ideally just compile-time substitution for types and no more. It's what would make `Map` and `List` useful in 64-bit code.
17. **Method values that carry a pointer**, which removes most of the need for class-variable state and opens the door to threads in libraries.

## What I'd leave alone

- **`is` for assignment and comparison.** It reads well, position makes the meaning clear, and the compiler warns on the risky case (`a is b is c`).
- **`;;` and `[end]`.** Clear and easy to parse, with no brace-matching problems.
- **One comparison per expression, and PHI's operator precedence.** Both remove real C bugs.
- **`call` as a statement.** Slightly wordy, but it makes the grammar simple and the code easy to scan.
- **The throw and catch model, the `.asm` listing and the helpful error messages.** These are what make PHI distinctive. Any change above should protect them.

## Appendix: behaviour re-tested

All built for `windows64` with the current compiler. The sources are throwaway files and aren't in this project.

| Test | Result |
|---|---|
| `return ptr;` in a method ending `[end: 0]` | Builds with a warning. It ran correctly here because the address happened to fit in 32 bits. |
| `(Get).v` | Error: `expected a value but found '.'` |
| `not (s.Ok: 0)` | Error: `S.Ok takes 1 argument but was given 2`, plus a misleading pointer warning |
| `ptr<B> b: a;` where `a` is a `ptr<N>` | Warning only |
| `ptr<A> a: 0; log a.v` with no catch | Exits with `0xC0000005` and prints nothing; `docs/language.md:829` says it should print the error and end with -1 |
| The same null pointer inside `if call ... throws e` | Caught, with the line number, and the program continues |
| Read after `free` | Runs without complaint and prints `0` |
| `ptr<u8> p: new u8[4]; p:100 is 9;` | Runs without complaint |
| `u8 a[4]; a:i is 9` with `i` = 100 | `PHI: index out of range on line 6` |
| Runaway recursion inside `if call ... throws` | Process dies with `0xC00000FD`, no message, not caught |
| `str s: 'abc'; s is 'abcdefgh';` | Stores all 8 characters; `docs/phi-for-c-programmers.md:79` says it stores `abc` |
| `str s: [3]; s is 'abcdefgh';` | Silently stores `abc` |
| 70,000 appends to one `str` | Silently stops at 65,535 |
| `int got` declared in both `if` and `else` | Builds; `docs/phi-for-c-programmers.md:66` says it's an error. Using it after the blocks is a clear error. |
| `when` with 8 consecutive integers | 8 `cmp`/`je` pairs, no jump table |
| `f64` addition on `windows64` | `fld`/`faddp` (x87) |
| Sieve to 5,000,000, 20 rounds | PHI 642 ms, C# Release 353 ms, same answer (6,970,260) |
