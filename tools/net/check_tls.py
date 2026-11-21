#!/usr/bin/env python3
"""netlib's TLS 1.2 client against OpenSSL's server (openssl s_server), on this computer.

    python3 tools/net/check_tls.py [--cases]

Makes a test root and certificates for phi.test (P-256, P-384 and RSA keys), builds tools/net/tlslive
for this computer with dist/netlib.philib (build.ps1 netlib first), and has it connect to s_server set up each way the client
must handle: every suite and curve it offers, each kind of signature, with and without the extended
master secret, a server asking for a client certificate, a large answer over many records; and the
ways it must refuse: the wrong name, an untrusted root, a server that speaks only TLS 1.3, and a
server that speaks TLS 1.3 answering TLS 1.2 to a client that fell back to it (RFC 8446's downgrade
mark). Each must end as it should, and an answer must be the bytes s_server sent.

With --cases, the exchanges (all but the large one) are written to libs/net/tests/tls/cases.bin,
which test_tls replays with no network: the same random bytes must make the same bytes to send, and
the server's bytes must give the same answer.

Needs OpenSSL 3 or later as `openssl` (Homebrew's on a Mac: /opt/homebrew/bin/openssl).
"""
import os, struct, subprocess, sys, tempfile, time, zlib, shutil

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PHI = os.environ.get('PHI_EXE', 'phi')
OPENSSL = shutil.which('openssl', path='/opt/homebrew/bin:' + os.environ.get('PATH', ''))
HOST = {'darwin': 'macos', 'linux': 'linux64'}.get(sys.platform, 'linux64')
PORT = 44400

def run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)

