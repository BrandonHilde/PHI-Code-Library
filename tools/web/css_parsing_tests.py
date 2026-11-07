#!/usr/bin/env python3
# Turns the JSON of css-parsing-tests (libs/web/tests/css-parsing-tests/*.json, data only) into a text
# form a PHI test can read without a JSON parser: tests/css-parsing-tests/converted/NAME.txt, one
# case a line, input TAB expected, each with bytes outside printable ASCII written \xNN. The expected
# side is the canonical text test_css_syntax.phi prints for what it parsed.
#
#   python tools/web/css_parsing_tests.py

import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, '..', '..', 'libs', 'web', 'tests', 'css-parsing-tests')
OUT = os.path.join(ROOT, 'converted')

def esc(data):
    out = []
    for b in data:
        if 32 <= b < 127 and b != 92:
            out.append(chr(b))
        else:
            out.append(chr(92) + 'x%02X' % b)
    return ''.join(out)

def text(s):
    # lone surrogates can't occur in these files' strings as data for us; keep them lossless if so
    return s.encode('utf-8', 'surrogatepass')

def number(v):
    if isinstance(v, int) or (isinstance(v, float) and v == int(v) and abs(v) < 1e15):
        return str(int(v))
    r = '%.6g' % v
    if 'e' in r:
        r = format(float(r), 'f').rstrip('0').rstrip('.')
    return r

def canon(x):
    if x is None:
        return 'null'
    if x is True:
        return 'true'
    if x is False:
        return 'false'
    if isinstance(x, (int, float)):
        return number(x)
    if isinstance(x, str):
        return '"' + esc_quoted(x) + '"'
    return '[' + ','.join(canon(i) for i in x) + ']'

def esc_quoted(s):
    out = []
    for b in text(s):
        if 32 <= b < 127 and b != 92 and b != 34:
            out.append(chr(b))
        else:
            out.append(chr(92) + 'x%02X' % b)
    return ''.join(out)

def main():
    os.makedirs(OUT, exist_ok=True)
    total = 0
    for name in sorted(os.listdir(ROOT)):
        if not name.endswith('.json') or name == 'stylesheet_bytes.json':
            continue
        with open(os.path.join(ROOT, name), encoding='utf-8') as f:
            data = json.load(f)
        lines = []
        for i in range(0, len(data), 2):
            source, expected = data[i], data[i + 1]
            lines.append(esc(text(source)) + '\t' + esc(text(canon(expected))))
        path = os.path.join(OUT, name[:-5].replace('+', '_') + '.txt')
        with open(path, 'w', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')
        total += len(lines)
        print(name, len(lines))
    print('total', total)

main()
