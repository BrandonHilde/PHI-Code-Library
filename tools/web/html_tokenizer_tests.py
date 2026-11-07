#!/usr/bin/env python3
"""Turns html5lib's tokenizer tests (JSON) into a flat form test_html5lib.phi reads.

    python -I tools/html_tokenizer_tests.py

Reads libs/web/tests/html5lib/tokenizer/*.test and writes libs/web/tests/html5lib/tokenizer-flat/*.txt.
The files are data and are only parsed. Every string is written as hex, so a test's bytes survive
as they are, and the line format needs no escaping:

    T <state> <last start tag, or -> <input>      a test, one per initial state
    C <text>                                      a character token (neighbours merged)
    M <text>                                      a comment
    S <name> <0 or 1, self-closing> [<name> <value>]...
    E <name>
    D <name or -> <public or -> <system or -> <0 or 1, correct>
    P <target> <data>                             a processing instruction
    .                                             the end of a test

An empty string is written as "=", and a missing one as "-".

The tests that need a lone surrogate in the input can't be run against a parser whose input is
UTF-8, where there's no way to write one. The parser's own input is decoded bytes: a surrogate can
only be there as bad UTF-8, which is U+FFFD. So they're counted here and left out, and
tokenizer-flat/SKIPPED.txt says which.
"""
import glob
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "..", "libs", "web", "tests", "html5lib", "tokenizer")
OUT = os.path.join(HERE, "..", "..", "libs", "web", "tests", "html5lib", "tokenizer-flat")


def hx(text):
    if text is None:
        return "-"
    if text == "":
        return "="
    return text.encode("utf-8", "surrogatepass").hex()


def unescape(text):
    """A doubleEscaped test's strings have \\uXXXX still in them, for what JSON can't carry."""
    return re.sub(r"\\u([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), text)


def has_surrogate(text):
    return text is not None and any(0xD800 <= ord(c) <= 0xDFFF for c in text)


STATES = {
    "Data state": "DATA",
    "PLAINTEXT state": "PLAINTEXT",
    "RCDATA state": "RCDATA",
    "RAWTEXT state": "RAWTEXT",
    "Script data state": "SCRIPT",
    "CDATA section state": "CDATA",
}


def strings_of(token):
    for part in token[1:]:
        if isinstance(part, str):
            yield part
        elif isinstance(part, dict):
            for k, v in part.items():
                yield k
                yield v


def main():
    os.makedirs(OUT, exist_ok=True)
    skipped = []
    totals = 0
    for path in sorted(glob.glob(os.path.join(SRC, "*.test"))):
        name = os.path.basename(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        tests = data.get("tests")
        if tests is None:
            # xmlViolation.test: for coercing to XML, which isn't an HTML parser's job
            skipped.append("%s: no 'tests' list (keys %s)" % (name, ",".join(data.keys())))
            continue
        lines = []
        for index, t in enumerate(tests):
            text = t["input"]
            output = t["output"]
            if t.get("doubleEscaped"):
                text = unescape(text)
                fixed = []
                for token in output:
                    new = [token[0]]
                    for part in token[1:]:
                        new.append(unescape(part) if isinstance(part, str) else part)
                    fixed.append(new)
                output = fixed
            if has_surrogate(text) or any(has_surrogate(s) for tok in output for s in strings_of(tok)):
                skipped.append("%s #%d: lone surrogate: %s" % (name, index, t["description"]))
                continue
            merged = []
            for token in output:
                if token[0] == "Character" and merged and merged[-1][0] == "Character":
                    merged[-1] = ["Character", merged[-1][1] + token[1]]
                else:
                    merged.append(list(token))
            for state in t.get("initialStates", ["Data state"]):
                last = t.get("lastStartTag")
                lines.append("T %s %s %s" % (STATES[state], hx(last) if last else "-", hx(text)))
                totals += 1
                for token in merged:
                    kind = token[0]
                    if kind == "Character":
                        lines.append("C " + hx(token[1]))
                    elif kind == "Comment":
                        lines.append("M " + hx(token[1]))
                    elif kind == "StartTag":
                        selfclosing = len(token) > 3 and token[3]
                        parts = ["S", hx(token[1]), "1" if selfclosing else "0"]
                        attrs = token[2] if len(token) > 2 else {}
                        for k in sorted(attrs, key=lambda s: s.encode("utf-8", "surrogatepass")):
                            parts += [hx(k), hx(attrs[k])]
                        lines.append(" ".join(parts))
                    elif kind == "EndTag":
                        lines.append("E " + hx(token[1]))
                    elif kind == "DOCTYPE":
                        lines.append("D %s %s %s %s" % (hx(token[1]), hx(token[2]), hx(token[3]), "1" if token[4] else "0"))
                    elif kind == "ProcessingInstruction":
                        lines.append("P %s %s" % (hx(token[1]), hx(token[2])))
                    else:
                        raise SystemExit("unknown token kind " + kind)
                lines.append(".")
        out_name = name.replace(".test", ".txt")
        with open(os.path.join(OUT, out_name), "w", newline="\n") as f:
            f.write("\n".join(lines) + "\n")
    with open(os.path.join(OUT, "SKIPPED.txt"), "w", newline="\n", encoding="ascii", errors="backslashreplace") as f:
        f.write("\n".join(skipped) + "\n")
    print("%d runs written, %d left out" % (totals, len(skipped)))


if __name__ == "__main__":
    main()
