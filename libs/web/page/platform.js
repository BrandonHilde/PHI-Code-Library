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
//   HTMLMediaElement               under <video> and <audio>: playing them is the page's (page/media.phi)
//   popovers                       showPopover, hidePopover, togglePopover, ToggleEvent (:popover-open)
//   <select> and <option>          options, selectedIndex, value, add, remove; text, selected, index
//   CSS.supports and CSS.escape, PerformanceObserver, requestIdleCallback, reportError,
//   crypto.getRandomValues and randomUUID (from %randomBytes: PHI's crypto.random), visualViewport,
//   and the names of the classes the window's own objects are made from (History, Location ...)
//   Web Animations: element.animate, getAnimations, Animation, KeyframeEffect (time is kept;
//   nothing moves)
// WebSocket (over the host's ws_open, ws_send and ws_close: page/socket.phi), and CloseEvent.
// Streams (ReadableStream, WritableStream, TransformStream, and the text and compression streams).
// Not kept: TouchEvent (a page would take this for a touch screen), workers.
(function (global) {
  "use strict";
  var randomBytes = global["%randomBytes"];
  delete global["%randomBytes"];
  var popoverNative = global["%popover"];
  delete global["%popover"];

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
  // ---- streams: ReadableStream, WritableStream, TransformStream, their readers, writers and
  // controllers, the queuing strategies, TextEncoderStream, TextDecoderStream, CompressionStream and
  // DecompressionStream (over %compress and %decompress). Not kept: byte streams' BYOB readers (a
  // "bytes" stream is read as a default one).
  var compressNative = global["%compress"], decompressNative = global["%decompress"];
  delete global["%compress"]; delete global["%decompress"];
  function settledPromise() {
    var p = {};
    p.promise = new Promise(function (res, rej) { p.resolve = res; p.reject = rej; });
    p.promise.catch(function () { });
    return p;
  }
  function sizeOf(strategy) {
    var f = strategy && strategy.size;
    return typeof f === "function" ? function (c) { return f.call(undefined, c); } : function () { return 1; };
  }
  function highWater(strategy, dflt) {
    if (!strategy || strategy.highWaterMark === undefined) return dflt;
    var h = Number(strategy.highWaterMark);
    if (h !== h || h < 0) throw new RangeError("highWaterMark must be a number that isn't negative");
    return h;
  }
  class CountQueuingStrategy {
    constructor(init) { hidden(this, "_hwm", Number(init.highWaterMark)); }
    get highWaterMark() { return this._hwm; }
    get size() { return function size() { return 1; }; }
  }
  class ByteLengthQueuingStrategy {
    constructor(init) { hidden(this, "_hwm", Number(init.highWaterMark)); }
    get highWaterMark() { return this._hwm; }
    get size() { return function size(chunk) { return chunk.byteLength; }; }
  }
  define("CountQueuingStrategy", CountQueuingStrategy);
  define("ByteLengthQueuingStrategy", ByteLengthQueuingStrategy);

  class ReadableStreamDefaultController {
    constructor(stream) { hidden(this, "_s", stream); }
    get desiredSize() {
      var s = this._s;
      if (s._state === "errored") return null;
      if (s._state === "closed") return 0;
      return s._hwm - s._queueSize;
    }
    enqueue(chunk) {
      var s = this._s;
      if (s._closeRequested || s._state !== "readable") throw new TypeError("The stream is closed or closing");
      if (s._reads.length > 0) {
        s._reads.shift().resolve({ value: chunk, done: false });
      } else {
        var size;
        try { size = s._size(chunk); } catch (e) { this.error(e); throw e; }
        s._queue.push({ value: chunk, size: size });
        s._queueSize += size;
      }
      s._pullIfNeeded();
    }
    close() {
      var s = this._s;
      if (s._closeRequested || s._state !== "readable") throw new TypeError("The stream is closed or closing");
      s._closeRequested = true;
      if (s._queue.length === 0) s._finish();
    }
    error(e) { this._s._error(e); }
  }
  define("ReadableStreamDefaultController", ReadableStreamDefaultController);

  class ReadableStream {
    constructor(source, strategy) {
      source = source || {};
      hidden(this, "_state", "readable");
      hidden(this, "_queue", []);
      hidden(this, "_queueSize", 0);
      hidden(this, "_reads", []);
      hidden(this, "_reader", null);
      hidden(this, "_closeRequested", false);
      hidden(this, "_started", false);
      hidden(this, "_pulling", false);
      hidden(this, "_pullAgain", false);
      hidden(this, "_disturbed", false);
      hidden(this, "_storedError", undefined);
      hidden(this, "_source", source);
      hidden(this, "_size", sizeOf(strategy));
      hidden(this, "_hwm", highWater(strategy, source.type === "bytes" ? 0 : 1));
      hidden(this, "_closedWait", settledPromise());
      var controller = new ReadableStreamDefaultController(this);
      hidden(this, "_controller", controller);
      var self = this;
      var started = typeof source.start === "function" ? source.start.call(source, controller) : undefined;
      Promise.resolve(started).then(function () { self._started = true; self._pullIfNeeded(); }, function (e) { self._error(e); });
    }
    _pullIfNeeded() {
      if (!this._started || this._state !== "readable" || this._closeRequested) return;
      if (this._reads.length === 0 && this._hwm - this._queueSize <= 0) return;
      if (typeof this._source.pull !== "function") return;
      if (this._pulling) { this._pullAgain = true; return; }
      this._pulling = true;
      var self = this;
      var r;
      try { r = this._source.pull.call(this._source, this._controller); } catch (e) { this._error(e); return; }
      Promise.resolve(r).then(function () {
        self._pulling = false;
        if (self._pullAgain) { self._pullAgain = false; self._pullIfNeeded(); }
      }, function (e) { self._error(e); });
    }
    _finish() {
      if (this._state !== "readable") return;
      this._state = "closed";
      while (this._reads.length) this._reads.shift().resolve({ value: undefined, done: true });
      this._closedWait.resolve(undefined);
    }
    _error(e) {
      if (this._state !== "readable") return;
      this._state = "errored";
      this._storedError = e;
      this._queue = [];
      this._queueSize = 0;
      while (this._reads.length) this._reads.shift().reject(e);
      this._closedWait.reject(e);
    }
    _read() {
      this._disturbed = true;
      if (this._queue.length > 0) {
        var item = this._queue.shift();
        this._queueSize -= item.size;
        if (this._queueSize < 0) this._queueSize = 0;
        if (this._closeRequested && this._queue.length === 0) this._finish();
        else this._pullIfNeeded();
        return Promise.resolve({ value: item.value, done: false });
      }
      if (this._state === "closed") return Promise.resolve({ value: undefined, done: true });
      if (this._state === "errored") return Promise.reject(this._storedError);
      var wait = settledPromise();
      this._reads.push(wait);
      this._pullIfNeeded();
      return wait.promise;
    }
    _cancel(reason) {
      this._disturbed = true;
      if (this._state === "closed") return Promise.resolve();
      if (this._state === "errored") return Promise.reject(this._storedError);
      this._queue = [];
      this._queueSize = 0;
      this._finish();
      var src = this._source;
      try { return Promise.resolve(typeof src.cancel === "function" ? src.cancel.call(src, reason) : undefined).then(function () { }); }
      catch (e) { return Promise.reject(e); }
    }
    get locked() { return this._reader !== null; }
    getReader(options) {
      if (options && options.mode !== undefined && String(options.mode) !== "byob") throw new TypeError("A reader's mode is \"byob\" or nothing");
      if (options && options.mode === "byob") throw new TypeError("BYOB readers aren't kept in this browser");
      return new ReadableStreamDefaultReader(this);
    }
    cancel(reason) {
      if (this._reader) return Promise.reject(new TypeError("The stream is locked to a reader"));
      return this._cancel(reason);
    }
    tee() {
      var reader = this.getReader(), c1, c2, cancelled = 0, reading = false;
      function pull() {
        if (reading) return Promise.resolve();
        reading = true;
        return reader.read().then(function (r) {
          reading = false;
          if (r.done) { try { c1.close(); } catch (e) { } try { c2.close(); } catch (e) { } return; }
          try { c1.enqueue(r.value); } catch (e) { }
          try { c2.enqueue(r.value); } catch (e) { }
        }, function (e) { reading = false; c1.error(e); c2.error(e); });
      }
      function cancel() { cancelled++; if (cancelled === 2) return reader.cancel(); }
      var a = new ReadableStream({ start: function (c) { c1 = c; }, pull: pull, cancel: cancel });
      var b = new ReadableStream({ start: function (c) { c2 = c; }, pull: pull, cancel: cancel });
      return [a, b];
    }
    pipeTo(dest, options) {
      options = options || {};
      if (!(dest instanceof WritableStream)) return Promise.reject(new TypeError("pipeTo needs a WritableStream"));
      if (this.locked) return Promise.reject(new TypeError("The stream is locked to a reader"));
      if (dest.locked) return Promise.reject(new TypeError("The writable stream is locked to a writer"));
      var reader = this.getReader(), writer = dest.getWriter();
      var signal = options.signal;
      return new Promise(function (resolve, reject) {
        var done = false;
        function release() { try { reader.releaseLock(); } catch (e) { } try { writer.releaseLock(); } catch (e) { } }
        function fail(e, fromSource) {
          if (done) return;
          done = true;
          if (fromSource) { if (!options.preventAbort) writer.abort(e); }
          else if (!options.preventCancel) reader.cancel(e);
          release();
          reject(e);
        }
        if (signal) {
          if (signal.aborted) { fail(signal.reason, true); if (!options.preventCancel) reader.cancel(signal.reason); return; }
          signal.addEventListener("abort", function () { if (!options.preventCancel) reader.cancel(signal.reason); fail(signal.reason, true); });
        }
        function step() {
          if (done) return;
          reader.read().then(function (r) {
            if (done) return;
            if (r.done) {
              var closing = options.preventClose ? Promise.resolve() : writer.close();
              closing.then(function () { if (!done) { done = true; release(); resolve(); } }, function (e) { fail(e, false); });
              return;
            }
            writer.ready.then(function () { return writer.write(r.value); }).then(step, function (e) { fail(e, false); });
          }, function (e) { fail(e, true); });
        }
        step();
      });
    }
    pipeThrough(pair, options) {
      if (!pair || !(pair.writable instanceof WritableStream) || !(pair.readable instanceof ReadableStream)) throw new TypeError("pipeThrough needs { writable, readable }");
      this.pipeTo(pair.writable, options).catch(function () { });
      return pair.readable;
    }
    values(options) {
      var reader = this.getReader();
      var keep = options && options.preventCancel;
      var it = {
        next: function () { return reader.read().then(function (r) { if (r.done) reader.releaseLock(); return r; }); },
        return: function (v) { var c = keep ? Promise.resolve() : reader.cancel(v); reader.releaseLock(); return c.then(function () { return { value: v, done: true }; }); }
      };
      it[Symbol.asyncIterator] = function () { return it; };
      return it;
    }
    [Symbol.asyncIterator](options) { return this.values(options); }
    static from(iterable) {
      if (iterable instanceof ReadableStream) return iterable;
      var it = iterable[Symbol.asyncIterator] ? iterable[Symbol.asyncIterator]() : iterable[Symbol.iterator]();
      return new ReadableStream({
        pull: function (c) {
          return Promise.resolve(it.next()).then(function (r) {
            if (r.done) c.close();
            else return Promise.resolve(r.value).then(function (v) { c.enqueue(v); });
          });
        },
        cancel: function (reason) { if (typeof it.return === "function") return it.return(reason); }
      }, { highWaterMark: 0 });
    }
  }
  Object.defineProperty(ReadableStream.prototype, Symbol.toStringTag, { value: "ReadableStream", configurable: true });
  define("ReadableStream", ReadableStream);

  class ReadableStreamDefaultReader {
    constructor(stream) {
      if (!(stream instanceof ReadableStream)) throw new TypeError("A reader needs a ReadableStream");
      if (stream._reader) throw new TypeError("The stream is locked to a reader");
      stream._reader = this;
      hidden(this, "_s", stream);
    }
    get closed() { return this._s ? this._s._closedWait.promise : Promise.reject(new TypeError("The reader is released")); }
    read() {
      if (!this._s) return Promise.reject(new TypeError("The reader is released"));
      return this._s._read();
    }
    cancel(reason) {
      if (!this._s) return Promise.reject(new TypeError("The reader is released"));
      return this._s._cancel(reason);
    }
    releaseLock() {
      var s = this._s;
      if (!s) return;
      var e = new TypeError("The reader was released");
      while (s._reads.length) s._reads.shift().reject(e);
      s._reader = null;
      this._s = null;
    }
  }
  define("ReadableStreamDefaultReader", ReadableStreamDefaultReader);

  class WritableStreamDefaultController {
    constructor(stream) { hidden(this, "_s", stream); hidden(this, "_abort", new AbortController()); }
    get signal() { return this._abort.signal; }
    error(e) { this._s._error(e); }
  }
  define("WritableStreamDefaultController", WritableStreamDefaultController);

  class WritableStream {
    constructor(sink, strategy) {
      sink = sink || {};
      hidden(this, "_sink", sink);
      hidden(this, "_state", "writable");
      hidden(this, "_writer", null);
      hidden(this, "_storedError", undefined);
      hidden(this, "_hwm", highWater(strategy, 1));
      hidden(this, "_size", sizeOf(strategy));
      hidden(this, "_pendingSize", 0);
      hidden(this, "_closedWait", settledPromise());
      var controller = new WritableStreamDefaultController(this);
      hidden(this, "_controller", controller);
      var self = this;
      var started = typeof sink.start === "function" ? sink.start.call(sink, controller) : undefined;
      // (each write and the close go one after another, after start)
      hidden(this, "_chain", Promise.resolve(started).catch(function (e) { self._error(e); }));
    }
    _error(e) {
      if (this._state === "errored" || this._state === "closed") return;
      this._state = "errored";
      this._storedError = e;
      this._closedWait.reject(e);
      this._controller._abort.abort(e);
    }
    _write(chunk) {
      var self = this, sink = this._sink;
      if (this._state !== "writable") return Promise.reject(this._state === "errored" ? this._storedError : new TypeError("The stream is closed or closing"));
      var size = 1;
      try { size = this._size(chunk); } catch (e) { this._error(e); return Promise.reject(e); }
      this._pendingSize += size;
      var p = this._chain.then(function () {
        if (self._state === "errored") throw self._storedError;
        return typeof sink.write === "function" ? sink.write.call(sink, chunk, self._controller) : undefined;
      }).then(function () { self._pendingSize -= size; }, function (e) { self._pendingSize -= size; self._error(e); throw e; });
      this._chain = p.catch(function () { });
      return p;
    }
    _close() {
      var self = this, sink = this._sink;
      if (this._state !== "writable") return Promise.reject(new TypeError("The stream is closed or closing"));
      this._state = "closing";
      var p = this._chain.then(function () {
        if (self._state === "errored") throw self._storedError;
        return typeof sink.close === "function" ? sink.close.call(sink) : undefined;
      }).then(function () { self._state = "closed"; self._closedWait.resolve(undefined); }, function (e) { self._state = "writable"; self._error(e); throw e; });
      this._chain = p.catch(function () { });
      return p;
    }
    _abortWith(reason) {
      if (this._state === "closed" || this._state === "errored") return Promise.resolve();
      var sink = this._sink;
      this._error(reason);
      try { return Promise.resolve(typeof sink.abort === "function" ? sink.abort.call(sink, reason) : undefined).then(function () { }); }
      catch (e) { return Promise.reject(e); }
    }
    get locked() { return this._writer !== null; }
    getWriter() { return new WritableStreamDefaultWriter(this); }
    abort(reason) {
      if (this._writer) return Promise.reject(new TypeError("The stream is locked to a writer"));
      return this._abortWith(reason);
    }
    close() {
      if (this._writer) return Promise.reject(new TypeError("The stream is locked to a writer"));
      return this._close();
    }
  }
  Object.defineProperty(WritableStream.prototype, Symbol.toStringTag, { value: "WritableStream", configurable: true });
  define("WritableStream", WritableStream);

  class WritableStreamDefaultWriter {
    constructor(stream) {
      if (!(stream instanceof WritableStream)) throw new TypeError("A writer needs a WritableStream");
      if (stream._writer) throw new TypeError("The stream is locked to a writer");
      stream._writer = this;
      hidden(this, "_s", stream);
    }
    get closed() { return this._s ? this._s._closedWait.promise : Promise.reject(new TypeError("The writer is released")); }
    get ready() { return this._s && this._s._state === "errored" ? Promise.reject(this._s._storedError) : Promise.resolve(undefined); }
    get desiredSize() {
      var s = this._s;
      if (!s) throw new TypeError("The writer is released");
      if (s._state === "errored") return null;
      if (s._state === "closed") return 0;
      return s._hwm - s._pendingSize;
    }
    write(chunk) { return this._s ? this._s._write(chunk) : Promise.reject(new TypeError("The writer is released")); }
    close() { return this._s ? this._s._close() : Promise.reject(new TypeError("The writer is released")); }
    abort(reason) { return this._s ? this._s._abortWith(reason) : Promise.reject(new TypeError("The writer is released")); }
    releaseLock() { if (this._s) { this._s._writer = null; this._s = null; } }
  }
  define("WritableStreamDefaultWriter", WritableStreamDefaultWriter);

  class TransformStreamDefaultController {
    constructor(t) { hidden(this, "_t", t); }
    get desiredSize() { return this._t._rc.desiredSize; }
    enqueue(chunk) { this._t._rc.enqueue(chunk); }
    error(e) { this._t._rc.error(e); this._t._writable._error(e); }
    terminate() { try { this._t._rc.close(); } catch (e) { } this._t._writable._error(new TypeError("The transform stream was terminated")); }
  }
  define("TransformStreamDefaultController", TransformStreamDefaultController);

  class TransformStream {
    constructor(transformer, writableStrategy, readableStrategy) {
      transformer = transformer || {};
      var self = this;
      var tc = new TransformStreamDefaultController(this);
      hidden(this, "_rc", null);
      hidden(this, "_readable", new ReadableStream({
        start: function (c) { self._rc = c; },
        cancel: function (reason) {
          if (typeof transformer.cancel === "function") return transformer.cancel.call(transformer, reason);
          self._writable._error(reason);
        }
      }, readableStrategy || { highWaterMark: 0 }));
      hidden(this, "_writable", new WritableStream({
        // (what the transformer throws, at once or later, errors the readable side too)
        write: function (chunk) {
          return new Promise(function (r) {
            if (typeof transformer.transform === "function") r(transformer.transform.call(transformer, chunk, tc));
            else { tc.enqueue(chunk); r(); }
          }).catch(function (e) { self._rc.error(e); throw e; });
        },
        close: function () {
          return new Promise(function (r) { r(typeof transformer.flush === "function" ? transformer.flush.call(transformer, tc) : undefined); }).then(function () {
            try { self._rc.close(); } catch (e) { }
          }, function (e) { self._rc.error(e); throw e; });
        },
        abort: function (reason) { self._rc.error(reason); }
      }, writableStrategy));
      if (typeof transformer.start === "function") transformer.start.call(transformer, tc);
    }
    get readable() { return this._readable; }
    get writable() { return this._writable; }
  }
  Object.defineProperty(TransformStream.prototype, Symbol.toStringTag, { value: "TransformStream", configurable: true });
  define("TransformStream", TransformStream);

  // the bytes of a chunk written to a byte stream: a view or an ArrayBuffer
  function chunkBytes(chunk) {
    if (chunk instanceof ArrayBuffer) return new Uint8Array(chunk);
    if (ArrayBuffer.isView(chunk)) return new Uint8Array(chunk.buffer, chunk.byteOffset, chunk.byteLength);
    throw new TypeError("The chunk isn't an ArrayBuffer or a view of one");
  }
  function joinBytes(parts, total) {
    var all = new Uint8Array(total), at = 0;
    for (var i = 0; i < parts.length; i++) { all.set(parts[i], at); at += parts[i].length; }
    return all;
  }
  // a stream's chunks, read to its end: the bytes
  function readAllBytes(stream) {
    var reader = stream.getReader(), parts = [], total = 0;
    return new Promise(function (resolve, reject) {
      function step() {
        reader.read().then(function (r) {
          if (r.done) { reader.releaseLock(); resolve(joinBytes(parts, total)); return; }
          var b = typeof r.value === "string" ? new TextEncoder().encode(r.value) : chunkBytes(r.value);
          parts.push(b.slice());
          total += b.length;
          step();
        }, reject);
      }
      step();
    });
  }

  class TextEncoderStream extends TransformStream {
    constructor() {
      var enc = new TextEncoder();
      super({ transform: function (chunk, c) { var s = String(chunk); if (s.length) c.enqueue(enc.encode(s)); } });
    }
    get encoding() { return "utf-8"; }
  }
  define("TextEncoderStream", TextEncoderStream);
  class TextDecoderStream extends TransformStream {
    constructor(label, options) {
      var dec = new TextDecoder(label, options);
      super({
        transform: function (chunk, c) { var s = dec.decode(chunkBytes(chunk), { stream: true }); if (s) c.enqueue(s); },
        flush: function (c) { var s = dec.decode(); if (s) c.enqueue(s); }
      });
      hidden(this, "_dec", dec);
    }
    get encoding() { return this._dec.encoding; }
    get fatal() { return this._dec.fatal; }
    get ignoreBOM() { return this._dec.ignoreBOM; }
  }
  define("TextDecoderStream", TextDecoderStream);

  // gzip, deflate (zlib's) and deflate-raw: what's written is packed (or unpacked) when the stream
  // is closed, and comes out as one chunk
  function packing(format, unpack) {
    format = String(format);
    if (format !== "gzip" && format !== "deflate" && format !== "deflate-raw") throw new TypeError("Unsupported compression format: '" + format + "'");
    var parts = [], total = 0;
    return {
      transform: function (chunk) { var b = chunkBytes(chunk); parts.push(b.slice()); total += b.length; },
      flush: function (c) {
        var all = joinBytes(parts, total);
        var out = (unpack ? decompressNative : compressNative)(format, all.buffer, all.length);
        if (out === null || out === undefined) throw new TypeError(unpack ? "The compressed data is invalid" : "Compression failed");
        if (out.byteLength > 0) c.enqueue(new Uint8Array(out));
      }
    };
  }
  if (typeof compressNative === "function") {
    class CompressionStream extends TransformStream { constructor(format) { super(packing(format, false)); } }
    class DecompressionStream extends TransformStream { constructor(format) { super(packing(format, true)); } }
    define("CompressionStream", CompressionStream);
    define("DecompressionStream", DecompressionStream);
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
    stream() {
      var bytes = this._bytes.slice();
      return new ReadableStream({ start: function (c) { if (bytes.length) c.enqueue(bytes); c.close(); } });
    }
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
      if (form && form.nodeType === 1 && form.querySelectorAll) {
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
    if (body instanceof ReadableStream) {
      if (body.locked || body._disturbed) throw new TypeError("The stream is locked or has been read");
      return { text: { _stream: body }, type: null };
    }
    if (body instanceof ArrayBuffer || ArrayBuffer.isView(body)) return { text: bytesOf(body), type: null };
    return { text: String(body), type: "text/plain;charset=UTF-8" };
  }
  function asText(body) { return typeof body === "string" ? body : new TextDecoder().decode(body); }
  function asBuffer(body) { return typeof body === "string" ? new TextEncoder().encode(body).buffer : body.slice().buffer; }
  // a body that's a stream ({ _stream }): read to its end first
  function bodyThen(body, f) {
    if (body && typeof body === "object" && body._stream) return readAllBytes(body._stream).then(f);
    return Promise.resolve(f(body));
  }
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
      return bodyThen(this._text, asText);
    },
    json: function () { return this.text().then(JSON.parse); },
    arrayBuffer: function () {
      if (this._used) return Promise.reject(new TypeError("The body has already been read"));
      this._used = true;
      if (this._native) return this._native.arrayBuffer();
      return bodyThen(this._text, asBuffer);
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
      hidden(this, "_noBody", body === undefined || body === null);
      hidden(this, "_stream", null);
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
    get bodyUsed() { return this._used || (this._stream !== null && this._stream._disturbed); }
    // its body as a stream: one chunk, once the answer's all come (none for a Response made without one)
    get body() {
      if (this._noBody && !this._native) return null;
      if (this._text && typeof this._text === "object" && this._text._stream) return this._text._stream;
      if (!this._stream) {
        var self = this;
        this._stream = new ReadableStream({
          pull: function (c) {
            return Body.arrayBuffer.call(self).then(function (b) { if (b.byteLength) c.enqueue(new Uint8Array(b)); c.close(); });
          }
        }, { highWaterMark: 0 });
      }
      return this._stream;
    }
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
      if (bodied && req._text && typeof req._text === "object" && req._text._stream) {
        // (a body that's a stream is read to its end, then sent)
        return readAllBytes(req._text._stream).then(function (bytes) { req._text = bytes; return global.fetch(req); });
      }
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
  eventClass("CloseEvent", global.Event, { code: 0, reason: "", wasClean: false });

  // ---- WebSocket: the host's connections (%wsOpen, %wsSend, %wsClose); what happens on them comes
  // back through %wsEvent(id, kind, data, code): 1 open (data the protocol), 2 text, 3 binary (an
  // ArrayBuffer), 4 error, 5 closed (code, data the reason)
  (function () {
    var wsOpen = global["%wsOpen"], wsSend = global["%wsSend"], wsClose = global["%wsClose"];
    delete global["%wsOpen"]; delete global["%wsSend"]; delete global["%wsClose"];
    if (!wsOpen) return;
    var sockets = {};
    // (EventTarget calls onopen and the rest itself)
    var fire = function (sock, ev) { sock.dispatchEvent(ev); };
    var failLater = function (sock) {
      setTimeout(function () {
        sock._state = 3;
        fire(sock, new global.Event("error"));
        fire(sock, new global.CloseEvent("close", { code: 1006, reason: "", wasClean: false }));
      }, 0);
    };
    class WebSocket extends global.EventTarget {
      constructor(url, protocols) {
        super();
        if (arguments.length < 1) throw new TypeError("Failed to construct 'WebSocket': 1 argument required");
        var u = new global.URL(String(url), (global.document && global.document.baseURI) || global.location.href);
        if (u.protocol === "http:") u.protocol = "ws:";
        else if (u.protocol === "https:") u.protocol = "wss:";
        if (u.protocol !== "ws:" && u.protocol !== "wss:") throw new global.DOMException("The URL's scheme must be either 'ws' or 'wss'.", "SyntaxError");
        if (u.hash) throw new global.DOMException("The URL contains a fragment identifier.", "SyntaxError");
        var list = protocols === undefined ? [] : (Array.isArray(protocols) ? protocols.map(String) : [String(protocols)]);
        hidden(this, "_url", u.href);
        hidden(this, "_state", 0);
        hidden(this, "_protocol", "");
        hidden(this, "_binaryType", "blob");
        this.onopen = null; this.onmessage = null; this.onerror = null; this.onclose = null;
        var id = wsOpen(u.href, list.join(", "));
        hidden(this, "_id", id);
        if (id) sockets[id] = this;
        else failLater(this);
      }
      get url() { return this._url; }
      get readyState() { return this._state; }
      get protocol() { return this._protocol; }
      get extensions() { return ""; }
      get bufferedAmount() { return 0; }
      get binaryType() { return this._binaryType; }
      set binaryType(v) { v = String(v); if (v === "blob" || v === "arraybuffer") this._binaryType = v; }
      send(data) {
        if (this._state === 0) throw new global.DOMException("Still in CONNECTING state.", "InvalidStateError");
        if (this._state !== 1) return;
        var id = this._id;
        if (typeof data === "string") { wsSend(id, data, false, 0); return; }
        if (data instanceof ArrayBuffer) { wsSend(id, data, true, data.byteLength); return; }
        if (ArrayBuffer.isView(data)) {
          var copy = new Uint8Array(data.byteLength);
          copy.set(new Uint8Array(data.buffer, data.byteOffset, data.byteLength));
          wsSend(id, copy.buffer, true, copy.byteLength);
          return;
        }
        if (global.Blob && data instanceof global.Blob) {
          data.arrayBuffer().then(function (b) { wsSend(id, b, true, b.byteLength); });
          return;
        }
        wsSend(id, String(data), false, 0);
      }
      close(code, reason) {
        if (code !== undefined) {
          code = Number(code);
          if (code !== 1000 && (code < 3000 || code > 4999)) throw new global.DOMException("The code must be either 1000, or between 3000 and 4999.", "InvalidAccessError");
        }
        if (this._state === 2 || this._state === 3) return;
        if (this._state === 0) { this._state = 3; delete sockets[this._id]; wsClose(this._id, 0, ""); failLater(this); return; }
        this._state = 2;
        wsClose(this._id, code === undefined ? 1000 : code, reason === undefined ? "" : String(reason));
      }
    }
    ["CONNECTING", "OPEN", "CLOSING", "CLOSED"].forEach(function (k, i) {
      Object.defineProperty(WebSocket, k, { value: i, enumerable: true });
      Object.defineProperty(WebSocket.prototype, k, { value: i, enumerable: true });
    });
    define("WebSocket", WebSocket);
    hidden(global, "%wsEvent", function (id, kind, data, code) {
      var sock = sockets[id];
      if (!sock) return;
      if (kind === 1) { sock._state = 1; sock._protocol = data || ""; fire(sock, new global.Event("open")); }
      else if (kind === 2 || kind === 3) {
        if (sock._state !== 1) return;
        var value = data;
        if (kind === 3 && sock._binaryType === "blob" && global.Blob) value = new global.Blob([data]);
        fire(sock, new global.MessageEvent("message", { data: value, origin: new global.URL(sock._url).origin }));
      }
      else if (kind === 4) fire(sock, new global.Event("error"));
      else if (kind === 5) {
        sock._state = 3;
        delete sockets[id];
        fire(sock, new global.CloseEvent("close", { code: code, reason: data || "", wasClean: code !== 1006 }));
      }
    });
  })();
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
  // What's measured: the page's own load (one "navigation" entry) and the marks and measures a
  // script makes. A PerformanceObserver is told of new ones, and with buffered: true of those made
  // before it began, as the standard has it. (Wikipedia's banner code waits for the navigation
  // entry before it shows anything: an observer that took the request and never answered left
  // it waiting for good.) Not measured: resources, paints, long tasks. supportedEntryTypes says
  // so, and observing one of those does nothing, as in a browser that doesn't have it.
  var perf = global.performance;
  var perfEntries = [];
  var perfObservers = [];
  var navEntry = null;
  function navigationEntry() {
    if (!navEntry) {
      navEntry = new PerformanceEntry(String(global.location ? global.location.href : ""), "navigation", 0, perf ? perf.now() : 0);
      ["unloadEventStart", "unloadEventEnd", "redirectStart", "redirectEnd", "workerStart", "fetchStart", "domainLookupStart",
        "domainLookupEnd", "connectStart", "connectEnd", "secureConnectionStart", "requestStart", "responseStart", "responseEnd",
        "domInteractive", "domContentLoadedEventStart", "domContentLoadedEventEnd", "domComplete", "loadEventStart", "loadEventEnd",
        "transferSize", "encodedBodySize", "decodedBodySize", "redirectCount", "responseStatus"].forEach(function (k) {
        Object.defineProperty(navEntry, k, { value: 0, enumerable: true });
      });
      Object.defineProperty(navEntry, "type", { value: "navigate", enumerable: true });
      Object.defineProperty(navEntry, "initiatorType", { value: "navigation", enumerable: true });
      Object.defineProperty(navEntry, "nextHopProtocol", { value: "", enumerable: true });
      Object.defineProperty(navEntry, "serverTiming", { value: Object.freeze([]), enumerable: true });
    }
    return navEntry;
  }
  function entriesOf(type, name) {
    return [navigationEntry()].concat(perfEntries).filter(function (e) {
      return (type === undefined || e.entryType === type) && (name === undefined || e.name === name);
    });
  }
  function perfList(entries) {
    return {
      getEntries: function () { return entries.slice(); },
      getEntriesByType: function (type) { return entries.filter(function (e) { return e.entryType === String(type); }); },
      getEntriesByName: function (name, type) { return entries.filter(function (e) { return e.name === String(name) && (type === undefined || e.entryType === String(type)); }); }
    };
  }
  // the observer hears of these in a task of its own, all that came by then at once
  function perfQueue(observer, entries) {
    if (!entries.length) return;
    for (var i = 0; i < entries.length; i++) observer._queue.push(entries[i]);
    if (observer._pending) return;
    observer._pending = true;
    global.setTimeout(function () {
      observer._pending = false;
      var batch = observer._queue.splice(0);
      if (!batch.length) return;
      observer._callback.call(observer, perfList(batch), observer);
    }, 0);
  }
  function perfAdd(entry) {
    perfEntries.push(entry);
    if (perfEntries.length > 2000) perfEntries.shift();
    perfObservers.forEach(function (o) { if (o._types.indexOf(entry.entryType) >= 0) perfQueue(o, [entry]); });
  }
  function markTime(v, otherwise) {
    if (v === undefined) return otherwise;
    if (typeof v === "number") return v;
    var found = entriesOf("mark", String(v));
    if (found.length) return found[found.length - 1].startTime;
    // (or one of the moments of the page's own loading, by its name in performance.timing)
    var timing = perf && perf.timing;
    if (timing && typeof timing[v] === "number") return timing[v] - (timing.navigationStart || 0);
    throw new DOMException("The mark '" + v + "' does not exist.", "SyntaxError");
  }
  class PerformanceObserver {
    constructor(callback) {
      if (typeof callback !== "function") throw new TypeError("PerformanceObserver needs a function");
      hidden(this, "_callback", callback);
      hidden(this, "_types", []);
      hidden(this, "_queue", []);
      hidden(this, "_pending", false);
    }
    observe(options) {
      if (!options || (options.entryTypes === undefined && options.type === undefined)) throw new TypeError("observe needs entryTypes or a type");
      var asked = options.entryTypes !== undefined ? Array.from(options.entryTypes, String) : [String(options.type)];
      var types = asked.filter(function (t) { return PerformanceObserver.supportedEntryTypes.indexOf(t) >= 0; });
      if (!types.length) return;
      var me = this;
      types.forEach(function (t) { if (me._types.indexOf(t) < 0) me._types.push(t); });
      if (perfObservers.indexOf(this) < 0) perfObservers.push(this);
      if (options.buffered && options.type !== undefined) perfQueue(this, entriesOf(types[0]));
    }
    disconnect() {
      this._types.length = 0;
      this._queue.length = 0;
      var i = perfObservers.indexOf(this);
      if (i >= 0) perfObservers.splice(i, 1);
    }
    takeRecords() { return this._queue.splice(0); }
  }
  PerformanceObserver.supportedEntryTypes = Object.freeze(["mark", "measure", "navigation"]);
  if (perf) {
    hidden(perf, "mark", function mark(name, options) {
      if (arguments.length < 1) throw new TypeError("mark needs a name");
      var e = new PerformanceEntry(String(name), "mark", options && options.startTime !== undefined ? Number(options.startTime) : perf.now(), 0);
      Object.defineProperty(e, "detail", { value: options && options.detail !== undefined ? options.detail : null, enumerable: true });
      perfAdd(e);
      return e;
    });
    hidden(perf, "measure", function measure(name, a, b) {
      if (arguments.length < 1) throw new TypeError("measure needs a name");
      var start = 0, end = perf.now(), detail = null;
      if (a !== null && typeof a === "object") {
        if (a.start !== undefined) start = markTime(a.start, 0);
        if (a.end !== undefined) end = markTime(a.end, end);
        else if (a.duration !== undefined && a.start !== undefined) end = start + Number(a.duration);
        if (a.duration !== undefined && a.start === undefined && a.end !== undefined) start = end - Number(a.duration);
        if (a.detail !== undefined) detail = a.detail;
      } else {
        start = markTime(a === null ? undefined : a, 0);
        end = markTime(b, end);
      }
      var e = new PerformanceEntry(String(name), "measure", start, end - start);
      Object.defineProperty(e, "detail", { value: detail, enumerable: true });
      perfAdd(e);
      return e;
    });
    hidden(perf, "getEntries", function getEntries() { return entriesOf(); });
    hidden(perf, "getEntriesByType", function getEntriesByType(type) { return entriesOf(String(type)); });
    hidden(perf, "getEntriesByName", function getEntriesByName(name, type) { return entriesOf(type === undefined ? undefined : String(type), String(name)); });
    hidden(perf, "clearMarks", function clearMarks(name) {
      perfEntries = perfEntries.filter(function (e) { return e.entryType !== "mark" || (name !== undefined && e.name !== String(name)); });
    });
    hidden(perf, "clearMeasures", function clearMeasures(name) {
      perfEntries = perfEntries.filter(function (e) { return e.entryType !== "measure" || (name !== undefined && e.name !== String(name)); });
    });
  }
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
  // crypto.subtle: digest, SHA-1, SHA-256, SHA-384 and SHA-512 (%digest: PHI's crypto). Not kept
  // yet: keys, signing and encryption.
  var digestNative = global["%digest"];
  delete global["%digest"];
  class SubtleCrypto {
    digest(algorithm, data) {
      var name = String(typeof algorithm === "object" && algorithm !== null ? algorithm.name : algorithm).toUpperCase();
      if (name !== "SHA-1" && name !== "SHA-256" && name !== "SHA-384" && name !== "SHA-512") {
        return Promise.reject(new DOMException("Unrecognized or unsupported algorithm: " + name, "NotSupportedError"));
      }
      var bytes;
      try { bytes = chunkBytes(data).slice(); } catch (e) { return Promise.reject(e); }
      return Promise.resolve(digestNative(name, bytes.buffer, bytes.length));
    }
  }
  define("SubtleCrypto", SubtleCrypto);
  var subtle = typeof digestNative === "function" ? new SubtleCrypto() : undefined;
  class Crypto {
    getRandomValues(a) { return getRandomValues(a); }
    randomUUID() { return randomUUID(); }
    get subtle() { return subtle; }
  }
  if (typeof global.crypto === "undefined" && typeof randomBytes === "function") {
    define("Crypto", Crypto);
    var crypto = new Crypto();
    Object.defineProperty(global, "crypto", { get: function () { return crypto; }, configurable: true, enumerable: true });
  }

  // ---- stylesheets: constructable ones, adoptedStyleSheets, and <style> and <link>'s ----
  // A CSSStyleSheet a script makes is parsed by the page once (%sheetSet), and styles each tree that
  // adopts it (%adopt): the document, or a shadow root. Its cssRules are the text of each rule.
  // A <style>'s sheet (style.sheet, document.styleSheets) has the rules its text has; once a script
  // changes them (insertRule, as styled-components and emotion do) they're what styles the page
  // (%styleText), until the element's text changes, which they're read from again. A <link>'s
  // rules are those of the sheet it brought (%linkText), none until it's come; one from another
  // origin that wasn't asked for by CORS can't be read (SecurityError). Rules a script puts in a
  // <link>'s sheet are kept in it but don't style the page here.

  var sheetNew = global["%sheetNew"], sheetSet = global["%sheetSet"], adopt = global["%adopt"];
  var styleText = global["%styleText"], linkText = global["%linkText"];
  delete global["%sheetNew"]; delete global["%sheetSet"]; delete global["%adopt"]; delete global["%styleText"];
  delete global["%linkText"];

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
    _set() {
      var text = this._disabled ? "" : this._rules.join("\n");
      if (!this._owner) sheetSet(this._key, text);
      else if (this._owner.localName === "style") styleText(this._owner, text);
    }
    // (a <style>'s: its text again if that's changed since its rules were read)
    _sync() {
      var el = this._owner;
      if (el && el.localName === "link") {
        // (read once it's come, from the sheet it brought; again if its href changes)
        var href = el.getAttribute("href");
        if (this._base !== null && this._href === href) return;
        var text = linkText(el);
        if (text === null) { this._rules = []; return; }
        this._href = href;
        this._base = "";
        this._cross = text === false;
        this._rules = text === false ? [] : splitRules(text);
        return;
      }
      if (!el || el.localName !== "style") return;
      var text = el.textContent;
      if (text !== this._base) {
        this._base = text;
        this._rules = splitRules(text);
      }
    }
    get cssRules() {
      this._sync();
      if (this._cross) throw new DOMException("Cannot access rules of a stylesheet from another origin", "SecurityError");
      var self = this;
      return this._rules.map(function (t) { return new CSSRule(t, self); });
    }
    get rules() { return this.cssRules; }
    get type() { return "text/css"; }
    get href() { return this._owner && this._owner.localName === "link" ? this._owner.href : null; }
    get ownerNode() { return this._owner || null; }
    get ownerRule() { return null; }
    get parentStyleSheet() { return null; }
    get title() { return null; }
    get media() {
      var m = this._owner ? (this._owner.getAttribute("media") || "") : this._media;
      return { mediaText: m, length: m ? 1 : 0 };
    }
    get disabled() { return this._disabled; }
    set disabled(v) { this._disabled = !!v; this._set(); }
    replaceSync(text) {
      if (this._owner) throw new DOMException("Only a sheet a script made can be replaced", "NotAllowedError");
      this._rules = splitRules(String(text)).filter(function (r) { return !/^@import\b/i.test(r); });
      this._set();
    }
    replace(text) {
      try { this.replaceSync(text); } catch (e) { return Promise.reject(e); }
      return Promise.resolve(this);
    }
    insertRule(rule, index) {
      this._sync();
      index = index === undefined ? 0 : index >>> 0;
      if (index > this._rules.length) throw new DOMException("The index is past the sheet's end", "IndexSizeError");
      var parts = splitRules(String(rule));
      if (parts.length !== 1) throw new DOMException("insertRule takes one rule", "SyntaxError");
      this._rules.splice(index, 0, parts[0]);
      this._set();
      return index;
    }
    deleteRule(index) {
      this._sync();
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

  // a <style> or <link>'s sheet, the same one each time (none while it's out of the document)
  var ownSheets = new WeakMap();
  function ownSheet(el) {
    if (!el.isConnected) return null;
    if (el.localName === "link" && !/(^|\s)stylesheet(\s|$)/i.test(el.getAttribute("rel") || "")) return null;
    var sheet = ownSheets.get(el);
    if (!sheet) {
      sheet = Object.create(CSSStyleSheet.prototype);
      hidden(sheet, "_key", 0);
      hidden(sheet, "_rules", []);
      hidden(sheet, "_media", "");
      hidden(sheet, "_disabled", false);
      hidden(sheet, "_owner", el);
      hidden(sheet, "_base", null);
      hidden(sheet, "_href", null);
      hidden(sheet, "_cross", false);
      ownSheets.set(el, sheet);
    }
    return sheet;
  }
  ["HTMLStyleElement", "HTMLLinkElement"].forEach(function (name) {
    var ctor = global[name];
    if (ctor && !Object.getOwnPropertyDescriptor(ctor.prototype, "sheet")) {
      Object.defineProperty(ctor.prototype, "sheet", {
        get: function () { return ownSheet(this); }, enumerable: true, configurable: true
      });
    }
  });
  // document.styleSheets: the document's <style>s and stylesheet <link>s, in order (not its shadow
  // trees')
  class StyleSheetList {
    constructor(list) { for (var i = 0; i < list.length; i++) this[i] = list[i]; hidden(this, "_n", list.length); }
    get length() { return this._n; }
    item(i) { i = i >>> 0; return i < this._n ? this[i] : null; }
    [Symbol.iterator]() { return Array.prototype.slice.call(this, 0, this._n)[Symbol.iterator](); }
  }
  define("StyleSheetList", StyleSheetList);
  if (global.Document && !Object.getOwnPropertyDescriptor(global.Document.prototype, "styleSheets")) {
    Object.defineProperty(global.Document.prototype, "styleSheets", {
      get: function () {
        var found = [], els = this.querySelectorAll("style, link");
        for (var i = 0; i < els.length; i++) {
          var sheet = els[i].namespaceURI === "http://www.w3.org/1999/xhtml" ? ownSheet(els[i]) : null;
          if (sheet) found.push(sheet);
        }
        return new StyleSheetList(found);
      },
      enumerable: true, configurable: true
    });
  }

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

  // element.hasAttributeNS(namespace, name)
  if (global.Element && !global.Element.prototype.hasAttributeNS) {
    hidden(global.Element.prototype, "hasAttributeNS", function hasAttributeNS(ns, name) {
      return this.getAttributeNS(ns, name) !== null;
    });
  }

  // element.part, and a link's relList: DOMTokenLists of an attribute's words (classList is the
  // engine's own). Shoelace's icons mark their <svg> with part.add("svg") and stop if it's missing.
  if (global.Element && !Object.getOwnPropertyDescriptor(global.Element.prototype, "part")) {
    var attrWords = function (el, attr) {
      var v = el.getAttribute(attr), out = [];
      if (v) v.split(/[ \t\n\f\r]+/).forEach(function (w) { if (w && out.indexOf(w) < 0) out.push(w); });
      return out;
    };
    var tokenOf = function (t) {
      t = String(t);
      if (t === "") throw new DOMException("The token provided must not be empty.", "SyntaxError");
      if (/[ \t\n\f\r]/.test(t)) throw new DOMException("The token provided ('" + t + "') contains HTML space characters, which are not valid in tokens.", "InvalidCharacterError");
      return t;
    };
    var AttrTokens = function (el, attr) { hidden(this, "_el", el); hidden(this, "_attr", attr); };
    AttrTokens.prototype = Object.create(global.DOMTokenList ? global.DOMTokenList.prototype : Object.prototype);
    var tp = AttrTokens.prototype;
    var keep = function (self, list) { self._el.setAttribute(self._attr, list.join(" ")); };
    Object.defineProperty(tp, "length", { get: function () { return attrWords(this._el, this._attr).length; }, configurable: true });
    Object.defineProperty(tp, "value", {
      get: function () { var v = this._el.getAttribute(this._attr); return v === null ? "" : v; },
      set: function (v) { this._el.setAttribute(this._attr, String(v)); }, configurable: true
    });
    hidden(tp, "item", function (i) { var l = attrWords(this._el, this._attr); i = Math.floor(Number(i)); return i >= 0 && i < l.length ? l[i] : null; });
    hidden(tp, "contains", function (t) { return attrWords(this._el, this._attr).indexOf(String(t)) >= 0; });
    hidden(tp, "add", function () {
      var l = attrWords(this._el, this._attr);
      for (var i = 0; i < arguments.length; i++) { var t = tokenOf(arguments[i]); if (l.indexOf(t) < 0) l.push(t); }
      keep(this, l);
    });
    hidden(tp, "remove", function () {
      var l = attrWords(this._el, this._attr);
      for (var i = 0; i < arguments.length; i++) { var k = l.indexOf(tokenOf(arguments[i])); if (k >= 0) l.splice(k, 1); }
      keep(this, l);
    });
    hidden(tp, "toggle", function (t, force) {
      t = tokenOf(t);
      var has = this.contains(t);
      if (has && force !== true) { this.remove(t); return false; }
      if (!has && force !== false) { this.add(t); return true; }
      return has;
    });
    hidden(tp, "replace", function (a, b) {
      a = tokenOf(a); b = tokenOf(b);
      var l = attrWords(this._el, this._attr), k = l.indexOf(a);
      if (k < 0) return false;
      if (l.indexOf(b) >= 0 && l.indexOf(b) !== k) l.splice(k, 1); else l[k] = b;
      keep(this, l);
      return true;
    });
    hidden(tp, "supports", function () { return true; });
    hidden(tp, "toString", function () { return this.value; });
    hidden(tp, "forEach", function (fn, self) { var l = attrWords(this._el, this._attr); for (var i = 0; i < l.length; i++) fn.call(self, l[i], i, this); });
    hidden(tp, Symbol.iterator, function () { return attrWords(this._el, this._attr)[Symbol.iterator](); });
    var tokensOf = function (attr, key) {
      return {
        get: function () { if (!this[key]) hidden(this, key, new AttrTokens(this, attr)); return this[key]; },
        set: function (v) { this.setAttribute(attr, String(v)); }, configurable: true, enumerable: true
      };
    };
    Object.defineProperty(global.Element.prototype, "part", tokensOf("part", "_partList"));
    ["HTMLAnchorElement", "HTMLAreaElement", "HTMLLinkElement"].forEach(function (k) {
      if (global[k] && !Object.getOwnPropertyDescriptor(global[k].prototype, "relList")) Object.defineProperty(global[k].prototype, "relList", tokensOf("rel", "_relList"));
    });
  }

  // node.isEqualNode(other): the same kind of node, saying the same, with equal children
  if (global.Node && !global.Node.prototype.isEqualNode) {
    var equalNodes = function (a, b) {
      if (a.nodeType !== b.nodeType) return false;
      switch (a.nodeType) {
        case 1:
          if (a.namespaceURI !== b.namespaceURI || a.prefix !== b.prefix || a.localName !== b.localName) return false;
          if (a.attributes.length !== b.attributes.length) return false;
          for (var i = 0; i < a.attributes.length; i++) {
            var at = a.attributes[i];
            if (b.getAttributeNS(at.namespaceURI, at.localName) !== at.value) return false;
          }
          break;
        case 3: case 4: case 8:
          if (a.data !== b.data) return false;
          break;
        case 7:
          if (a.target !== b.target || a.data !== b.data) return false;
          break;
        case 10:
          if (a.name !== b.name || a.publicId !== b.publicId || a.systemId !== b.systemId) return false;
          break;
      }
      var ak = a.childNodes, bk = b.childNodes;
      if (ak.length !== bk.length) return false;
      for (var k = 0; k < ak.length; k++) if (!equalNodes(ak[k], bk[k])) return false;
      return true;
    };
    hidden(global.Node.prototype, "isEqualNode", function isEqualNode(other) {
      if (other === null || other === undefined) return false;
      if (!(other instanceof global.Node)) throw new TypeError("isEqualNode takes a Node");
      return equalNodes(this, other);
    });
  }

  // an <img>'s state: its picture is the browser's to draw, so as far as a script can tell it has
  // come once asked for (its load event says so), with no size of its own to report
  if (global.HTMLImageElement) {
    var imgProto = global.HTMLImageElement.prototype;
    [["complete", function () { return true; }], ["naturalWidth", function () { return 0; }],
     ["naturalHeight", function () { return 0; }], ["currentSrc", function () { return this.src; }]
    ].forEach(function (p) {
      if (!Object.getOwnPropertyDescriptor(imgProto, p[0])) {
        Object.defineProperty(imgProto, p[0], { get: p[1], enumerable: true, configurable: true });
      }
    });
    if (!imgProto.decode) hidden(imgProto, "decode", function decode() { return Promise.resolve(); });
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

  // A <script>'s text: what its text nodes hold, and setting it is setting its text. jQuery runs
  // every script it's handed this way (a page's HTML put in with .html() or .append(), a script it
  // fetched): script.text = code, then into the document. Without it nothing ran, silently.
  if (global.HTMLScriptElement) {
    if (!Object.getOwnPropertyDescriptor(global.HTMLScriptElement.prototype, "text")) {
      Object.defineProperty(global.HTMLScriptElement.prototype, "text", {
        get: function () {
          var out = "";
          for (var c = this.firstChild; c; c = c.nextSibling) if (c.nodeType === 3) out += c.data;
          return out;
        },
        set: function (v) { this.textContent = v === null || v === undefined ? "" : String(v); },
        enumerable: true, configurable: true
      });
    }
    ["async", "defer", "noModule"].forEach(function (k) {
      if (Object.getOwnPropertyDescriptor(global.HTMLScriptElement.prototype, k)) return;
      var attr = k.toLowerCase();
      Object.defineProperty(global.HTMLScriptElement.prototype, k, {
        get: function () { return this.hasAttribute(attr); },
        set: function (v) { if (v) this.setAttribute(attr, ""); else this.removeAttribute(attr); },
        enumerable: true, configurable: true
      });
    });
  }
  if (global.HTMLTitleElement && !Object.getOwnPropertyDescriptor(global.HTMLTitleElement.prototype, "text")) {
    Object.defineProperty(global.HTMLTitleElement.prototype, "text", {
      get: function () { return this.textContent; },
      set: function (v) { this.textContent = v; },
      enumerable: true, configurable: true
    });
  }

  // ---- forms ----
  // A form's fields: form.elements (in order, and by name or id), form.length, and each field's
  // own .form. form.email is the field of that name too, before anything of the form's own: the
  // page's binding looks for it (PageBind.FormHookGet), and asks %radioList for the list when
  // several share the name. submit() and requestSubmit() send the form as its method and enctype
  // say (and its submitter's formaction, formmethod and formenctype): a GET to its address with the
  // fields after a ?, a POST through the host (%post) as application/x-www-form-urlencoded,
  // multipart/form-data or text/plain; reset() puts back what the page wrote. Not kept: files in a
  // multipart form, validation (checkValidity says yes), fields tied to a form by a form="id" attribute from outside it, and
  // a checkbox's or radio button's first state once a script has changed it (checked is its
  // attribute here, so reset() finds it as it is now).
  var LISTED = { BUTTON: 1, FIELDSET: 1, INPUT: 1, OBJECT: 1, OUTPUT: 1, SELECT: 1, TEXTAREA: 1 };
  function formControls(form) {
    var out = [], all = global.Element.prototype.getElementsByTagName.call(form, "*");
    for (var i = 0; i < all.length; i++) {
      var e = all[i];
      if (LISTED[e.tagName] && !(e.tagName === "INPUT" && (e.getAttribute("type") || "").toLowerCase() === "image")) out.push(e);
    }
    return out;
  }
  class RadioNodeList {
    get value() {
      for (var i = 0; i < this.length; i++) {
        var e = this[i];
        if (e.tagName === "INPUT" && (e.getAttribute("type") || "").toLowerCase() === "radio" && e.checked) return e.value === "" && !e.hasAttribute("value") ? "on" : e.value;
      }
      return "";
    }
    set value(v) {
      v = String(v);
      for (var i = 0; i < this.length; i++) {
        var e = this[i];
        if (e.tagName === "INPUT" && (e.getAttribute("type") || "").toLowerCase() === "radio" && (e.value === v || (v === "on" && !e.hasAttribute("value")))) { e.checked = true; return; }
      }
    }
    item(i) { return this[i] || null; }
    forEach(fn, me) { for (var i = 0; i < this.length; i++) fn.call(me, this[i], i, this); }
    [Symbol.iterator]() { return Array.prototype.slice.call(this)[Symbol.iterator](); }
  }
  define("RadioNodeList", RadioNodeList);
  class HTMLFormControlsCollection {
    item(i) { return this[i] || null; }
    namedItem(name) { return namedIn(Array.prototype.slice.call(this), String(name)); }
    [Symbol.iterator]() { return Array.prototype.slice.call(this)[Symbol.iterator](); }
  }
  define("HTMLFormControlsCollection", HTMLFormControlsCollection);
  function listOf(proto, items) {
    var list = Object.create(proto);
    for (var i = 0; i < items.length; i++) list[i] = items[i];
    hidden(list, "length", items.length);
    return list;
  }
  function namedIn(items, name) {
    var found = items.filter(function (e) { return e.id === name || e.getAttribute("name") === name; });
    if (!found.length) return null;
    return found.length === 1 ? found[0] : listOf(RadioNodeList.prototype, found);
  }
  hidden(global, "%radioList", function (form, name) { return namedIn(formControls(form), String(name)); });
  if (global.HTMLFormElement) {
    var formProto = global.HTMLFormElement.prototype;
    Object.defineProperty(formProto, "elements", {
      get: function () {
        var items = formControls(this), list = listOf(HTMLFormControlsCollection.prototype, items), seen = {};
        items.forEach(function (e) {
          [e.id, e.getAttribute("name")].forEach(function (k) {
            if (k && !seen[k] && !(k in list)) { seen[k] = 1; hidden(list, k, namedIn(items, k)); }
          });
        });
        return list;
      },
      enumerable: true, configurable: true
    });
    Object.defineProperty(formProto, "length", { get: function () { return formControls(this).length; }, enumerable: true, configurable: true });
    [["name", "name", ""], ["target", "target", ""], ["acceptCharset", "accept-charset", ""], ["autocomplete", "autocomplete", "on"],
      ["method", "method", "get"], ["enctype", "enctype", "application/x-www-form-urlencoded"], ["encoding", "enctype", "application/x-www-form-urlencoded"]].forEach(function (p) {
      // (method and enctype say what a form without them does, not nothing)
      if (p[2] === "" && Object.getOwnPropertyDescriptor(formProto, p[0])) return;
      Object.defineProperty(formProto, p[0], {
        get: function () { var v = this.getAttribute(p[1]); return v === null ? p[2] : p[0] === "method" ? (/^(post|dialog)$/i.test(v) ? v.toLowerCase() : "get") : v; },
        set: function (v) { this.setAttribute(p[1], String(v)); },
        enumerable: true, configurable: true
      });
    });
    Object.defineProperty(formProto, "noValidate", {
      get: function () { return this.hasAttribute("novalidate"); },
      set: function (v) { if (v) this.setAttribute("novalidate", ""); else this.removeAttribute("novalidate"); },
      enumerable: true, configurable: true
    });
    hidden(formProto, "checkValidity", function checkValidity() { return true; });
    hidden(formProto, "reportValidity", function reportValidity() { return true; });
    var postNative = global["%post"];
    delete global["%post"];
    var formAttr = function (form, submitter, name, own) {
      var v = submitter && submitter.getAttribute && submitter.getAttribute(name);
      if (v !== null && v !== undefined) return v;
      return form.getAttribute(own) || "";
    };
    var goForm = function (form, submitter) {
      var method = String(formAttr(form, submitter, "formmethod", "method") || "get").toLowerCase();
      if (method === "dialog") {
        var d = form.closest && form.closest("dialog");
        if (d && d.close) d.close(submitter && submitter.value !== undefined ? String(submitter.value) : undefined);
        return;
      }
      var to = new global.URL(formAttr(form, submitter, "formaction", "action"), global.document.baseURI || global.location.href);
      var list = [];
      new FormData(form).forEach(function (value, key) { if (typeof value === "string") list.push([key, value]); });
      if (submitter && submitter.getAttribute && submitter.getAttribute("name")) list.push([submitter.getAttribute("name"), String(submitter.value === undefined ? "" : submitter.value)]);
      if (method !== "post") {
        var pairs = new global.URLSearchParams();
        list.forEach(function (kv) { pairs.append(kv[0], kv[1]); });
        to.search = pairs.toString();
        global.location.href = to.href;
        return;
      }
      var enctype = String(formAttr(form, submitter, "formenctype", "enctype")).toLowerCase();
      var type, body;
      if (enctype === "multipart/form-data") {
        var boundary = "----PhiFormBoundary" + Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
        var esc = function (s) { return String(s).replace(/\r\n|\r|\n/g, "%0D%0A").replace(/"/g, "%22"); };
        body = "";
        list.forEach(function (kv) {
          body += "--" + boundary + "\r\nContent-Disposition: form-data; name=\"" + esc(kv[0]) + "\"\r\n\r\n" + String(kv[1]).replace(/\r\n|\r|\n/g, "\r\n") + "\r\n";
        });
        body += "--" + boundary + "--\r\n";
        type = "multipart/form-data; boundary=" + boundary;
      } else if (enctype === "text/plain") {
        body = list.map(function (kv) { return kv[0] + "=" + kv[1] + "\r\n"; }).join("");
        type = "text/plain";
      } else {
        var form_pairs = new global.URLSearchParams();
        list.forEach(function (kv) { form_pairs.append(kv[0], kv[1]); });
        body = form_pairs.toString();
        type = "application/x-www-form-urlencoded";
      }
      if (!postNative || !postNative(to.href, type, body)) {
        if (global.console) global.console.warn("form.submit(): this browser can't send a POST");
      }
    };
    hidden(formProto, "submit", function submit() { goForm(this, null); });
    hidden(formProto, "requestSubmit", function requestSubmit(submitter) {
      var Ev = global.SubmitEvent || global.Event;
      if (this.dispatchEvent(new Ev("submit", { bubbles: true, cancelable: true, submitter: submitter || null }))) goForm(this, submitter || null);
    });
    hidden(formProto, "reset", function reset() {
      if (!this.dispatchEvent(new global.Event("reset", { bubbles: true, cancelable: true }))) return;
      formControls(this).forEach(function (e) {
        if (e.tagName === "INPUT") {
          var type = (e.getAttribute("type") || "").toLowerCase();
          if (type === "checkbox" || type === "radio") e.checked = e.hasAttribute("checked");
          else if (type !== "submit" && type !== "button" && type !== "reset" && type !== "hidden" && type !== "file") e.value = e.getAttribute("value") || "";
        } else if (e.tagName === "TEXTAREA") {
          e.value = e.textContent;
        } else if (e.tagName === "SELECT" && e.options) {
          for (var i = 0; i < e.options.length; i++) e.options[i].selected = e.options[i].hasAttribute("selected");
        }
      });
    });
  }
  ["HTMLInputElement", "HTMLSelectElement", "HTMLTextAreaElement", "HTMLButtonElement", "HTMLFieldSetElement", "HTMLOutputElement",
    "HTMLOptionElement", "HTMLLabelElement", "HTMLObjectElement", "HTMLLegendElement"].forEach(function (name) {
    var C = global[name];
    if (!C || Object.getOwnPropertyDescriptor(C.prototype, "form")) return;
    Object.defineProperty(C.prototype, "form", {
      get: function () {
        var id = this.getAttribute("form");
        if (id !== null && name !== "HTMLOptionElement" && name !== "HTMLLabelElement" && name !== "HTMLLegendElement") {
          var f = global.document.getElementById(id);
          return f && f.tagName === "FORM" ? f : null;
        }
        return this.closest ? this.closest("form") : null;
      },
      enumerable: true, configurable: true
    });
  });

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

  // ---- Web Animations: element.animate(), getAnimations() ----
  // Nothing on the page moves here: an animation keeps time all the same, so what a script waits
  // for comes when it would. It runs for its delay, duration times iterations and endDelay, then
  // is finished: its finished promise resolves and finish fires (one that repeats for ever never
  // is); cancel() rejects the promise (marked handled) and fires cancel. Its keyframes are kept for
  // getKeyframes, and commitStyles writes the last into its element's style. Component libraries
  // (Shoelace, Web Awesome, Material) wait on these before they show a dialog or a menu.

  var running = [];
  function now() { return global.performance ? global.performance.now() : Date.now(); }
  class AnimationPlaybackEvent extends Event {
    constructor(type, init) {
      super(type, init);
      init = init || {};
      hidden(this, "_current", init.currentTime === undefined ? null : init.currentTime);
      hidden(this, "_timeline", init.timelineTime === undefined ? null : init.timelineTime);
    }
    get currentTime() { return this._current; }
    get timelineTime() { return this._timeline; }
  }
  function timingOf(options) {
    var t = { delay: 0, endDelay: 0, fill: "auto", iterationStart: 0, iterations: 1, duration: "auto",
      direction: "normal", easing: "linear" };
    if (typeof options === "number") t.duration = options;
    else if (options && typeof options === "object") {
      for (var k in t) if (options[k] !== undefined) t[k] = options[k];
    }
    if (typeof t.duration === "number" && (t.duration < 0 || t.duration !== t.duration)) throw new TypeError("An animation's duration can't be negative");
    if (t.iterations < 0 || t.iterations !== t.iterations) throw new TypeError("An animation's iterations can't be negative");
    return t;
  }
  // keyframes as a list of them, from a list or from { property: [values] }
  function framesOf(keyframes) {
    if (keyframes === null || keyframes === undefined) return [];
    if (typeof keyframes[Symbol.iterator] === "function") {
      return Array.from(keyframes, function (f) { return Object.assign({}, f); });
    }
    var names = Object.keys(keyframes), most = 0, out = [];
    names.forEach(function (k) { var v = keyframes[k]; most = Math.max(most, Array.isArray(v) ? v.length : 1); });
    for (var i = 0; i < most; i++) {
      var f = {};
      names.forEach(function (k) {
        var v = keyframes[k];
        if (Array.isArray(v)) { if (i < v.length) f[k] = v[i]; }
        else if (i === most - 1) f[k] = v;
      });
      out.push(f);
    }
    return out;
  }
  class AnimationEffect {
    getTiming() { return Object.assign({}, this._timing); }
    getComputedTiming() {
      var t = this._timing, d = typeof t.duration === "number" ? t.duration : 0;
      var active = d * t.iterations;
      return Object.assign({}, t, { duration: d, activeDuration: active, endTime: Math.max(t.delay + active + t.endDelay, 0),
        localTime: null, progress: null, currentIteration: null });
    }
    updateTiming(options) { this._timing = timingOf(Object.assign(this.getTiming(), options || {})); }
  }
  class KeyframeEffect extends AnimationEffect {
    constructor(target, keyframes, options) {
      super();
      if (target instanceof KeyframeEffect) {
        hidden(this, "_target", target._target);
        hidden(this, "_frames", target._frames.slice());
        hidden(this, "_timing", Object.assign({}, target._timing));
        return;
      }
      hidden(this, "_target", target || null);
      hidden(this, "_frames", framesOf(keyframes));
      hidden(this, "_timing", timingOf(options));
    }
    get target() { return this._target; }
    set target(t) { this._target = t; }
    get pseudoElement() { return null; }
    get composite() { return "replace"; }
    getKeyframes() {
      var n = this._frames.length;
      return this._frames.map(function (f, i) {
        return Object.assign({ offset: f.offset === undefined ? null : f.offset,
          computedOffset: f.offset !== undefined ? f.offset : (n > 1 ? i / (n - 1) : 1), easing: "linear", composite: "auto" }, f);
      });
    }
    setKeyframes(keyframes) { this._frames = framesOf(keyframes); }
  }
  class Animation extends EventTarget {
    constructor(effect, timeline) {
      super();
      hidden(this, "_effect", effect || null);
      hidden(this, "_state", "idle");
      hidden(this, "_timer", 0);
      hidden(this, "_began", 0);
      hidden(this, "_held", 0);
      hidden(this, "_rate", 1);
      hidden(this, "_resolve", null);
      hidden(this, "_reject", null);
      hidden(this, "_finished", null);
      this._promise();
      this.id = "";
      this.onfinish = null;
      this.oncancel = null;
      this.onremove = null;
    }
    _promise() {
      var self = this;
      this._finished = new Promise(function (resolve, reject) { self._resolve = resolve; self._reject = reject; });
      this._finished.catch(function () {});
    }
    // how long it runs, in ms: Infinity if it repeats for ever
    _length() {
      if (!this._effect || !this._effect._timing) return 0;
      var t = this._effect.getComputedTiming();
      return t.endTime;
    }
    _elapsed() {
      if (this._state === "running") return (now() - this._began) * Math.abs(this._rate);
      return this._held;
    }
    _schedule() {
      var self = this, left = this._length() - this._elapsed();
      clearTimeout(this._timer);
      if (left === Infinity) return;
      this._timer = setTimeout(function () { self._done(); }, Math.max(0, left / Math.max(Math.abs(this._rate), 0.0001)));
    }
    _listed(on) {
      var i = running.indexOf(this);
      if (on && i < 0) running.push(this);
      else if (!on && i >= 0) running.splice(i, 1);
    }
    _done() {
      clearTimeout(this._timer);
      this._held = this._length();
      this._state = "finished";
      this._listed(false);
      this._resolve(this);
      var self = this, at = this._held;
      setTimeout(function () { self.dispatchEvent(new AnimationPlaybackEvent("finish", { currentTime: at, timelineTime: now() })); }, 0);
    }
    get effect() { return this._effect; }
    set effect(e) { this._effect = e; }
    get timeline() { return global.document ? global.document.timeline : null; }
    get playState() { return this._state; }
    get pending() { return false; }
    get replaceState() { return "active"; }
    get ready() { return Promise.resolve(this); }
    get finished() { return this._finished; }
    get playbackRate() { return this._rate; }
    set playbackRate(r) { this._rate = +r; if (this._state === "running") this._schedule(); }
    updatePlaybackRate(r) { this.playbackRate = r; }
    get startTime() { return this._state === "running" ? this._began : null; }
    set startTime(t) { if (t !== null) { this._began = +t; if (this._state === "running") this._schedule(); } }
    get currentTime() { return this._state === "idle" ? null : this._elapsed(); }
    set currentTime(t) {
      t = +t;
      if (this._state === "running") { this._began = now() - t; this._schedule(); }
      else { this._held = t; if (this._state === "idle") this._state = "paused"; }
    }
    play() {
      if (this._state === "running") return;
      if (this._state === "finished" || this._state === "idle") {
        if (this._state === "finished") this._promise();
        this._held = 0;
      }
      this._state = "running";
      this._began = now() - this._held;
      this._listed(true);
      this._schedule();
    }
    pause() {
      if (this._state === "paused" || this._state === "finished") return;
      this._held = this._elapsed();
      clearTimeout(this._timer);
      this._state = "paused";
      this._listed(true);
    }
    finish() {
      if (this._length() === Infinity) throw new DOMException("An animation that repeats for ever can't be finished", "InvalidStateError");
      if (this._state !== "finished") this._done();
    }
    cancel() {
      if (this._state === "idle") return;
      clearTimeout(this._timer);
      this._state = "idle";
      this._held = 0;
      this._listed(false);
      this._reject(new DOMException("The animation was canceled", "AbortError"));
      this._promise();
      var self = this;
      setTimeout(function () { self.dispatchEvent(new AnimationPlaybackEvent("cancel", { timelineTime: now() })); }, 0);
    }
    reverse() { this._rate = -this._rate; this._held = 0; if (this._state === "finished") this._promise(); this._state = "idle"; this.play(); }
    persist() {}
    commitStyles() {
      var effect = this._effect, target = effect && effect._target;
      if (!target || !target.style || !effect._frames.length) return;
      var last = effect._frames[effect._frames.length - 1];
      for (var k in last) {
        if (k === "offset" || k === "easing" || k === "composite") continue;
        try { target.style[k] = last[k]; } catch (e) { }
      }
    }
  }
  class DocumentTimeline {
    constructor() { }
    get currentTime() { return now(); }
  }
  define("AnimationPlaybackEvent", AnimationPlaybackEvent);
  define("AnimationEffect", AnimationEffect);
  define("KeyframeEffect", KeyframeEffect);
  define("Animation", Animation);
  define("AnimationTimeline", DocumentTimeline);
  define("DocumentTimeline", DocumentTimeline);
  if (global.Element && !global.Element.prototype.animate) {
    hidden(global.Element.prototype, "animate", function animate(keyframes, options) {
      var a = new Animation(new KeyframeEffect(this, keyframes, options));
      if (options && typeof options === "object" && options.id !== undefined) a.id = String(options.id);
      a.play();
      return a;
    });
    hidden(global.Element.prototype, "getAnimations", function getAnimations(options) {
      var el = this, deep = !!(options && options.subtree);
      return running.filter(function (a) {
        var t = a._effect && a._effect._target;
        return t === el || (deep && t && el.contains(t));
      });
    });
  }
  if (global.Document && !global.Document.prototype.getAnimations) {
    var timeline = new DocumentTimeline();
    hidden(global.Document.prototype, "getAnimations", function getAnimations() { return running.slice(); });
    Object.defineProperty(global.Document.prototype, "timeline", { get: function () { return timeline; }, configurable: true, enumerable: true });
  }

  // ---- document.fonts (a FontFaceSet) and FontFace ----
  // The faces are the page's @font-face rules, through %fontFaces() (each [family, lowest weight,
  // highest weight, style]), and any a script adds. A face is taken as loaded: the host fetches a
  // rule's font when text is drawn in it, and a FontFace a script makes isn't drawn with (yet).
  // What pages ask of it is mostly document.fonts.load(font).then(faces => ...) and
  // document.fonts.ready, to know when to show text in a web font (FontFaceObserver).

  var facesNative = global["%fontFaces"];
  delete global["%fontFaces"];
  if (facesNative && global.Document && !("fonts" in global.Document.prototype)) {
    var FontFace = function FontFace(family, source, descriptors) {
      if (!(this instanceof FontFace)) throw new TypeError("Failed to construct 'FontFace': Please use the 'new' operator");
      if (arguments.length < 2) throw new TypeError("Failed to construct 'FontFace': 2 arguments required, but only " + arguments.length + " present.");
      var d = descriptors || {};
      hidden(this, "_family", String(family).replace(/^\s*["']|["']\s*$/g, ""));
      hidden(this, "_style", d.style !== undefined ? String(d.style) : "normal");
      hidden(this, "_weight", d.weight !== undefined ? String(d.weight) : "normal");
      hidden(this, "_stretch", d.stretch !== undefined ? String(d.stretch) : "normal");
      hidden(this, "_unicodeRange", d.unicodeRange !== undefined ? String(d.unicodeRange) : "U+0-10FFFF");
      hidden(this, "_display", d.display !== undefined ? String(d.display) : "auto");
      var self = this;
      hidden(this, "_status", "unloaded");
      hidden(this, "_loaded", new Promise(function (resolve) { hidden(self, "_resolve", resolve); }));
      if (typeof source !== "string") this.load();
    };
    ["family", "style", "weight", "stretch", "unicodeRange", "display"].forEach(function (k) {
      Object.defineProperty(FontFace.prototype, k, {
        get: function () { return this["_" + k]; },
        set: function (v) { this["_" + k] = String(v); },
        configurable: true, enumerable: true
      });
    });
    ["featureSettings", "variationSettings"].forEach(function (k) {
      Object.defineProperty(FontFace.prototype, k, { get: function () { return "normal"; }, set: function () {}, configurable: true, enumerable: true });
    });
    Object.defineProperty(FontFace.prototype, "status", { get: function () { return this._status; }, configurable: true, enumerable: true });
    Object.defineProperty(FontFace.prototype, "loaded", { get: function () { return this._loaded; }, configurable: true, enumerable: true });
    hidden(FontFace.prototype, "load", function load() {
      if (this._status !== "loaded") {
        this._status = "loaded";
        this._resolve(this);
      }
      return this._loaded;
    });
    hidden(global, "FontFace", FontFace);

    // the page's rules as faces: the same object for the same rule each time it's asked
    var ruleFaces = {};
    var fromRules = function () {
      var list = facesNative() || [];
      var out = [];
      for (var i = 0; i < list.length; i++) {
        var r = list[i];
        var weight = r[1] === r[2] ? String(r[1]) : r[1] + " " + r[2];
        var key = r[0] + "|" + weight + "|" + r[3];
        var face = ruleFaces[key];
        if (!face) {
          face = new FontFace(r[0], "local()", { weight: weight, style: r[3] });
          face.load();
          ruleFaces[key] = face;
        }
        out.push(face);
      }
      return out;
    };
    var added = [];
    var all = function () { return fromRules().concat(added); };
    // the families a CSS font shorthand names ("bold 16px 'Noto Sans', serif"), lower case
    var families = function (font) {
      var m = /(?:^|\s)(?:[\d.]+(?:px|pt|pc|em|rem|ex|ch|%|vw|vh|vmin|vmax|in|cm|mm|q)|xx-small|x-small|small|medium|large|x-large|xx-large|xxx-large|smaller|larger)(?:\s*\/\s*\S+)?\s+(.+)$/i.exec(String(font).trim());
      if (!m) throw new DOMException("Could not resolve '" + font + "' as a font.", "SyntaxError");
      return m[1].split(",").map(function (s) { return s.trim().replace(/^["']|["']$/g, "").toLowerCase(); });
    };
    var matching = function (font) {
      var names = families(font);
      return all().filter(function (f) { return names.indexOf(f.family.toLowerCase()) >= 0; });
    };

    var FontFaceSet = function FontFaceSet() { throw new TypeError("Illegal constructor"); };
    var fonts = new EventTarget();
    Object.setPrototypeOf(FontFaceSet.prototype, EventTarget.prototype);
    Object.setPrototypeOf(fonts, FontFaceSet.prototype);
    hidden(global, "FontFaceSet", FontFaceSet);
    var ready = Promise.resolve(fonts);
    Object.defineProperty(FontFaceSet.prototype, "ready", { get: function () { return ready; }, configurable: true, enumerable: true });
    Object.defineProperty(FontFaceSet.prototype, "status", { get: function () { return "loaded"; }, configurable: true, enumerable: true });
    Object.defineProperty(FontFaceSet.prototype, "size", { get: function () { return all().length; }, configurable: true, enumerable: true });
    ["onloading", "onloadingdone", "onloadingerror"].forEach(function (k) {
      var store = null;
      Object.defineProperty(FontFaceSet.prototype, k, { get: function () { return store; }, set: function (v) { store = v; }, configurable: true, enumerable: true });
    });
    hidden(FontFaceSet.prototype, "load", function load(font, text) {
      try {
        var faces = matching(font);
        return Promise.all(faces.map(function (f) { return f.load(); }));
      } catch (e) {
        return Promise.reject(e);
      }
    });
    hidden(FontFaceSet.prototype, "check", function check(font, text) {
      var faces = matching(font);
      for (var i = 0; i < faces.length; i++) if (faces[i].status !== "loaded") return false;
      return true;
    });
    hidden(FontFaceSet.prototype, "add", function add(face) {
      if (!(face instanceof FontFace)) throw new TypeError("Failed to execute 'add' on 'FontFaceSet': parameter 1 is not of type 'FontFace'.");
      if (added.indexOf(face) < 0) added.push(face);
      return this;
    });
    hidden(FontFaceSet.prototype, "delete", function (face) {
      var i = added.indexOf(face);
      if (i < 0) return false;
      added.splice(i, 1);
      return true;
    });
    hidden(FontFaceSet.prototype, "has", function has(face) { return all().indexOf(face) >= 0; });
    hidden(FontFaceSet.prototype, "clear", function clear() { added.length = 0; });
    hidden(FontFaceSet.prototype, "forEach", function forEach(fn, that) {
      var list = all();
      for (var i = 0; i < list.length; i++) fn.call(that, list[i], list[i], this);
    });
    hidden(FontFaceSet.prototype, "values", function values() { return all()[Symbol.iterator](); });
    hidden(FontFaceSet.prototype, "keys", FontFaceSet.prototype.values);
    hidden(FontFaceSet.prototype, "entries", function entries() { return all().map(function (f) { return [f, f]; })[Symbol.iterator](); });
    hidden(FontFaceSet.prototype, Symbol.iterator, FontFaceSet.prototype.values);
    Object.defineProperty(global.Document.prototype, "fonts", { get: function () { return fonts; }, configurable: true, enumerable: true });
  }

  // ---- <video> and <audio> ----
  // HTMLMediaElement, under both, as the standard has it. What's playing, its clock and its events
  // are the page's own (page/media.phi), asked through %media(element, what, value): 0 the state
  // as a list, 1 load(), 2 play() (an error code, 0 for none), 3 pause(), 4 seek to a time, 5 the
  // volume, 6 muted, 7 the rate, 8 canPlayType's answer (0 "", 1 "maybe", 2 "probably").

  var Media = global.HTMLMediaElement;
  var mediaNative = global["%media"];
  delete global["%media"];
  if (Media && mediaNative) {
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
    // the state: paused, ended, seeking, readyState, networkState, error, duration, currentTime,
    // videoWidth, videoHeight, currentSrc, volume, muted, playbackRate
    var state = function (el) { return mediaNative(el, 0); };
    var errors = [null];
    var MediaError = function MediaError(code) {
      hidden(this, "_code", code);
    };
    Object.defineProperty(MediaError.prototype, "code", { get: function () { return this._code; }, enumerable: true, configurable: true });
    Object.defineProperty(MediaError.prototype, "message", { get: function () {
      return ["", "The fetching process was aborted", "A network error made it fail", "It couldn't be decoded",
        "Its format isn't one this browser plays"][this._code] || "";
    }, enumerable: true, configurable: true });
    ["MEDIA_ERR_ABORTED", "MEDIA_ERR_NETWORK", "MEDIA_ERR_DECODE", "MEDIA_ERR_SRC_NOT_SUPPORTED"].forEach(function (k, i) {
      Object.defineProperty(MediaError, k, { value: i + 1, enumerable: true });
      Object.defineProperty(MediaError.prototype, k, { value: i + 1, enumerable: true });
    });
    define("MediaError", MediaError);
    var ranges = function (end) {
      return {
        length: end > 0 ? 1 : 0,
        start: function (i) { if (i !== 0 || !(end > 0)) throw new DOMException("There's no range " + i, "IndexSizeError"); return 0; },
        end: function (i) { if (i !== 0 || !(end > 0)) throw new DOMException("There's no range " + i, "IndexSizeError"); return end; }
      };
    };
    var mediaProps = {
      paused: function () { return state(this)[0]; },
      ended: function () { return state(this)[1]; },
      seeking: function () { return state(this)[2]; },
      readyState: function () { return state(this)[3]; },
      networkState: function () { return state(this)[4]; },
      error: function () { var c = state(this)[5]; return c ? new MediaError(c) : null; },
      duration: function () { var s = state(this); return s[3] > 0 ? s[6] : NaN; },
      currentSrc: function () { return state(this)[10]; },
      videoWidth: function () { return state(this)[8]; },
      videoHeight: function () { return state(this)[9]; },
      buffered: function () { var s = state(this); return ranges(s[3] > 0 ? s[6] : 0); },
      seekable: function () { var s = state(this); return ranges(s[3] > 0 ? s[6] : 0); },
      played: function () { return ranges(0); },
      textTracks: function () { return []; },
      srcObject: function () { return null; }
    };
    Object.keys(mediaProps).forEach(function (k) {
      Object.defineProperty(mediaProto, k, { get: mediaProps[k], enumerable: true, configurable: true });
    });
    Object.defineProperty(mediaProto, "currentTime", {
      get: function () { return state(this)[7]; },
      set: function (v) { v = Number(v); if (v === v) mediaNative(this, 4, v); },
      enumerable: true, configurable: true
    });
    Object.defineProperty(mediaProto, "volume", {
      get: function () { return state(this)[11]; },
      set: function (v) {
        v = Number(v);
        if (!(v >= 0 && v <= 1)) throw new DOMException("The volume provided (" + v + ") is outside the range [0, 1].", "IndexSizeError");
        mediaNative(this, 5, v);
      },
      enumerable: true, configurable: true
    });
    Object.defineProperty(mediaProto, "muted", {
      get: function () { return state(this)[12]; },
      set: function (v) { mediaNative(this, 6, !!v); },
      enumerable: true, configurable: true
    });
    Object.defineProperty(mediaProto, "playbackRate", {
      get: function () { return state(this)[13]; },
      set: function (v) { mediaNative(this, 7, Number(v)); },
      enumerable: true, configurable: true
    });
    Object.defineProperty(mediaProto, "defaultPlaybackRate", {
      get: function () { return this._defaultRate === undefined ? 1 : this._defaultRate; },
      set: function (v) { hidden(this, "_defaultRate", Number(v)); },
      enumerable: true, configurable: true
    });
    ["autoplay", "loop", "controls", "playsInline", "defaultMuted"].forEach(function (k) {
      var attr = k === "playsInline" ? "playsinline" : k === "defaultMuted" ? "muted" : k;
      Object.defineProperty(mediaProto, k, {
        get: function () { return this.hasAttribute(attr); },
        set: function (v) { if (v) this.setAttribute(attr, ""); else this.removeAttribute(attr); },
        enumerable: true, configurable: true
      });
    });
    Object.defineProperty(mediaProto, "preload", {
      get: function () { var v = (this.getAttribute("preload") || "").toLowerCase(); return v === "none" || v === "metadata" ? v : "auto"; },
      set: function (v) { this.setAttribute("preload", String(v)); },
      enumerable: true, configurable: true
    });
    hidden(mediaProto, "load", function load() { mediaNative(this, 1); });
    hidden(mediaProto, "play", function play() {
      var el = this;
      if (mediaNative(el, 2)) {
        return Promise.reject(new DOMException("The element has no supported sources.", "NotSupportedError"));
      }
      var s = state(el);
      if (!s[0] && s[3] >= 2) return Promise.resolve();
      return new Promise(function (resolve, reject) {
        var done = function () {
          el.removeEventListener("playing", ok);
          el.removeEventListener("error", bad);
          el.removeEventListener("pause", stopped);
        };
        var ok = function () { done(); resolve(); };
        var bad = function () { done(); reject(new DOMException("Failed to load because no supported source was found.", "NotSupportedError")); };
        var stopped = function () { done(); reject(new DOMException("The play() request was interrupted by a call to pause().", "AbortError")); };
        el.addEventListener("playing", ok);
        el.addEventListener("error", bad);
        el.addEventListener("pause", stopped);
      });
    });
    hidden(mediaProto, "pause", function pause() { mediaNative(this, 3); });
    hidden(mediaProto, "canPlayType", function canPlayType(type) { return ["", "maybe", "probably"][mediaNative(this, 8, String(type))] || ""; });
    hidden(mediaProto, "fastSeek", function fastSeek(t) { this.currentTime = t; });
    hidden(mediaProto, "addTextTrack", function addTextTrack(kind, label, language) {
      return { kind: String(kind), label: label === undefined ? "" : String(label), language: language === undefined ? "" : String(language), mode: "hidden", cues: [], addCue: function () { }, removeCue: function () { } };
    });
    // new Audio(src): an <audio> with preload auto
    if (global.HTMLAudioElement && typeof global.Audio === "undefined") {
      var Audio = function Audio(src) {
        var a = document.createElement("audio");
        a.setAttribute("preload", "auto");
        if (src !== undefined) a.setAttribute("src", String(src));
        return a;
      };
      Audio.prototype = global.HTMLAudioElement.prototype;
      define("Audio", Audio);
    }
  }

  // ---- popovers ----
  // An element with a popover attribute is hidden until it's shown (css/ua.phi:
  // [popover]:not(:popover-open)); showPopover, hidePopover and togglePopover say which, with the
  // beforetoggle and toggle events the standard has. Not kept: light dismiss (a click outside
  // closing an "auto" one), and closing other auto popovers when one opens.
  if (global.HTMLElement && !global.HTMLElement.prototype.showPopover) {
    if (typeof global.ToggleEvent === "undefined") {
      class ToggleEvent extends Event {
        constructor(type, init) {
          super(type, init);
          init = init || {};
          hidden(this, "_old", String(init.oldState || ""));
          hidden(this, "_new", String(init.newState || ""));
        }
        get oldState() { return this._old; }
        get newState() { return this._new; }
      }
      define("ToggleEvent", ToggleEvent);
    }
    var openPopovers = new WeakSet();
    var settle = function (el, open, force) {
      if (!el.hasAttribute("popover")) {
        throw new DOMException("Not supported on elements that do not have a valid value for the 'popover' attribute.", "NotSupportedError");
      }
      var was = openPopovers.has(el);
      if (was === open) return was;
      var before = new global.ToggleEvent("beforetoggle", { cancelable: open, oldState: was ? "open" : "closed", newState: open ? "open" : "closed" });
      if (!el.dispatchEvent(before) && open) return was;
      if (open) openPopovers.add(el); else openPopovers.delete(el);
      popoverNative(el, open);
      var after = new global.ToggleEvent("toggle", { oldState: was ? "open" : "closed", newState: open ? "open" : "closed" });
      setTimeout(function () { el.dispatchEvent(after); }, 0);
      return open;
    };
    var hp = global.HTMLElement.prototype;
    hidden(hp, "showPopover", function showPopover() { settle(this, true); });
    hidden(hp, "hidePopover", function hidePopover() { settle(this, false); });
    hidden(hp, "togglePopover", function togglePopover(force) {
      var open = force === undefined ? !openPopovers.has(this) : !!force;
      return settle(this, open);
    });
  }

  // ---- <select> and <option> ----
  // What scripts build and read menus with. Which options are selected is their selected attributes
  // (what the browser shows is the first of them); a single select with none selected shows its
  // first option, and says so.
  if (global.HTMLSelectElement && !global.HTMLSelectElement.prototype.add) {
    var sp = global.HTMLSelectElement.prototype, op = global.HTMLOptionElement.prototype;
    var optionsOf = function (sel) {
      var list = [];
      for (var c = sel.firstElementChild; c; c = c.nextElementSibling) {
        if (c.localName === "option") list.push(c);
        else if (c.localName === "optgroup") {
          for (var g = c.firstElementChild; g; g = g.nextElementSibling) if (g.localName === "option") list.push(g);
        }
      }
      return list;
    };
    var selectOf = function (opt) {
      var p = opt.parentElement;
      if (p && p.localName === "optgroup") p = p.parentElement;
      return p && p.localName === "select" ? p : null;
    };
    var chosen = function (sel) {
      var list = optionsOf(sel);
      for (var i = 0; i < list.length; i++) if (list[i].hasAttribute("selected")) return i;
      return list.length && !sel.multiple ? 0 : -1;
    };
    var choose = function (sel, index) {
      var list = optionsOf(sel);
      for (var i = 0; i < list.length; i++) {
        if (i === index) list[i].setAttribute("selected", "");
        else if (!sel.multiple || index < 0) list[i].removeAttribute("selected");
      }
    };
    var collection = function (sel) {
      var list = optionsOf(sel);
      list.item = function (i) { return list[i] || null; };
      list.namedItem = function (n) { return list.find(function (o) { return o.id === n || o.getAttribute("name") === n; }) || null; };
      list.add = function (el, before) { sel.add(el, before); };
      list.remove = function (i) { sel.remove(i); };
      Object.defineProperty(list, "selectedIndex", { get: function () { return sel.selectedIndex; }, set: function (v) { sel.selectedIndex = v; } });
      return list;
    };
    Object.defineProperties(sp, {
      options: { get: function () { return collection(this); }, configurable: true, enumerable: true },
      length: {
        get: function () { return optionsOf(this).length; },
        set: function (n) {
          var list = optionsOf(this);
          n = Math.max(0, n >>> 0);
          while (list.length > n) list.pop().remove();
          for (var i = list.length; i < n; i++) this.appendChild(global.document.createElement("option"));
        },
        configurable: true, enumerable: true
      },
      selectedIndex: {
        get: function () { return chosen(this); },
        set: function (i) { choose(this, i | 0); },
        configurable: true, enumerable: true
      },
      value: {
        get: function () { var i = chosen(this); return i < 0 ? "" : optionsOf(this)[i].value; },
        set: function (v) {
          v = String(v);
          var list = optionsOf(this), at = -1;
          for (var i = 0; i < list.length; i++) if (list[i].value === v) { at = i; break; }
          choose(this, at);
        },
        configurable: true, enumerable: true
      },
      selectedOptions: {
        get: function () { var self = this, i = chosen(this); return optionsOf(this).filter(function (o, k) { return o.hasAttribute("selected") || (k === i && !self.multiple); }); },
        configurable: true, enumerable: true
      },
      type: { get: function () { return this.multiple ? "select-multiple" : "select-one"; }, configurable: true, enumerable: true }
    });
    hidden(sp, "add", function add(el, before) {
      var ref = typeof before === "number" ? (optionsOf(this)[before] || null) : (before || null);
      if (ref) ref.parentNode.insertBefore(el, ref); else this.appendChild(el);
    });
    hidden(sp, "item", function item(i) { return optionsOf(this)[i] || null; });
    hidden(sp, "namedItem", function namedItem(n) { return collection(this).namedItem(n); });
    var removeSelf = global.Element.prototype.remove;
    hidden(sp, "remove", function remove(index) {
      if (arguments.length === 0) return removeSelf.call(this);
      var o = optionsOf(this)[index];
      if (o) o.remove();
    });
    Object.defineProperties(op, {
      text: {
        get: function () { return this.textContent.replace(/[ \t\n\f\r]+/g, " ").trim(); },
        set: function (v) { this.textContent = String(v); },
        configurable: true, enumerable: true
      },
      index: {
        get: function () { var sel = selectOf(this); return sel ? optionsOf(sel).indexOf(this) : 0; },
        configurable: true, enumerable: true
      },
      selected: {
        get: function () { var sel = selectOf(this); return this.hasAttribute("selected") || (!!sel && !sel.multiple && chosen(sel) === optionsOf(sel).indexOf(this)); },
        set: function (v) {
          var sel = selectOf(this);
          if (v && sel && !sel.multiple) choose(sel, optionsOf(sel).indexOf(this));
          else if (v) this.setAttribute("selected", "");
          else this.removeAttribute("selected");
        },
        configurable: true, enumerable: true
      },
      // (an option with no value attribute has its text for its value)
      value: {
        get: function () { var v = this.getAttribute("value"); return v === null ? this.text : v; },
        set: function (v) { this.setAttribute("value", String(v)); },
        configurable: true, enumerable: true
      },
      defaultSelected: {
        get: function () { return this.hasAttribute("selected"); },
        set: function (v) { if (v) this.setAttribute("selected", ""); else this.removeAttribute("selected"); },
        configurable: true, enumerable: true
      },
      label: {
        get: function () { return this.hasAttribute("label") ? this.getAttribute("label") : this.text; },
        set: function (v) { this.setAttribute("label", String(v)); },
        configurable: true, enumerable: true
      }
    });
  }
})(this);
