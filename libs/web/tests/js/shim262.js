// Stand-ins for builtins that aren't written yet, for running test262's language tests only: its
// harness and many of its tests use them in passing, which says nothing about the language. Each one
// is defined only if the real thing is missing, so as builtins arrive this file fades away. It
// isn't part of the engine, and pages never see it.
(function (g) {
  function def(o, name, f) {
    if (typeof o[name] === 'undefined') {
      Object.defineProperty(o, name, { value: f, writable: true, configurable: true, enumerable: false });
    }
  }
  if (typeof g.Math === 'undefined') {
    Object.defineProperty(g, 'Math', { value: {}, writable: true, configurable: true, enumerable: false });
  }
  var M = g.Math;
  def(M, 'floor', function (x) { x = +x; var t = x | 0; if (x !== x || x === Infinity || x === -Infinity) return x; if (t === x) return x; if (x > 2147483647 || x < -2147483648) return x; return x < t ? t - 1 : t; });
  def(M, 'ceil', function (x) { return -M.floor(-x); });
  def(M, 'abs', function (x) { x = +x; return x < 0 ? -x : (x === 0 ? 0 : x); });
  def(M, 'max', function () { var r = -Infinity; for (var i = 0; i < arguments.length; i++) { var v = +arguments[i]; if (v !== v) return NaN; if (v > r) r = v; } return r; });
  def(M, 'min', function () { var r = Infinity; for (var i = 0; i < arguments.length; i++) { var v = +arguments[i]; if (v !== v) return NaN; if (v < r) r = v; } return r; });
  def(M, 'pow', function (a, b) { return a ** b; });
  def(M, 'sqrt', function (a) { return a ** 0.5; });
  def(M, 'round', function (x) { return M.floor(+x + 0.5); });
  def(M, 'random', function () { return 0.5; });
  def(M, 'trunc', function (x) { return x < 0 ? M.ceil(x) : M.floor(x); });
  def(M, 'sign', function (x) { x = +x; return x > 0 ? 1 : x < 0 ? -1 : x; });
  if (typeof M.PI === 'undefined') M.PI = 3.141592653589793;

  var AP = Array.prototype, SP = String.prototype;
  def(AP, 'forEach', function (f, t) { for (var i = 0; i < this.length; i++) if (i in this) f.call(t, this[i], i, this); });
  def(AP, 'map', function (f, t) { var r = []; for (var i = 0; i < this.length; i++) if (i in this) r[i] = f.call(t, this[i], i, this); r.length = this.length; return r; });
  def(AP, 'filter', function (f, t) { var r = []; for (var i = 0; i < this.length; i++) if (i in this && f.call(t, this[i], i, this)) r.push(this[i]); return r; });
  def(AP, 'some', function (f, t) { for (var i = 0; i < this.length; i++) if (i in this && f.call(t, this[i], i, this)) return true; return false; });
  def(AP, 'every', function (f, t) { for (var i = 0; i < this.length; i++) if (i in this && !f.call(t, this[i], i, this)) return false; return true; });
  def(AP, 'reduce', function (f, v) { var i = 0; if (arguments.length < 2) v = this[i++]; for (; i < this.length; i++) if (i in this) v = f(v, this[i], i, this); return v; });
  def(AP, 'includes', function (x) { for (var i = 0; i < this.length; i++) { var e = this[i]; if (e === x || (e !== e && x !== x)) return true; } return false; });
  def(AP, 'concat', function () { var r = []; function add(v) { if (Array.isArray(v)) { for (var i = 0; i < v.length; i++) r.push(v[i]); } else r.push(v); } add(this); for (var i = 0; i < arguments.length; i++) add(arguments[i]); return r; });
  def(AP, 'reverse', function () { for (var i = 0, j = this.length - 1; i < j; i++, j--) { var t = this[i]; this[i] = this[j]; this[j] = t; } return this; });
  def(AP, 'shift', function () { if (this.length === 0) return undefined; var v = this[0]; for (var i = 1; i < this.length; i++) this[i - 1] = this[i]; this.length--; return v; });
  def(AP, 'unshift', function () { var n = arguments.length; for (var i = this.length - 1; i >= 0; i--) this[i + n] = this[i]; for (var j = 0; j < n; j++) this[j] = arguments[j]; return this.length; });
  def(AP, 'splice', function (s, d) { var out = this.slice(s, s + d); var rest = this.slice(s + d); this.length = s; for (var i = 2; i < arguments.length; i++) this.push(arguments[i]); for (var j = 0; j < rest.length; j++) this.push(rest[j]); return out; });
  def(AP, 'sort', function (c) { c = c || function (a, b) { a = String(a); b = String(b); return a < b ? -1 : a > b ? 1 : 0; }; for (var i = 1; i < this.length; i++) { var v = this[i], j = i - 1; while (j >= 0 && c(this[j], v) > 0) { this[j + 1] = this[j]; j--; } this[j + 1] = v; } return this; });
  def(AP, 'lastIndexOf', function (x) { for (var i = this.length - 1; i >= 0; i--) if (this[i] === x) return i; return -1; });
  def(Array, 'from', function (x) { var r = []; if (x[Symbol.iterator]) { for (var v of x) r.push(v); } else { for (var i = 0; i < x.length; i++) r.push(x[i]); } return r; });
  def(Array, 'of', function () { var r = []; for (var i = 0; i < arguments.length; i++) r.push(arguments[i]); return r; });

  def(SP, 'substring', function (a, b) { var s = String(this); var n = s.length; a = a === undefined ? 0 : M.min(M.max(a | 0, 0), n); b = b === undefined ? n : M.min(M.max(b | 0, 0), n); return a < b ? s.slice(a, b) : s.slice(b, a); });
  def(SP, 'substr', function (a, n) { var s = String(this); return s.slice(a, n === undefined ? undefined : a + n); });
  def(SP, 'split', function (sep) { var s = String(this), r = [], from = 0; if (sep === undefined) return [s]; sep = String(sep); if (sep === '') { for (var k = 0; k < s.length; k++) r.push(s.charAt(k)); return r; } for (;;) { var i = s.indexOf(sep, from); if (i < 0) break; r.push(s.slice(from, i)); from = i + sep.length; } r.push(s.slice(from)); return r; });
  def(SP, 'replace', function (a, b) { var s = String(this); a = String(a); var i = s.indexOf(a); if (i < 0) return s; return s.slice(0, i) + (typeof b === 'function' ? b(a, i, s) : b) + s.slice(i + a.length); });
  def(SP, 'concat', function () { var s = String(this); for (var i = 0; i < arguments.length; i++) s += arguments[i]; return s; });
  def(SP, 'includes', function (x) { return String(this).indexOf(x) >= 0; });
  def(SP, 'startsWith', function (x) { return String(this).indexOf(x) === 0; });
  def(SP, 'lastIndexOf', function (x) { var s = String(this), r = -1, i = -1; while ((i = s.indexOf(x, i + 1)) >= 0) r = i; return r; });
  def(SP, 'toLowerCase', function () { var s = String(this), r = ''; for (var i = 0; i < s.length; i++) { var c = s.charCodeAt(i); r += (c >= 65 && c <= 90) ? String.fromCharCode(c + 32) : s.charAt(i); } return r; });
  def(SP, 'toUpperCase', function () { var s = String(this), r = ''; for (var i = 0; i < s.length; i++) { var c = s.charCodeAt(i); r += (c >= 97 && c <= 122) ? String.fromCharCode(c - 32) : s.charAt(i); } return r; });
  def(SP, 'codePointAt', function (i) { var s = String(this), c = s.charCodeAt(i); if (c >= 0xD800 && c < 0xDC00) { var d = s.charCodeAt(i + 1); if (d >= 0xDC00 && d < 0xE000) return (c - 0xD800) * 1024 + (d - 0xDC00) + 0x10000; } return c === c ? c : undefined; });
  def(SP, 'padStart', function (n, f) { var s = String(this); f = f === undefined ? ' ' : String(f); while (s.length < n) s = f + s; return s; });
  def(SP, 'trim', function () { var s = String(this), a = 0, b = s.length; while (a < b && s.charCodeAt(a) <= 32) a++; while (b > a && s.charCodeAt(b - 1) <= 32) b--; return s.slice(a, b); });
  def(String, 'fromCodePoint', function (c) { if (c < 0x10000) return String.fromCharCode(c); c -= 0x10000; return String.fromCharCode(0xD800 + (c >> 10), 0xDC00 + (c & 1023)); });
  def(String, 'raw', function (t) { var r = '', n = t.raw.length; for (var i = 0; i < n; i++) { r += t.raw[i]; if (i + 1 < n && i + 1 < arguments.length) r += arguments[i + 1]; } return r; });

  def(Object, 'assign', function (t) { for (var i = 1; i < arguments.length; i++) { var s = arguments[i]; if (s === null || s === undefined) continue; var k = Object.keys(s); for (var j = 0; j < k.length; j++) t[k[j]] = s[k[j]]; var y = Object.getOwnPropertySymbols(s); for (var q = 0; q < y.length; q++) if (Object.prototype.propertyIsEnumerable.call(s, y[q])) t[y[q]] = s[y[q]]; } return t; });
  def(Object, 'entries', function (o) { return Object.keys(o).map(function (k) { return [k, o[k]]; }); });
  def(Object, 'values', function (o) { return Object.keys(o).map(function (k) { return o[k]; }); });
  def(Object, 'getOwnPropertyDescriptors', function (o) { var r = {}; Object.getOwnPropertyNames(o).forEach(function (k) { r[k] = Object.getOwnPropertyDescriptor(o, k); }); return r; });
  def(Object, 'isSealed', function (o) { if (Object(o) !== o) return true; if (Object.isExtensible(o)) return false; return Object.getOwnPropertyNames(o).every(function (k) { return !Object.getOwnPropertyDescriptor(o, k).configurable; }); });
  def(Object, 'fromEntries', function (e) { var r = {}; for (var p of e) r[p[0]] = p[1]; return r; });
  def(Object.prototype, '__lookupGetter__', function (k) { var o = this; while (o) { var d = Object.getOwnPropertyDescriptor(o, k); if (d) return d.get; o = Object.getPrototypeOf(o); } });
  def(Object.prototype, '__lookupSetter__', function (k) { var o = this; while (o) { var d = Object.getOwnPropertyDescriptor(o, k); if (d) return d.set; o = Object.getPrototypeOf(o); } });
  def(Object.prototype, '__defineGetter__', function (k, f) { Object.defineProperty(this, k, { get: f, enumerable: true, configurable: true }); });
  def(Object.prototype, '__defineSetter__', function (k, f) { Object.defineProperty(this, k, { set: f, enumerable: true, configurable: true }); });

  def(g, 'parseInt', function (s, r) { s = String(s).trim(); r = r | 0; var neg = false, v = 0, any = false, i = 0; if (s.charAt(0) === '-' || s.charAt(0) === '+') { neg = s.charAt(0) === '-'; i = 1; } if ((r === 0 || r === 16) && s.charAt(i) === '0' && (s.charAt(i + 1) === 'x' || s.charAt(i + 1) === 'X')) { r = 16; i += 2; } if (r === 0) r = 10; for (; i < s.length; i++) { var c = s.charCodeAt(i), d = c >= 48 && c <= 57 ? c - 48 : c >= 97 && c <= 122 ? c - 87 : c >= 65 && c <= 90 ? c - 55 : 99; if (d >= r) break; v = v * r + d; any = true; } return any ? (neg ? -v : v) : NaN; });
  def(g, 'parseFloat', function (s) { s = String(s).trim(); var i = 0; while (i < s.length && '0123456789.eE+-'.indexOf(s.charAt(i)) >= 0) i++; var v = +s.slice(0, i); return v; });

  if (typeof g.Reflect === 'undefined') {
    Object.defineProperty(g, 'Reflect', { value: {}, writable: true, configurable: true, enumerable: false });
  }
  var R = g.Reflect;
  def(R, 'ownKeys', function (o) { return Object.getOwnPropertyNames(o).concat(Object.getOwnPropertySymbols(o)); });
  def(R, 'apply', function (f, t, a) { return Function.prototype.apply.call(f, t, a); });
  def(R, 'getOwnPropertyDescriptor', function (o, k) { return Object.getOwnPropertyDescriptor(o, k); });
  def(R, 'defineProperty', function (o, k, d) { try { Object.defineProperty(o, k, d); return true; } catch (e) { return false; } });
  def(R, 'getPrototypeOf', function (o) { return Object.getPrototypeOf(o); });
  def(R, 'setPrototypeOf', function (o, p) { try { Object.setPrototypeOf(o, p); return true; } catch (e) { return false; } });
  def(R, 'has', function (o, k) { return k in o; });
  def(R, 'get', function (o, k) { return o[k]; });
  def(R, 'set', function (o, k, v) { o[k] = v; return true; });

  if (typeof g.JSON === 'undefined') {
    var str = function (v) {
      if (v === null) return 'null';
      var t = typeof v;
      if (t === 'string') return '"' + v + '"';
      if (t === 'number' || t === 'boolean') return String(v);
      if (t !== 'object') return undefined;
      if (Array.isArray(v)) return '[' + v.map(function (x) { var s = str(x); return s === undefined ? 'null' : s; }).join(',') + ']';
      var ks = Object.keys(v), parts = [];
      for (var i = 0; i < ks.length; i++) { var s = str(v[ks[i]]); if (s !== undefined) parts.push('"' + ks[i] + '":' + s); }
      return '{' + parts.join(',') + '}';
    };
    Object.defineProperty(g, 'JSON', { value: { stringify: str }, writable: true, configurable: true, enumerable: false });
  }

  // a Map and a Set good enough to be used, not tested
  function ListMap() { this.k = []; this.v = []; }
  ListMap.prototype.find = function (k) { for (var i = 0; i < this.k.length; i++) { var e = this.k[i]; if (e === k || (e !== e && k !== k)) return i; } return -1; };
  ListMap.prototype.get = function (k) { var i = this.find(k); return i < 0 ? undefined : this.v[i]; };
  ListMap.prototype.set = function (k, v) { var i = this.find(k); if (i < 0) { this.k.push(k); this.v.push(v); } else this.v[i] = v; return this; };
  ListMap.prototype.has = function (k) { return this.find(k) >= 0; };
  ListMap.prototype.add = function (k) { return this.set(k, k); };
  ListMap.prototype.delete = function (k) { var i = this.find(k); if (i < 0) return false; this.k.splice(i, 1); this.v.splice(i, 1); return true; };
  ListMap.prototype.forEach = function (f) { for (var i = 0; i < this.k.length; i++) f(this.v[i], this.k[i], this); };
  ListMap.prototype.keys = function () { return this.k[Symbol.iterator](); };
  ListMap.prototype.values = function () { return this.v[Symbol.iterator](); };
  Object.defineProperty(ListMap.prototype, 'size', { get: function () { return this.k.length; } });
})(this);