def make_certs(work):
    def key(kind, name):
        if kind == 'rsa':
            run([OPENSSL, 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048', '-out', name])
        else:
            run([OPENSSL, 'genpkey', '-algorithm', 'EC', '-pkeyopt', 'ec_paramgen_curve:' + kind, '-out', name])
    os.chdir(work)
    with open('ca.ext', 'w') as f:
        f.write('basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\n')
    with open('leaf.ext', 'w') as f:
        f.write('subjectAltName=DNS:phi.test\nbasicConstraints=CA:FALSE\n')
    for root, kind in (('root_ec', 'P-256'), ('root_rsa', 'rsa'), ('other', 'P-256')):
        key(kind, root + '.key')
        run([OPENSSL, 'req', '-x509', '-key', root + '.key', '-out', root + '.pem', '-days', '3650',
             '-subj', '/CN=PHI netlib test ' + root, '-extensions', 'v3_ca', '-addext', 'basicConstraints=critical,CA:TRUE'])
        run([OPENSSL, 'x509', '-in', root + '.pem', '-outform', 'DER', '-out', root + '.der'])
    for leaf, kind, root in (('p256', 'P-256', 'root_ec'), ('p384', 'P-384', 'root_ec'), ('rsa', 'rsa', 'root_rsa')):
        key(kind, leaf + '.key')
        run([OPENSSL, 'req', '-new', '-key', leaf + '.key', '-out', leaf + '.csr', '-subj', '/CN=phi.test'])
        run([OPENSSL, 'x509', '-req', '-in', leaf + '.csr', '-CA', root + '.pem', '-CAkey', root + '.key',
             '-CAcreateserial', '-out', leaf + '.pem', '-days', '3650', '-extfile', 'leaf.ext'])
    with open('big.bin', 'wb') as f:
        f.write(bytes((i * 7 + (i >> 9)) & 255 for i in range(300000)))

# (name, leaf, root, server options, name asked for, fallback, path, what must happen)
CASES = [
    ('ecdsa-aes-x25519', 'p256', 'root_ec', ['-tls1_2', '-cipher', 'ECDHE-ECDSA-AES128-GCM-SHA256', '-groups', 'X25519'], 'phi.test', 0, '/', 'ok'),
    ('ecdsa-chacha-x25519', 'p256', 'root_ec', ['-tls1_2', '-cipher', 'ECDHE-ECDSA-CHACHA20-POLY1305', '-groups', 'X25519'], 'phi.test', 0, '/', 'ok'),
    ('ecdsa-aes-p256', 'p256', 'root_ec', ['-tls1_2', '-cipher', 'ECDHE-ECDSA-AES128-GCM-SHA256', '-groups', 'P-256'], 'phi.test', 0, '/', 'ok'),
    ('ecdsa-aes-p384-curve', 'p256', 'root_ec', ['-tls1_2', '-groups', 'P-384'], 'phi.test', 0, '/', 'ok'),
    ('ecdsa-p384-sha384', 'p384', 'root_ec', ['-tls1_2', '-cipher', 'ECDHE-ECDSA-AES128-GCM-SHA256', '-sigalgs', 'ECDSA+SHA384'], 'phi.test', 0, '/', 'ok'),
    ('rsa-pss', 'rsa', 'root_rsa', ['-tls1_2', '-cipher', 'ECDHE-RSA-AES128-GCM-SHA256', '-sigalgs', 'rsa_pss_rsae_sha256'], 'phi.test', 0, '/', 'ok'),
    ('rsa-pkcs1-sha256', 'rsa', 'root_rsa', ['-tls1_2', '-cipher', 'ECDHE-RSA-CHACHA20-POLY1305', '-sigalgs', 'RSA+SHA256'], 'phi.test', 0, '/', 'ok'),
    ('rsa-pkcs1-sha384-p256', 'rsa', 'root_rsa', ['-tls1_2', '-cipher', 'ECDHE-RSA-AES128-GCM-SHA256', '-sigalgs', 'RSA+SHA384', '-groups', 'P-256'], 'phi.test', 0, '/', 'ok'),
    ('no-ems', 'p256', 'root_ec', ['-tls1_2', '-no_ems'], 'phi.test', 0, '/', 'ok'),
    ('asks-for-certificate', 'p256', 'root_ec', ['-tls1_2', '-verify', '1'], 'phi.test', 0, '/', 'ok'),
    ('large-answer', 'rsa', 'root_rsa', ['-tls1_2', '-WWW'], 'phi.test', 0, '/big.bin', 'big'),
    ('wrong-name', 'p256', 'root_ec', ['-tls1_2'], 'other.test', 0, '/', 'fail:the server\'s certificate'),
    ('untrusted-root', 'p256', 'other', ['-tls1_2'], 'phi.test', 0, '/', 'fail:the server\'s certificate'),
    ('tls13-only', 'p256', 'root_ec', ['-tls1_3'], 'phi.test', 0, '/', 'fail:the server doesn\'t speak TLS 1.2 (alert 70)'),
    ('downgrade-mark', 'p256', 'root_ec', [], 'phi.test', 1, '/', 'fail:the server speaks TLS 1.3'),
    ('downgrade-mark-not-fallback', 'p256', 'root_ec', [], 'phi.test', 0, '/', 'ok'),
]

def main():
    if not OPENSSL:
        sys.exit('no openssl')
    write_cases = '--cases' in sys.argv
    work = tempfile.mkdtemp(prefix='netlib-tls-')
    make_certs(work)
    build = os.path.join(work, 'build')
    os.makedirs(build)
    # netlib and corelib as build.ps1 made them (run it first), and the tool beside them
    for lib in ('netlib', 'corelib'):
        shutil.copy(os.path.join(ROOT, 'dist', lib + '.philib'), build)
    shutil.copy(os.path.join(ROOT, 'tools', 'net', 'tlslive', 'tlslive.phi'), build)
    r = run([PHI, 'build', os.path.join(build, 'tlslive.phi'), '--target', HOST, '-o', build])
    if r.returncode:
        sys.exit(r.stdout + r.stderr)
    tool = os.path.join(build, 'tlslive', 'tlslive') if os.path.isdir(os.path.join(build, 'tlslive')) else os.path.join(build, 'tlslive')
    random_bytes = os.urandom(4096)
    with open('random.bin', 'wb') as f:
        f.write(random_bytes)
    big = open('big.bin', 'rb').read()

    passed = 0
    records = []
    for i, (name, leaf, root, options, asked, fallback, path, want) in enumerate(CASES):
        port = PORT + i
        server = subprocess.Popen([OPENSSL, 's_server', '-accept', str(port), '-cert', leaf + '.pem', '-key', leaf + '.key',
                                   '-cert_chain', ('root_rsa' if leaf == 'rsa' else 'root_ec') + '.pem', '-quiet'] +
                                  (options if '-WWW' in options else options + ['-www']),
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=work)
        time.sleep(0.6)
        now = int(time.time())
        out = run([tool, '127.0.0.1', str(port), asked, root + '.der', 'random.bin', str(fallback), 'rec_' + name, path],
                  cwd=work, timeout=120).stdout.strip()
        server.kill()
        server.wait()
        good = False
        if want == 'ok':
            good = out.startswith('connected:') and 'HTTP/1.0 200 ok' in out and 'then failed' not in out
        elif want == 'big':
            answer = open(os.path.join(work, 'rec_' + name + '.answer'), 'rb').read()
            good = out.startswith('connected:') and answer.startswith(b'HTTP/1.0 200 ok') and answer.endswith(b'\r\n\r\n' + big)
        else:
            good = out.startswith('failed: ' + want[5:])
        passed += good
        print('%-28s %s  %s' % (name, 'ok  ' if good else 'BAD ', out))
        if write_cases and want != 'big':
            sent = open(os.path.join(work, 'rec_' + name + '.sent'), 'rb').read()
            got = open(os.path.join(work, 'rec_' + name + '.got'), 'rb').read()
            answer_length, crc, error = 0, 0, b''
            if out.startswith('connected:'):
                answer_length = int(out.split('(')[1].split(' ')[0])
                crc = int(out.split('crc ')[1].rstrip(')'))
            else:
                error = want[5:].encode()
            records.append((name, asked, fallback, now, open(root + '.der', 'rb').read(), sent, got,
                            1 if out.startswith('connected:') else 0, answer_length, crc, error))
    print('%d/%d as they should be' % (passed, len(CASES)))
    if write_cases:
        folder = os.path.join(ROOT, 'libs', 'net', 'tests', 'tls')
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, 'cases.bin'), 'wb') as f:
            f.write(struct.pack('<I', len(records)))
            f.write(struct.pack('<I', len(random_bytes)) + random_bytes)
            for name, asked, fallback, now, root_der, sent, got, connected, answer_length, crc, error in records:
                for text in (name.encode(), asked.encode()):
                    f.write(bytes([len(text)]) + text)
                f.write(struct.pack('<BI', fallback, now))
                for blob in (root_der, sent, got):
                    f.write(struct.pack('<I', len(blob)) + blob)
                f.write(struct.pack('<BII', connected, answer_length, crc))
                f.write(bytes([len(error)]) + error)
        print('wrote', len(records), 'cases to', os.path.relpath(os.path.join(folder, 'cases.bin'), ROOT))
    sys.exit(0 if passed == len(CASES) else 1)

main()
