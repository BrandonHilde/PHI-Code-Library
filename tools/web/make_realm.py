#!/usr/bin/env python3
"""Writes libs/web/page/realm.phi: PageRealm, which keeps each page's own JS classes, prototypes and
symbols when another page is used (Page.Use).

Each page has its own JS runtime, and what the page code makes in it at Install (PageBind's node
classes and prototypes, PageEvents', PageCanvas' ...) is held in program fields, which there is one
of for all pages. So when pages live side by side (an iframe's page beside the window's), Page.Use
saves the fields into the page it leaves and loads those of the page it goes to, as Js.Use does for
the runtime itself.

The fields are found here: every program-level ptr<JsObj>, ptr<JsClass> or ptr<JsSym> in
libs/web/page/*.phi. Run this after adding or removing one:  python3 tools/web/make_realm.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGE = os.path.join(ROOT, 'libs', 'web', 'page')
OUT = os.path.join(PAGE, 'realm.phi')
FIELD = re.compile(r'^\t(ptr<(JsObj|JsClass|JsSym)>) ([a-z_0-9]+)(: [^;]*)?;')
LIST = re.compile(r'^\t(ptr<(JsObj|JsClass|JsSym)>) ([a-z_0-9]+)\[atmost (\d+)\];')
PROGRAM = re.compile(r'^phi\.([A-Za-z0-9_]+):')


def fields():
    found = []
    for name in sorted(os.listdir(PAGE)):
        if not name.endswith('.phi') or name == 'realm.phi' or name.endswith('js.phi'):
            continue
        program = None
        for line in open(os.path.join(PAGE, name), encoding='utf-8'):
            m = PROGRAM.match(line)
            if m:
                program = m.group(1)
                continue
            if program is None:
                continue
            m = FIELD.match(line)
            if m:
                found.append((program, m.group(3), m.group(1), 0))
                continue
            m = LIST.match(line)
            if m:
                found.append((program, m.group(3), m.group(1), int(m.group(4))))
    return found


def main():
    fs = fields()
    room = int(re.search(r'const int REALM_ROOM: (\d+);', open(os.path.join(PAGE, 'page.phi'), encoding='utf-8').read()).group(1))
    slots = sum(1 + n for _, _, _, n in fs)
    if slots > room:
        print('make_realm: %d slots, but Page.realm has room for %d: make Page.REALM_ROOM (and Page.realm) bigger' % (slots, room))
        return 1
    out = []
    out.append('# Made by tools/web/make_realm.py: don\'t change it by hand, run that after adding or removing a')
    out.append('# program-level ptr<JsObj>, ptr<JsClass> or ptr<JsSym> (or a list of them) in page/*.phi.')
    out.append('#')
    out.append('# Each page\'s own JS classes, prototypes and symbols (made in its runtime at Install, held in')
    out.append('# program fields there\'s one of for all pages): saved into the page Page.Use leaves (Page.realm)')
    out.append('# and loaded from the one it goes to, so pages side by side (an iframe\'s and the window\'s)')
    out.append('# don\'t use each other\'s.')
    out.append('')
    out.append('use page.page;')
    out.append('')
    out.append('phi.PageRealm:Library')
    out.append('{')
    out.append('\tconst int SLOTS: %d;         # (Page.realm has room for Page.REALM_ROOM)' % slots)
    out.append('')
    save, load, clear = [], [], []
    at = 0
    for prog, name, kind, n in fs:
        if n == 0:
            save.append('\t\tr:%d is %s.%s as u64;' % (at, prog, name))
            load.append('\t\t%s.%s is r:%d as %s;' % (prog, name, at, kind))
            clear.append('\t\t%s.%s is 0 as %s;' % (prog, name, kind))
            at += 1
            continue
        # a list: how many, then each (room for all it can hold)
        save.append('\t\tr:%d is %s.%s.len as u64;' % (at, prog, name))
        save.append('\t\twhile u32 i: 0; i < %s.%s.len; i++;' % (prog, name))
        save.append('\t\t\tr:(%d + i) is %s.%s:i as u64;' % (at + 1, prog, name))
        save.append('\t\t;;')
        load.append('\t\t%s.%s.len is r:%d as u32;' % (prog, name, at))
        load.append('\t\twhile u32 i: 0; i < %s.%s.len; i++;' % (prog, name))
        load.append('\t\t\t%s.%s:i is r:(%d + i) as %s;' % (prog, name, at + 1, kind))
        load.append('\t\t;;')
        clear.append('\t\t%s.%s.len is 0;' % (prog, name))
        at += 1 + n
    out.append('\t[Save: ptr<Page> p: 0;]')
    out.append('\t\tptr<u64> r: addr p.realm:0;')
    out += save
    out.append('\t[end]')
    out.append('')
    out.append('\t[Load: ptr<Page> p: 0;]')
    out.append('\t\tptr<u64> r: addr p.realm:0;')
    out += load
    out.append('\t[end]')
    out.append('')
    out.append('\t# a new page\'s: none yet (its Install makes them)')
    out.append('\t[Clear]')
    out += clear
    out.append('\t[end]')
    out.append('}')
    out.append('')
    open(OUT, 'w', encoding='utf-8').write('\n'.join(out))
    print('realm.phi: %d fields and lists, %d slots' % (len(fs), slots))
    return 0


if __name__ == '__main__':
    sys.exit(main())
