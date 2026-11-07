#!/usr/bin/env python3
"""Fetches test262 into libs/web/tests/test262, at the commit weblib's results were measured against.

    python tools/web/fetch_test262.py

It's 217 MB, which is why it isn't in git. Only tools/web/js_test262.py uses it: `phi test` doesn't,
since test_js262's self-test has its own copy of the three harness files it needs. Running this again
leaves a checkout that's already at the commit alone, and moves one that isn't.
"""
import os
import subprocess
import sys

COMMIT = 'd11543772591a5c24b3229e6195a74c73e56032e'   # 2026-11-04, the one weblib's README reports on
URL = 'https://github.com/tc39/test262'

HERE = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.normpath(os.path.join(HERE, '..', '..', 'libs', 'web', 'tests', 'test262'))


def git(*args):
    subprocess.run(['git', '-C', DEST] + list(args), check=True)


def main():
    if os.path.isdir(os.path.join(DEST, '.git')):
        head = subprocess.run(['git', '-C', DEST, 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
        if head == COMMIT:
            print('test262 is already at %s, in %s' % (COMMIT[:12], DEST))
            return
    elif os.path.exists(DEST) and os.listdir(DEST):
        sys.exit('%s has something in it that isn\'t a git checkout: move it, then run this again' % DEST)
    else:
        os.makedirs(DEST, exist_ok=True)
        git('init', '-q')
        git('remote', 'add', 'origin', URL)
    # just the one commit, with no history
    git('fetch', '-q', '--depth', '1', 'origin', COMMIT)
    git('checkout', '-q', '--detach', 'FETCH_HEAD')
    print('test262 is at %s, in %s' % (COMMIT[:12], DEST))


if __name__ == '__main__':
    main()
