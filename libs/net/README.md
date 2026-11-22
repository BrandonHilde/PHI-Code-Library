# netlib

What a web client needs between its connections and its pages: HTTP/1.1 messages (a request's head
written, an answer read as its bytes come, its body unpacked), HTTP/2 (many requests on one
connection, with HPACK), cookies as browsers keep them, and a TLS 1.2 client for the servers that
don't speak TLS 1.3 yet (which can offer HTTP/2 by ALPN). It opens no connections: the program
connects, sends what netlib makes, and hands over what comes back (PHI OS's browser does this in
`brw/web.phi`). It uses corelib (for gzip, deflate and Brotli) and PHI's own `crypto` modules (for TLS).

```phi
use netlib;

call NetLib.Start;
WireTarget t;                                             # (2.3 KB: new one in a method)
bln ok: (WireHttp.Split: 'https://example.com/a?b' addr t);
int n: (WireHttp.Request: head 4096 'GET' addr t extra 0 false);   # send these n bytes
WireAnswer a;
call WireHttp.Begin: addr a false 8000000;                # not a HEAD; the most a body may be
# for each piece that comes:  u32 used: (WireHttp.Take: addr a bytes got);
# if the connection closes:   call WireHttp.Ended: addr a;
# until a.done or a.failed;   then a.status, a.keep, (WireHttp.Header: addr a 'Content-Type' target size)
ok is (WireHttp.Unpack: addr a);                          # a.body, a.body_length: as before Content-Encoding
call WireHttp.Free: addr a;
```

## API

These names are the API. Other methods of these classes are how they work, and may change.

