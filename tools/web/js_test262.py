#!/usr/bin/env python3
"""Runs test262 through weblib's JS engine, and adds up the results by area and by cause.

    python tools/web/js_test262.py language/expressions language/statements    (from the repository root)
    python tools/web/js_test262.py --all
    python tools/web/js_test262.py built-ins/Math --out report.txt

An argument is a folder under test262's test/ (or a single file). It builds nothing: build the runner
first, from libs/web: `phi build test_js262.phi --target windows64` (or linux64). test262 itself
isn't in git: tools/web/fetch_test262.py fetches it, at the commit the README's results are from.

Each batch of tests is one run of the program, so a crash costs only that batch's tail: the test it
stopped on is counted as CRASH (and which it was is in the report), and the next batch starts after
it. Test files are data: they only ever go through the engine. Nothing here reads them except to list
their paths.
"""
import argparse
import collections
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
WEBLIB = os.path.normpath(os.path.join(HERE, '..', '..', 'libs', 'web'))
TEST262 = os.path.join(WEBLIB, 'tests', 'test262')
# where `phi build test_js262.phi --target windows64` (or linux64) puts it
EXE = os.path.join(WEBLIB, 'build', 'test_js262', 'test_js262' + ('.exe' if os.name == 'nt' else ''))


def list_tests(args):
    found = []
    for a in args:
        root = os.path.join(TEST262, 'test', a)
        if os.path.isfile(root):
            found.append(root)
            continue
        for d, _, files in os.walk(root):
            for f in files:
                if f.endswith('.js') and not f.endswith('_FIXTURE.js'):
                    found.append(os.path.join(d, f))
    found.sort()
    return found


def run_batch(paths, exe, timeout):
    """Returns {path: (status, cause)}, for each path, crash or no crash."""
    results = {}
    pending = list(paths)
    harness = os.path.join(TEST262, 'harness')
    while pending:
        fd, listfile = tempfile.mkstemp(suffix='.txt', prefix='js262')
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(pending) + '\n')
        try:
            p = subprocess.run([exe, listfile, harness], cwd=WEBLIB, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=timeout * len(pending) + 30)
            out = p.stdout.decode('latin-1', 'replace')
            crashed = p.returncode != 0
            tail = out[-300:]
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or b'').decode('latin-1', 'replace')
            crashed = True
            tail = 'timeout'
        finally:
            os.unlink(listfile)
        done = 0
        for line in out.splitlines():
            m = re.match(r'R (PASS|FAIL|SKIP|MISSING) (\S+) ?(.*)$', line)
            if m:
                results[m.group(2)] = (m.group(1), m.group(3))
                done += 1
        pending = [q for q in pending if q not in results]
        if pending:
            # the one it stopped on is what crashed it
            results[pending[0]] = ('CRASH', 'exit %s' % (tail.strip().splitlines()[-1] if tail.strip() else 'nothing printed'))
            pending = pending[1:]
    return results


def cause_key(cause):
    """A failure's cause with what varies taken out, to count them."""
    c = re.sub(r"\(line \d+\)", '', cause)
    c = re.sub(r'Expected SameValue.*', 'assertion: SameValue', c)
    c = re.sub(r'Expected a (\w+) to be thrown.*', r'assertion: expected a \1', c)
    c = re.sub(r"'[^']*'", "'..'", c)
    c = re.sub(r'\d+', 'N', c)
    return c[:100]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('paths', nargs='*', help='folders under test262/test (default: language)')
    ap.add_argument('--all', action='store_true', help='everything that is checked out')
    ap.add_argument('--exe', default=EXE)
    ap.add_argument('--jobs', type=int, default=os.cpu_count() or 4)
    ap.add_argument('--batch', type=int, default=150)
    ap.add_argument('--timeout', type=int, default=20, help='seconds allowed per test')
    ap.add_argument('--out', help='also write the report here')
    ap.add_argument('--fails', help='write every failure, one a line, to this file')
    ap.add_argument('--depth', type=int, default=2, help='how many folder levels to report by')
    ap.add_argument('--causes', type=int, default=40, help='how many causes to show')
    a = ap.parse_args()
    args = a.paths or ['language']
    if a.all:
        args = ['']
    if not os.path.isdir(os.path.join(TEST262, 'test')):
        sys.exit('test262 isn\'t here (%s): python tools/web/fetch_test262.py fetches it' % TEST262)
    tests = list_tests(args)
    if not tests:
        sys.exit('no tests found under ' + TEST262)
    if not os.path.exists(a.exe):
        sys.exit('build it first, in libs/web: phi build test_js262.phi --target %s  (no %s)'
                 % ('windows64' if os.name == 'nt' else 'linux64', a.exe))
    batches = [tests[i:i + a.batch] for i in range(0, len(tests), a.batch)]
    results = {}
    lock = threading.Lock()
    started = time.time()
    with ThreadPoolExecutor(a.jobs) as pool:
        for r in pool.map(lambda b: run_batch(b, a.exe, a.timeout), batches):
            with lock:
                results.update(r)
                print('\r%d of %d' % (len(results), len(tests)), end='', file=sys.stderr, flush=True)
    print('', file=sys.stderr)

    root = os.path.join(TEST262, 'test')
    areas = collections.defaultdict(collections.Counter)
    causes = collections.Counter()
    examples = {}
    lines = []
    for path, (status, cause) in sorted(results.items()):
        rel = os.path.relpath(path, root).replace(os.sep, '/')
        parts = rel.split('/')
        area = '/'.join(parts[:a.depth]) if len(parts) > a.depth else '/'.join(parts[:-1])
        areas[area][status] += 1
        areas['TOTAL'][status] += 1
        if status in ('FAIL', 'CRASH'):
            k = cause_key(cause) if status == 'FAIL' else 'CRASH ' + cause[:60]
            causes[k] += 1
            examples.setdefault(k, rel)
            lines.append('%s %s %s' % (status, rel, cause))
    rows = ['%-45s %7s %7s %7s %7s %7s' % ('area', 'pass', 'fail', 'crash', 'skip', '%')]
    for area in sorted(areas, key=lambda x: (x == 'TOTAL', x)):
        c = areas[area]
        ran = c['PASS'] + c['FAIL'] + c['CRASH']
        pct = 100.0 * c['PASS'] / ran if ran else 0.0
        rows.append('%-45s %7d %7d %7d %7d %6.1f%%' % (area, c['PASS'], c['FAIL'], c['CRASH'], c['SKIP'], pct))
    rows.append('')
    rows.append('causes of failure, most common first:')
    for k, n in causes.most_common(a.causes):
        rows.append('%6d  %s    [%s]' % (n, k, examples[k]))
    rows.append('')
    rows.append('%d tests in %.0f s' % (len(results), time.time() - started))
    report = '\n'.join(rows)
    print(report)
    if a.out:
        with open(a.out, 'w', encoding='utf-8', newline='\n') as f:
            f.write(report + '\n')
    if a.fails:
        with open(a.fails, 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
