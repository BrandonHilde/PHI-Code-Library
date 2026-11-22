// Atomics, and Uint8Array's base64 and hex (fromBase64, fromHex, toBase64, toHex, setFromBase64,
// setFromHex). JsLazy (lazy.phi) runs this the first time one of them is called; typedx.phi makes the
// natives scripts see. exports["%typedKind"] is a native of the engine's: a typed array's kind (as
// JsTyped numbers them), or -1 for anything else; and a TypeError if it's detached or out of bounds,
// unless its second argument is true, or if its third is true and its buffer is immutable.
//
// There's one thread, so an atomic operation is a read and a write. Atomics.wait can't be woken by
// another agent, so it returns "not-equal" or "timed-out" at once; Atomics.waitAsync's promises are woken
// by Atomics.notify.
(function (global, exports) {
  "use strict";

  var typedKind = exports["%typedKind"];
  var defineProperty = Object.defineProperty;
  var ObjectCreate = Object.create;
  var apply = Reflect.apply;
  var Uint8ArrayCtor = Uint8Array;
  var TypedArrayPrototype = Object.getPrototypeOf(Uint8Array.prototype);
  var lengthOf = Object.getOwnPropertyDescriptor(TypedArrayPrototype, "length").get;
  var bufferOf = Object.getOwnPropertyDescriptor(TypedArrayPrototype, "buffer").get;
  var byteOffsetOf = Object.getOwnPropertyDescriptor(TypedArrayPrototype, "byteOffset").get;
  var sharedLength = Object.getOwnPropertyDescriptor(SharedArrayBuffer.prototype, "byteLength").get;
  var charCodeAt = String.prototype.charCodeAt;
  var fromCharCode = String.fromCharCode;
  var NumberCtor = Number;
  var BigIntCtor = BigInt;
  var MathTrunc = Math.trunc;
  var PromiseCtor = Promise;
  var MAX_SAFE = 9007199254740991;

  var INT8 = 0, UINT8 = 1, UINT8C = 2, INT16 = 3, UINT16 = 4, INT32 = 5, UINT32 = 6, FLOAT32 = 7,
      FLOAT64 = 8, BIGINT64 = 9, BIGUINT64 = 10, FLOAT16 = 11;

  function isObject(v) {
    return (typeof v === "object" && v !== null) || typeof v === "function";
  }

  function toIntegerOrInfinity(v) {
    var n = +v;
    if (n !== n || n === 0) return 0;
    if (n === Infinity || n === -Infinity) return n;
    return MathTrunc(n);
  }

  function toIndex(v) {
    if (v === undefined) return 0;
    var n = toIntegerOrInfinity(v);
    if (n < 0 || n > MAX_SAFE) throw new RangeError("Invalid index");
    return n;
  }

  // ToBigInt: no numbers, which BigInt() would take
  function bigOf(v) {
    if (typeof v === "bigint") return v;
    var p = v;
    if (isObject(v)) p = toPrimitiveNumber(v);
    if (typeof p === "number") throw new TypeError("Cannot convert a Number to a BigInt");
    if (typeof p === "symbol") throw new TypeError("Cannot convert a Symbol to a BigInt");
    if (p === undefined || p === null) throw new TypeError("Cannot convert " + p + " to a BigInt");
    return BigIntCtor(p);
  }

  function toPrimitiveNumber(o) {
    var exotic = o[exports["%Symbol.toPrimitive"]];
    if (exotic !== undefined && exotic !== null) {
      var r = apply(exotic, o, ["number"]);
      if (isObject(r)) throw new TypeError("Cannot convert an object to a primitive");
      return r;
    }
    var names = ["valueOf", "toString"];
    for (var i = 0; i < 2; i++) {
      var f = o[names[i]];
      if (typeof f === "function") {
        var v = apply(f, o, []);
        if (!isObject(v)) return v;
      }
    }
    throw new TypeError("Cannot convert an object to a primitive");
  }

  function isBigKind(kind) {
    return kind === BIGINT64 || kind === BIGUINT64;
  }

  // ---- Atomics ----

  // ValidateIntegerTypedArray, then ValidateAtomicAccess: the kind and the index
  function access(ta, index, waitable) {
    var kind = typedKind(ta);
    if (kind < 0) throw new TypeError("Atomics needs a typed array");
    if (waitable) {
      if (kind !== INT32 && kind !== BIGINT64) throw new TypeError("Atomics.wait needs an Int32Array or BigInt64Array");
    } else if (kind === UINT8C || kind === FLOAT32 || kind === FLOAT64 || kind === FLOAT16) {
      throw new TypeError("Atomics needs a typed array of integers");
    }
    var length = apply(lengthOf, ta, []);
    var i = toIndex(index);
    if (i >= length) throw new RangeError("Index out of range");
    return { kind: kind, index: i };
  }

  function convert(kind, v) {
    return isBigKind(kind) ? bigOf(v) : toIntegerOrInfinity(v);
  }

  // RevalidateAtomicAccess: the conversions could have detached or shrunk the buffer
  function revalidate(ta, a) {
    typedKind(ta);
    if (a.index >= apply(lengthOf, ta, [])) throw new RangeError("Index out of range");
  }

  // what v becomes as an element of the kind
  var scratch = [];
  function asElement(kind, v) {
    var s = scratch[kind];
    if (s === undefined) {
      var C = [Int8Array, Uint8Array, Uint8ClampedArray, Int16Array, Uint16Array, Int32Array, Uint32Array,
               Float32Array, Float64Array, BigInt64Array, BigUint64Array][kind];
      s = scratch[kind] = new C(1);
    }
    s[0] = v;
    return s[0];
  }

  function modify(op) {
    return function (ta, index, value) {
      typedKind(ta, true, true);
      var a = access(ta, index, false);
      var v = convert(a.kind, value);
      revalidate(ta, a);
      var old = ta[a.index];
      var w = asElement(a.kind, v);
      var result;
      switch (op) {
        case 0: result = old + w; break;
        case 1: result = old - w; break;
        case 2: result = old & w; break;
        case 3: result = old | w; break;
        case 4: result = old ^ w; break;
        default: result = w;
      }
      ta[a.index] = result;
      return old;
    };
  }

  exports.atomicsAdd = modify(0);
  exports.atomicsSub = modify(1);
  exports.atomicsAnd = modify(2);
  exports.atomicsOr = modify(3);
  exports.atomicsXor = modify(4);
  exports.atomicsExchange = modify(5);

  exports.atomicsCompareExchange = function (ta, index, expectedValue, replacementValue) {
    typedKind(ta, true, true);
    var a = access(ta, index, false);
    var expected = convert(a.kind, expectedValue);
    var replacement = convert(a.kind, replacementValue);
    revalidate(ta, a);
    var old = ta[a.index];
    if (old === asElement(a.kind, expected)) ta[a.index] = replacement;
    return old;
  };

  exports.atomicsLoad = function (ta, index) {
    var a = access(ta, index, false);
    revalidate(ta, a);
    return ta[a.index];
  };

  exports.atomicsStore = function (ta, index, value) {
    typedKind(ta, true, true);
    var a = access(ta, index, false);
    var v = convert(a.kind, value);
    revalidate(ta, a);
    ta[a.index] = v;
    return v;
  };

  exports.atomicsIsLockFree = function (size) {
    var n = toIntegerOrInfinity(size);
    return n === 1 || n === 2 || n === 4 || n === 8;
  };

  function isShared(ta) {
    try {
      apply(sharedLength, apply(bufferOf, ta, []), []);
      return true;
    } catch (e) {
      return false;
    }
  }

  // DoWait's checks: the index, the value, and the timeout
  function waitArgs(ta, index, value, timeout) {
    var kind = typedKind(ta);
    if (kind !== INT32 && kind !== BIGINT64) throw new TypeError("Atomics.wait needs an Int32Array or BigInt64Array");
    if (!isShared(ta)) throw new TypeError("Atomics.wait needs a shared buffer");
    var a = access(ta, index, true);
    var v = convert(a.kind, value);
    var t = NumberCtor(timeout);
    if (t !== t) t = Infinity;
    else if (t < 0) t = 0;
    return { a: a, v: v, t: t };
  }

  exports.atomicsWait = function (ta, index, value, timeout) {
    var w = waitArgs(ta, index, value, timeout);
    if (ta[w.a.index] !== asElement(w.a.kind, w.v)) return "not-equal";
    return "timed-out";
  };

  // waitAsync's waiters, by where they wait: [buffer, byte index, resolve]
  var waiters = [];

  exports.atomicsWaitAsync = function (ta, index, value, timeout) {
    var w = waitArgs(ta, index, value, timeout);
    if (ta[w.a.index] !== asElement(w.a.kind, w.v)) return { async: false, value: "not-equal" };
    if (w.t === 0) return { async: false, value: "timed-out" };
    var resolveIt;
    var promise = new PromiseCtor(function (resolve) { resolveIt = resolve; });
    var where = apply(byteOffsetOf, ta, []) + w.a.index * (w.a.kind === INT32 ? 4 : 8);
    defineProperty(waiters, waiters.length, {
      value: { buffer: apply(bufferOf, ta, []), where: where, resolve: resolveIt },
      writable: true, enumerable: true, configurable: true
    });
    return { async: true, value: promise };
  };

  exports.atomicsNotify = function (ta, index, count) {
    var a = access(ta, index, true);
    var c = Infinity;
    if (count !== undefined) {
      c = toIntegerOrInfinity(count);
      if (c < 0) c = 0;
    }
    if (!isShared(ta)) return 0;
    var buffer = apply(bufferOf, ta, []);
    var where = apply(byteOffsetOf, ta, []) + a.index * (a.kind === INT32 ? 4 : 8);
    var woken = 0;
    var kept = [];
    for (var i = 0; i < waiters.length; i++) {
      var w = waiters[i];
      if (woken < c && w.buffer === buffer && w.where === where) {
        woken++;
        w.resolve("ok");
      } else {
        defineProperty(kept, kept.length, { value: w, writable: true, enumerable: true, configurable: true });
      }
    }
    waiters = kept;
    return woken;
  };

  exports.atomicsPause = function (n) {
    if (n !== undefined && (typeof n !== "number" || MathTrunc(n) !== n)) {
      throw new TypeError("Atomics.pause takes a whole number");
    }
    return undefined;
  };

  // ---- Uint8Array and base64 / hex ----

  var BASE64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  var BASE64URL = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
  var VALUES = [];
  for (var vi = 0; vi < 64; vi++) VALUES[apply(charCodeAt, BASE64, [vi])] = vi;

  function requireUint8(o) {
    if (typedKind(o, true) !== UINT8) throw new TypeError("This needs a Uint8Array");
  }

  function optionsOf(options) {
    if (options === undefined) return ObjectCreate(null);
    if (!isObject(options)) throw new TypeError("options must be an object");
    return options;
  }

  function alphabetOf(opts) {
    var alphabet = opts.alphabet;
    if (alphabet === undefined) return "base64";
    if (alphabet !== "base64" && alphabet !== "base64url") throw new TypeError("alphabet must be \"base64\" or \"base64url\"");
    return alphabet;
  }

  function lastChunkOf(opts) {
    var h = opts.lastChunkHandling;
    if (h === undefined) return "loose";
    if (h !== "loose" && h !== "strict" && h !== "stop-before-partial") {
      throw new TypeError("lastChunkHandling must be \"loose\", \"strict\" or \"stop-before-partial\"");
    }
    return h;
  }

  function isSpace(c) {
    return c === 9 || c === 10 || c === 12 || c === 13 || c === 32;
  }

  function skipSpace(s, i) {
    while (i < s.length && isSpace(apply(charCodeAt, s, [i]))) i++;
    return i;
  }

  // DecodeBase64Chunk: 2 to 4 values to 1 to 3 bytes; null if extra bits are set and that's an error
  function decodeChunk(chunk, bytes, strict) {
    var n = chunk.length;
    var a = chunk[0], b = chunk[1], c = n > 2 ? chunk[2] : 0, d = n > 3 ? chunk[3] : 0;
    var x = (a << 18) | (b << 12) | (c << 6) | d;
    var b0 = (x >> 16) & 255, b1 = (x >> 8) & 255, b2 = x & 255;
    if (n === 2) {
      if (strict && b1 !== 0) return false;
      bytes.push(b0);
    } else if (n === 3) {
      if (strict && b2 !== 0) return false;
      bytes.push(b0, b1);
    } else {
      bytes.push(b0, b1, b2);
    }
    return true;
  }

  // FromBase64: { read, bytes, error }
  function fromBase64(s, alphabet, last, maxLength) {
    var bytes = [];
    var read = 0;
    if (maxLength === 0) return { read: 0, bytes: bytes, error: false };
    var chunk = [];
    var index = 0;
    var length = s.length;
    for (;;) {
      index = skipSpace(s, index);
      if (index === length) {
        if (chunk.length > 0) {
          if (last === "stop-before-partial") return { read: read, bytes: bytes, error: false };
          if (last === "loose") {
            if (chunk.length === 1) return { read: read, bytes: bytes, error: true };
            decodeChunk(chunk, bytes, false);
          } else {
            return { read: read, bytes: bytes, error: true };
          }
        }
        return { read: length, bytes: bytes, error: false };
      }
      var c = apply(charCodeAt, s, [index]);
      index++;
      if (c === 61) {
        if (chunk.length < 2) return { read: read, bytes: bytes, error: true };
        index = skipSpace(s, index);
        if (chunk.length === 2) {
          if (index === length) {
            if (last === "stop-before-partial") return { read: read, bytes: bytes, error: false };
            return { read: read, bytes: bytes, error: true };
          }
          if (apply(charCodeAt, s, [index]) === 61) index = skipSpace(s, index + 1);
        }
        if (index < length) return { read: read, bytes: bytes, error: true };
        if (!decodeChunk(chunk, bytes, last === "strict")) return { read: read, bytes: bytes, error: true };
        return { read: length, bytes: bytes, error: false };
      }
      if (alphabet === "base64url") {
        if (c === 43 || c === 47) return { read: read, bytes: bytes, error: true };
        if (c === 45) c = 43;
        else if (c === 95) c = 47;
      }
      var v = c < 128 ? VALUES[c] : undefined;
      if (v === undefined) return { read: read, bytes: bytes, error: true };
      var remaining = maxLength - bytes.length;
      if ((remaining === 1 && chunk.length === 2) || (remaining === 2 && chunk.length === 3)) {
        return { read: read, bytes: bytes, error: false };
      }
      chunk.push(v);
      if (chunk.length === 4) {
        decodeChunk(chunk, bytes, false);
        chunk = [];
        read = index;
        if (bytes.length === maxLength) return { read: read, bytes: bytes, error: false };
      }
    }
  }

  function hexValue(c) {
    if (c >= 48 && c <= 57) return c - 48;
    if (c >= 65 && c <= 70) return c - 55;
    if (c >= 97 && c <= 102) return c - 87;
    return -1;
  }

  // FromHex: { read, bytes, error }
  function fromHex(s, maxLength) {
    var bytes = [];
    var read = 0;
    if (s.length % 2 !== 0) return { read: 0, bytes: bytes, error: true };
    while (read < s.length && bytes.length < maxLength) {
      var hi = hexValue(apply(charCodeAt, s, [read]));
      var lo = hexValue(apply(charCodeAt, s, [read + 1]));
      if (hi < 0 || lo < 0) return { read: read, bytes: bytes, error: true };
      read += 2;
      bytes.push(hi * 16 + lo);
    }
    return { read: read, bytes: bytes, error: false };
  }

  function made(bytes) {
    var ta = new Uint8ArrayCtor(bytes.length);
    for (var i = 0; i < bytes.length; i++) ta[i] = bytes[i];
    return ta;
  }

  exports.fromBase64 = function (string, options) {
    if (typeof string !== "string") throw new TypeError("Uint8Array.fromBase64 takes a string");
    var opts = optionsOf(options);
    var alphabet = alphabetOf(opts);
    var last = lastChunkOf(opts);
    var r = fromBase64(string, alphabet, last, MAX_SAFE);
    if (r.error) throw new SyntaxError("Invalid base64 text");
    return made(r.bytes);
  };

  exports.fromHex = function (string) {
    if (typeof string !== "string") throw new TypeError("Uint8Array.fromHex takes a string");
    var r = fromHex(string, MAX_SAFE);
    if (r.error) throw new SyntaxError("Invalid hex text");
    return made(r.bytes);
  };

  exports.toBase64 = function (options) {
    var o = this;
    requireUint8(o);
    var opts = optionsOf(options);
    var alphabet = alphabetOf(opts);
    var omit = !!opts.omitPadding;
    typedKind(o);
    var table = alphabet === "base64" ? BASE64 : BASE64URL;
    var n = apply(lengthOf, o, []);
    var out = "";
    for (var i = 0; i < n; i += 3) {
      var b0 = o[i], b1 = i + 1 < n ? o[i + 1] : 0, b2 = i + 2 < n ? o[i + 2] : 0;
      var x = (b0 << 16) | (b1 << 8) | b2;
      out += table[(x >> 18) & 63] + table[(x >> 12) & 63];
      if (i + 1 < n) out += table[(x >> 6) & 63];
      else if (!omit) out += "=";
      if (i + 2 < n) out += table[x & 63];
      else if (!omit) out += "=";
    }
    return out;
  };

  exports.toHex = function () {
    var o = this;
    requireUint8(o);
    typedKind(o);
    var n = apply(lengthOf, o, []);
    var out = "";
    var digits = "0123456789abcdef";
    for (var i = 0; i < n; i++) out += digits[o[i] >> 4] + digits[o[i] & 15];
    return out;
  };

  function result(read, written) {
    var r = {};
    r.read = read;
    r.written = written;
    return r;
  }

  exports.setFromBase64 = function (string, options) {
    var into = this;
    requireUint8(into);
    typedKind(into, true, true);
    if (typeof string !== "string") throw new TypeError("setFromBase64 takes a string");
    var opts = optionsOf(options);
    var alphabet = alphabetOf(opts);
    var last = lastChunkOf(opts);
    typedKind(into);
    var r = fromBase64(string, alphabet, last, apply(lengthOf, into, []));
    for (var i = 0; i < r.bytes.length; i++) into[i] = r.bytes[i];
    if (r.error) throw new SyntaxError("Invalid base64 text");
    return result(r.read, r.bytes.length);
  };

  exports.setFromHex = function (string) {
    var into = this;
    requireUint8(into);
    typedKind(into, true, true);
    if (typeof string !== "string") throw new TypeError("setFromHex takes a string");
    typedKind(into);
    var r = fromHex(string, apply(lengthOf, into, []));
    for (var i = 0; i < r.bytes.length; i++) into[i] = r.bytes[i];
    if (r.error) throw new SyntaxError("Invalid hex text");
    return result(r.read, r.bytes.length);
  };
})
