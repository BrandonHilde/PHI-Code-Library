#!/usr/bin/env python3
"""Makes libs/web/js/builtins/intljs.phi from intl.js and intl_data.js in that folder: the script as PHI
text, which JsIntl runs when the engine starts (a library opens no files, so the script is in the code).

    python3 tools/web/make_intl.py           makes intljs.phi
    python3 tools/web/make_intl.py --data    first makes intl_data.js again, then intljs.phi

intl_data.js holds what the script needs to know and can't work out:
  - each time zone the IANA database names, with its rule now (a name that is only a link to another
    is written NAME=N, the others NAME:N): the POSIX TZ string that
    ends each compiled zone file (/usr/share/zoneinfo here, as macOS and Linux have it). The rule now
    is used for every date, so times long ago in a zone whose rules have changed can be an hour out.
  - how Latin letters with marks come apart (Unicode's canonical decompositions, from Python's
    unicodedata), so that the collator can sort "é" with "e" and tell them apart after.
"""
import os
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.join(ROOT, 'libs', 'web', 'js', 'builtins')
ZONEINFO = '/usr/share/zoneinfo'


def footer(name):
    data = open(os.path.join(ZONEINFO, name), 'rb').read()
    if not data.startswith(b'TZif'):
        return None
    return data.rstrip(b'\n').rsplit(b'\n', 1)[-1].decode('ascii')


def links():
    # names that are only other names for a zone (tzdata.zi's "L" lines); ECMA-402 lists "UTC" alone
    found = {'Etc/UTC', 'Etc/GMT'}
    for line in open(os.path.join(ZONEINFO, 'tzdata.zi')):
        if line.startswith('L '):
            found.add(line.split()[2])
    found.discard('UTC')
    return found


def zones():
    import zoneinfo
    names = sorted(zoneinfo.available_timezones())
    linked = links()
    rules = []
    index = {}
    pairs = []
    for name in names:
        if name in ('Factory', 'localtime', 'posixrules') or name.startswith('posix/') or name.startswith('right/'):
            continue
        rule = footer(name)
        if rule is None or rule == '':
            continue
        if rule not in index:
            index[rule] = len(rules)
            rules.append(rule)
        pairs.append('%s%s%d' % (name, '=' if name in linked else ':', index[rule]))
    return rules, pairs


def folds():
    # each character of Latin-1, Latin Extended-A and B and Latin Extended Additional that comes
    # apart into an ASCII letter and marks: the character, the letter, the marks
    out = []
    for cp in list(range(0xC0, 0x250)) + list(range(0x1E00, 0x1F00)):
        ch = chr(cp)
        d = unicodedata.normalize('NFD', ch)
        if len(d) < 2 or not ('A' <= d[0] <= 'Z' or 'a' <= d[0] <= 'z'):
            continue
        marks = d[1:]
        if any(unicodedata.combining(m) == 0 for m in marks):
            continue
        out.append(ch + d[0] + marks)
    return out


def js_string(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def make_data():
    rules, pairs = zones()
    fold = folds()
    lines = ['// Made by tools/web/make_intl.py --data: the time zones (from the IANA database, as',
             '// /usr/share/zoneinfo has it) and Latin letters with marks (from Unicode). Run that to remake it.',
             'var ZONE_RULES = [']
    for i in range(0, len(rules), 4):
        lines.append('  ' + ', '.join(js_string(r) for r in rules[i:i + 4]) + ',')
    lines.append('];')
    lines.append('var ZONE_NAMES = (')
    chunk = []
    size = 0
    for p in pairs:
        chunk.append(p)
        size += len(p) + 1
        if size > 90:
            lines.append('  "' + ' '.join(chunk) + ' " +')
            chunk = []
            size = 0
    lines.append('  "' + ' '.join(chunk) + '");')
    # each entry: the character, its letter, then its marks; entries end with "|"
    text = '|'.join(fold)
    lines.append('var FOLDS = (')
    for i in range(0, len(text), 60):
        lines.append('  ' + js_string(text[i:i + 60]) + ' +')
    lines.append('  "");')
    open(os.path.join(HERE, 'intl_data.js'), 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('intl_data.js: %d zones, %d rules, %d letters' % (len(pairs), len(rules), len(fold)))


def phi_text(line):
    # PHI's text is bytes: anything past ASCII is written as \u escapes for the script to read
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


def make_phi():
    script = open(os.path.join(HERE, 'intl.js'), encoding='utf-8').read().split('\n')
    data = open(os.path.join(HERE, 'intl_data.js'), encoding='utf-8').read().split('\n')
    lines = []
    for line in script:
        if line.strip() == '// @data':
            lines += data
        else:
            lines.append(line)
    out = ['# Made by tools/web/make_intl.py from intl.js and intl_data.js: change those, then run it.',
           '', 'phi.JsIntlJs:Library', '{', '\t[Source: : str]', "\t\tstr js: '';"]
    count = 0
    # a few long pieces, not a statement a line: each statement is code, and 3,500 of them were most
    # of what this added to a program
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
    open(os.path.join(HERE, 'intljs.phi'), 'w').write('\n'.join(out))
    print('intljs.phi: %d lines, %d bytes of script' % (len(out), count))


if '--data' in sys.argv:
    make_data()
make_phi()