| Name | What it is |
|---|---|
| `NetLib.Start` | Call once, before anything else. `NetLib.VERSION` is 1 |
| **HTTP** | |
| `WireTarget` | Where an address goes: `secure` (https), `host` (lower case; IPv6 without brackets), `port`, `path` (the path and query, `/` at least) |
| `WireHttp.Split: url t` → | `t` for an `http://` or `https://` address; false for any other, or one with no host |
| `WireHttp.Resolve: base location target max` → | A `Location` made whole against the address asked for (RFC 3986 5.2, dot segments taken out): its length, or -1 if it doesn't fit |
| `WireHttp.Request: target max verb t extra length send_length` → | A request's head: the request line, `Host`, `User-Agent` (`WireHttp.agent`), `Accept-Encoding` (gzip and deflate, and br when `WireHttp.brotli` is set), `Connection: keep-alive`, `Content-Length` when `length` isn't 0 or `send_length` is true, then `extra` (whole header lines, each ending `\r\n`, or 0) and the blank line. Its length, or -1 if it doesn't fit |
| `WireAnswer` | An answer as it comes: `status`, `done`, `failed`, `error`, `keep` (another request may follow on the connection), `body`, `body_length`, `head` |
| `WireHttp.Begin: a no_body most` | `a` made ready for an answer; `no_body` for a HEAD's; `most`, the most its body may be |
| `WireHttp.Take: a data length` → | Bytes that came: how many were the answer's (what's after its end isn't). 1xx answers are passed over; a body is sized, chunked, or runs to the end; HEAD, 204 and 304 have none |
| `WireHttp.Ended: a` | The connection closed: that ends a body that runs to the end, and fails anything else |
| `WireHttp.Header: a name target size` → | A header's first value (its name in any case), trimmed: its length, or -1 |
| `WireHttp.HeaderAt: a name index target size` → | Its `index`th value, for headers that come many times (`Set-Cookie`) |
| `WireHttp.Unpack: a` → | The body as it was before its `Content-Encoding` (gzip, x-gzip, deflate as zlib or bare, br, identity, several in a row); false, with `a.error`, if a coding isn't known or the body doesn't unpack. Brotli needs corelib's dictionary (`CoreBrotli.Dictionary`) |
| `WireHttp.Free: a` | Gives back `a`'s memory |
| **HTTP/2** | |
| `WireH2` | A connection (big: make it with `new`). `failed`, `error`, `goaway` (the server is closing: no new requests) |
| `WireH2.Start: c most` | `c` made ready, with the preface and settings waiting to be sent first; `most`, the most an answer's body may be |
| `WireH2.CanRequest: c` → | Whether another request can go now (32 at once, and no more than the server allows) |
| `WireH2.Request: c verb t extra body length` → | A request: `:method`, `:scheme`, `:authority` and `:path` from `t`, `user-agent`, `accept-encoding` (with br when `WireHttp.brotli` is set), `content-length` when there's a body, then `extra` (whole header lines as `WireHttp.Request` takes them; `Connection`, `Host` and the like are left out, as HTTP/2 has no place for them). `body` must stay until it's sent. Its stream's number, or -1 if it can't go now |
| `WireH2.Pending: c` →, `Outgoing: c` →, `Sent: c n` | What to send, where it is, and how much went |
| `WireH2.Take: c data length` → | Bytes that came: false once the connection's failed. Settings are acknowledged, pings answered, and the windows kept open as the bodies are read |
| `WireH2.Answer: c id` → | The stream's answer: a `WireAnswer`, whose head is written as `HTTP/2 200` and a `name: value` line a header, so `WireHttp.Header`, `HeaderAt` and `Unpack` read it |
| `WireH2.Done: c id` | Finished with an answer: its memory back, and the server told to stop if it hadn't all come |
| `WireH2.Ended: c`, `Free: c` | The connection closed (what wasn't done fails); `c`'s memory back |
| **Cookies** | |
| `WireJar` | Every cookie: start one zeroed |
| `WireCookies.Take: jar t header now from_script` → | A `Set-Cookie` value from the answer to `t` (now: seconds since 1970); false if it isn't kept (`WireCookies.why` says why) or it deleted one. `from_script` for `document.cookie = ...` |
| `WireCookies.Header: jar t now context from_script target size` → | The `Cookie` header's value for a request for `t`: its length (0: none go). `context` is `SAME_SITE`, `CROSS_TOP` (a navigation of the window from another site, with GET) or `CROSS`, for SameSite |
| `WireCookies.SameSite: a b` → | Whether two hosts are the same site (the same registrable domain) |
| `WireCookies.Suffixes: list length` → | Gives the Public Suffix List's text (publicsuffix.org), which must stay where it is; until then a short list of the commonest is used |
| `WireCookies.Save: jar now target size` → | The cookies that outlast the session, as text lines: its length, or -1 if it doesn't fit |
| `WireCookies.Load: jar data length now` → | Takes back what `Save` made: how many came back |
| `WireCookies.EndSession: jar`, `Clear: jar`, `Free: jar` | Forgets the session's cookies; forgets them all; gives back the memory |
| `WireCookies.Date: text length` → | An `Expires` date as seconds since 1970 (RFC 6265 5.1.1's way, so any form servers write); `WireCookies.date_ok` says whether it was one |
| **TLS 1.2** | |
| `WireTls.random` | The program's random bytes: a `method<ptr<u8> u32>`, which must be set before `Client` |
| `WireTlsSession` | One connection: `connected`, `failed`, `closed`, `error`, `alert`, `room`, `suite`, `group`, `ems` |
| `WireTls.Client: s host fallback h2` → | `s`, a client of `host` with its ClientHello ready to send. `fallback`: TLS 1.3 was tried first, so a server that marks its answer as one that speaks 1.3 is refused. `h2`: ALPN offers `h2`, then `http/1.1`, and `s.h2` says whether the server chose `h2` |
| `WireTls.Pending: s` →, `Outgoing: s` →, `Sent: s n` | What to send, where it is, and how much went |
| `WireTls.Room: s` →, `Received: s n` → | Where what comes goes (`s.room` bytes), and how much came: false once `s` failed |
| `WireTls.Read: s buffer max` →, `Write: s data length` → | Data that came (0 if none yet, -1 once closed), and data to send |
| `WireTls.Close: s`, `Free: s` | close_notify, to send; and the session's memory back |

## How it's checked

- **TLS 1.2** against OpenSSL 4's server (`tools/net/check_tls.py`, which makes its own root and
  certificates): every suite and curve offered, ECDSA (P-256, P-384), RSA-PSS and RSA PKCS #1
  signatures, with and without the extended master secret, a server that asks for a client
  certificate, a 300 KB answer over many records checked byte for byte; and refusals: the wrong name,
  a root not trusted, a server that speaks only TLS 1.3, and RFC 8446's downgrade mark. 16 of 16. Those
  exchanges are kept (`tests/tls/cases.bin`), and `test_tls` replays them with no network: the same
  random bytes must send the same bytes and get the same answer. And xkcd.com, which speaks only TLS
  1.2, from PHI OS.
- **HTTP** (`test_http`): RFC 3986's resolution examples, answers fed whole and a byte at a time, the
  answers that must fail, and bodies packed by Python's zlib and gzip and Google's brotli
  (`tools/net/make_http_tests.py`) unpacked to the same bytes.
- **HTTP/2** (`test_http2`): RFC 7541's examples of answers (C.6: Huffman strings, and a dynamic table
  of 256 bytes that has to let entries go, each table's size as the RFC gives it); and an exchange with
  Node.js's HTTP/2 server, recorded by `tools/net/check_http2.js` and replayed with no network: six
  requests at once (a GET with extra headers, a gzipped answer, a HEAD, a POST with a body, a 404, and
  300,000 bytes in many frames), the requests the same bytes they were then, and the server's answer,
  fed whole and a byte at a time, read the same. And ALPN in the TLS 1.2 client: offered when asked
  for, and a server's choice of `h2` read. The HPACK tables are made from RFC 7541's own text
  (`tools/net/make_hpack_tables.py`, which checks the code is the complete, canonical one).
- **Cookies** (`test_cookies`): each rule, by cases worked out from RFC 6265 and its successor draft.

## Limits

- HTTP/2: no server push (it's refused in the settings), no priorities, and a request's headers aren't
  kept in HPACK's table (each goes as a literal). A browser on PHI's own TLS 1.3 (`net.tls13`) can't
  use it yet: that offers no ALPN, so a server there speaks HTTP/1.1.
- TLS 1.2 only offers what PHI's crypto has: AES-128-GCM and ChaCha20-Poly1305 with ECDHE. A server
  with only CBC ciphers, RSA key exchange or AES-256 isn't reached (few are left).
- `crypto.x509` checks certificate dates against the system's clock (`OS.Now`) unless `X509.now` is set.
- Cookies: the Public Suffix List is the program's to give; without it, a domain the short list doesn't
  know may take a cookie for a suffix it shouldn't (the short list has the commonest). No partitioned
  cookies (CHIPS).
- Each class does one thing at a time: a program with threads holds a lock round each (PHI OS's browser
  holds `Secure.crypto` round `WireTls`, as PHI's `net.tlslink` does round `net.tls13`, and a lock of its
  own round its jar).
