#!/usr/bin/env python3
"""Makes libs/web/page/observersjs.phi from libs/web/page/observers.js: the script as PHI text, which
PageObservers runs in each page (a library opens no files, so the script is in the code).

    python3 tools/web/make_observers.py
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
page = os.path.join(ROOT, 'libs', 'web', 'page')
lines = open(os.path.join(page, 'observers.js')).read().split('\n')
out = ['# Made by tools/web/make_observers.py from observers.js: change that, then run it.',
       '', 'phi.PageObserversJs:Library', '{', '\t[Source: : str]', "\t\tstr js: '';"]
for line in lines:
    code = line.split('//')[0].rstrip() if line.lstrip().startswith('//') else line.rstrip()
    if not code.strip():
        continue
    code = code.strip()
    text = code.replace('\\', '\\\\').replace("'", "\\'")
    out.append("\t\tjs++ '%s\\n';" % text)
out += ['\t[end: js]', '}', '']
open(os.path.join(page, 'observersjs.phi'), 'w').write('\n'.join(out))
print('observersjs.phi:', len(out), 'lines')
