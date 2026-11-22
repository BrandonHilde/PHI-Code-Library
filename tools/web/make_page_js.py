#!/usr/bin/env python3
"""Makes libs/web/page/NAMEjs.phi from libs/web/page/NAME.js: the script as PHI text, which the page
runs in each page (a library opens no files, so the script is in its code), as phi.Page<Name>Js.Source.

    python3 tools/web/make_page_js.py elements

(observers.js has its own, make_observers.py, which does the same.)
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from js_to_phi import phi_text

page = os.path.join(ROOT, 'libs', 'web', 'page')
name = sys.argv[1]
lines = open(os.path.join(page, name + '.js'), encoding='utf-8').read().split('\n')
out = ['# Made by tools/web/make_page_js.py %s from %s.js: change that, then run it.' % (name, name),
       '', 'phi.Page%sJs:Library' % name.capitalize(), '{', '\t[Source: : str]', "\t\tstr js: '';"]
piece = ''
for line in lines:
    code = line.strip()
    if not code or code.startswith('//'):
        continue
    piece += phi_text(code) + '\\n'
    if len(piece) > 2000:
        out.append("\t\tjs++ '%s';" % piece)
        piece = ''
if piece:
    out.append("\t\tjs++ '%s';" % piece)
out += ['\t[end: js]', '}', '']
open(os.path.join(page, name + 'js.phi'), 'w').write('\n'.join(out))
print('%sjs.phi: %d lines' % (name, len(out)))
