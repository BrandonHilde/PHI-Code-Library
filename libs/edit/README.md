# editlib

Text being edited, for any program with somewhere to type: a line to type a name in, a notes
program, a code editor. It keeps the text, the caret and what's selected; it moves by characters,
words and lines; it types, deletes, undoes and redoes, and finds. It draws nothing and reads no
keys, so it works the same in a window, in a terminal or in a kernel: the program turns its own
keys and clicks into the calls below, and draws the text however it draws text. It depends on no
other library here.

```phi
use editlib;

call EditLib.Start;
ptr<EdText> t: (Ed.New: 262144);            # at most 256 KB of text (0: Ed.MOST, 64 MB)
call t.Set: bytes length;                   # what a file had: the caret at the start, nothing to undo
call t.Typed: 'a';                          # a character by its number, in place of what's selected
call t.WordRight: true;                     # the caret past the next word, selecting (Shift held)
u8 copied[256];
int n: (t.CopySelection: addr copied 256);  # what's selected, for a clipboard
call t.Insert: pasted pasted_length;        # pasted, in place of what's selected
call t.Undo;
ptr<u8> all: (t.Contents);                  # all of it in one piece, a zero after it: to save or draw
call Ed.Free: t;
```

## API

These names are the API. Everything else (`EdText`'s fields other than those listed, its methods
not listed, and `Ed`'s step constants) is how it works, and may change.

| Name | What it is |
|---|---|
| `EditLib.Start` | Call once, before anything else. `EditLib.VERSION` is 1 |
| `Ed.New: most` → `ptr<EdText>` | Empty text that may grow to `most` bytes (0 or more than `Ed.MOST`: `Ed.MOST`, 64 MB). 0 if there's no memory, with the reason in `Ed.error` |
| `Ed.NewLine: most` → | The same, for one line: a new line can't be typed, and in what's put in each is a space (a `\r\n` is one), as are tabs and the other bytes below 32 |
| `Ed.Free: t` | Gives it back (0 is allowed) |
| `Ed.IsWord: c` →, `Ed.Encode: code bytes` → | What counts as part of a word (letters, digits, `_`, and anything past ASCII); a character as UTF-8 into 4 bytes, how many it took (0 for a number that's no character) |

**What's there.** `Length` →, `At: pos` → (a byte; 0 outside), `Contents` → (all of it in one piece
with a zero after it, good until the next change), `CopyOut: from n dest`, `Lines` →, `LineOf: pos` →,
`StartOf: line` → (-1 for no such line), `LineStart: pos` →, `LineEnd: pos` → (at its `\n`),
`Column: pos` → (characters from the line's start), `PosAt: line column` → (the line's end if it's
shorter). Fields to read: `caret`, `anchor` (where what's selected begins), `changed` (since `Set`
or `Saved`), `one_line`.

**What's selected** is between `anchor` and `caret`. `HasSelection` →, `SelectionStart` →,
`SelectionEnd` →, `Selected` → (its length), `CopySelection: dest size` → (as much as fits, ending
on a whole character), `Select: from to`, `SelectAll`, `SelectWord: pos` (a double click),
`SelectLine: pos` (a triple click).

**Moving.** Each takes `extend`: true grows or shrinks what's selected to the caret (Shift held),
false leaves nothing selected. `MoveTo: pos`, `Left`, `Right` (with something selected and not
extending, to its start or end), `WordLeft`, `WordRight` (past the word and what follows it on the
line), `ToLineStart`, `ToLineEnd`, `ToStart`, `ToEnd`, `Vertical: rows` (down, or up below 0,
keeping to the column it started from, as a text editor's arrows do).

**Changing it.** Each takes what's selected away first, is one action for `Undo`, and answers
false when it did nothing (for `Insert` and `Typed`, when not all of it fit under `most`; what does
fit goes in, ending on a whole character). `Insert: bytes n`, `Typed: code`, `Backspace: word`,
`Delete: word` (with `word` true, to the start or end of a word, as Ctrl does), `DeleteSelection`,
`Set: bytes n` (the whole text, with nothing to undo and `changed` false), `Saved` (`changed` false).

**Undoing.** `Undo` →, `Redo` →, `CanUndo` →, `CanRedo` →, `Break` (the next change is an action of
its own). Characters typed one after another are one action to each word, and so are Backspaces or
Deletes one after another, so `Undo` takes back a word at a time, and the caret and what was
selected come back as they were. `undo_most` (a field, 1 MB unless it's set; 0 keeps nothing) is the
most bytes of history kept: the oldest actions go past it. With no memory for more history it's
forgotten, and the change is still made.

**Finding.** `Find: needle n from any_case` → and `FindBack: needle n before any_case` → (-1 if it
isn't there). `any_case` matches ASCII letters in either case.

## How it works

A gap buffer: the text before the gap at the start of the buffer and the text after it at the end,
with room between, so typing costs the same however long the text is, and moving the caret far
moves the bytes in between once. `LineOf` starts from its last answer, so asking about nearby
places (as drawing a screenful does) doesn't count from the top each time. A history is a list of
steps, each a run of bytes put in or taken out at a place, with the action it belongs to.

Positions are bytes, and the caret never stops inside a character: moves go by whole UTF-8
characters (a byte that isn't one is a character of its own). A column counts characters, and what
a character looks like (its width, whether it joins the next) is the program's business.

**One thread at a time** for each `EdText`; `Ed.error` is shared.

## How it's checked

There's no outside suite for an editor's behaviour, so the tests write out the text, the caret and
what's selected after each action (`test_edit.phi`), and every line of the expected output was read
and worked out by hand: moves, undo by words, typing over a selection, lines and columns, finding,
UTF-8, one-line text and its limit, 20,000 characters typed and undone, and a short history.
`tests/use/test_editlib.phi` uses `editlib.philib` alone.
