// Records an HTTP/2 exchange for netlib's test_http2: Node.js's own HTTP/2 server (cleartext, as a
// client that knows it speaks HTTP/2 talks to it) is sent the bytes test_http2 made
// (libs/net/tests/http2/client.bin), and what it sends back in the next second is kept as
// server.bin. Run test_http2 with `write` first, then this, from the repository's root:
//
//   node tools/net/check_http2.js
//
// It answers /hello (with two cookies), /gzip (a gzip body), HEAD, /echo (what was posted, back),
// /big (300,000 bytes, many frames) and anything else with a 404.
'use strict';
const http2 = require('http2');
const net = require('net');
const zlib = require('zlib');
const fs = require('fs');
const path = require('path');

const dir = path.join(__dirname, '..', '..', 'libs', 'net', 'tests', 'http2');
const client = fs.readFileSync(path.join(dir, 'client.bin'));

const server = http2.createServer();
server.on('stream', (stream, headers) => {
  const p = headers[':path'];
  if (p === '/hello') {
    stream.respond({ ':status': 200, 'content-type': 'text/plain; charset=utf-8', 'set-cookie': ['a=1; Path=/', 'b=2; HttpOnly'], 'x-seen': headers['x-test'] || 'none' });
    stream.end(headers[':method'] === 'HEAD' ? undefined : 'Hello over HTTP/2');
  } else if (p === '/gzip') {
    stream.respond({ ':status': 200, 'content-type': 'text/plain', 'content-encoding': 'gzip' });
    stream.end(zlib.gzipSync(Buffer.from('this came gzipped')));
  } else if (p === '/echo') {
    const parts = [];
    stream.on('data', d => parts.push(d));
    stream.on('end', () => {
      stream.respond({ ':status': 201, 'content-type': headers['content-type'] || 'none' });
      stream.end('got: ' + Buffer.concat(parts).toString());
    });
  } else if (p === '/big') {
    const big = Buffer.alloc(300000);
    for (let i = 0; i < big.length; i++) big[i] = (i * 7 + (i >> 8)) & 255;
    stream.respond({ ':status': 200, 'content-type': 'application/octet-stream' });
    stream.end(big);
  } else {
    stream.respond({ ':status': 404, 'content-type': 'text/html' });
    stream.end('<h1>not here</h1>');
  }
});
server.listen(0, '127.0.0.1', () => {
  const port = server.address().port;
  const got = [];
  const sock = net.connect(port, '127.0.0.1', () => sock.write(client));
  sock.on('data', d => got.push(d));
  setTimeout(() => {
    const all = Buffer.concat(got);
    fs.writeFileSync(path.join(dir, 'server.bin'), all);
    console.log('server.bin: ' + all.length + ' bytes');
    sock.destroy();
    server.close();
  }, 1500);
});
