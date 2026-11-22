#!/usr/bin/env python3
"""Makes a builtin written in JavaScript into PHI text a library can hold (a library opens no files, so a
script it runs is in its code). For libs/web/js/builtins/NAME.js:

    python3 tools/web/js_to_phi.py NAME      makes NAME + js.phi there, with phi.Js<Name>Js.Source

make_intl.py uses the same, for intl.js and its data.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.join(ROOT, 'libs', 'web', 'js', 'builtins')


def phi_text(line):
    # PHI's text is bytes: anything past ASCII is written as \\u escapes for the script to read
    out = []
    for ch in line:
        if ord(ch) < 128:
            out.append(ch)
        elif ord(ch) < 0x10000:
            out.append('\\u%04x' % ord(ch))
        else:
            v = ord(ch) - 0x10000
            out.append('\\u%04x\\u%04x' % (0xD800 + (v >> 10), 0xDC00 + (v & 0x3FF)))
    return ''.join(out).replace('\\', '\\\\').replace("'", "\\'")


def make(lines, out_name, library, made_from):
    """lines: the script's lines. Comments on lines of their own and blank lines are left out."""
    out = ['# Made by tools/web/%s: change those, then run it.' % made_from,
           '', 'phi.%s:Library' % library, '{', '\t[Source: : str]', "\t\tstr js: '';"]
    count = 0
    # a few long pieces, not a statement a line: each statement is code, and 3,500 of them were most
    # of what Intl added to a program
    piece = ''
    for line in lines:
        code = line.strip()
        if not code or code.startswith('//'):
            continue
        piece += phi_text(code) + '\\n'
        count += len(code) + 1
        if len(piece) > 2000:
            out.append("\t\tjs++ '%s';" % piece)
            piece = ''
    if piece:
        out.append("\t\tjs++ '%s';" % piece)
    out += ['\t[end: js]', '}', '']
    open(os.path.join(HERE, out_name), 'w').write('\n'.join(out))
    print('%s: %d lines, %d bytes of script' % (out_name, len(out), count))


if __name__ == '__main__':
    name = sys.argv[1]
    lines = open(os.path.join(HERE, name + '.js'), encoding='utf-8').read().split('\n')
    make(lines, name + 'js.phi', 'Js%sJs' % name.capitalize(), 'js_to_phi.py %s from %s.js' % (name, name))
