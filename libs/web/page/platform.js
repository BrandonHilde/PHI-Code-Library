// The parts of the web platform written in JavaScript, for every page: run once, after the window and
// the DOM's other scripts are set up (page/platform.phi holds it, made by tools/web/make_page_js.py).
//
//   URL and URLSearchParams        the URL standard's parser, for the schemes pages use (special ones,
//                                  http, https, ws, wss, ftp and file, and opaque ones like data:);
//                                  host names are lowercased but not made punycode
//   TextEncoder, TextDecoder       UTF-8 (and decoding UTF-16 and Latin-1)
//   DOMException, AbortController and AbortSignal
//   Blob, File, FileReader, FormData, and blob: URLs
//   Headers, Request, Response     fetch takes a Request and gives a Response (the page's natives do
//                                  the fetching: %fetchText)
//   events                         the classes pages construct and test for
//   DOMRect, DOMPoint, DOMMatrix   (a 2D matrix)
//   URL attributes                 a.href, img.src and the rest resolved; <a>'s and <area>'s parts
//   XMLHttpRequest                 made of fetch, which sends the method, headers and body it's given
//   HTMLMediaElement               under <video> and <audio>: what a browser that plays nothing says
//   CSS.supports and CSS.escape, PerformanceObserver, requestIdleCallback, reportError,
//   crypto.getRandomValues and randomUUID (from %randomBytes: PHI's crypto.random), visualViewport,
//   and the names of the classes the window's own objects are made from (History, Location ...)
// Not kept: TouchEvent (a page would take this for a touch screen), streams, WebSocket, workers.
(function (global) {
  "use strict";
  var randomBytes = global["%randomBytes"];
  delete global["%randomBytes"];

  function hidden(o, name, value) {
    Object.defineProperty(o, name, { value: value, writable: true, configurable: true, enumerable: false });
  }
  function define(name, value) {
    if (typeof global[name] === "undefined") hidden(global, name, value);
  }
  function report(error) {
    setTimeout(function () { throw error; }, 0);
  }

  // ---- DOMException ----

  var codes = { IndexSizeError: 1, HierarchyRequestError: 3, WrongDocumentError: 4, InvalidCharacterError: 5,
    NoModificationAllowedError: 7, NotFoundError: 8, NotSupportedError: 9, InvalidStateError: 11, SyntaxError: 12,
    InvalidModificationError: 13, NamespaceError: 14, InvalidAccessError: 15, TypeMismatchError: 17,
    SecurityError: 18, NetworkError: 19, AbortError: 20, URLMismatchError: 21, QuotaExceededError: 22,
    TimeoutError: 23, InvalidNodeTypeError: 24, DataCloneError: 25 };
  class DOMException extends Error {
    constructor(message, name) {
      super(message === undefined ? "" : String(message));
      var n = name === undefined ? "Error" : String(name);
      Object.defineProperty(this, "name", { value: n, configurable: true, writable: true });
      Object.defineProperty(this, "code", { value: codes[n] || 0, configurable: true });
    }
  }
  for (var cn in codes) {
    var constName = cn.replace(/([a-z])([A-Z])/g, "$1_$2").toUpperCase().replace(/_ERROR$/, "_ERR");
    DOMException[constName] = codes[cn];
  }
  define("DOMException", DOMException);

  // ---- URLSearchParams ----

  function formEncode(s) {
    return encodeURIComponent(s).replace(/%20/g, "+").replace(/[!'()~]/g, function (c) {
      return "%" + c.charCodeAt(0).toString(16).toUpperCase();
    });
  }
  function formDecode(s) {
    s = s.replace(/\+/g, " ");
    try { return decodeURIComponent(s); } catch (e) {
      return s.replace(/%([0-9A-Fa-f]{2})/g, function (m, h) { return String.fromCharCode(parseInt(h, 16)); });
    }
  }

  class URLSearchParams {
    constructor(init) {
      hidden(this, "_list", []);
      hidden(this, "_url", null);
      if (init === undefined || init === null) return;
      if (typeof init === "object" || typeof init === "function") {
        if (typeof init[Symbol.iterator] === "function") {
          for (var pair of init) {
            var p = Array.from(pair);
            if (p.length !== 2) throw new TypeError("Each pair for URLSearchParams must have two items");
            this._list.push([String(p[0]), String(p[1])]);
          }
        } else {
          for (var key of Object.keys(init)) this._list.push([key, String(init[key])]);
        }
        return;
      }
      this._parse(String(init));
    }
    _parse(s) {
      this._list.length = 0;
      if (s.charAt(0) === "?") s = s.slice(1);
      var parts = s.split("&");
      for (var i = 0; i < parts.length; i++) {
        if (parts[i] === "") continue;
        var eq = parts[i].indexOf("=");
        var name = eq < 0 ? parts[i] : parts[i].slice(0, eq);
        var value = eq < 0 ? "" : parts[i].slice(eq + 1);
        this._list.push([formDecode(name), formDecode(value)]);
      }
    }
    _changed() {
      if (this._url !== null) {
        var q = this.toString();
        this._url._r.query = q === "" ? null : q;
      }
    }
    get size() { return this._list.length; }
    append(name, value) { this._list.push([String(name), String(value)]); this._changed(); }
    delete(name, value) {
      name = String(name);
      var v = value === undefined ? undefined : String(value);
      this._list = this._list.filter(function (p) { return !(p[0] === name && (v === undefined || p[1] === v)); });
      this._changed();
    }
    get(name) {
      name = String(name);
      for (var i = 0; i < this._list.length; i++) if (this._list[i][0] === name) return this._list[i][1];
      return null;
    }
    getAll(name) {
      name = String(name);
      return this._list.filter(function (p) { return p[0] === name; }).map(function (p) { return p[1]; });
    }
    has(name, value) {
      name = String(name);
      var v = value === undefined ? undefined : String(value);
      return this._list.some(function (p) { return p[0] === name && (v === undefined || p[1] === v); });
    }
    set(name, value) {
      name = String(name); value = String(value);
      var found = false, out = [];
      for (var i = 0; i < this._list.length; i++) {
        var p = this._list[i];
        if (p[0] !== name) out.push(p);
        else if (!found) { out.push([name, value]); found = true; }
      }
      if (!found) out.push([name, value]);
      this._list = out;
      this._changed();
    }
    sort() {
      var indexed = this._list.map(function (p, i) { return [p, i]; });
      indexed.sort(function (a, b) {
        if (a[0][0] < b[0][0]) return -1;
        if (a[0][0] > b[0][0]) return 1;
        return a[1] - b[1];
      });
      this._list = indexed.map(function (x) { return x[0]; });
      this._changed();
    }
    forEach(fn, thisArg) {
      for (var i = 0; i < this._list.length; i++) fn.call(thisArg, this._list[i][1], this._list[i][0], this);
    }
    *entries() { for (var i = 0; i < this._list.length; i++) yield [this._list[i][0], this._list[i][1]]; }
    *keys() { for (var i = 0; i < this._list.length; i++) yield this._list[i][0]; }
    *values() { for (var i = 0; i < this._list.length; i++) yield this._list[i][1]; }
    [Symbol.iterator]() { return this.entries(); }
    toString() {
      return this._list.map(function (p) { return formEncode(p[0]) + "=" + formEncode(p[1]); }).join("&");
    }
  }
  Object.defineProperty(URLSearchParams.prototype, Symbol.toStringTag, { value: "URLSearchParams", configurable: true });
  define("URLSearchParams", URLSearchParams);

  // ---- URL ----

  var specialPorts = { "ftp": 21, "file": null, "http": 80, "https": 443, "ws": 80, "wss": 443 };
  function isSpecial(scheme) { return Object.prototype.hasOwnProperty.call(specialPorts, scheme); }

  // percent-encodes what's in the set, controls (and with a set, the space), and everything past ASCII
  // (as UTF-8); an empty set is the C0 control set, for opaque paths
  function encodeSet(s, set) {
    var out = "", lowest = set === "" ? 0x20 : 0x21;
    for (var i = 0; i < s.length; i++) {
      var c = s.charAt(i), code = s.charCodeAt(i);
      if (code >= 0xD800 && code <= 0xDBFF && i + 1 < s.length) {
        out += encodeURIComponent(s.slice(i, i + 2));
        i++;
      } else if (code < lowest || code > 0x7E || set.indexOf(c) >= 0) {
        if (code >= 0xD800 && code <= 0xDFFF) out += "%EF%BF%BD";
        else out += encodeURIComponent(c).replace(/[!'()*~]/g, function (x) { return "%" + x.charCodeAt(0).toString(16).toUpperCase(); });
      } else out += c;
    }
    return out;
  }
  var PATH_SET = " \"#<>?`{}";
  var QUERY_SET = " \"#<>";
  var SPECIAL_QUERY_SET = " \"#<>'";
  var FRAGMENT_SET = " \"<>`";
  var USERINFO_SET = " \"#<>?`{}/:;=@[\\]^|";

  function parseHost(input, special) {
    if (input.charAt(0) === "[") {
      if (input.charAt(input.length - 1) !== "]") return null;
      return input.toLowerCase();
    }
    if (!special) return encodeSet(input, " #/<>?@[\\]^|");
    var host;
    try { host = decodeURIComponent(input); } catch (e) { return null; }
    host = host.toLowerCase();
    if (host === "" || /[\u0000\t\n\r #%\/:<>?@[\\\]^|]/.test(host)) return null;
    // a host of numbers is an IPv4 address, written out in full
    var parts = host.split(".");
    if (parts[parts.length - 1] === "") parts.pop();
    var last = parts[parts.length - 1];
    if (parts.length <= 4 && last !== undefined && /^(0x[0-9a-f]*|[0-9]+)$/.test(last)) {
      var nums = [];
      for (var i = 0; i < parts.length; i++) {
        var p = parts[i], n;
        if (/^0x[0-9a-f]*$/.test(p)) n = p.length === 2 ? 0 : parseInt(p.slice(2), 16);
        else if (/^0[0-7]+$/.test(p)) n = parseInt(p, 8);
        else if (/^[0-9]+$/.test(p)) n = parseInt(p, 10);
        else return null;
        nums.push(n);
      }
      var value = 0;
      for (var j = 0; j < nums.length - 1; j++) {
        if (nums[j] > 255) return null;
        value += nums[j] * Math.pow(256, 3 - j);
      }
      if (nums[nums.length - 1] >= Math.pow(256, 5 - nums.length)) return null;
      value += nums[nums.length - 1];
      return [Math.floor(value / 16777216) % 256, Math.floor(value / 65536) % 256, Math.floor(value / 256) % 256, value % 256].join(".");
    }
    return host;
  }

  function normalizePath(segments, special) {
    var out = [];
    for (var i = 0; i < segments.length; i++) {
      var s = segments[i], lower = s.toLowerCase();
      var dot = s === "." || lower === "%2e";
      var dots = s === ".." || lower === ".%2e" || lower === "%2e." || lower === "%2e%2e";
      var last = i === segments.length - 1;
      if (dots) {
        if (out.length) out.pop();
        if (last) out.push("");
      } else if (dot) {
        if (last) out.push("");
      } else out.push(encodeSet(s, PATH_SET));
    }
    return out;
  }

  function splitTail(rest, r, special) {
    var hash = rest.indexOf("#");
    if (hash >= 0) {
      r.fragment = encodeSet(rest.slice(hash + 1), FRAGMENT_SET);
      rest = rest.slice(0, hash);
    }
    var q = rest.indexOf("?");
    if (q >= 0) {
      r.query = encodeSet(rest.slice(q + 1), special ? SPECIAL_QUERY_SET : QUERY_SET);
      rest = rest.slice(0, q);
    }
    return rest;
  }

  function setPath(r, path) {
    var special = isSpecial(r.scheme);
    if (special) path = path.replace(/\\/g, "/");
    if (path === "" && !special) { r.path = []; return; }
    if (path.charAt(0) === "/") path = path.slice(1);
    r.path = normalizePath(path.split("/"), special);
  }

  function authority(rest, r) {
    var special = isSpecial(r.scheme);
    var end = rest.length;
    for (var i = 0; i < rest.length; i++) {
      var c = rest.charAt(i);
      if (c === "/" || c === "?" || c === "#" || (special && c === "\\")) { end = i; break; }
    }
    var auth = rest.slice(0, end);
    var at = auth.lastIndexOf("@");
    if (at >= 0) {
      var info = auth.slice(0, at);
      var colon = info.indexOf(":");
      r.username = encodeSet(colon < 0 ? info : info.slice(0, colon), USERINFO_SET);
      r.password = colon < 0 ? "" : encodeSet(info.slice(colon + 1), USERINFO_SET);
      auth = auth.slice(at + 1);
    }
    var portAt = -1;
    if (auth.charAt(0) === "[") {
      var close = auth.indexOf("]");
      if (close >= 0 && auth.charAt(close + 1) === ":") portAt = close + 1;
    } else portAt = auth.lastIndexOf(":");
    var hostText = portAt >= 0 ? auth.slice(0, portAt) : auth;
    if (portAt >= 0) {
      var portText = auth.slice(portAt + 1);
      if (portText !== "") {
        if (!/^[0-9]+$/.test(portText)) return null;
        var port = parseInt(portText, 10);
        if (port > 65535) return null;
        r.port = port === specialPorts[r.scheme] ? null : port;
      }
    }
    if (hostText === "") {
      if (special && r.scheme !== "file") return null;
      r.host = "";
    } else {
      var host = parseHost(hostText, special);
      if (host === null) return null;
      r.host = host;
    }
    return rest.slice(end);
  }

  function parseURL(input, base) {
    input = String(input).replace(/^[\u0000- ]+|[\u0000- ]+$/g, "").replace(/[\t\n\r]/g, "");
    var r = { scheme: "", username: "", password: "", host: null, port: null, path: [], opaque: null, query: null, fragment: null };
    var m = /^([A-Za-z][A-Za-z0-9+.\-]*):/.exec(input);
    if (m) {
      r.scheme = m[1].toLowerCase();
      var rest = input.slice(m[0].length);
      var special = isSpecial(r.scheme);
      if (special) {
        if (base && base.scheme === r.scheme && !/^[\/\\]/.test(rest)) return relative(rest, base);
        if (r.scheme === "file") {
          rest = rest.replace(/^[\/\\]{0,2}/, "");
          rest = authority(rest, r);
          if (rest === null) return null;
        } else {
          rest = authority(rest.replace(/^[\/\\]*/, ""), r);
          if (rest === null) return null;
        }
        rest = splitTail(rest, r, true);
        setPath(r, rest);
        if (r.path.length === 0) r.path = [""];
        return r;
      }
      if (rest.slice(0, 2) === "//") {
        rest = authority(rest.slice(2), r);
        if (rest === null) return null;
        rest = splitTail(rest, r, false);
        if (rest !== "") setPath(r, rest);
        return r;
      }
      if (rest.charAt(0) === "/") {
        rest = splitTail(rest, r, false);
        setPath(r, rest);
        return r;
      }
      rest = splitTail(rest, r, false);
      r.opaque = encodeSet(rest, "");
      return r;
    }
    if (!base) return null;
    return relative(input, base);
  }

  function copyRecord(b) {
    return { scheme: b.scheme, username: b.username, password: b.password, host: b.host, port: b.port,
      path: b.path.slice(), opaque: b.opaque, query: b.query, fragment: b.fragment };
  }

  function relative(input, base) {
    var special = isSpecial(base.scheme);
    var r = copyRecord(base);
    r.fragment = null;
    if (base.opaque !== null) {
      if (input.charAt(0) !== "#") return null;
      r.fragment = encodeSet(input.slice(1), FRAGMENT_SET);
      return r;
    }
    var slash = special ? /^[\/\\]/ : /^\//;
    if (input.length >= 2 && slash.test(input.charAt(0)) && slash.test(input.charAt(1))) {
      r.username = ""; r.password = ""; r.host = null; r.port = null; r.query = null;
      var rest = authority(input.slice(2), r);
      if (rest === null) return null;
      rest = splitTail(rest, r, special);
      setPath(r, rest);
      if (special && r.path.length === 0) r.path = [""];
      return r;
    }
    if (slash.test(input.charAt(0))) {
      r.query = null;
      var rest2 = splitTail(input, r, special);
      setPath(r, rest2);
      return r;
    }
    if (input.charAt(0) === "?") {
      r.query = null;
      splitTail(input, r, special);
      return r;
    }
    if (input.charAt(0) === "#") {
      r.fragment = encodeSet(input.slice(1), FRAGMENT_SET);
      return r;
    }
    r.query = null;
    var rest3 = splitTail(input, r, special);
    if (special) rest3 = rest3.replace(/\\/g, "/");
    var dir = base.path.slice(0, -1);
    r.path = normalizePath(dir.concat(rest3.split("/")), special);
    if (special && r.path.length === 0) r.path = [""];
    return r;
  }

  function serializeHost(r) {
    var s = r.host === null ? "" : r.host;
    if (r.port !== null) s += ":" + r.port;
    return s;
  }
  function serializePath(r) {
    if (r.opaque !== null) return r.opaque;
    if (r.path.length === 0) return "";
    return "/" + r.path.join("/");
  }
  function serialize(r, noFragment) {
    var s = r.scheme + ":";
    if (r.host !== null) {
      s += "//";
      if (r.username !== "" || r.password !== "") {
        s += r.username;
        if (r.password !== "") s += ":" + r.password;
        s += "@";
      }
      s += serializeHost(r);
    } else if (r.opaque === null && r.path.length > 1 && r.path[0] === "") s += "/.";
    s += serializePath(r);
    if (r.query !== null) s += "?" + r.query;
    if (!noFragment && r.fragment !== null) s += "#" + r.fragment;
    return s;
  }

  function baseRecord(base) {
    if (base === undefined) return null;
    var b = base instanceof URL ? base._r : parseURL(String(base), null);
    if (b === null) throw new TypeError("Invalid base URL: " + base);
    return b;
  }

  class URL {
    constructor(url, base) {
      var r = parseURL(String(url), baseRecord(base));
      if (r === null) throw new TypeError("Invalid URL: " + url);
      hidden(this, "_r", r);
      hidden(this, "_params", null);
    }
    static canParse(url, base) {
      try { return parseURL(String(url), baseRecord(base)) !== null; } catch (e) { return false; }
    }
    static parse(url, base) {
      try { return new URL(url, base); } catch (e) { return null; }
    }
    get href() { return serialize(this._r); }
    set href(v) {
      var r = parseURL(String(v), null);
      if (r === null) throw new TypeError("Invalid URL: " + v);
      this._r = r;
      if (this._params) this._params._parse(r.query || "");
    }
    get origin() {
      var r = this._r;
      if (r.scheme === "blob") {
        var inner = parseURL(serializePath(r), null);
        return inner && (inner.scheme === "http" || inner.scheme === "https") ? new URL(serializePath(r)).origin : "null";
      }
      if (r.scheme === "http" || r.scheme === "https" || r.scheme === "ws" || r.scheme === "wss" || r.scheme === "ftp") {
        return r.scheme + "://" + serializeHost(r);
      }
      return "null";
    }
    get protocol() { return this._r.scheme + ":"; }
    set protocol(v) {
      var s = String(v).replace(/:.*$/, "").toLowerCase();
      if (!/^[a-z][a-z0-9+.\-]*$/.test(s)) return;
      if (isSpecial(s) !== isSpecial(this._r.scheme)) return;
      this._r.scheme = s;
      if (this._r.port === specialPorts[s]) this._r.port = null;
    }
    get username() { return this._r.username; }
    set username(v) { if (this._r.host) this._r.username = encodeSet(String(v), USERINFO_SET); }
    get password() { return this._r.password; }
    set password(v) { if (this._r.host) this._r.password = encodeSet(String(v), USERINFO_SET); }
    get host() { return this._r.host === null ? "" : serializeHost(this._r); }
    set host(v) {
      if (this._r.opaque !== null) return;
      var t = { scheme: this._r.scheme, username: "", password: "", host: null, port: this._r.port };
      if (authority(String(v), t) !== null && t.host !== null) { this._r.host = t.host; this._r.port = t.port; }
    }
    get hostname() { return this._r.host === null ? "" : this._r.host; }
    set hostname(v) {
      if (this._r.opaque !== null) return;
      var h = parseHost(String(v), isSpecial(this._r.scheme));
      if (h !== null) this._r.host = h;
    }
    get port() { return this._r.port === null ? "" : String(this._r.port); }
    set port(v) {
      if (this._r.host === null || this._r.scheme === "file") return;
      var s = String(v);
      if (s === "") { this._r.port = null; return; }
      var m = /^[0-9]+/.exec(s);
      if (!m) return;
      var p = parseInt(m[0], 10);
      if (p > 65535) return;
      this._r.port = p === specialPorts[this._r.scheme] ? null : p;
    }
    get pathname() { return serializePath(this._r); }
    set pathname(v) {
      if (this._r.opaque !== null) return;
      setPath(this._r, String(v));
      if (isSpecial(this._r.scheme) && this._r.path.length === 0) this._r.path = [""];
    }
    get search() { return this._r.query === null || this._r.query === "" ? "" : "?" + this._r.query; }
    set search(v) {
      var s = String(v);
      if (s.charAt(0) === "?") s = s.slice(1);
      this._r.query = s === "" ? null : encodeSet(s, isSpecial(this._r.scheme) ? SPECIAL_QUERY_SET : QUERY_SET);
      if (this._params) this._params._parse(s);
    }
    get searchParams() {
      if (this._params === null) {
        this._params = new URLSearchParams(this._r.query || "");
        this._params._url = this;
      }
      return this._params;
    }
    get hash() { return this._r.fragment === null || this._r.fragment === "" ? "" : "#" + this._r.fragment; }
    set hash(v) {
      var s = String(v);
      if (s.charAt(0) === "#") s = s.slice(1);
      this._r.fragment = s === "" ? null : encodeSet(s, FRAGMENT_SET);
    }
    toString() { return this.href; }
    toJSON() { return this.href; }
  }
  Object.defineProperty(URL.prototype, Symbol.toStringTag, { value: "URL", configurable: true });

  var blobs = new Map();
  var blobCount = 0;
  URL.createObjectURL = function (blob) {
    var id = "blob:" + (global.location ? global.location.origin : "null") + "/" + (++blobCount).toString(16) + "-" + Date.now().toString(16);
    blobs.set(id, blob);
    return id;
  };
  URL.revokeObjectURL = function (id) { blobs.delete(String(id)); };
  define("URL", URL);
  define("webkitURL", URL);

  // ---- TextEncoder, TextDecoder ----

  class TextEncoder {
    get encoding() { return "utf-8"; }
    encode(s) {
      s = s === undefined ? "" : String(s);
      var out = [];
      for (var i = 0; i < s.length; i++) {
        var c = s.charCodeAt(i);
        if (c >= 0xD800 && c <= 0xDBFF && i + 1 < s.length) {
          var d = s.charCodeAt(i + 1);
          if (d >= 0xDC00 && d <= 0xDFFF) { c = 0x10000 + ((c - 0xD800) << 10) + (d - 0xDC00); i++; } else c = 0xFFFD;
        } else if (c >= 0xD800 && c <= 0xDFFF) c = 0xFFFD;
        if (c < 0x80) out.push(c);
        else if (c < 0x800) out.push(0xC0 | (c >> 6), 0x80 | (c & 63));
        else if (c < 0x10000) out.push(0xE0 | (c >> 12), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
        else out.push(0xF0 | (c >> 18), 0x80 | ((c >> 12) & 63), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
      }
      return new Uint8Array(out);
    }
    encodeInto(s, dest) {
      var bytes = this.encode(s);
      var n = Math.min(bytes.length, dest.length);
      // (whole characters only)
      while (n > 0 && n < bytes.length && (bytes[n] & 0xC0) === 0x80) n--;
      dest.set(bytes.subarray(0, n));
      var read = new TextDecoder().decode(bytes.subarray(0, n)).length;
      return { read: read, written: n };
    }
  }
  define("TextEncoder", TextEncoder);

  var labels = { "utf-8": "utf-8", "utf8": "utf-8", "unicode-1-1-utf-8": "utf-8", "utf-16le": "utf-16le", "utf-16": "utf-16le",
    "utf-16be": "utf-16be", "latin1": "windows-1252", "iso-8859-1": "windows-1252", "windows-1252": "windows-1252",
    "ascii": "windows-1252", "us-ascii": "windows-1252" };
  class TextDecoder {
    constructor(label, options) {
      var l = label === undefined ? "utf-8" : String(label).trim().toLowerCase();
      if (!labels[l]) throw new RangeError("The encoding '" + label + "' isn't known");
      hidden(this, "_enc", labels[l]);
      hidden(this, "_fatal", !!(options && options.fatal));
      hidden(this, "_bom", !!(options && options.ignoreBOM));
      hidden(this, "_pending", []);
    }
    get encoding() { return this._enc; }
    get fatal() { return this._fatal; }
    get ignoreBOM() { return this._bom; }
    decode(input, options) {
      var bytes;
      if (input === undefined) bytes = new Uint8Array(0);
      else if (input instanceof ArrayBuffer) bytes = new Uint8Array(input);
      else if (ArrayBuffer.isView(input)) bytes = new Uint8Array(input.buffer, input.byteOffset, input.byteLength);
      else throw new TypeError("decode needs an ArrayBuffer or a view of one");
      var stream = !!(options && options.stream);
      if (this._pending.length) {
        var joined = new Uint8Array(this._pending.length + bytes.length);
        joined.set(this._pending);
        joined.set(bytes, this._pending.length);
        bytes = joined;
        this._pending = [];
      }
      var out = "", i = 0, n = bytes.length;
      if (this._enc === "windows-1252") {
        for (; i < n; i++) out += String.fromCharCode(bytes[i]);
        return out;
      }
      if (this._enc !== "utf-8") {
        var be = this._enc === "utf-16be";
        if (!this._bom && n >= 2 && ((!be && bytes[0] === 0xFF && bytes[1] === 0xFE) || (be && bytes[0] === 0xFE && bytes[1] === 0xFF))) i = 2;
        var units = [];
        for (; i + 1 < n; i += 2) units.push(be ? (bytes[i] << 8) | bytes[i + 1] : bytes[i] | (bytes[i + 1] << 8));
        if (i < n && stream) this._pending = [bytes[i]];
        for (var u = 0; u < units.length; u += 4096) out += String.fromCharCode.apply(null, units.slice(u, u + 4096));
        return out;
      }
      if (!this._bom && n >= 3 && bytes[0] === 0xEF && bytes[1] === 0xBB && bytes[2] === 0xBF) i = 3;
      var chunk = [];
      while (i < n) {
        var b = bytes[i], need = 0, c = 0, lower = 0x80, upper = 0xBF;
        if (b < 0x80) { chunk.push(b); i++; }
        else {
          if (b >= 0xC2 && b <= 0xDF) { need = 1; c = b & 31; }
          else if (b >= 0xE0 && b <= 0xEF) { need = 2; c = b & 15; if (b === 0xE0) lower = 0xA0; if (b === 0xED) upper = 0x9F; }
          else if (b >= 0xF0 && b <= 0xF4) { need = 3; c = b & 7; if (b === 0xF0) lower = 0x90; if (b === 0xF4) upper = 0x8F; }
          else need = -1;
          var j = i + 1, ok = need > 0;
          for (var k = 0; ok && k < need; k++, j++) {
            if (j >= n) {
              if (stream) { this._pending = Array.prototype.slice.call(bytes, i); i = n; ok = false; need = -2; break; }
              ok = false; break;
            }
            var x = bytes[j];
            if (x < lower || x > upper) { ok = false; break; }
            lower = 0x80; upper = 0xBF;
            c = (c << 6) | (x & 63);
          }
          if (need === -2) break;
          if (ok) {
            if (c >= 0x10000) { c -= 0x10000; chunk.push(0xD800 + (c >> 10), 0xDC00 + (c & 1023)); } else chunk.push(c);
            i = j;
          } else {
            if (this._fatal) throw new TypeError("The data isn't valid UTF-8");
            chunk.push(0xFFFD);
            i = need > 0 ? Math.max(i + 1, j) : i + 1;
          }
        }
        if (chunk.length >= 4096) { out += String.fromCharCode.apply(null, chunk); chunk = []; }
      }
      if (chunk.length) out += String.fromCharCode.apply(null, chunk);
      return out;
    }
  }
  define("TextDecoder", TextDecoder);

  // ---- AbortController, AbortSignal ----

  class AbortSignal extends EventTarget {
    constructor() {
      super();
      hidden(this, "_aborted", false);
      hidden(this, "_reason", undefined);
      this.onabort = null;
    }
    get aborted() { return this._aborted; }
    get reason() { return this._reason; }
    throwIfAborted() { if (this._aborted) throw this._reason; }
    _abort(reason) {
      if (this._aborted) return;
      this._aborted = true;
      this._reason = reason === undefined ? new DOMException("signal is aborted without reason", "AbortError") : reason;
      this.dispatchEvent(new Event("abort"));
    }
    static abort(reason) {
      var s = new AbortSignal();
      s._abort(reason);
      return s;
    }
    static timeout(ms) {
      var s = new AbortSignal();
      setTimeout(function () { s._abort(new DOMException("signal timed out", "TimeoutError")); }, ms);
      return s;
    }
    static any(signals) {
      var s = new AbortSignal();
      for (var x of signals) {
        if (x.aborted) { s._abort(x.reason); return s; }
      }
      for (var y of signals) {
        y.addEventListener("abort", function () { s._abort(this.reason); });
      }
      return s;
    }
  }
  define("AbortSignal", AbortSignal);
  class AbortController {
    constructor() { hidden(this, "_signal", new AbortSignal()); }
    get signal() { return this._signal; }
    abort(reason) { this._signal._abort(reason); }
  }
  define("AbortController", AbortController);

  // ---- Blob, File, FileReader, FormData ----

  function bytesOf(part) {
    if (part instanceof Blob) return part._bytes;
    if (part instanceof ArrayBuffer) return new Uint8Array(part.slice(0));
    if (ArrayBuffer.isView(part)) return new Uint8Array(part.buffer.slice(part.byteOffset, part.byteOffset + part.byteLength));
    return new TextEncoder().encode(String(part));
  }
  class Blob {
    constructor(parts, options) {
      var chunks = [], total = 0;
      if (parts !== undefined) {
        for (var p of parts) { var b = bytesOf(p); chunks.push(b); total += b.length; }
      }
      var all = new Uint8Array(total), at = 0;
      for (var i = 0; i < chunks.length; i++) { all.set(chunks[i], at); at += chunks[i].length; }
      hidden(this, "_bytes", all);
      hidden(this, "_type", options && options.type !== undefined ? String(options.type).toLowerCase() : "");
    }
    get size() { return this._bytes.length; }
    get type() { return this._type; }
    slice(start, end, type) {
      var n = this._bytes.length;
      var s = start === undefined ? 0 : start < 0 ? Math.max(n + start, 0) : Math.min(start, n);
      var e = end === undefined ? n : end < 0 ? Math.max(n + end, 0) : Math.min(end, n);
      return new Blob([this._bytes.subarray(s, Math.max(s, e))], { type: type === undefined ? "" : type });
    }
    text() { return Promise.resolve(new TextDecoder().decode(this._bytes)); }
    arrayBuffer() { return Promise.resolve(this._bytes.slice().buffer); }
    bytes() { return Promise.resolve(this._bytes.slice()); }
  }
  Object.defineProperty(Blob.prototype, Symbol.toStringTag, { value: "Blob", configurable: true });
  define("Blob", Blob);
  class File extends Blob {
    constructor(parts, name, options) {
      super(parts, options);
      hidden(this, "_name", String(name));
      hidden(this, "_modified", options && options.lastModified !== undefined ? Number(options.lastModified) : Date.now());
    }
    get name() { return this._name; }
    get lastModified() { return this._modified; }
  }
  Object.defineProperty(File.prototype, Symbol.toStringTag, { value: "File", configurable: true });
  define("File", File);

  class FileReader extends EventTarget {
    constructor() {
      super();
      this.result = null;
      this.error = null;
      this.readyState = 0;
      this.onload = null; this.onloadend = null; this.onerror = null; this.onloadstart = null; this.onprogress = null; this.onabort = null;
    }
    _read(blob, how) {
      var self = this;
      this.readyState = 1;
      setTimeout(function () {
        var b = blob._bytes;
        if (how === "text") self.result = new TextDecoder().decode(b);
        else if (how === "buffer") self.result = b.slice().buffer;
        else if (how === "binary") { var s = ""; for (var i = 0; i < b.length; i++) s += String.fromCharCode(b[i]); self.result = s; }
        else {
          var bin = "";
          for (var j = 0; j < b.length; j++) bin += String.fromCharCode(b[j]);
          self.result = "data:" + (blob.type || "application/octet-stream") + ";base64," + btoa(bin);
        }
        self.readyState = 2;
        self.dispatchEvent(new Event("load"));
        self.dispatchEvent(new Event("loadend"));
      }, 0);
    }
    readAsText(blob) { this._read(blob, "text"); }
    readAsArrayBuffer(blob) { this._read(blob, "buffer"); }
    readAsBinaryString(blob) { this._read(blob, "binary"); }
    readAsDataURL(blob) { this._read(blob, "url"); }
    abort() { }
  }
  FileReader.EMPTY = 0; FileReader.LOADING = 1; FileReader.DONE = 2;
  define("FileReader", FileReader);

  class FormData {
    constructor(form) {
      hidden(this, "_list", []);
      if (form && form.elements === undefined && form.querySelectorAll) {
        var fields = form.querySelectorAll("input[name], select[name], textarea[name]");
        for (var i = 0; i < fields.length; i++) {
          var f = fields[i];
          if (f.disabled) continue;
          var type = (f.getAttribute("type") || "").toLowerCase();
          if ((type === "checkbox" || type === "radio") && !f.checked) continue;
          if (type === "submit" || type === "button" || type === "reset" || type === "file") continue;
          this._list.push([f.getAttribute("name"), String(f.value === undefined ? "" : f.value)]);
        }
      }
    }
    _value(v, filename) {
      if (v instanceof Blob) {
        if (!(v instanceof File) || filename !== undefined) return new File([v], filename === undefined ? "blob" : String(filename), { type: v.type });
        return v;
      }
      return String(v);
    }
    append(name, value, filename) { this._list.push([String(name), this._value(value, filename)]); }
    delete(name) { name = String(name); this._list = this._list.filter(function (p) { return p[0] !== name; }); }
    get(name) {
      name = String(name);
      for (var i = 0; i < this._list.length; i++) if (this._list[i][0] === name) return this._list[i][1];
      return null;
    }
    getAll(name) { name = String(name); return this._list.filter(function (p) { return p[0] === name; }).map(function (p) { return p[1]; }); }
    has(name) { name = String(name); return this._list.some(function (p) { return p[0] === name; }); }
    set(name, value, filename) {
      name = String(name);
      var v = this._value(value, filename), found = false, out = [];
      for (var i = 0; i < this._list.length; i++) {
        if (this._list[i][0] !== name) out.push(this._list[i]);
        else if (!found) { out.push([name, v]); found = true; }
      }
      if (!found) out.push([name, v]);
      this._list = out;
    }
    forEach(fn, thisArg) { for (var i = 0; i < this._list.length; i++) fn.call(thisArg, this._list[i][1], this._list[i][0], this); }
    *entries() { for (var i = 0; i < this._list.length; i++) yield [this._list[i][0], this._list[i][1]]; }
    *keys() { for (var i = 0; i < this._list.length; i++) yield this._list[i][0]; }
    *values() { for (var i = 0; i < this._list.length; i++) yield this._list[i][1]; }
    [Symbol.iterator]() { return this.entries(); }
  }
  define("FormData", FormData);

  // ---- Headers, Request, Response, and fetch through them ----

  class Headers {
    constructor(init) {
      hidden(this, "_list", []);
      if (init === undefined || init === null) return;
      if (init instanceof Headers) { this._list = init._list.map(function (p) { return p.slice(); }); return; }
      if (typeof init[Symbol.iterator] === "function") {
        for (var pair of init) { var p = Array.from(pair); this.append(p[0], p[1]); }
      } else {
        for (var key of Object.keys(init)) this.append(key, init[key]);
      }
    }
    append(name, value) { this._list.push([String(name).toLowerCase(), String(value).trim()]); }
    delete(name) { name = String(name).toLowerCase(); this._list = this._list.filter(function (p) { return p[0] !== name; }); }
    get(name) {
      name = String(name).toLowerCase();
      var found = this._list.filter(function (p) { return p[0] === name; }).map(function (p) { return p[1]; });
      return found.length ? found.join(", ") : null;
    }
    getSetCookie() { return this._list.filter(function (p) { return p[0] === "set-cookie"; }).map(function (p) { return p[1]; }); }
    has(name) { name = String(name).toLowerCase(); return this._list.some(function (p) { return p[0] === name; }); }
    set(name, value) { this.delete(name); this.append(name, value); }
    _sorted() {
      var names = [];
      this._list.forEach(function (p) { if (names.indexOf(p[0]) < 0) names.push(p[0]); });
      names.sort();
      var self = this;
      return names.map(function (n) { return [n, self.get(n)]; });
    }
    forEach(fn, thisArg) { var s = this._sorted(); for (var i = 0; i < s.length; i++) fn.call(thisArg, s[i][1], s[i][0], this); }
    *entries() { yield* this._sorted(); }
    *keys() { for (var p of this._sorted()) yield p[0]; }
    *values() { for (var p of this._sorted()) yield p[1]; }
    [Symbol.iterator]() { return this.entries(); }
  }
  Object.defineProperty(Headers.prototype, Symbol.toStringTag, { value: "Headers", configurable: true });
  define("Headers", Headers);

  // a body, as text or as bytes (a Uint8Array), with the Content-Type it brings (fetch's "extract a
  // body"); text goes as UTF-8
  function extract(body) {
    if (typeof body === "string") return { text: body, type: "text/plain;charset=UTF-8" };
    if (body instanceof URLSearchParams) return { text: body.toString(), type: "application/x-www-form-urlencoded;charset=UTF-8" };
    if (body instanceof FormData) {
      var boundary = "----formdata-phi-" + Math.random().toString(16).slice(2);
      var quoted = function (v) { return String(v).replace(/\r/g, "%0D").replace(/\n/g, "%0A").replace(/"/g, "%22"); };
      var parts = [], text = "", binary = false;
      body._list.forEach(function (p) {
        text += "--" + boundary + "\r\nContent-Disposition: form-data; name=\"" + quoted(p[0]) + "\"";
        if (p[1] instanceof Blob) {
          text += "; filename=\"" + quoted(p[1].name) + "\"\r\nContent-Type: " + (p[1].type || "application/octet-stream") + "\r\n\r\n";
          parts.push(text, p[1]._bytes);
          text = "\r\n";
          binary = true;
        } else {
          text += "\r\n\r\n" + p[1] + "\r\n";
        }
      });
      text += "--" + boundary + "--\r\n";
      var type = "multipart/form-data; boundary=" + boundary;
      if (!binary) return { text: text, type: type };
      parts.push(text);
      return { text: new Blob(parts)._bytes, type: type };
    }
    if (body instanceof Blob) return { text: body._bytes.slice(), type: body.type || null };
    if (body instanceof ArrayBuffer || ArrayBuffer.isView(body)) return { text: bytesOf(body), type: null };
    return { text: String(body), type: "text/plain;charset=UTF-8" };
  }
  function asText(body) { return typeof body === "string" ? body : new TextDecoder().decode(body); }
  function asBuffer(body) { return typeof body === "string" ? new TextEncoder().encode(body).buffer : body.slice().buffer; }
  // the body (text or bytes), and its Content-Type on the headers unless they say one
  function takeBody(body, headers) {
    if (body === undefined || body === null) return "";
    var e = extract(body);
    if (e.type && !headers.has("content-type")) headers.set("content-type", e.type);
    return e.text;
  }
  // what the browser says itself, or mustn't be told by a page (fetch's forbidden request headers)
  var forbidden = /^(accept-charset|accept-encoding|access-control-request-headers|access-control-request-method|connection|content-length|cookie|cookie2|date|dnt|expect|host|keep-alive|origin|referer|set-cookie|te|trailer|transfer-encoding|upgrade|user-agent|via|proxy-.*|sec-.*)$/;
  function headerLines(headers) {
    var text = "";
    headers._list.forEach(function (p) {
      if (forbidden.test(p[0]) || /[\r\n]/.test(p[1])) return;
      text += p[0].replace(/(^|-)[a-z]/g, function (c) { return c.toUpperCase(); }) + ": " + p[1] + "\r\n";
    });
    return text;
  }
  // an answer's status line and header lines into its Headers (not its cookies, which are the
  // browser's): its status text
  function takeHead(text, headers) {
    var lines = String(text).split(/\r?\n/);
    var statusText = "";
    var start = 0;
    var m = /^HTTP\/[\d.]+\s+\d+\s*(.*)$/.exec(lines[0]);
    if (m) { statusText = m[1]; start = 1; }
    for (var i = start; i < lines.length; i++) {
      var colon = lines[i].indexOf(":");
      if (colon <= 0) continue;
      var name = lines[i].slice(0, colon).trim();
      if (/^set-cookie2?$/i.test(name)) continue;
      headers.append(name, lines[i].slice(colon + 1));
    }
    return statusText;
  }

  // the body's methods, shared by Request and Response: the body is text, or the native answer's
  var Body = {
    text: function () {
      if (this._used) return Promise.reject(new TypeError("The body has already been read"));
      this._used = true;
      if (this._native) return this._native.text();
      return Promise.resolve(asText(this._text));
    },
    json: function () { return this.text().then(JSON.parse); },
    arrayBuffer: function () {
      if (this._used) return Promise.reject(new TypeError("The body has already been read"));
      this._used = true;
      if (this._native) return this._native.arrayBuffer();
      return Promise.resolve(asBuffer(this._text));
    },
    bytes: function () { return this.arrayBuffer().then(function (b) { return new Uint8Array(b); }); },
    blob: function () {
      var type = this.headers.get("content-type") || "";
      return this.arrayBuffer().then(function (b) { return new Blob([b], { type: type }); });
    },
    formData: function () {
      return this.text().then(function (t) {
        var f = new FormData();
        new URLSearchParams(t).forEach(function (v, k) { f.append(k, v); });
        return f;
      });
    }
  };

  class Request {
    constructor(input, init) {
      init = init || {};
      // (one made from another is made from what that one holds, not what its getters say now: a
      // page may give a Request a url getter of its own, and fetch still asks for the one it was made with)
      var from = input instanceof Request ? input : null;
      var base = global.document ? documentBase(global.document) : global.location ? global.location.href : undefined;
      hidden(this, "_url", from ? from._url : new URL(String(input), base).href);
      var method = init.method !== undefined ? String(init.method) : from ? from._method : "GET";
      if (/^(delete|get|head|options|post|put)$/i.test(method)) method = method.toUpperCase();
      if (/^(connect|trace|track)$/i.test(method)) throw new TypeError("'" + method + "' HTTP method is unsupported.");
      hidden(this, "_method", method);
      hidden(this, "_headers", new Headers(init.headers || (from ? from._headers : undefined)));
      if ((this._method === "GET" || this._method === "HEAD") && init.body !== undefined && init.body !== null) {
        throw new TypeError("Request with GET/HEAD method cannot have body.");
      }
      hidden(this, "_text", init.body !== undefined ? takeBody(init.body, this._headers) : from ? from._text : "");
      hidden(this, "_signal", init.signal || (from ? from._signal : new AbortSignal()));
      hidden(this, "_used", false);
      hidden(this, "_native", null);
      hidden(this, "_credentials", init.credentials || (from ? from._credentials : "same-origin"));
      hidden(this, "_mode", init.mode || (from ? from._mode : "cors"));
    }
    get url() { return this._url; }
    get method() { return this._method; }
    get headers() { return this._headers; }
    get signal() { return this._signal; }
    get credentials() { return this._credentials; }
    get mode() { return this._mode; }
    get cache() { return "default"; }
    get redirect() { return "follow"; }
    get referrer() { return "about:client"; }
    get bodyUsed() { return this._used; }
    clone() { return new Request(this); }
  }
  Object.assign(Request.prototype, Body);
  Object.defineProperty(Request.prototype, Symbol.toStringTag, { value: "Request", configurable: true });
  define("Request", Request);

  class Response {
    constructor(body, init) {
      init = init || {};
      var status = init.status === undefined ? 200 : init.status | 0;
      if (status < 200 || status > 599) throw new RangeError("A Response's status must be from 200 to 599");
      hidden(this, "_status", status);
      hidden(this, "_statusText", init.statusText === undefined ? "" : String(init.statusText));
      hidden(this, "_headers", new Headers(init.headers));
      hidden(this, "_text", takeBody(body, this._headers));
      hidden(this, "_url", "");
      hidden(this, "_type", "default");
      hidden(this, "_used", false);
      hidden(this, "_native", null);
      hidden(this, "_redirected", false);
    }
    get status() { return this._status; }
    get statusText() { return this._statusText; }
    get ok() { return this._status >= 200 && this._status < 300; }
    get headers() { return this._headers; }
    get url() { return this._url; }
    get type() { return this._type; }
    get redirected() { return this._redirected; }
    get bodyUsed() { return this._used; }
    get body() { return null; }
    clone() {
      if (this._used) throw new TypeError("The body has already been read");
      var r = new Response(null, { status: this._status === 0 ? 200 : this._status, statusText: this._statusText, headers: this._headers });
      r._status = this._status;
      r._text = this._text;
      r._native = this._native;
      r._url = this._url;
      r._type = this._type;
      if (this._native) {
        // each reads the same answer: the native one can be read once, so both keep its text
        var shared = this._native.text();
        var me = this;
        me._native = { text: function () { return shared; }, arrayBuffer: function () { return shared.then(function (t) { return new TextEncoder().encode(t).buffer; }); } };
        r._native = me._native;
      }
      return r;
    }
    static error() { var r = new Response(null); r._status = 0; r._type = "error"; return r; }
    static redirect(url, status) {
      var r = new Response(null, { status: status === undefined ? 302 : status });
      r._headers.set("location", new URL(url, global.location ? global.location.href : undefined).href);
      return r;
    }
    static json(data, init) {
      var r = new Response(JSON.stringify(data), init);
      if (!r._headers.has("content-type")) r._headers.set("content-type", "application/json");
      return r;
    }
  }
  Object.assign(Response.prototype, Body);
  Object.defineProperty(Response.prototype, Symbol.toStringTag, { value: "Response", configurable: true });
  define("Response", Response);

  var nativeFetch = global.fetch;
  if (typeof nativeFetch === "function") {
    hidden(global, "fetch", function fetch(input, init) {
      var req;
      try { req = new Request(input, init); } catch (e) { return Promise.reject(e); }
      if (req._signal.aborted) return Promise.reject(req._signal.reason);
      if (req._url.slice(0, 5) === "blob:") {
        var blob = blobs.get(req._url);
        if (!blob) return Promise.reject(new TypeError("Failed to fetch"));
        var r = new Response(blob, { headers: { "content-type": blob.type } });
        r._native = { text: function () { return blob.text(); }, arrayBuffer: function () { return blob.arrayBuffer(); } };
        return Promise.resolve(r);
      }
      var bodied = req._method !== "GET" && req._method !== "HEAD";
      var options = { method: req._method, headers: headerLines(req._headers), body: bodied ? (typeof req._text === "string" ? req._text : asBuffer(req._text)) : undefined };
      return new Promise(function (resolve, reject) {
        var settled = false;
        req._signal.addEventListener("abort", function () {
          if (!settled) { settled = true; reject(req._signal.reason); }
        });
        nativeFetch(req._url, options).then(function (n) {
          if (settled) return;
          settled = true;
          var r = new Response(null, { status: n.status >= 200 && n.status <= 599 ? n.status : 200 });
          r._statusText = takeHead(n.headers || "", r._headers);
          r._status = n.status;
          r._url = n.url;
          r._type = "basic";
          r._native = n;
          resolve(r);
        }, function (e) {
          if (!settled) { settled = true; reject(e); }
        });
      });
    });
  }

  // ---- events ----

  function eventClass(name, parentClass, fields) {
    if (typeof global[name] !== "undefined" || typeof parentClass !== "function") return;
    var C = class extends parentClass {
      constructor(type, init) {
        super(type, init);
        init = init || {};
        for (var key in fields) {
          Object.defineProperty(this, key, { value: init[key] === undefined ? fields[key] : init[key], enumerable: true, configurable: true });
        }
      }
    };
    Object.defineProperty(C, "name", { value: name });
    hidden(global, name, C);
  }
  var mouse = global.MouseEvent || global.Event;
  eventClass("WheelEvent", mouse, { deltaX: 0, deltaY: 0, deltaZ: 0, deltaMode: 0 });
  eventClass("PointerEvent", mouse, { pointerId: 0, width: 1, height: 1, pressure: 0, tangentialPressure: 0, tiltX: 0, tiltY: 0, twist: 0, pointerType: "mouse", isPrimary: false });
  eventClass("DragEvent", mouse, { dataTransfer: null });
  eventClass("ErrorEvent", global.Event, { message: "", filename: "", lineno: 0, colno: 0, error: undefined });
  eventClass("PromiseRejectionEvent", global.Event, { promise: undefined, reason: undefined });
  eventClass("HashChangeEvent", global.Event, { oldURL: "", newURL: "" });
  eventClass("PopStateEvent", global.Event, { state: null });
  eventClass("PageTransitionEvent", global.Event, { persisted: false });
  eventClass("ProgressEvent", global.Event, { lengthComputable: false, loaded: 0, total: 0 });
  eventClass("AnimationEvent", global.Event, { animationName: "", elapsedTime: 0, pseudoElement: "" });
  eventClass("TransitionEvent", global.Event, { propertyName: "", elapsedTime: 0, pseudoElement: "" });
  eventClass("SubmitEvent", global.Event, { submitter: null });
  eventClass("StorageEvent", global.Event, { key: null, oldValue: null, newValue: null, url: "", storageArea: null });
  eventClass("CompositionEvent", global.UIEvent || global.Event, { data: "" });
  eventClass("ClipboardEvent", global.Event, { clipboardData: null });
  eventClass("BeforeUnloadEvent", global.Event, { returnValue: "" });

  // ---- geometry ----

  class DOMRectReadOnly {
    constructor(x, y, width, height) {
      hidden(this, "_x", +x || 0); hidden(this, "_y", +y || 0);
      hidden(this, "_w", +width || 0); hidden(this, "_h", +height || 0);
    }
    static fromRect(r) { r = r || {}; return new this(r.x, r.y, r.width, r.height); }
    get x() { return this._x; }
    get y() { return this._y; }
    get width() { return this._w; }
    get height() { return this._h; }
    get left() { return Math.min(this._x, this._x + this._w); }
    get right() { return Math.max(this._x, this._x + this._w); }
    get top() { return Math.min(this._y, this._y + this._h); }
    get bottom() { return Math.max(this._y, this._y + this._h); }
    toJSON() { return { x: this.x, y: this.y, width: this.width, height: this.height, top: this.top, right: this.right, bottom: this.bottom, left: this.left }; }
  }
  class DOMRect extends DOMRectReadOnly {
    get x() { return this._x; } set x(v) { this._x = +v; }
    get y() { return this._y; } set y(v) { this._y = +v; }
    get width() { return this._w; } set width(v) { this._w = +v; }
    get height() { return this._h; } set height(v) { this._h = +v; }
  }
  define("DOMRectReadOnly", DOMRectReadOnly);
  define("DOMRect", DOMRect);

  class DOMPointReadOnly {
    constructor(x, y, z, w) {
      hidden(this, "_p", [+x || 0, +y || 0, +z || 0, w === undefined ? 1 : +w]);
    }
    static fromPoint(p) { p = p || {}; return new this(p.x, p.y, p.z, p.w); }
    get x() { return this._p[0]; }
    get y() { return this._p[1]; }
    get z() { return this._p[2]; }
    get w() { return this._p[3]; }
    matrixTransform(m) { return new DOMMatrix(m).transformPoint(this); }
    toJSON() { return { x: this.x, y: this.y, z: this.z, w: this.w }; }
  }
  class DOMPoint extends DOMPointReadOnly {
    get x() { return this._p[0]; } set x(v) { this._p[0] = +v; }
    get y() { return this._p[1]; } set y(v) { this._p[1] = +v; }
    get z() { return this._p[2]; } set z(v) { this._p[2] = +v; }
    get w() { return this._p[3]; } set w(v) { this._p[3] = +v; }
  }
  define("DOMPointReadOnly", DOMPointReadOnly);
  define("DOMPoint", DOMPoint);

  // a 2D matrix: a b c d e f, as CSS's matrix() has them
  class DOMMatrixReadOnly {
    constructor(init) {
      var m = [1, 0, 0, 1, 0, 0];
      if (Array.isArray(init) && init.length >= 6) m = init.slice(0, 6).map(Number);
      else if (init && typeof init === "object" && "a" in init) m = [init.a, init.b, init.c, init.d, init.e, init.f].map(Number);
      else if (typeof init === "string") {
        var found = /matrix\(([^)]*)\)/.exec(init);
        if (found) m = found[1].split(/[\s,]+/).map(Number);
      }
      hidden(this, "_m", m);
    }
    get a() { return this._m[0]; } get b() { return this._m[1]; } get c() { return this._m[2]; }
    get d() { return this._m[3]; } get e() { return this._m[4]; } get f() { return this._m[5]; }
    get m11() { return this._m[0]; } get m12() { return this._m[1]; } get m21() { return this._m[2]; }
    get m22() { return this._m[3]; } get m41() { return this._m[4]; } get m42() { return this._m[5]; }
    get is2D() { return true; }
    get isIdentity() { var m = this._m; return m[0] === 1 && m[1] === 0 && m[2] === 0 && m[3] === 1 && m[4] === 0 && m[5] === 0; }
    multiply(o) {
      var a = this._m, b = new DOMMatrix(o)._m;
      return new DOMMatrix([a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1], a[0] * b[2] + a[2] * b[3],
        a[1] * b[2] + a[3] * b[3], a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5]]);
    }
    translate(x, y) { return this.multiply([1, 0, 0, 1, +x || 0, +y || 0]); }
    scale(sx, sy) { if (sy === undefined) sy = sx; return this.multiply([+sx, 0, 0, +sy, 0, 0]); }
    rotate(deg) { var r = (+deg || 0) * Math.PI / 180, c = Math.cos(r), s = Math.sin(r); return this.multiply([c, s, -s, c, 0, 0]); }
    inverse() {
      var m = this._m, det = m[0] * m[3] - m[1] * m[2];
      if (det === 0) return new DOMMatrix([NaN, NaN, NaN, NaN, NaN, NaN]);
      return new DOMMatrix([m[3] / det, -m[1] / det, -m[2] / det, m[0] / det,
        (m[2] * m[5] - m[3] * m[4]) / det, (m[1] * m[4] - m[0] * m[5]) / det]);
    }
    transformPoint(p) {
      p = p || {};
      var m = this._m, x = +p.x || 0, y = +p.y || 0;
      return new DOMPoint(m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5], +p.z || 0, p.w === undefined ? 1 : p.w);
    }
    toString() { return "matrix(" + this._m.join(", ") + ")"; }
    toJSON() { var m = this._m; return { a: m[0], b: m[1], c: m[2], d: m[3], e: m[4], f: m[5], is2D: true, isIdentity: this.isIdentity }; }
  }
  class DOMMatrix extends DOMMatrixReadOnly { }
  ["a", "b", "c", "d", "e", "f"].forEach(function (k, i) {
    Object.defineProperty(DOMMatrix.prototype, k, { get: function () { return this._m[i]; }, set: function (v) { this._m[i] = +v; }, configurable: true });
  });
  define("DOMMatrixReadOnly", DOMMatrixReadOnly);
  define("DOMMatrix", DOMMatrix);
  define("WebKitCSSMatrix", DOMMatrix);

  // ---- CSS, performance, idle callbacks, errors ----

  var cssEscapeRe = /[\0-\x1f\x7f]|^-?[0-9]|^-$|[^\x80-￿\w-]/g;
  var CSS = global.CSS || {};
  if (typeof CSS.escape !== "function") {
    CSS.escape = function (value) {
      var s = String(value), out = "";
      for (var i = 0; i < s.length; i++) {
        var c = s.charCodeAt(i), ch = s.charAt(i);
        if (c === 0) out += "�";
        else if ((c >= 1 && c <= 31) || c === 127 || (i === 0 && c >= 48 && c <= 57) || (i === 1 && c >= 48 && c <= 57 && s.charCodeAt(0) === 45)) out += "\\" + c.toString(16) + " ";
        else if (i === 0 && c === 45 && s.length === 1) out += "\\" + ch;
        else if (c >= 128 || c === 45 || c === 95 || (c >= 48 && c <= 57) || (c >= 65 && c <= 90) || (c >= 97 && c <= 122)) out += ch;
        else out += "\\" + ch;
      }
      return out;
    };
  }
  if (typeof CSS.supports !== "function") {
    var probe = null;
    CSS.supports = function (property, value) {
      var text = String(property);
      if (value === undefined) {
        var m = /^\s*selector\((.*)\)\s*$/.exec(text);
        if (m) { try { global.document.querySelector(m[1]); return true; } catch (e) { return false; } }
        m = /^\s*\(?\s*([\w-]+)\s*:\s*(.*?)\s*\)?\s*$/.exec(text);
        if (!m) return false;
        text = m[1]; value = m[2];
      }
      if (/^--/.test(text)) return true;
      if (probe === null) probe = global.document.createElement("div");
      probe.style.cssText = "";
      probe.style.setProperty(text, String(value));
      return probe.style.getPropertyValue(text) !== "";
    };
  }
  hidden(global, "CSS", CSS);

  class PerformanceEntry {
    constructor(name, type, start, duration) {
      hidden(this, "_v", [name, type, start, duration]);
    }
    get name() { return this._v[0]; }
    get entryType() { return this._v[1]; }
    get startTime() { return this._v[2]; }
    get duration() { return this._v[3]; }
    toJSON() { return { name: this.name, entryType: this.entryType, startTime: this.startTime, duration: this.duration }; }
  }
  define("PerformanceEntry", PerformanceEntry);
  class PerformanceObserver {
    constructor(callback) {
      if (typeof callback !== "function") throw new TypeError("PerformanceObserver needs a function");
      hidden(this, "_callback", callback);
    }
    observe() { }
    disconnect() { }
    takeRecords() { return []; }
  }
  PerformanceObserver.supportedEntryTypes = [];
  define("PerformanceObserver", PerformanceObserver);

  var idleIds = 0;
  var idleTimers = new Map();
  define("requestIdleCallback", function requestIdleCallback(fn, options) {
    var id = ++idleIds;
    var started = Date.now();
    idleTimers.set(id, setTimeout(function () {
      idleTimers.delete(id);
      fn({ didTimeout: false, timeRemaining: function () { return Math.max(0, 50 - (Date.now() - started)); } });
    }, 1));
    return id;
  });
  define("cancelIdleCallback", function cancelIdleCallback(id) {
    if (idleTimers.has(id)) { clearTimeout(idleTimers.get(id)); idleTimers.delete(id); }
  });
  define("reportError", function reportError(e) { report(e); });

  // ---- crypto ----

  function getRandomValues(array) {
    if (!ArrayBuffer.isView(array) || array instanceof Float32Array || array instanceof Float64Array || array instanceof DataView) {
      throw new DOMException("getRandomValues needs an integer typed array", "TypeMismatchError");
    }
    if (array.byteLength > 65536) throw new DOMException("At most 65536 bytes at once", "QuotaExceededError");
    randomBytes(new Uint8Array(array.buffer, array.byteOffset, array.byteLength));
    return array;
  }
  function randomUUID() {
    var b = getRandomValues(new Uint8Array(16));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    var h = Array.prototype.map.call(b, function (x) { return (x + 256).toString(16).slice(1); }).join("");
    return h.slice(0, 8) + "-" + h.slice(8, 12) + "-" + h.slice(12, 16) + "-" + h.slice(16, 20) + "-" + h.slice(20);
  }
  class Crypto {
    getRandomValues(a) { return getRandomValues(a); }
    randomUUID() { return randomUUID(); }
  }
  if (typeof global.crypto === "undefined" && typeof randomBytes === "function") {
    define("Crypto", Crypto);
    var crypto = new Crypto();
    Object.defineProperty(global, "crypto", { get: function () { return crypto; }, configurable: true, enumerable: true });
  }

  // ---- constructable stylesheets, and adoptedStyleSheets ----
  // A CSSStyleSheet a script makes is parsed by the page once (%sheetSet), and styles each tree that
  // adopts it (%adopt): the document, or a shadow root. Its cssRules are the text of each rule.

  var sheetNew = global["%sheetNew"], sheetSet = global["%sheetSet"], adopt = global["%adopt"];
  delete global["%sheetNew"]; delete global["%sheetSet"]; delete global["%adopt"];

  // a sheet's text, cut into its rules at the top level (strings and comments looked past)
  function splitRules(text) {
    var rules = [], depth = 0, start = 0, i = 0, n = text.length;
    while (i < n) {
      var c = text.charAt(i);
      if (c === "/" && text.charAt(i + 1) === "*") {
        var end = text.indexOf("*/", i + 2);
        i = end < 0 ? n : end + 2;
        // (a comment between rules is no rule's)
        if (depth === 0 && text.slice(start, i).replace(/\/\*[\s\S]*?(\*\/|$)/g, "").trim() === "") start = i;
        continue;
      }
      if (c === "\"" || c === "'") {
        i++;
        while (i < n && text.charAt(i) !== c) i += text.charAt(i) === "\\" ? 2 : 1;
        i++;
        continue;
      }
      if (c === "{") depth++;
      else if (c === "}") {
        depth--;
        if (depth === 0) { var r = text.slice(start, i + 1).trim(); if (r) rules.push(r); start = i + 1; }
      } else if (c === ";" && depth === 0) {
        var at = text.slice(start, i + 1).trim();
        if (at) rules.push(at);
        start = i + 1;
      }
      i++;
    }
    return rules;
  }

  class CSSRule {
    constructor(text, sheet) { hidden(this, "_text", text); hidden(this, "_sheet", sheet); }
    get cssText() { return this._text; }
    get parentStyleSheet() { return this._sheet; }
    get selectorText() { var b = this._text.indexOf("{"); return b < 0 ? "" : this._text.slice(0, b).trim(); }
    get type() { return this._text.charAt(0) === "@" ? 0 : 1; }
  }
  class StyleSheet { }
  class CSSStyleSheet extends StyleSheet {
    constructor(options) {
      super();
      options = options || {};
      hidden(this, "_key", sheetNew());
      hidden(this, "_rules", []);
      hidden(this, "_media", options.media === undefined ? "" : String(options.media));
      hidden(this, "_disabled", !!options.disabled);
    }
    _set() { sheetSet(this._key, this._disabled ? "" : this._rules.join("\n")); }
    get cssRules() { var self = this; return this._rules.map(function (t) { return new CSSRule(t, self); }); }
    get rules() { return this.cssRules; }
    get type() { return "text/css"; }
    get href() { return null; }
    get ownerNode() { return null; }
    get ownerRule() { return null; }
    get parentStyleSheet() { return null; }
    get title() { return null; }
    get media() { return { mediaText: this._media, length: this._media ? 1 : 0 }; }
    get disabled() { return this._disabled; }
    set disabled(v) { this._disabled = !!v; this._set(); }
    replaceSync(text) {
      this._rules = splitRules(String(text)).filter(function (r) { return !/^@import\b/i.test(r); });
      this._set();
    }
    replace(text) {
      try { this.replaceSync(text); } catch (e) { return Promise.reject(e); }
      return Promise.resolve(this);
    }
    insertRule(rule, index) {
      index = index === undefined ? 0 : index >>> 0;
      if (index > this._rules.length) throw new DOMException("The index is past the sheet's end", "IndexSizeError");
      var parts = splitRules(String(rule));
      if (parts.length !== 1) throw new DOMException("insertRule takes one rule", "SyntaxError");
      this._rules.splice(index, 0, parts[0]);
      this._set();
      return index;
    }
    deleteRule(index) {
      index = index >>> 0;
      if (index >= this._rules.length) throw new DOMException("There's no rule there", "IndexSizeError");
      this._rules.splice(index, 1);
      this._set();
    }
    addRule(selector, style, index) {
      return this.insertRule(String(selector) + " { " + String(style === undefined ? "" : style) + " }", index === undefined ? this._rules.length : index);
    }
    removeRule(index) { this.deleteRule(index === undefined ? 0 : index); }
  }
  define("CSSRule", CSSRule);
  define("StyleSheet", StyleSheet);
  define("CSSStyleSheet", CSSStyleSheet);

  var adopted = new WeakMap();
  function adoptedAccessor(proto) {
    if (!proto) return;
    Object.defineProperty(proto, "adoptedStyleSheets", {
      get: function () { return adopted.get(this) || []; },
      set: function (list) {
        var sheets = Array.from(list);
        for (var i = 0; i < sheets.length; i++) {
          if (!(sheets[i] instanceof CSSStyleSheet)) throw new TypeError("adoptedStyleSheets takes CSSStyleSheets");
        }
        adopted.set(this, sheets);
        adopt(this, sheets.map(function (s) { return s._key; }));
      },
      configurable: true, enumerable: true
    });
  }
  adoptedAccessor(global.Document && global.Document.prototype);
  adoptedAccessor(global.ShadowRoot && global.ShadowRoot.prototype);

  // ---- import maps: <script type=importmap>'s JSON, as the page keeps it (page/pmodules.phi) ----
  // [scope, specifier, address, ...]: scope "" for the top level; specifiers that are addresses, and
  // every address and scope, resolved against the page's; what isn't a string is left out

  hidden(global, "%importMap", function (text, base) {
    var map;
    try { map = JSON.parse(text); } catch (e) { throw new TypeError("An import map isn't JSON: " + e.message); }
    var out = [];
    function add(scope, imports) {
      if (!imports || typeof imports !== "object") return;
      for (var key of Object.keys(imports)) {
        var value = imports[key];
        if (typeof value !== "string") continue;
        var k = key;
        if (/^(\/|\.\/|\.\.\/)/.test(key) || URL.canParse(key)) k = new URL(key, base).href;
        var v = URL.parse(value, base);
        if (v !== null) out.push(scope, k, v.href);
      }
    }
    add("", map.imports);
    if (map.scopes && typeof map.scopes === "object") {
      for (var scope of Object.keys(map.scopes)) {
        var su = URL.parse(scope, base);
        if (su !== null) add(su.href, map.scopes[scope]);
      }
    }
    return out;
  });

  // ---- el.attributes: a NamedNodeMap (an array of Attrs, made by the page) ----

  if (global.NamedNodeMap) {
    var nnm = global.NamedNodeMap.prototype;
    var findAttr = function (map, name) {
      for (var i = 0; i < map.length; i++) if (map[i].name === name) return map[i];
      return null;
    };
    hidden(nnm, "item", function item(i) { return this[i] === undefined ? null : this[i]; });
    hidden(nnm, "getNamedItem", function getNamedItem(name) { return findAttr(this, String(name).toLowerCase()) || findAttr(this, String(name)); });
    hidden(nnm, "getNamedItemNS", function getNamedItemNS(ns, local) { return findAttr(this, String(local)); });
    hidden(nnm, "setNamedItem", function setNamedItem(attr) {
      var was = findAttr(this, attr.name);
      this["%owner"].setAttribute(attr.name, attr.value);
      return was;
    });
    hidden(nnm, "setNamedItemNS", nnm.setNamedItem);
    hidden(nnm, "removeNamedItem", function removeNamedItem(name) {
      var was = findAttr(this, String(name));
      if (!was) throw new DOMException("There's no attribute named " + name, "NotFoundError");
      this["%owner"].removeAttribute(name);
      return was;
    });
    hidden(nnm, "removeNamedItemNS", function removeNamedItemNS(ns, local) { return this.removeNamedItem(local); });
  }

  // ---- the window's own objects: their classes' names, and a few more ----

  function nameClass(name, object) {
    if (typeof global[name] !== "undefined" || object === undefined || object === null) return;
    var proto = Object.getPrototypeOf(object);
    if (proto === Object.prototype || proto === null) {
      proto = Object.create(Object.prototype);
      Object.setPrototypeOf(object, proto);
    }
    var C = function () { throw new TypeError("Illegal constructor"); };
    Object.defineProperty(C, "name", { value: name });
    C.prototype = proto;
    hidden(proto, "constructor", C);
    if (!Object.prototype.hasOwnProperty.call(proto, Symbol.toStringTag)) {
      Object.defineProperty(proto, Symbol.toStringTag, { value: name, configurable: true });
    }
    hidden(global, name, C);
  }
  nameClass("History", global.history);
  nameClass("Location", global.location);
  nameClass("Navigator", global.navigator);
  nameClass("Screen", global.screen);
  nameClass("Storage", global.localStorage);
  nameClass("Performance", global.performance);

  if (typeof global.Option === "undefined") {
    hidden(global, "Option", function Option(text, value, defaultSelected, selected) {
      var o = global.document.createElement("option");
      if (text !== undefined) o.textContent = String(text);
      if (value !== undefined) o.setAttribute("value", String(value));
      if (defaultSelected) o.setAttribute("selected", "");
      return o;
    });
  }
  if (typeof global.Audio === "undefined") {
    hidden(global, "Audio", function Audio(src) {
      var a = global.document.createElement("audio");
      if (src !== undefined) a.setAttribute("src", String(src));
      return a;
    });
  }
  if (typeof global.visualViewport === "undefined") {
    var vv = new EventTarget();
    Object.defineProperties(vv, {
      width: { get: function () { return global.innerWidth; }, enumerable: true },
      height: { get: function () { return global.innerHeight; }, enumerable: true },
      offsetLeft: { value: 0, enumerable: true }, offsetTop: { value: 0, enumerable: true },
      pageLeft: { get: function () { return global.scrollX || 0; }, enumerable: true },
      pageTop: { get: function () { return global.scrollY || 0; }, enumerable: true },
      scale: { value: 1, enumerable: true }
    });
    vv.onresize = null; vv.onscroll = null;
    hidden(global, "visualViewport", vv);
  }
  if (typeof global.BroadcastChannel === "undefined") {
    class BroadcastChannel extends EventTarget {
      constructor(name) { super(); hidden(this, "_name", String(name)); this.onmessage = null; this.onmessageerror = null; }
      get name() { return this._name; }
      postMessage() { }
      close() { }
    }
    define("BroadcastChannel", BroadcastChannel);
  }

  // ---- URLs in attributes ----
  // a.href, img.src and the others give the attribute as a whole URL, resolved against the
  // document's base (its first <base href>, else its own URL), or as written when it isn't one;
  // and <a> and <area> give the parts of theirs (protocol, host, pathname ...), which set the
  // attribute when they're set, as URL's do.

  function documentBase(d) {
    var url = d.URL || global.location.href;
    var head = d.head;
    var base = head ? head.querySelector("base[href]") : null;
    if (base) {
      try { return new global.URL(base.getAttribute("href"), url).href; } catch (e) { }
    }
    return url;
  }
  function resolved(el, attr) {
    var v = el.getAttribute(attr);
    if (v === null) return null;
    try { return new global.URL(v, documentBase(el.ownerDocument || global.document)); } catch (e) { return v; }
  }
  function urlProperty(proto, prop, attr, missing) {
    if (!proto) return;
    Object.defineProperty(proto, prop, {
      get: function () {
        var u = resolved(this, attr);
        if (u === null) return missing ? missing(this) : "";
        return typeof u === "string" ? u : u.href;
      },
      set: function (v) { this.setAttribute(attr, String(v)); },
      enumerable: true, configurable: true
    });
  }
  [["HTMLAnchorElement", "href"], ["HTMLAreaElement", "href"], ["HTMLLinkElement", "href"],
   ["HTMLScriptElement", "src"], ["HTMLImageElement", "src"], ["HTMLIFrameElement", "src"],
   ["HTMLInputElement", "src"], ["HTMLVideoElement", "src"], ["HTMLAudioElement", "src"],
   ["HTMLSourceElement", "src"], ["HTMLEmbedElement", "src"], ["HTMLTrackElement", "src"],
   ["HTMLVideoElement", "poster"], ["HTMLObjectElement", "data"],
   ["HTMLInputElement", "formAction", "formaction"], ["HTMLButtonElement", "formAction", "formaction"]
  ].forEach(function (r) {
    var C = global[r[0]];
    urlProperty(C && C.prototype, r[1], r[2] || r[1]);
  });
  // (a form without an action sends to its document's URL)
  if (global.HTMLFormElement) {
    urlProperty(global.HTMLFormElement.prototype, "action", "action", function (form) {
      return (form.ownerDocument || global.document).URL;
    });
  }

  ["HTMLAnchorElement", "HTMLAreaElement"].forEach(function (name) {
    var C = global[name];
    if (!C) return;
    var proto = C.prototype;
    ["protocol", "username", "password", "host", "hostname", "port", "pathname", "search", "hash"].forEach(function (part) {
      Object.defineProperty(proto, part, {
        get: function () {
          var u = resolved(this, "href");
          if (u === null || typeof u === "string") return part === "protocol" ? ":" : "";
          return u[part];
        },
        set: function (v) {
          var u = resolved(this, "href");
          if (u === null || typeof u === "string") return;
          u[part] = v;
          this.setAttribute("href", u.href);
        },
        enumerable: true, configurable: true
      });
    });
    Object.defineProperty(proto, "origin", {
      get: function () {
        var u = resolved(this, "href");
        return u === null || typeof u === "string" ? "" : u.origin;
      },
      enumerable: true, configurable: true
    });
    hidden(proto, "toString", function toString() { return this.href; });
  });
  if (global.HTMLAnchorElement && !Object.getOwnPropertyDescriptor(global.HTMLAnchorElement.prototype, "text")) {
    Object.defineProperty(global.HTMLAnchorElement.prototype, "text", {
      get: function () { return this.textContent; },
      set: function (v) { this.textContent = v; },
      enumerable: true, configurable: true
    });
  }

  // ---- document.domain ----
  // its URL's host (none for a document with an opaque origin); setting it to the host or one of
  // the domains above it is taken, as it was when that relaxed the same-origin rule, and else refused
  if (global.Document && !Object.getOwnPropertyDescriptor(global.Document.prototype, "domain")) {
    Object.defineProperty(global.Document.prototype, "domain", {
      get: function () {
        if (this._domain !== undefined) return this._domain;
        try {
          var u = new global.URL(this.URL);
          return u.protocol === "http:" || u.protocol === "https:" || u.protocol === "file:" ? u.hostname : "";
        } catch (e) { return ""; }
      },
      set: function (v) {
        v = String(v).toLowerCase();
        var now = this.domain;
        if (now === "" || !(v === now || now.slice(-(v.length + 1)) === "." + v)) {
          throw new DOMException("'" + v + "' is not a suffix of '" + now + "'.", "SecurityError");
        }
        if (v !== now && v.indexOf(".") < 0) {
          throw new DOMException("'" + v + "' is a top-level domain.", "SecurityError");
        }
        hidden(this, "_domain", v);
      },
      enumerable: true, configurable: true
    });
  }

  // ---- XMLHttpRequest, made of fetch ----
  // Its states and events as the standard has them, its request headers and body, and its answer
  // as text, JSON, an ArrayBuffer, a Blob or a document. Not kept: waiting for the answer
  // (open(method, url, false) answers later all the same), and progress events while sending.

  var xhrEvents = ["readystatechange", "loadstart", "progress", "abort", "error", "load", "timeout", "loadend"];
  class XMLHttpRequestEventTarget extends EventTarget {
    constructor() {
      super();
      if (new.target === XMLHttpRequestEventTarget) throw new TypeError("Illegal constructor");
    }
  }
  class XMLHttpRequestUpload extends XMLHttpRequestEventTarget {
    constructor(key) {
      if (key !== xhrEvents) throw new TypeError("Illegal constructor");
      super();
      for (var i = 1; i < xhrEvents.length; i++) this["on" + xhrEvents[i]] = null;
    }
  }
  function xhrState(name) {
    return new DOMException("Failed to execute '" + name + "' on 'XMLHttpRequest': the object's state must be OPENED.", "InvalidStateError");
  }
  class XMLHttpRequest extends XMLHttpRequestEventTarget {
    constructor() {
      super();
      for (var i = 0; i < xhrEvents.length; i++) this["on" + xhrEvents[i]] = null;
      hidden(this, "_x", {
        state: 0, sent: false, method: "GET", url: "", headers: new Headers(), status: 0, statusText: "",
        answer: new Headers(), responseURL: "", type: "", text: "", buffer: null, parsed: undefined,
        timeout: 0, credentials: false, control: null, turn: 0, upload: new XMLHttpRequestUpload(xhrEvents)
      });
    }
    get readyState() { return this._x.state; }
    get status() { return this._x.status; }
    get statusText() { return this._x.statusText; }
    get responseURL() { return this._x.responseURL; }
    get upload() { return this._x.upload; }
    get timeout() { return this._x.timeout; }
    set timeout(v) { this._x.timeout = Math.max(0, Number(v) || 0); }
    get withCredentials() { return this._x.credentials; }
    set withCredentials(v) { this._x.credentials = !!v; }
    get responseType() { return this._x.type; }
    set responseType(v) {
      v = String(v);
      if (["", "arraybuffer", "blob", "document", "json", "text"].indexOf(v) < 0) return;
      if (this._x.state === 3 || this._x.state === 4) {
        throw new DOMException("The response type can't be set once loading has started.", "InvalidStateError");
      }
      this._x.type = v;
    }
    get responseText() {
      var x = this._x;
      if (x.type !== "" && x.type !== "text") {
        throw new DOMException("responseText is only there when responseType is '' or 'text' (it is '" + x.type + "')", "InvalidStateError");
      }
      return x.state === 3 || x.state === 4 ? x.text : "";
    }
    get response() {
      var x = this._x;
      if (x.type === "" || x.type === "text") return x.state === 3 || x.state === 4 ? x.text : "";
      if (x.state !== 4 || x.status === 0) return null;
      if (x.parsed === undefined) {
        if (x.type === "json") {
          try { x.parsed = JSON.parse(x.text); } catch (e) { x.parsed = null; }
        } else if (x.type === "arraybuffer") {
          x.parsed = x.buffer;
        } else if (x.type === "blob") {
          x.parsed = new Blob([x.buffer], { type: x.answer.get("content-type") || "" });
        } else {
          x.parsed = this._document();
        }
      }
      return x.parsed;
    }
    get responseXML() {
      var x = this._x;
      if (x.type !== "" && x.type !== "document") {
        throw new DOMException("responseXML is only there when responseType is '' or 'document'", "InvalidStateError");
      }
      if (x.state !== 4 || x.status === 0) return null;
      if (x.parsed === undefined) x.parsed = this._document();
      return x.parsed;
    }
    _document() {
      var kind = (this._x.answer.get("content-type") || "").split(";")[0].trim().toLowerCase();
      if (kind !== "text/html" && kind !== "text/xml" && kind !== "application/xml" && !/\+xml$/.test(kind)) {
        return null;
      }
      try { return new DOMParser().parseFromString(this._x.text, kind === "text/html" ? "text/html" : "application/xml"); } catch (e) { return null; }
    }
    open(method, url) {
      if (arguments.length < 2) throw new TypeError("Failed to execute 'open' on 'XMLHttpRequest': 2 arguments required.");
      method = String(method);
      var upper = method.toUpperCase();
      if (["DELETE", "GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH"].indexOf(upper) >= 0) method = upper;
      if (upper === "CONNECT" || upper === "TRACE" || upper === "TRACK") {
        throw new DOMException("'" + method + "' HTTP method is unsupported.", "SecurityError");
      }
      var full;
      try { full = new URL(String(url), documentBase(global.document)).href; } catch (e) {
        throw new DOMException("Failed to execute 'open' on 'XMLHttpRequest': Invalid URL", "SyntaxError");
      }
      var x = this._x;
      if (x.control) x.control.abort();
      x.control = null;
      x.turn++;
      x.method = method; x.url = full; x.headers = new Headers(); x.sent = false;
      x.status = 0; x.statusText = ""; x.answer = new Headers(); x.responseURL = "";
      x.text = ""; x.buffer = null; x.parsed = undefined;
      if (x.state !== 1) {
        x.state = 1;
        this._fire("readystatechange");
      }
    }
    setRequestHeader(name, value) {
      var x = this._x;
      if (x.state !== 1 || x.sent) throw xhrState("setRequestHeader");
      x.headers.append(name, value);
    }
    getResponseHeader(name) {
      if (this._x.state < 2) return null;
      return this._x.answer.get(name);
    }
    getAllResponseHeaders() {
      if (this._x.state < 2) return "";
      var text = "";
      this._x.answer.forEach(function (v, k) { text += k + ": " + v + "\r\n"; });
      return text;
    }
    overrideMimeType(type) {
      if (this._x.state === 3 || this._x.state === 4) throw new DOMException("overrideMimeType must come before the answer", "InvalidStateError");
    }
    send(body) {
      var x = this._x;
      if (x.state !== 1 || x.sent) throw xhrState("send");
      var init = { method: x.method, headers: x.headers, credentials: x.credentials ? "include" : "same-origin" };
      if (x.method !== "GET" && x.method !== "HEAD" && body !== undefined && body !== null) {
        if (body instanceof global.Document) {
          body = body.documentElement ? body.documentElement.outerHTML : "";
          if (!x.headers.has("content-type")) x.headers.set("content-type", "application/xml;charset=UTF-8");
        }
        init.body = body;
      }
      x.sent = true;
      var control = new AbortController();
      x.control = control;
      init.signal = control.signal;
      var turn = x.turn;
      var self = this;
      this._fire("loadstart", 0, 0, false);
      if (x.timeout > 0) {
        setTimeout(function () {
          if (x.turn !== turn || x.state === 4) return;
          control.abort();
          self._failed("timeout");
        }, x.timeout);
      }
      var binary = x.type === "arraybuffer" || x.type === "blob";
      fetch(x.url, init).then(function (r) {
        if (x.turn !== turn) return;
        x.status = r.status; x.statusText = r.statusText; x.answer = r.headers; x.responseURL = r.url;
        x.state = 2;
        self._fire("readystatechange");
        return (binary ? r.arrayBuffer() : r.text()).then(function (v) {
          if (x.turn !== turn) return;
          var n;
          if (binary) { x.buffer = v; n = v.byteLength; } else { x.text = v; n = v.length; }
          x.state = 3;
          self._fire("readystatechange");
          self._fire("progress", n, n, true);
          x.state = 4;
          x.sent = false;
          x.control = null;
          self._fire("readystatechange");
          self._fire("load", n, n, true);
          self._fire("loadend", n, n, true);
        });
      }).catch(function (e) {
        if (x.turn !== turn) return;
        self._failed("error");
      });
    }
    abort() {
      var x = this._x;
      if (x.control) x.control.abort();
      x.control = null;
      var busy = (x.state === 1 && x.sent) || x.state === 2 || x.state === 3;
      x.turn++;
      if (busy) this._failed("abort");
      if (x.state === 4) {
        x.state = 0;
        x.status = 0; x.statusText = "";
      }
    }
    _failed(type) {
      var x = this._x;
      x.turn++;
      x.state = 4; x.sent = false; x.control = null;
      x.status = 0; x.statusText = ""; x.answer = new Headers(); x.text = ""; x.buffer = null; x.parsed = undefined;
      this._fire("readystatechange");
      this._fire(type, 0, 0, false);
      this._fire("loadend", 0, 0, false);
    }
    _fire(type, loaded, total, computable) {
      var e = type === "readystatechange" ? new Event(type)
        : new ProgressEvent(type, { loaded: loaded || 0, total: total || 0, lengthComputable: !!computable });
      this.dispatchEvent(e);
    }
  }
  ["UNSENT", "OPENED", "HEADERS_RECEIVED", "LOADING", "DONE"].forEach(function (name, i) {
    Object.defineProperty(XMLHttpRequest, name, { value: i, enumerable: true });
    Object.defineProperty(XMLHttpRequest.prototype, name, { value: i, enumerable: true });
  });
  hidden(global, "XMLHttpRequestEventTarget", XMLHttpRequestEventTarget);
  hidden(global, "XMLHttpRequestUpload", XMLHttpRequestUpload);
  hidden(global, "XMLHttpRequest", XMLHttpRequest);

  // ---- <video> and <audio> ----
  // HTMLMediaElement, under both, as the standard has it. This browser plays nothing, and says so as
  // a browser that can't play a file does: canPlayType answers "", play() is refused with a
  // NotSupportedError, and the state is that of a medium with nothing loaded.

  var Media = global.HTMLMediaElement;
  if (Media) {
    ["HTMLVideoElement", "HTMLAudioElement"].forEach(function (name) {
      var C = global[name];
      if (!C || C.prototype instanceof Media) return;
      Object.setPrototypeOf(C.prototype, Media.prototype);
      Object.setPrototypeOf(C, Media);
    });
    var mediaProto = Media.prototype;
    ["NETWORK_EMPTY", "NETWORK_IDLE", "NETWORK_LOADING", "NETWORK_NO_SOURCE"].forEach(function (k, i) {
      Object.defineProperty(Media, k, { value: i, enumerable: true });
      Object.defineProperty(mediaProto, k, { value: i, enumerable: true });
    });
    ["HAVE_NOTHING", "HAVE_METADATA", "HAVE_CURRENT_DATA", "HAVE_FUTURE_DATA", "HAVE_ENOUGH_DATA"].forEach(function (k, i) {
      Object.defineProperty(Media, k, { value: i, enumerable: true });
      Object.defineProperty(mediaProto, k, { value: i, enumerable: true });
    });
    var mediaState = function (el) {
      if (!el._media) {
        hidden(el, "_media", { paused: true, time: 0, volume: 1, muted: el.hasAttribute("muted"), rate: 1, defaultRate: 1 });
      }
      return el._media;
    };
    var noRanges = { length: 0, start: function () { throw new DOMException("There are no ranges", "IndexSizeError"); }, end: function () { throw new DOMException("There are no ranges", "IndexSizeError"); } };
    var later = function (el, type) { setTimeout(function () { el.dispatchEvent(new Event(type)); }, 0); };
    var mediaProps = {
      paused: function () { return mediaState(this).paused; },
      ended: function () { return false; },
      seeking: function () { return false; },
      duration: function () { return NaN; },
      readyState: function () { return 0; },
      networkState: function () { return this.hasAttribute("src") || this.querySelector("source") ? 3 : 0; },
      error: function () { return null; },
      currentSrc: function () { return ""; },
      buffered: function () { return noRanges; },
      seekable: function () { return noRanges; },
      played: function () { return noRanges; },
      textTracks: function () { return []; },
      srcObject: function () { return null; }
    };
    Object.keys(mediaProps).forEach(function (k) {
      Object.defineProperty(mediaProto, k, { get: mediaProps[k], enumerable: true, configurable: true });
    });
    [["currentTime", "time", function (v) { return Number(v) || 0; }],
     ["volume", "volume", function (v) {
       v = Number(v);
       if (!(v >= 0 && v <= 1)) throw new DOMException("The volume provided (" + v + ") is outside the range [0, 1].", "IndexSizeError");
       return v;
     }],
     ["muted", "muted", function (v) { return !!v; }],
     ["playbackRate", "rate", function (v) { return Number(v); }],
     ["defaultPlaybackRate", "defaultRate", function (v) { return Number(v); }]
    ].forEach(function (p) {
      Object.defineProperty(mediaProto, p[0], {
        get: function () { return mediaState(this)[p[1]]; },
        set: function (v) {
          var st = mediaState(this), now = p[2](v);
          if (st[p[1]] === now) return;
          st[p[1]] = now;
          if (p[0] === "volume" || p[0] === "muted") later(this, "volumechange");
          else if (p[0] === "playbackRate") later(this, "ratechange");
        },
        enumerable: true, configurable: true
      });
    });
    ["autoplay", "loop", "controls", "playsInline", "defaultMuted"].forEach(function (k) {
      var attr = k === "playsInline" ? "playsinline" : k === "defaultMuted" ? "muted" : k;
      Object.defineProperty(mediaProto, k, {
        get: function () { return this.hasAttribute(attr); },
        set: function (v) { if (v) this.setAttribute(attr, ""); else this.removeAttribute(attr); },
        enumerable: true, configurable: true
      });
    });
    hidden(mediaProto, "load", function load() {
      var st = mediaState(this);
      st.paused = true;
      st.time = 0;
      if (this.hasAttribute("src") || this.querySelector("source")) {
        later(this, "loadstart");
        later(this, "error");
      } else {
        later(this, "emptied");
      }
    });
    hidden(mediaProto, "play", function play() {
      return Promise.reject(new DOMException("The element has no supported sources.", "NotSupportedError"));
    });
    hidden(mediaProto, "pause", function pause() {
      var st = mediaState(this);
      if (!st.paused) {
        st.paused = true;
        later(this, "pause");
      }
    });
    hidden(mediaProto, "canPlayType", function canPlayType(type) { return ""; });
    hidden(mediaProto, "fastSeek", function fastSeek(t) { this.currentTime = t; });
    hidden(mediaProto, "addTextTrack", function addTextTrack(kind, label, language) {
      return { kind: String(kind), label: label === undefined ? "" : String(label), language: language === undefined ? "" : String(language), mode: "hidden", cues: [], addCue: function () { }, removeCue: function () { } };
    });
    if (global.HTMLVideoElement) {
      ["videoWidth", "videoHeight"].forEach(function (k) {
        Object.defineProperty(global.HTMLVideoElement.prototype, k, { get: function () { return 0; }, enumerable: true, configurable: true });
      });
    }
  }
})(this);
