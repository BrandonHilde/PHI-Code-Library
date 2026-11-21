// Intl (ECMA-402) for the engine, run once when it starts (js/builtins/intl.phi; intljs.phi holds it,
// made by tools/web/make_intl.py, with intl_data.js put in at the "@data" line).
//
// There is one locale, English as the United States writes it: any locale asked for is taken,
// checked and tidied as the standard has it, and then formats as "en-US" does (or "en", if that was
// asked for), as a browser with only English would. What is here: Intl.getCanonicalLocales and
// supportedValuesOf; Collator, NumberFormat (every style and notation, rounding options, ranges),
// PluralRules, DateTimeFormat (time zones from the IANA rules in intl_data.js, each zone's rule now
// used for every date), RelativeTimeFormat, ListFormat, DisplayNames (common names only), Locale (a
// short table of likely subtags), Segmenter (graphemes, words and sentences by simple rules); and
// toLocaleString on numbers, BigInts, dates and arrays, localeCompare, and the locale case changes.
// Also DurationFormat. Not here: calendars or numbering systems other than Gregorian and Latin digits.
(function (global) {
  "use strict";

  // @data

  // ---- what the script uses, taken now: a page changing these later changes nothing here ----

  var Obj = Object, defProp = Obj.defineProperty, create = Obj.create, getProto = Obj.getPrototypeOf;
  var keysOf = Obj.keys, ownKeys = Reflect.ownKeys;
  var FnProto = Function.prototype, call = FnProto.call, bind = FnProto.bind;
  var uncurry = bind.bind(call);
  var apply = uncurry(FnProto.apply);
  var SLOTS = new WeakMap();
  var wmGet = uncurry(WeakMap.prototype.get), wmSet = uncurry(WeakMap.prototype.set);
  var StringCtor = String, NumberCtor = Number, BigIntCtor = BigInt, SymbolCtor = Symbol;
  var TypeErr = TypeError, RangeErr = RangeError;
  var strSlice = uncurry(String.prototype.slice), strIndexOf = uncurry(String.prototype.indexOf);
  var strLastIndexOf = uncurry(String.prototype.lastIndexOf);
  var toLower = uncurry(String.prototype.toLowerCase), toUpper = uncurry(String.prototype.toUpperCase);
  var charCodeAt = uncurry(String.prototype.charCodeAt), codePointAt = uncurry(String.prototype.codePointAt);
  var strTrim = uncurry(String.prototype.trim), strRepeat = uncurry(String.prototype.repeat);
  var fromCharCode = String.fromCharCode, fromCodePoint = String.fromCodePoint;
  var reTest = uncurry(RegExp.prototype.test);
  var toExponential = uncurry(Number.prototype.toExponential);
  var bigToString = uncurry(BigInt.prototype.toString);
  var bigValueOf = uncurry(BigInt.prototype.valueOf);
  var numValueOf = uncurry(Number.prototype.valueOf);
  var dateTime = uncurry(Date.prototype.getTime);
  var dateOffset = uncurry(Date.prototype.getTimezoneOffset);
  var dateNow = Date.now;
  var arrayJoin = uncurry(Array.prototype.join), arraySort = uncurry(Array.prototype.sort);
  var floor = Math.floor, abs = Math.abs, min = Math.min, max = Math.max;
  var isArray = Array.isArray;
  var symIterator = Symbol.iterator, symTag = Symbol.toStringTag, symToPrimitive = Symbol.toPrimitive;
  var FALLBACK = SymbolCtor("IntlLegacyConstructedSymbol");
  var NativeDate = Date;

  // ---- small things ----

  function own(o, k, v) {
    defProp(o, k, { value: v, writable: true, enumerable: true, configurable: true });
  }

  function hidden(o, k, v) {
    defProp(o, k, { value: v, writable: true, enumerable: false, configurable: true });
  }

  // onto an array a script will get: as CreateDataProperty, past any setter a script put on Array.prototype
  function push(a, v) {
    defProp(a, a.length, { value: v, writable: true, enumerable: true, configurable: true });
  }

  // an array only this script sees: with no prototype, a setter a page put on Array.prototype or
  // Object.prototype can't see it filled in
  var setProto = Obj.setPrototypeOf;

  function newList() {
    var a = [];
    setProto(a, null);
    return a;
  }

  // onto an array only this script sees
  function add(a, v) {
    a[a.length] = v;
  }

  function has(list, v) {
    for (var i = 0; i < list.length; i++) {
      if (list[i] === v) return true;
    }
    return false;
  }

  function isObject(v) {
    return (typeof v === "object" && v !== null) || typeof v === "function";
  }

  function toStr(v) {
    return `${v}`;
  }

  function toNum(v) {
    return +v;
  }

  function toObject(v) {
    if (v === undefined || v === null) throw new TypeErr("Cannot convert undefined or null to object");
    return Obj(v);
  }

  function pad(n, width) {
    var s = toStr(n);
    while (s.length < width) s = "0" + s;
    return s;
  }

  function isDigit(c) {
    return c >= "0" && c <= "9";
  }

  // the internal slots of an Intl object: kept here, out of a script's reach
  function slotsOf(o, kind, what) {
    var s = isObject(o) ? wmGet(SLOTS, o) : undefined;
    if (s === undefined || s.kind !== kind) {
      throw new TypeErr(what + " called on an object that isn't an Intl." + kind);
    }
    return s;
  }

  function newSlots(o, kind) {
    var s = create(null);
    s.kind = kind;
    wmSet(SLOTS, o, s);
    return s;
  }

  function ordinaryHasInstance(C, O) {
    if (!isObject(O)) return false;
    var P = C.prototype;
    for (var o = getProto(O); o !== null; o = getProto(o)) {
      if (o === P) return true;
    }
    return false;
  }

  // GetPrototypeFromConstructor: a subclass's prototype, or the built-in one
  function protoFrom(newTarget, fallback) {
    var p = newTarget.prototype;
    return isObject(p) ? p : fallback;
  }

  // ---- options ----

  // CoerceOptionsToObject
  function coerceOptions(options) {
    return options === undefined ? create(null) : toObject(options);
  }

  // GetOptionsObject
  function optionsObject(options) {
    if (options === undefined) return create(null);
    if (isObject(options)) return options;
    throw new TypeErr("Options must be an object");
  }

  function getOption(options, name, type, values, fallback) {
    var v = options[name];
    if (v === undefined) return fallback;
    if (type === "boolean") v = !!v;
    else v = toStr(v);
    if (values !== undefined && !has(values, v)) {
      throw new RangeErr("Value " + v + " out of range for Intl option " + name);
    }
    return v;
  }

  function defaultNumberOption(v, lo, hi, fallback, name) {
    if (v === undefined) return fallback;
    v = toNum(v);
    if (v !== v || v < lo || v > hi) throw new RangeErr((name || "Value") + " out of range");
    return floor(v);
  }

  function getNumberOption(options, name, lo, hi, fallback) {
    return defaultNumberOption(options[name], lo, hi, fallback, name);
  }

  // a "type" of a Unicode locale extension: one or more alphanumeric pieces of 3 to 8, with hyphens
  function isTypeSequence(s) {
    return reTest(/^[a-zA-Z0-9]{3,8}(-[a-zA-Z0-9]{3,8})*$/, s);
  }

  // ---- language tags (BCP 47 as Unicode's locale identifiers have them) ----

  var LANGUAGE_ALIASES = {
    iw: "he", "in": "id", ji: "yi", jw: "jv", mo: "ro", sh: "sr-Latn", tl: "fil", cmn: "zh",
    aar: "aa", ces: "cs", deu: "de", ell: "el", eng: "en", fra: "fr", heb: "he", hun: "hu",
    ita: "it", jpn: "ja", kor: "ko", nld: "nl", pol: "pl", por: "pt", rus: "ru", spa: "es",
    swe: "sv", tur: "tr", zho: "zh", arb: "ar", no: "no", nb: "nb"
  };
  var REGION_ALIASES = {
    DD: "DE", FX: "FR", BU: "MM", TP: "TL", YD: "YE", ZR: "CD", UK: "GB", SU: "RU", YU: "RS",
    CS: "RS", AN: "CW", NT: "SA", "062": "034", "172": "RU", "200": "CZ", "230": "ET", "280": "DE",
    "532": "CW", "582": "FM", "736": "SD", "830": "JE", "886": "YE", "890": "RS"
  };

  // a tag taken apart, or null if it isn't one
  function parseTag(tag) {
    if (typeof tag !== "string" || tag === "" || !reTest(/^[a-zA-Z0-9]+(-[a-zA-Z0-9]+)*$/, tag)) {
      return null;
    }
    var subs = splitOn(toLower(tag), "-");
    var t = { language: "", script: "", region: "", variants: [], extensions: [], privateUse: "" };
    var i = 0, s = subs[0];
    if (!reTest(/^([a-z]{2,3}|[a-z]{5,8})$/, s)) return null;
    t.language = s;
    i++;
    if (i < subs.length && reTest(/^[a-z]{4}$/, subs[i])) {
      t.script = subs[i];
      i++;
    }
    if (i < subs.length && reTest(/^([a-z]{2}|[0-9]{3})$/, subs[i])) {
      t.region = subs[i];
      i++;
    }
    while (i < subs.length && reTest(/^([a-z0-9]{5,8}|[0-9][a-z0-9]{3})$/, subs[i])) {
      if (has(t.variants, subs[i])) return null;
      add(t.variants, subs[i]);
      i++;
    }
    var seen = "";
    while (i < subs.length && subs[i].length === 1) {
      var single = subs[i];
      i++;
      if (single === "x") {
        var start = i;
        while (i < subs.length && reTest(/^[a-z0-9]{1,8}$/, subs[i])) i++;
        if (i === start) return null;
        t.privateUse = "x-" + joinRange(subs, start, i);
        break;
      }
      if (strIndexOf(seen, single) >= 0) return null;
      seen += single;
      var first = i;
      while (i < subs.length && subs[i].length > 1) {
        if (!reTest(/^[a-z0-9]{2,8}$/, subs[i])) return null;
        i++;
      }
      if (i === first) return null;
      var ext = sliceList(subs, first, i);
      if (single === "u") {
        ext = parseUnicodeExt(ext);
      } else if (single === "t") {
        ext = parseTransformedExt(ext);
      } else {
        ext = { singleton: single, text: single + "-" + arrayJoin(ext, "-") };
      }
      if (ext === null) return null;
      add(t.extensions, ext);
    }
    if (i < subs.length) return null;
    return t;
  }

  function splitOn(s, sep) {
    var out = newList(), from = 0;
    for (;;) {
      var at = strIndexOf(s, sep, from);
      if (at < 0) break;
      add(out, strSlice(s, from, at));
      from = at + sep.length;
    }
    add(out, strSlice(s, from));
    return out;
  }

  function sliceList(list, from, to) {
    var out = newList();
    for (var i = from; i < to; i++) add(out, list[i]);
    return out;
  }

  function joinRange(list, from, to) {
    return arrayJoin(sliceList(list, from, to), "-");
  }

  // -u-: attributes, then keywords (a key of two, then its type's pieces)
  function parseUnicodeExt(subs) {
    var e = { singleton: "u", attributes: [], keywords: [] };
    var i = 0;
    while (i < subs.length && subs[i].length >= 3) {
      add(e.attributes, subs[i]);
      i++;
    }
    while (i < subs.length) {
      var key = subs[i];
      if (!reTest(/^[a-z0-9][a-z]$/, key)) return null;
      i++;
      var start = i;
      while (i < subs.length && subs[i].length >= 3) i++;
      add(e.keywords, [key, joinRange(subs, start, i)]);
    }
    return e;
  }

  // -t-: a language tag perhaps, then fields (a letter and a digit, then pieces)
  function parseTransformedExt(subs) {
    var e = { singleton: "t", lang: "", fields: [] };
    var i = 0;
    if (i < subs.length && reTest(/^[a-z]{2,3}$|^[a-z]{5,8}$/, subs[i])) {
      var start = i;
      i++;
      if (i < subs.length && reTest(/^[a-z]{4}$/, subs[i])) i++;
      if (i < subs.length && reTest(/^([a-z]{2}|[0-9]{3})$/, subs[i])) i++;
      var vs = newList();
      while (i < subs.length && reTest(/^([a-z0-9]{5,8}|[0-9][a-z0-9]{3})$/, subs[i])) {
        if (has(vs, subs[i])) return null;
        add(vs, subs[i]);
        i++;
      }
      var lt = parseTag(joinRange(subs, start, i));
      if (lt === null) return null;
      e.lang = tagText(canonicalParts(lt));
    }
    while (i < subs.length) {
      var key = subs[i];
      if (!reTest(/^[a-z][0-9]$/, key)) return null;
      i++;
      var from = i;
      while (i < subs.length && reTest(/^[a-z0-9]{3,8}$/, subs[i])) i++;
      if (i === from) return null;
      add(e.fields, [key, joinRange(subs, from, i)]);
    }
    if (e.lang === "" && e.fields.length === 0) return null;
    return e;
  }

  function byFirst(a, b) {
    return a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0;
  }

  function bySingleton(a, b) {
    return a.singleton < b.singleton ? -1 : a.singleton > b.singleton ? 1 : 0;
  }

  var VALUE_ALIASES = {
    ca: { "ethiopic-amete-alem": "ethioaa", islamicc: "islamic-civil" },
    ks: { primary: "level1", tertiary: "level3" },
    ms: { imperial: "uksystem" },
    tz: { cnckg: "cnsha", eire: "iedub", est: "papty", gmt0: "gmt", uct: "utc", zulu: "utc" }
  };
  // tags that were "grandfathered" and are now well-formed: what they stand for
  var GRANDFATHERED = { "art-lojban": "jbo", "cel-gaulish": "xtg", "zh-guoyu": "zh", "zh-hakka": "hak", "zh-xiang": "hsn" };

  // the parts in canonical form: aliases replaced, cases and orders as UTS 35 has them
  function canonicalParts(t) {
    if (t.variants.length === 1 && t.script === "" && t.region === "") {
      var g = GRANDFATHERED[t.language + "-" + t.variants[0]];
      if (typeof g === "string") {
        t.language = g;
        t.variants = newList();
      }
    }
    var lang = t.language;
    var alias = LANGUAGE_ALIASES[lang];
    if (typeof alias === "string" && alias !== lang) {
      var at = strIndexOf(alias, "-");
      if (at > 0) {
        if (t.script === "") t.script = toLower(strSlice(alias, at + 1));
        lang = strSlice(alias, 0, at);
      } else {
        lang = alias;
      }
    }
    t.language = lang;
    if (t.script !== "") {
      t.script = toUpper(t.script[0]) + strSlice(t.script, 1);
    }
    if (t.region !== "") {
      var region = toUpper(t.region);
      var ra = REGION_ALIASES[region];
      t.region = typeof ra === "string" ? ra : region;
    }
    arraySort(t.variants);
    for (var i = 0; i < t.extensions.length; i++) {
      var e = t.extensions[i];
      if (e.singleton === "u") {
        var attrs = newList();
        arraySort(e.attributes);
        for (var j = 0; j < e.attributes.length; j++) {
          if (!has(attrs, e.attributes[j])) add(attrs, e.attributes[j]);
        }
        e.attributes = attrs;
        var kws = newList(), keys = newList();
        for (j = 0; j < e.keywords.length; j++) {
          var kw = e.keywords[j];
          if (has(keys, kw[0])) continue;
          add(keys, kw[0]);
          var value = kw[1] === "yes" ? "true" : kw[1];
          var aliases = VALUE_ALIASES[kw[0]];
          if (aliases !== undefined && typeof aliases[value] === "string") value = aliases[value];
          add(kws, [kw[0], value === "true" ? "" : value]);
        }
        arraySort(kws, byFirst);
        e.keywords = kws;
      } else if (e.singleton === "t") {
        arraySort(e.fields, byFirst);
      }
    }
    arraySort(t.extensions, bySingleton);
    return t;
  }

  function extensionText(e) {
    var out = e.singleton;
    var i;
    if (e.singleton === "u") {
      for (i = 0; i < e.attributes.length; i++) out += "-" + e.attributes[i];
      for (i = 0; i < e.keywords.length; i++) {
        out += "-" + e.keywords[i][0];
        if (e.keywords[i][1] !== "") out += "-" + e.keywords[i][1];
      }
      return out;
    }
    if (e.singleton === "t") {
      if (e.lang !== "") out += "-" + toLower(e.lang);
      for (i = 0; i < e.fields.length; i++) out += "-" + e.fields[i][0] + "-" + e.fields[i][1];
      return out;
    }
    return e.text;
  }

  function baseText(t) {
    var out = t.language;
    if (t.script !== "") out += "-" + t.script;
    if (t.region !== "") out += "-" + t.region;
    for (var i = 0; i < t.variants.length; i++) out += "-" + t.variants[i];
    return out;
  }

  function tagText(t) {
    var out = baseText(t);
    for (var i = 0; i < t.extensions.length; i++) out += "-" + extensionText(t.extensions[i]);
    if (t.privateUse !== "") out += "-" + t.privateUse;
    return out;
  }

  var canonicalCache = create(null);

  function canonicalizeTag(tag) {
    var known = canonicalCache[tag];
    if (known !== undefined) return known;
    var c = canonicalizeTagNow(tag);
    canonicalCache[tag] = c;
    return c;
  }

  function canonicalizeTagNow(tag) {
    var t = parseTag(tag);
    if (t === null) throw new RangeErr("Invalid language tag: " + tag);
    return tagText(canonicalParts(t));
  }

  // CanonicalizeLocaleList
  function localeList(locales) {
    var seen = [];
    if (locales === undefined) return seen;
    var O;
    if (typeof locales === "string" || localeSlots(locales) !== undefined) {
      O = [locales];
    } else {
      O = toObject(locales);
    }
    var len = toLength(O.length);
    for (var k = 0; k < len; k++) {
      var pk = toStr(k);
      if (!(pk in O)) continue;
      var v = O[pk];
      if (typeof v !== "string" && !isObject(v)) throw new TypeErr("Locale must be a string or an object");
      var ls = localeSlots(v);
      var tag = ls !== undefined ? ls.locale : toStr(v);
      tag = canonicalizeTag(tag);
      if (!has(seen, tag)) push(seen, tag);
    }
    return seen;
  }

  function toLength(v) {
    var n = toNum(v);
    if (n !== n || n <= 0) return 0;
    n = floor(n);
    return n > 9007199254740991 ? 9007199254740991 : n;
  }

  function localeSlots(v) {
    if (!isObject(v)) return undefined;
    var s = wmGet(SLOTS, v);
    return s !== undefined && s.kind === "Locale" ? s : undefined;
  }

  // ---- the locales here, and choosing among them ----

  var AVAILABLE = ["en", "en-US"];
  var DEFAULT_LOCALE = "en-US";

  var plainCache = create(null);

  function withoutUnicodeExt(tag) {
    var known = plainCache[tag];
    if (known === undefined) {
      known = withoutUnicodeExtNow(tag);
      plainCache[tag] = known;
    }
    return known;
  }

  function withoutUnicodeExtNow(tag) {
    var t = parseTag(tag);
    if (t === null) return tag;
    var exts = newList();
    for (var i = 0; i < t.extensions.length; i++) {
      if (t.extensions[i].singleton !== "u") add(exts, t.extensions[i]);
    }
    t.extensions = exts;
    return tagText(canonicalParts(t));
  }

  function unicodeExtOf(tag) {
    var t = parseTag(tag);
    if (t === null) return null;
    for (var i = 0; i < t.extensions.length; i++) {
      if (t.extensions[i].singleton === "u") return t.extensions[i];
    }
    return null;
  }

  // BestAvailableLocale
  function bestAvailable(tag) {
    var candidate = tag;
    for (;;) {
      if (has(AVAILABLE, candidate)) return candidate;
      var pos = strLastIndexOf(candidate, "-");
      if (pos < 0) return undefined;
      if (pos >= 2 && candidate[pos - 2] === "-") pos -= 2;
      candidate = strSlice(candidate, 0, pos);
    }
  }

  // ResolveLocale: keys are the extension keys the service looks at; data[key] its values, the
  // first the default; options[key] what the options asked for
  function resolveLocale(requested, opt, keys, data) {
    var found, ext = null;
    for (var i = 0; i < requested.length; i++) {
      var plain = withoutUnicodeExt(requested[i]);
      var a = bestAvailable(plain);
      if (a !== undefined) {
        found = a;
        ext = unicodeExtOf(requested[i]);
        break;
      }
    }
    if (found === undefined) found = DEFAULT_LOCALE;
    var result = create(null);
    result.dataLocale = found;
    var supported = "";
    for (i = 0; i < keys.length; i++) {
      var key = keys[i];
      var values = data[key];
      var value = values[0];
      var keyword = "";
      if (ext !== null) {
        for (var j = 0; j < ext.keywords.length; j++) {
          if (ext.keywords[j][0] !== key) continue;
          var want = ext.keywords[j][1];
          if (want !== "") {
            if (has(values, want)) {
              value = want;
              keyword = "-" + key + "-" + want;
            }
          } else if (has(values, "true")) {
            value = "true";
            keyword = "-" + key;
          }
          break;
        }
      }
      if (opt[key] !== undefined) {
        var ov = opt[key];
        if (has(values, ov) && ov !== value) {
          value = ov;
          keyword = "";
        }
      }
      result[key] = value;
      supported += keyword;
    }
    result.locale = supported !== "" ? found + "-u" + supported : found;
    return result;
  }

  function supportedLocales(locales, options) {
    var requested = localeList(locales);
    options = coerceOptions(options);
    getOption(options, "localeMatcher", "string", ["lookup", "best fit"], "best fit");
    var out = [];
    for (var i = 0; i < requested.length; i++) {
      if (bestAvailable(withoutUnicodeExt(requested[i])) !== undefined) push(out, requested[i]);
    }
    return out;
  }

  // ---- making the built-ins look built in ----

  // methods from an object literal or class: no prototype, not constructors, right name and length
  function methods(target, source) {
    var names = ownKeys(source);
    for (var i = 0; i < names.length; i++) {
      var d = Obj.getOwnPropertyDescriptor(source, names[i]);
      d.enumerable = false;
      defProp(target, names[i], d);
    }
  }

  function tag(proto, name) {
    defProp(proto, symTag, { value: name, writable: false, enumerable: false, configurable: true });
  }

  function constructorFn(fn, proto, statics) {
    defProp(fn, "prototype", { value: proto, writable: false, enumerable: false, configurable: false });
    hidden(proto, "constructor", fn);
    methods(fn, statics);
  }

  // the lazy Intl the engine made (js/builtins/intl.phi), to fill in; a new one where there's none
  var Intl = global["%intlStub"];
  try { delete global["%intlStub"]; } catch (e) { }
  if (!isObject(Intl)) {
    Intl = {};
    hidden(global, "Intl", Intl);
  }
  tag(Intl, "Intl");

  // ======== numbers: exact decimals, rounding, and the patterns ========

  // A decimal: s whether negative, d its digits (none for zero, no zeros at either end), e where the
  // point goes: the value is 0.d times ten to the e. Or nan, or inf (with s).

  function decZero(neg) {
    return { s: neg, d: "", e: 0 };
  }

  function decFromNumber(x) {
    if (x !== x) return { nan: true, s: false };
    var neg = x < 0 || (x === 0 && 1 / x < 0);
    if (x === 0) return decZero(neg);
    if (x === Infinity || x === -Infinity) return { inf: true, s: neg };
    var t = toExponential(neg ? -x : x);           // the shortest digits that give x back
    var at = strIndexOf(t, "e");
    var mant = strSlice(t, 0, at), exp = toNum(strSlice(t, at + 1));
    var digits = mant[0] + (mant.length > 2 ? strSlice(mant, 2) : "");
    return decTrim(neg, digits, exp + 1);
  }

  function decTrim(neg, digits, e) {
    var a = 0;
    while (a < digits.length && digits[a] === "0") a++;
    var b = digits.length;
    while (b > a && digits[b - 1] === "0") b--;
    if (a === b) return decZero(neg);
    return { s: neg, d: strSlice(digits, a, b), e: e - a };
  }

  function decFromBigInt(b) {
    var neg = b < 0n;
    var t = bigToString(neg ? -b : b);
    return decTrim(neg, t, t.length);
  }

  // StringIntlMV: the exact value a numeric string names
  function decFromString(text) {
    var s = strTrim(text);
    if (s === "") return decZero(false);
    if (reTest(/^0[xX][0-9a-fA-F]+$|^0[oO][0-7]+$|^0[bB][01]+$/, s)) return decFromBigInt(BigIntCtor(s));
    if (!reTest(/^[+-]?(Infinity|([0-9]+\.?[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?)$/, s)) return { nan: true, s: false };
    var neg = s[0] === "-";
    if (s[0] === "+" || s[0] === "-") s = strSlice(s, 1);
    if (s === "Infinity") return { inf: true, s: neg };
    var e = 0;
    var at = strIndexOf(s, "e");
    if (at < 0) at = strIndexOf(s, "E");
    if (at >= 0) {
      e = toNum(strSlice(s, at + 1));
      s = strSlice(s, 0, at);
    }
    var point = strIndexOf(s, ".");
    var whole = point < 0 ? s : strSlice(s, 0, point);
    var frac = point < 0 ? "" : strSlice(s, point + 1);
    return decTrim(neg, whole + frac, whole.length + e);
  }

  // ToIntlMathematicalValue
  function toMathValue(v) {
    var p = v;
    if (isObject(v)) {
      var exotic = v[symToPrimitive];
      if (exotic !== undefined && exotic !== null) {
        p = apply(exotic, v, ["number"]);
        if (isObject(p)) throw new TypeErr("Cannot convert object to primitive value");
      } else {
        p = ordinaryToPrimitive(v);
      }
    }
    if (typeof p === "bigint") return decFromBigInt(p);
    if (typeof p === "string") return decFromString(p);
    return decFromNumber(toNum(p));
  }

  function ordinaryToPrimitive(o) {
    var names = ["valueOf", "toString"];
    for (var i = 0; i < 2; i++) {
      var f = o[names[i]];
      if (typeof f === "function") {
        var r = apply(f, o, []);
        if (!isObject(r)) return r;
      }
    }
    throw new TypeErr("Cannot convert object to primitive value");
  }

  function decIsZero(x) {
    return !x.nan && !x.inf && x.d === "";
  }

  function decIsInteger(x) {
    return x.d.length <= x.e;
  }

  // times ten to the n
  function decScale(x, n) {
    if (x.nan || x.inf || x.d === "") return x;
    return { s: x.s, d: x.d, e: x.e + n };
  }

  function decMulSmall(x, k) {
    if (x.d === "") return x;
    var out = "", carry = 0;
    for (var i = x.d.length - 1; i >= 0; i--) {
      var v = (charCodeAt(x.d, i) - 48) * k + carry;
      out = fromCharCode(48 + v % 10) + out;
      carry = floor(v / 10);
    }
    var extra = 0;
    while (carry > 0) {
      out = fromCharCode(48 + carry % 10) + out;
      carry = floor(carry / 10);
      extra++;
    }
    return decTrim(x.s, out, x.e + extra);
  }

  function roundUp(mode, neg, half, odd) {
    // half: -1 under a half, 0 a half exactly, 1 over (and always something dropped)
    switch (mode) {
      case "ceil": return !neg;
      case "floor": return neg;
      case "expand": return true;
      case "trunc": return false;
      case "halfCeil": return half > 0 || (half === 0 && !neg);
      case "halfFloor": return half > 0 || (half === 0 && neg);
      case "halfTrunc": return half > 0;
      case "halfEven": return half > 0 || (half === 0 && odd);
      default: return half >= 0;     // halfExpand
    }
  }

  // keeps the digits worth ten to the pos or more
  function decRound(x, pos, mode) {
    if (x.nan || x.inf) return x;
    var keep = x.e - pos;
    var d = x.d;
    if (keep >= d.length) return x;
    var kept = "", half = -1;
    if (keep >= 0) {
      kept = strSlice(d, 0, keep);
      var f = d[keep];
      half = f > "5" ? 1 : f < "5" ? -1 : (d.length > keep + 1 ? 1 : 0);
    }
    var odd = kept.length > 0 && ((charCodeAt(kept, kept.length - 1) - 48) & 1) === 1;
    if (!roundUp(mode, x.s, half, odd)) return decTrim(x.s, kept, x.e);
    if (keep <= 0) return { s: x.s, d: "1", e: pos + 1 };
    var i = kept.length - 1;
    while (i >= 0 && kept[i] === "9") i--;
    if (i < 0) return { s: x.s, d: "1", e: x.e + 1 };
    return decTrim(x.s, strSlice(kept, 0, i) + fromCharCode(charCodeAt(kept, i) + 1), x.e);
  }

  // to a multiple of increment times ten to the -digits
  function decRoundIncrement(x, digits, increment, mode) {
    var k = 0, m = increment;
    while (m % 10 === 0) {
      m = m / 10;
      k++;
    }
    var pos = k - digits;
    if (m === 1) return decRound(x, pos, mode);
    var q = m === 25 ? 2 : 1;
    var f = m === 25 ? 4 : m === 2 ? 5 : 2;
    var z = decRound(decMulSmall(x, f), pos + q, mode);
    return decScale(decMulSmall(z, m), -q);
  }

  // FormatNumericToString's rounding: the decimal, and how many fraction digits to show at least
  function roundFor(o, x) {
    if (x.nan || x.inf) return { x: x, minFrac: 0 };
    var type = o.roundingType;
    var sd, fd, sdMag = 0, fdMag = 0;
    if (type !== "fractionDigits") {
      sdMag = (x.d === "" ? 1 : x.e) - o.maximumSignificantDigits;
      sd = decRound(x, sdMag, o.roundingMode);
    }
    if (type !== "significantDigits") {
      fdMag = -o.maximumFractionDigits;
      fd = decRoundIncrement(x, o.maximumFractionDigits, o.roundingIncrement, o.roundingMode);
    }
    var useSd;
    if (type === "significantDigits") useSd = true;
    else if (type === "fractionDigits") useSd = false;
    else if (type === "morePrecision") useSd = sdMag <= fdMag;
    else useSd = sdMag > fdMag;
    var r, minFrac;
    if (useSd) {
      r = sd;
      minFrac = r.d === "" ? o.minimumSignificantDigits - 1 : o.minimumSignificantDigits - r.e;
      if (minFrac < 0) minFrac = 0;
    } else {
      r = fd;
      minFrac = o.minimumFractionDigits;
    }
    if (o.trailingZeroDisplay === "stripIfInteger" && decIsInteger(r)) minFrac = 0;
    return { x: r, minFrac: minFrac };
  }

  // the digits before and after the point
  function decDigits(x, minFrac, minInt) {
    var d = x.d, e = x.e, whole, frac;
    if (d === "") {
      whole = "";
      frac = "";
    } else if (e <= 0) {
      whole = "";
      frac = strRepeat("0", -e) + d;
    } else if (e >= d.length) {
      whole = d + strRepeat("0", e - d.length);
      frac = "";
    } else {
      whole = strSlice(d, 0, e);
      frac = strSlice(d, e);
    }
    while (frac.length < minFrac) frac += "0";
    while (whole.length < minInt) whole = "0" + whole;
    if (whole === "") whole = "0";
    return { whole: whole, frac: frac };
  }

  // SetNumberFormatDigitOptions
  function digitOptions(o, options, mnfdDefault, mxfdDefault, notation) {
    var mnid = getNumberOption(options, "minimumIntegerDigits", 1, 21, 1);
    var mnfd = options.minimumFractionDigits;
    var mxfd = options.maximumFractionDigits;
    var mnsd = options.minimumSignificantDigits;
    var mxsd = options.maximumSignificantDigits;
    o.minimumIntegerDigits = mnid;
    var increment = getNumberOption(options, "roundingIncrement", 1, 5000, 1);
    if (!has([1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 2500, 5000], increment)) {
      throw new RangeErr("roundingIncrement value is out of range");
    }
    var mode = getOption(options, "roundingMode", "string",
      ["ceil", "floor", "expand", "trunc", "halfCeil", "halfFloor", "halfExpand", "halfTrunc", "halfEven"], "halfExpand");
    var priority = getOption(options, "roundingPriority", "string", ["auto", "morePrecision", "lessPrecision"], "auto");
    var tzd = getOption(options, "trailingZeroDisplay", "string", ["auto", "stripIfInteger"], "auto");
    if (increment !== 1) mxfdDefault = mnfdDefault;
    o.roundingIncrement = increment;
    o.roundingMode = mode;
    o.trailingZeroDisplay = tzd;
    var hasSd = mnsd !== undefined || mxsd !== undefined;
    var hasFd = mnfd !== undefined || mxfd !== undefined;
    var needSd = true, needFd = true;
    if (priority === "auto") {
      needSd = hasSd;
      if (needSd || (!hasFd && notation === "compact")) needFd = false;
    }
    if (needSd) {
      if (hasSd) {
        mnsd = defaultNumberOption(mnsd, 1, 21, 1, "minimumSignificantDigits");
        mxsd = defaultNumberOption(mxsd, mnsd, 21, 21, "maximumSignificantDigits");
        o.minimumSignificantDigits = mnsd;
        o.maximumSignificantDigits = mxsd;
      } else {
        o.minimumSignificantDigits = 1;
        o.maximumSignificantDigits = 21;
      }
    }
    if (needFd) {
      if (hasFd) {
        mnfd = defaultNumberOption(mnfd, 0, 100, undefined, "minimumFractionDigits");
        mxfd = defaultNumberOption(mxfd, 0, 100, undefined, "maximumFractionDigits");
        if (mnfd === undefined) mnfd = min(mnfdDefault, mxfd);
        else if (mxfd === undefined) mxfd = max(mxfdDefault, mnfd);
        else if (mnfd > mxfd) throw new RangeErr("maximumFractionDigits is less than minimumFractionDigits");
        o.minimumFractionDigits = mnfd;
        o.maximumFractionDigits = mxfd;
      } else {
        o.minimumFractionDigits = mnfdDefault;
        o.maximumFractionDigits = mxfdDefault;
      }
    }
    if (!needSd && !needFd) {
      o.minimumFractionDigits = 0;
      o.maximumFractionDigits = 0;
      o.minimumSignificantDigits = 1;
      o.maximumSignificantDigits = 2;
      o.roundingType = "morePrecision";
      o.roundingPriority = "morePrecision";
    } else if (priority === "auto") {
      o.roundingType = needSd ? "significantDigits" : "fractionDigits";
      o.roundingPriority = "auto";
    } else {
      o.roundingType = priority;
      o.roundingPriority = priority;
    }
    if (increment !== 1) {
      if (o.roundingType !== "fractionDigits") throw new TypeErr("roundingIncrement needs fraction digits");
      if (o.maximumFractionDigits !== o.minimumFractionDigits) {
        throw new RangeErr("With roundingIncrement, the fraction digits must be the same");
      }
    }
  }

  // ---- currencies and units, in English ----

  // symbol, narrow symbol, one, other, display name
  var CURRENCIES = {
    USD: ["$", "$", "US dollar", "US dollars", "US Dollar"],
    EUR: ["€", "€", "euro", "euros", "Euro"],
    GBP: ["£", "£", "British pound", "British pounds", "British Pound"],
    JPY: ["¥", "¥", "Japanese yen", "Japanese yen", "Japanese Yen"],
    CNY: ["CN¥", "¥", "Chinese yuan", "Chinese yuan", "Chinese Yuan"],
    INR: ["₹", "₹", "Indian rupee", "Indian rupees", "Indian Rupee"],
    CAD: ["CA$", "$", "Canadian dollar", "Canadian dollars", "Canadian Dollar"],
    AUD: ["A$", "$", "Australian dollar", "Australian dollars", "Australian Dollar"],
    NZD: ["NZ$", "$", "New Zealand dollar", "New Zealand dollars", "New Zealand Dollar"],
    HKD: ["HK$", "$", "Hong Kong dollar", "Hong Kong dollars", "Hong Kong Dollar"],
    TWD: ["NT$", "$", "New Taiwan dollar", "New Taiwan dollars", "New Taiwan Dollar"],
    MXN: ["MX$", "$", "Mexican peso", "Mexican pesos", "Mexican Peso"],
    BRL: ["R$", "R$", "Brazilian real", "Brazilian reals", "Brazilian Real"],
    KRW: ["₩", "₩", "South Korean won", "South Korean won", "South Korean Won"],
    ILS: ["₪", "₪", "Israeli new shekel", "Israeli new shekels", "Israeli New Shekel"],
    VND: ["₫", "₫", "Vietnamese dong", "Vietnamese dong", "Vietnamese Dong"],
    PHP: ["₱", "₱", "Philippine peso", "Philippine pesos", "Philippine Peso"],
    XAF: ["FCFA", "FCFA", "Central African CFA franc", "Central African CFA francs", "Central African CFA Franc"],
    XOF: ["F CFA", "F CFA", "West African CFA franc", "West African CFA francs", "West African CFA Franc"],
    CHF: ["CHF", "CHF", "Swiss franc", "Swiss francs", "Swiss Franc"],
    SEK: ["SEK", "kr", "Swedish krona", "Swedish kronor", "Swedish Krona"],
    NOK: ["NOK", "kr", "Norwegian krone", "Norwegian kroner", "Norwegian Krone"],
    DKK: ["DKK", "kr", "Danish krone", "Danish kroner", "Danish Krone"],
    PLN: ["PLN", "zł", "Polish zloty", "Polish zlotys", "Polish Zloty"],
    CZK: ["CZK", "Kč", "Czech koruna", "Czech korunas", "Czech Koruna"],
    HUF: ["HUF", "Ft", "Hungarian forint", "Hungarian forints", "Hungarian Forint"],
    RUB: ["RUB", "₽", "Russian ruble", "Russian rubles", "Russian Ruble"],
    UAH: ["UAH", "₴", "Ukrainian hryvnia", "Ukrainian hryvnias", "Ukrainian Hryvnia"],
    TRY: ["TRY", "₺", "Turkish lira", "Turkish Lira", "Turkish Lira"],
    SGD: ["SGD", "$", "Singapore dollar", "Singapore dollars", "Singapore Dollar"],
    ZAR: ["ZAR", "R", "South African rand", "South African rand", "South African Rand"],
    THB: ["THB", "฿", "Thai baht", "Thai baht", "Thai Baht"],
    IDR: ["IDR", "Rp", "Indonesian rupiah", "Indonesian rupiahs", "Indonesian Rupiah"],
    MYR: ["MYR", "RM", "Malaysian ringgit", "Malaysian ringgits", "Malaysian Ringgit"],
    NGN: ["NGN", "₦", "Nigerian naira", "Nigerian nairas", "Nigerian Naira"],
    EGP: ["EGP", "E£", "Egyptian pound", "Egyptian pounds", "Egyptian Pound"],
    SAR: ["SAR", "SAR", "Saudi riyal", "Saudi riyals", "Saudi Riyal"],
    AED: ["AED", "AED", "UAE dirham", "UAE dirhams", "United Arab Emirates Dirham"],
    ARS: ["ARS", "$", "Argentine peso", "Argentine pesos", "Argentine Peso"],
    CLP: ["CLP", "$", "Chilean peso", "Chilean pesos", "Chilean Peso"],
    COP: ["COP", "$", "Colombian peso", "Colombian pesos", "Colombian Peso"],
    PKR: ["PKR", "Rs", "Pakistani rupee", "Pakistani rupees", "Pakistani Rupee"],
    BTN: ["BTN", "BTN", "Bhutanese ngultrum", "Bhutanese ngultrums", "Bhutanese Ngultrum"]
  };

  // ISO 4217's minor units where they aren't 2
  var CURRENCY_DIGITS = {
    BHD: 3, BIF: 0, CLF: 4, CLP: 0, DJF: 0, GNF: 0, IQD: 3, ISK: 0, JOD: 3, JPY: 0, KMF: 0,
    KRW: 0, KWD: 3, LYD: 3, OMR: 3, PYG: 0, RWF: 0, TND: 3, UGX: 0, UYI: 0, UYW: 4, VND: 0,
    VUV: 0, XAF: 0, XOF: 0, XPF: 0
  };

  function currencyDigits(code) {
    var d = CURRENCY_DIGITS[code];
    return typeof d === "number" ? d : 2;
  }

  // short one, short other, narrow, long one, long other (a short or narrow form without a space
  // starts with "!")
  var UNITS = {
    acre: ["ac", "ac", "ac", "acre", "acres"],
    bit: ["bit", "bit", "bit", "bit", "bits"],
    "byte": ["byte", "byte", "B", "byte", "bytes"],
    celsius: ["!°C", "!°C", "!°C", "degree Celsius", "degrees Celsius"],
    centimeter: ["cm", "cm", "!cm", "centimeter", "centimeters"],
    day: ["day", "days", "!d", "day", "days"],
    degree: ["deg", "deg", "!°", "degree", "degrees"],
    fahrenheit: ["!°F", "!°F", "!°", "degree Fahrenheit", "degrees Fahrenheit"],
    "fluid-ounce": ["fl oz", "fl oz", "!fl oz", "fluid ounce", "fluid ounces"],
    foot: ["ft", "ft", "!′", "foot", "feet"],
    gallon: ["gal", "gal", "!gal", "gallon", "gallons"],
    gigabit: ["Gb", "Gb", "!Gb", "gigabit", "gigabits"],
    gigabyte: ["GB", "GB", "!GB", "gigabyte", "gigabytes"],
    gram: ["g", "g", "!g", "gram", "grams"],
    hectare: ["ha", "ha", "!ha", "hectare", "hectares"],
    hour: ["hr", "hr", "!h", "hour", "hours"],
    inch: ["in", "in", "!″", "inch", "inches"],
    kilobit: ["kb", "kb", "!kb", "kilobit", "kilobits"],
    kilobyte: ["kB", "kB", "!kB", "kilobyte", "kilobytes"],
    kilogram: ["kg", "kg", "!kg", "kilogram", "kilograms"],
    kilometer: ["km", "km", "!km", "kilometer", "kilometers"],
    liter: ["L", "L", "!L", "liter", "liters"],
    megabit: ["Mb", "Mb", "!Mb", "megabit", "megabits"],
    megabyte: ["MB", "MB", "!MB", "megabyte", "megabytes"],
    meter: ["m", "m", "!m", "meter", "meters"],
    microsecond: ["μs", "μs", "!μs", "microsecond", "microseconds"],
    mile: ["mi", "mi", "!mi", "mile", "miles"],
    "mile-scandinavian": ["smi", "smi", "!smi", "mile-scandinavian", "miles-scandinavian"],
    milliliter: ["mL", "mL", "!mL", "milliliter", "milliliters"],
    millimeter: ["mm", "mm", "!mm", "millimeter", "millimeters"],
    millisecond: ["ms", "ms", "!ms", "millisecond", "milliseconds"],
    minute: ["min", "min", "!m", "minute", "minutes"],
    month: ["mth", "mths", "!m", "month", "months"],
    nanosecond: ["ns", "ns", "!ns", "nanosecond", "nanoseconds"],
    ounce: ["oz", "oz", "!oz", "ounce", "ounces"],
    percent: ["!%", "!%", "!%", "percent", "percent"],
    petabyte: ["PB", "PB", "!PB", "petabyte", "petabytes"],
    pound: ["lb", "lb", "!#", "pound", "pounds"],
    second: ["sec", "sec", "!s", "second", "seconds"],
    stone: ["st", "st", "!st", "stone", "stones"],
    terabit: ["Tb", "Tb", "!Tb", "terabit", "terabits"],
    terabyte: ["TB", "TB", "!TB", "terabyte", "terabytes"],
    week: ["wk", "wks", "!w", "week", "weeks"],
    yard: ["yd", "yd", "!yd", "yard", "yards"],
    year: ["yr", "yrs", "!y", "year", "years"]
  };
  var UNIT_PER = {
    "kilometer-per-hour": ["km/h", "km/h", "!km/h", "kilometer per hour", "kilometers per hour"],
    "mile-per-hour": ["mph", "mph", "!mph", "mile per hour", "miles per hour"],
    "mile-per-gallon": ["mpg", "mpg", "!mpg", "mile per gallon", "miles per gallon"],
    "meter-per-second": ["m/s", "m/s", "!m/s", "meter per second", "meters per second"],
    "liter-per-kilometer": ["L/km", "L/km", "!L/km", "liter per kilometer", "liters per kilometer"]
  };

  function isSimpleUnit(u) {
    return typeof UNITS[u] === "object" && Obj.prototype.hasOwnProperty.call(UNITS, u);
  }

  function isWellFormedUnit(u) {
    if (isSimpleUnit(u)) return true;
    var at = strIndexOf(u, "-per-");
    if (at < 0) return false;
    return isSimpleUnit(strSlice(u, 0, at)) && isSimpleUnit(strSlice(u, at + 5));
  }

  function unitNames(u) {
    if (isSimpleUnit(u)) return UNITS[u];
    if (Obj.prototype.hasOwnProperty.call(UNIT_PER, u)) return UNIT_PER[u];
    var at = strIndexOf(u, "-per-");
    var a = UNITS[strSlice(u, 0, at)], b = UNITS[strSlice(u, at + 5)];
    var bs = b[0][0] === "!" ? strSlice(b[0], 1) : b[0];
    var as = a[1][0] === "!" ? strSlice(a[1], 1) : a[1];
    var an = a[2][0] === "!" ? strSlice(a[2], 1) : a[2];
    var bn = b[2][0] === "!" ? strSlice(b[2], 1) : b[2];
    return [as + "/" + bs, as + "/" + bs, "!" + an + "/" + bn, a[3] + " per " + b[3], a[4] + " per " + b[3]];
  }

  // ---- NumberFormat ----

  function NumberFormat() {
    var locales = arguments[0], options = arguments[1];
    var nt = new.target === undefined ? NumberFormat : new.target;
    var nf = create(protoFrom(nt, NumberFormatProto));
    initNumberFormat(nf, locales, options);
    if (new.target === undefined && ordinaryHasInstance(NumberFormat, this)) {
      defProp(this, FALLBACK, { value: nf, writable: false, enumerable: false, configurable: false });
      return this;
    }
    return nf;
  }

  var NUMBER_KEYS = ["nu"];
  var NUMBER_DATA = { nu: ["latn"] };

  function initNumberFormat(nf, locales, options) {
    var o = newSlots(nf, "NumberFormat");
    numberSetup(o, locales, options, false);
  }

  function numberSetup(o, locales, options, plural) {
    var requested = localeList(locales);
    options = coerceOptions(options);
    var opt = create(null);
    opt.localeMatcher = getOption(options, "localeMatcher", "string", ["lookup", "best fit"], "best fit");
    if (!plural) {
      var nu = getOption(options, "numberingSystem", "string", undefined, undefined);
      if (nu !== undefined && !isTypeSequence(nu)) throw new RangeErr("Invalid numberingSystem");
      opt.nu = nu === undefined ? undefined : toLower(nu);
    }
    var r = resolveLocale(requested, opt, plural ? [] : NUMBER_KEYS, NUMBER_DATA);
    o.locale = r.locale;
    o.numberingSystem = "latn";
    if (plural) {
      o.type = getOption(options, "type", "string", ["cardinal", "ordinal"], "cardinal");
      o.notation = getOption(options, "notation", "string", ["standard", "scientific", "engineering", "compact"], "standard");
      var cd = getOption(options, "compactDisplay", "string", ["short", "long"], "short");
      if (o.notation === "compact") o.compactDisplay = cd;
      digitOptions(o, options, 0, 3, o.notation);
      return;
    }
    // SetNumberFormatUnitOptions
    var style = getOption(options, "style", "string", ["decimal", "percent", "currency", "unit"], "decimal");
    o.style = style;
    var currency = getOption(options, "currency", "string", undefined, undefined);
    if (currency === undefined) {
      if (style === "currency") throw new TypeErr("Currency code is required with currency style.");
    } else if (!reTest(/^[a-zA-Z]{3}$/, currency)) {
      throw new RangeErr("Invalid currency code : " + currency);
    }
    var currencyDisplay = getOption(options, "currencyDisplay", "string", ["code", "symbol", "narrowSymbol", "name"], "symbol");
    var currencySign = getOption(options, "currencySign", "string", ["standard", "accounting"], "standard");
    var unit = getOption(options, "unit", "string", undefined, undefined);
    if (unit === undefined) {
      if (style === "unit") throw new TypeErr("Unit is required with unit style.");
    } else if (!isWellFormedUnit(unit)) {
      throw new RangeErr("Invalid unit argument: " + unit);
    }
    var unitDisplay = getOption(options, "unitDisplay", "string", ["short", "narrow", "long"], "short");
    if (style === "currency") {
      o.currency = toUpper(currency);
      o.currencyDisplay = currencyDisplay;
      o.currencySign = currencySign;
    }
    if (style === "unit") {
      o.unit = unit;
      o.unitDisplay = unitDisplay;
    }
    var notation = getOption(options, "notation", "string", ["standard", "scientific", "engineering", "compact"], "standard");
    o.notation = notation;
    var mnfdDefault = 0, mxfdDefault = style === "percent" ? 0 : 3;
    if (style === "currency" && notation === "standard") {
      mnfdDefault = mxfdDefault = currencyDigits(o.currency);
    }
    digitOptions(o, options, mnfdDefault, mxfdDefault, notation);
    var compactDisplay = getOption(options, "compactDisplay", "string", ["short", "long"], "short");
    if (notation === "compact") o.compactDisplay = compactDisplay;
    var defaultGrouping = notation === "compact" ? "min2" : "auto";
    o.useGrouping = groupingOption(options, defaultGrouping);
    o.signDisplay = getOption(options, "signDisplay", "string", ["auto", "never", "always", "exceptZero", "negative"], "auto");
  }

  function groupingOption(options, fallback) {
    var v = options.useGrouping;
    if (v === undefined) return fallback;
    if (v === true) return "always";
    if (!v) return false;
    v = toStr(v);
    if (v === "true" || v === "false") return fallback;
    if (!has(["min2", "auto", "always"], v)) throw new RangeErr("Invalid useGrouping value");
    return v;
  }

  function unwrapNumberFormat(nf) {
    if (isObject(nf) && (wmGet(SLOTS, nf) === undefined || wmGet(SLOTS, nf).kind !== "NumberFormat") &&
        ordinaryHasInstance(NumberFormat, nf)) {
      nf = nf[FALLBACK];
    }
    return nf;
  }

  // the exponent for a compact, scientific or engineering number (ComputeExponent)
  function exponentForMagnitude(o, m) {
    if (o.notation === "scientific") return m;
    if (o.notation === "engineering") return floor(m / 3) * 3;
    if (m < 3) return 0;
    if (m >= 15) return 12;
    return floor(m / 3) * 3;
  }

  function computeExponent(o, x) {
    if (x.d === "") return 0;
    var m = x.e - 1;
    var e = exponentForMagnitude(o, m);
    var r = roundFor(o, decScale(x, -e)).x;
    if (r.d === "") return e;
    if (r.e - 1 === m - e) return e;
    return exponentForMagnitude(o, m + 1);
  }

  var COMPACT_SHORT = ["", "K", "M", "B", "T"];
  var COMPACT_LONG = ["", "thousand", "million", "billion", "trillion"];

  function grouped(o, whole, parts) {
    var g = o.useGrouping;
    var n = whole.length;
    var groupOn = g !== false && (g === "min2" ? n >= 5 : n >= 4);
    if (!groupOn) {
      add(parts, { type: "integer", value: whole });
      return;
    }
    var first = n % 3 === 0 ? 3 : n % 3;
    add(parts, { type: "integer", value: strSlice(whole, 0, first) });
    for (var i = first; i < n; i += 3) {
      add(parts, { type: "group", value: "," });
      add(parts, { type: "integer", value: strSlice(whole, i, i + 3) });
    }
  }

  // PartitionNumberPattern: [{type, value}]
  function numberParts(o, x) {
    var parts = newList();
    var exponent = 0;
    var r = x;
    var minFrac = 0;
    if (!x.nan && !x.inf) {
      if (o.style === "percent") r = decScale(r, 2);
      if (o.notation !== "standard") {
        exponent = computeExponent(o, r);
        r = decScale(r, -exponent);
      }
      var rounded = roundFor(o, r);
      r = rounded.x;
      minFrac = rounded.minFrac;
    }
    // the sign
    var neg = x.s;
    var zero = decIsZero(r);
    var sign = "";
    switch (o.signDisplay) {
      case "auto": sign = neg ? "-" : ""; break;
      case "always": sign = neg ? "-" : "+"; break;
      case "exceptZero": sign = x.nan || zero ? "" : neg ? "-" : "+"; break;
      case "negative": sign = neg && !zero ? "-" : ""; break;
      default: sign = "";
    }
    var accounting = o.style === "currency" && o.currencySign === "accounting" && sign === "-";
    // the number itself
    var num = newList();
    if (x.nan) {
      add(num, { type: "nan", value: "NaN" });
    } else if (x.inf) {
      add(num, { type: "infinity", value: "∞" });
    } else {
      var dg = decDigits(r, minFrac, o.minimumIntegerDigits);
      grouped(o, dg.whole, num);
      if (dg.frac !== "") {
        add(num, { type: "decimal", value: "." });
        add(num, { type: "fraction", value: dg.frac });
      }
      if (o.notation === "scientific" || o.notation === "engineering") {
        add(num, { type: "exponentSeparator", value: "E" });
        if (exponent < 0) add(num, { type: "exponentMinusSign", value: "-" });
        add(num, { type: "exponentInteger", value: toStr(abs(exponent)) });
      } else if (o.notation === "compact" && exponent > 0) {
        if (o.compactDisplay === "long") {
          add(num, { type: "literal", value: " " });
          add(num, { type: "compact", value: COMPACT_LONG[exponent / 3] });
        } else {
          add(num, { type: "compact", value: COMPACT_SHORT[exponent / 3] });
        }
      }
    }
    var signPart = sign === "" ? null : { type: sign === "-" ? "minusSign" : "plusSign", value: sign };
    var i;
    if (o.style === "currency") {
      var c = CURRENCIES[o.currency];
      var known = Obj.prototype.hasOwnProperty.call(CURRENCIES, o.currency);
      if (o.currencyDisplay === "name") {
        if (signPart) add(parts, signPart);
        for (i = 0; i < num.length; i++) add(parts, num[i]);
        var one = !x.nan && !x.inf && r.d === "1" && r.e === 1 && minFrac === 0;
        add(parts, { type: "literal", value: " " });
        add(parts, { type: "currency", value: known ? c[one ? 2 : 3] : o.currency });
        return parts;
      }
      var symbol = o.currency;
      if (known && o.currencyDisplay === "symbol") symbol = c[0];
      else if (known && o.currencyDisplay === "narrowSymbol") symbol = c[1];
      if (accounting) add(parts, { type: "literal", value: "(" });
      else if (signPart) add(parts, signPart);
      add(parts, { type: "currency", value: symbol });
      if (reTest(/[A-Za-z]$/, symbol)) add(parts, { type: "literal", value: " " });
      for (i = 0; i < num.length; i++) add(parts, num[i]);
      if (accounting) add(parts, { type: "literal", value: ")" });
      return parts;
    }
    if (signPart) add(parts, signPart);
    for (i = 0; i < num.length; i++) add(parts, num[i]);
    if (o.style === "percent") {
      add(parts, { type: "percentSign", value: "%" });
    } else if (o.style === "unit") {
      var names = unitNames(o.unit);
      var isOne = !x.nan && !x.inf && r.d === "1" && r.e === 1 && minFrac === 0;
      var text = o.unitDisplay === "long" ? names[isOne ? 3 : 4] : o.unitDisplay === "narrow" ? names[2] : names[isOne ? 0 : 1];
      if (text[0] === "!") {
        text = strSlice(text, 1);
      } else {
        add(parts, { type: "literal", value: " " });
      }
      add(parts, { type: "unit", value: text });
    }
    return parts;
  }

  function joinParts(parts) {
    var s = "";
    for (var i = 0; i < parts.length; i++) s += parts[i].value;
    return s;
  }

  function partsArray(parts, extra) {
    var out = [];
    for (var i = 0; i < parts.length; i++) {
      var p = {};
      own(p, "type", parts[i].type);
      own(p, "value", parts[i].value);
      if (extra !== undefined) own(p, extra[0], parts[i][extra[0]] !== undefined ? parts[i][extra[0]] : extra[1]);
      push(out, p);
    }
    return out;
  }

  function formatNumber(o, x) {
    return joinParts(numberParts(o, x));
  }

  // a number formatted only for its digits (what plural rules and relative times look at)
  function plainDigits(o, x) {
    var r = roundFor(o, x);
    var dg = decDigits(r.x, r.minFrac, o.minimumIntegerDigits);
    return dg.frac === "" ? dg.whole : dg.whole + "." + dg.frac;
  }

  // the range of two numbers (PartitionNumberRangePattern)
  function numberRangeParts(o, x, y) {
    var a = numberParts(o, x), b = numberParts(o, y);
    var out = newList();
    var i;
    if (joinParts(a) === joinParts(b)) {
      add(out, { type: "approximatelySign", value: "~", source: "shared" });
      for (i = 0; i < a.length; i++) add(out, { type: a[i].type, value: a[i].value, source: "shared" });
      return out;
    }
    for (i = 0; i < a.length; i++) add(out, { type: a[i].type, value: a[i].value, source: "startRange" });
    var plain = reTest(/^[0-9.,]+$/, joinParts(a)) && reTest(/^[0-9.,]+$/, joinParts(b));
    add(out, { type: "literal", value: plain ? "–" : " – ", source: "shared" });
    for (i = 0; i < b.length; i++) add(out, { type: b[i].type, value: b[i].value, source: "endRange" });
    return out;
  }

  function rangeValues(start, end) {
    if (start === undefined || end === undefined) throw new TypeErr("start and end are required");
    var x = toMathValue(start), y = toMathValue(end);
    if (x.nan || y.nan) throw new RangeErr("Invalid range: NaN");
    return [x, y];
  }

  var NumberFormatProto = {};
  methods(NumberFormatProto, {
    get format() {
      var nf = unwrapNumberFormat(this);
      var o = slotsOf(nf, "NumberFormat", "get Intl.NumberFormat.prototype.format");
      if (o.bound === undefined) {
        o.bound = (0, (value) => formatNumber(o, toMathValue(value)));
      }
      return o.bound;
    },
    formatToParts(value) {
      var o = slotsOf(this, "NumberFormat", "Intl.NumberFormat.prototype.formatToParts");
      return partsArray(numberParts(o, toMathValue(value)));
    },
    formatRange(start, end) {
      var o = slotsOf(this, "NumberFormat", "Intl.NumberFormat.prototype.formatRange");
      var v = rangeValues(start, end);
      return joinParts(numberRangeParts(o, v[0], v[1]));
    },
    formatRangeToParts(start, end) {
      var o = slotsOf(this, "NumberFormat", "Intl.NumberFormat.prototype.formatRangeToParts");
      var v = rangeValues(start, end);
      return partsArray(numberRangeParts(o, v[0], v[1]), ["source", "shared"]);
    },
    resolvedOptions() {
      var nf = unwrapNumberFormat(this);
      var o = slotsOf(nf, "NumberFormat", "Intl.NumberFormat.prototype.resolvedOptions");
      var out = {};
      var names = ["locale", "numberingSystem", "style", "currency", "currencyDisplay", "currencySign",
        "unit", "unitDisplay", "minimumIntegerDigits", "minimumFractionDigits", "maximumFractionDigits",
        "minimumSignificantDigits", "maximumSignificantDigits", "useGrouping", "notation", "compactDisplay",
        "signDisplay", "roundingIncrement", "roundingMode", "roundingPriority", "trailingZeroDisplay"];
      for (var i = 0; i < names.length; i++) {
        if (o[names[i]] !== undefined) own(out, names[i], o[names[i]]);
      }
      return out;
    }
  });
  tag(NumberFormatProto, "Intl.NumberFormat");
  constructorFn(NumberFormat, NumberFormatProto, {
    supportedLocalesOf(locales) {
      return supportedLocales(locales, arguments[1]);
    }
  });

  // ---- PluralRules ----

  function pluralCategory(o, x) {
    if (x.nan || x.inf) return "other";
    var text = plainDigits(o, x);
    var point = strIndexOf(text, ".");
    var whole = point < 0 ? text : strSlice(text, 0, point);
    var fracDigits = point < 0 ? 0 : text.length - point - 1;
    if (o.type === "ordinal") {
      var n10 = toNum(strSlice(whole, -1)), n100 = toNum(strSlice(whole, -2));
      if (fracDigits > 0) return "other";
      if (n10 === 1 && n100 !== 11) return "one";
      if (n10 === 2 && n100 !== 12) return "two";
      if (n10 === 3 && n100 !== 13) return "few";
      return "other";
    }
    return whole === "1" && fracDigits === 0 ? "one" : "other";
  }

  class PluralRules {
    constructor() {
      var locales = arguments[0], options = arguments[1];
      var pr = create(protoFrom(new.target, PluralRulesProto));
      var o = newSlots(pr, "PluralRules");
      numberSetup(o, locales, options, true);
      return pr;
    }
    static supportedLocalesOf(locales) {
      return supportedLocales(locales, arguments[1]);
    }
  }
  var PluralRulesProto = PluralRules.prototype;
  methods(PluralRulesProto, {
    select(value) {
      var o = slotsOf(this, "PluralRules", "Intl.PluralRules.prototype.select");
      return pluralCategory(o, decFromNumber(toNum(value)));
    },
    selectRange(start, end) {
      var o = slotsOf(this, "PluralRules", "Intl.PluralRules.prototype.selectRange");
      if (start === undefined || end === undefined) throw new TypeErr("start and end are required");
      var x = toNum(start), y = toNum(end);
      if (x !== x || y !== y) throw new RangeErr("Invalid range: NaN");
      return pluralCategory(o, decFromNumber(y));
    },
    resolvedOptions() {
      var o = slotsOf(this, "PluralRules", "Intl.PluralRules.prototype.resolvedOptions");
      var out = {};
      own(out, "locale", o.locale);
      own(out, "type", o.type);
      own(out, "notation", o.notation);
      if (o.compactDisplay !== undefined) own(out, "compactDisplay", o.compactDisplay);
      var names = ["minimumIntegerDigits", "minimumFractionDigits", "maximumFractionDigits",
        "minimumSignificantDigits", "maximumSignificantDigits"];
      for (var i = 0; i < names.length; i++) {
        if (o[names[i]] !== undefined) own(out, names[i], o[names[i]]);
      }
      own(out, "pluralCategories", o.type === "ordinal" ? ["one", "two", "few", "other"] : ["one", "other"]);
      own(out, "roundingIncrement", o.roundingIncrement);
      own(out, "roundingMode", o.roundingMode);
      own(out, "roundingPriority", o.roundingPriority);
      own(out, "trailingZeroDisplay", o.trailingZeroDisplay);
      return out;
    }
  });
  tag(PluralRulesProto, "Intl.PluralRules");

  // ======== time zones ========

  var zoneIndex = null;        // lower-case name -> [name, rule number]
  var zoneList = null;
  var zoneLinks = null;        // the names that are only links to others
  var ruleCache = newList();

  function zones() {
    if (zoneIndex !== null) return zoneIndex;
    zoneIndex = create(null);
    zoneList = newList();
    zoneLinks = create(null);
    var items = splitOn(strTrim(ZONE_NAMES), " ");
    for (var i = 0; i < items.length; i++) {
      var at = strIndexOf(items[i], ":");
      if (at < 0) {
        at = strIndexOf(items[i], "=");
        zoneLinks[strSlice(items[i], 0, at)] = true;
      }
      var name = strSlice(items[i], 0, at);
      zoneIndex[toLower(name)] = [name, toNum(strSlice(items[i], at + 1))];
      add(zoneList, name);
    }
    return zoneIndex;
  }

  // a POSIX TZ rule, as tzfile(5) has it at the end of each zone's file
  function parseRule(text) {
    var i = 0;
    function name() {
      var start;
      if (text[i] === "<") {
        start = i + 1;
        i = strIndexOf(text, ">", i) + 1;
        return strSlice(text, start, i - 1);
      }
      start = i;
      while (i < text.length && reTest(/[A-Za-z]/, text[i])) i++;
      return strSlice(text, start, i);
    }
    function number() {
      var start = i;
      while (i < text.length && isDigit(text[i])) i++;
      return toNum(strSlice(text, start, i));
    }
    function clock() {
      // [+-]hh[:mm[:ss]], in seconds
      var sign = 1;
      if (text[i] === "+") i++;
      else if (text[i] === "-") {
        sign = -1;
        i++;
      }
      var s = number() * 3600;
      if (text[i] === ":") {
        i++;
        s += number() * 60;
        if (text[i] === ":") {
          i++;
          s += number();
        }
      }
      return sign * s;
    }
    function when() {
      var w = create(null);
      if (text[i] === "M") {
        i++;
        w.month = number();
        i++;
        w.week = number();
        i++;
        w.weekday = number();
      } else if (text[i] === "J") {
        i++;
        w.julian = number();
      } else {
        w.day = number();
      }
      w.time = 7200;
      if (text[i] === "/") {
        i++;
        w.time = clock();
      }
      return w;
    }
    var r = create(null);
    r.std = name();
    r.stdOffset = -clock();
    r.dst = "";
    if (i < text.length && text[i] !== ",") {
      r.dst = name();
      r.dstOffset = i < text.length && text[i] !== "," ? -clock() : r.stdOffset + 3600;
    }
    if (text[i] === ",") {
      i++;
      r.start = when();
      i++;
      r.end = when();
    }
    return r;
  }

  function zoneRule(n) {
    if (ruleCache[n] === undefined) ruleCache[n] = parseRule(ZONE_RULES[n]);
    return ruleCache[n];
  }

  // when, in UTC seconds, a rule's change comes in a year, given the offset before it
  function changeAt(w, year, offset) {
    var day;
    if (w.month !== undefined) {
      var first = daysFromCivil(year, w.month, 1);
      var wd = ((first + 4) % 7 + 7) % 7;
      day = first + (w.weekday - wd + 7) % 7 + (w.week - 1) * 7;
      var next = w.month === 12 ? daysFromCivil(year + 1, 1, 1) : daysFromCivil(year, w.month + 1, 1);
      while (day >= next) day -= 7;
    } else if (w.julian !== undefined) {
      day = daysFromCivil(year, 1, 1) + w.julian - 1;
      if (w.julian >= 60 && isLeap(year)) day++;
    } else {
      day = daysFromCivil(year, 1, 1) + w.day;
    }
    return day * 86400 + w.time - offset;
  }

  // the zone's offset east of UTC, in seconds, at a time (ms), and whether it's the second (summer) one
  function zoneOffset(z, t) {
    if (z.offset !== undefined) return [z.offset, false];
    var r = zoneRule(z.rule);
    if (r.start === undefined) return [r.stdOffset, false];
    var secs = floor(t / 1000);
    var year = civil((secs + r.stdOffset) * 1000).year;
    var a = changeAt(r.start, year, r.stdOffset);
    var b = changeAt(r.end, year, r.dstOffset);
    var dst = a < b ? secs >= a && secs < b : secs >= a || secs < b;
    return dst ? [r.dstOffset, true] : [r.stdOffset, false];
  }

  // a time zone named as a script names it: its record, or undefined if there's no such zone
  function findZone(name) {
    var m = /^([+-])([01][0-9]|2[0-3])(?::?([0-5][0-9]))?$/.exec(name);
    var z = create(null);
    if (m !== null) {
      var mins = toNum(m[2]) * 60 + (m[3] !== undefined ? toNum(m[3]) : 0);
      if (m[1] === "-") mins = -mins;
      z.offset = mins * 60;
      z.name = offsetName(mins, true);
      return z;
    }
    var found = zones()[toLower(name)];
    if (found === undefined) return undefined;
    z.name = found[0];
    z.rule = found[1];
    return z;
  }

  function offsetName(mins, colon) {
    var sign = mins < 0 ? "-" : "+";
    mins = abs(mins);
    return sign + pad(floor(mins / 60), 2) + (colon ? ":" : "") + pad(mins % 60, 2);
  }

  // the host's zone: the engine knows only its offset, so that's what it is
  function defaultZone() {
    var mins = -dateOffset(new NativeDate(0));
    if (mins === 0) return findZone("UTC");
    return findZone(offsetName(mins, true));
  }

  // what each kind of zone is called in English (by the zone's rule names and offset)
  var ZONE_TITLES = {
    "EST-300": ["Eastern", "ET"], "CST-360": ["Central", "CT"], "MST-420": ["Mountain", "MT"],
    "PST-480": ["Pacific", "PT"], "AKST-540": ["Alaska", "AKT"], "HST-600": ["Hawaii-Aleutian", "HST"],
    "AST-240": ["Atlantic", "AT"], "NST-210": ["Newfoundland", ""],
    "CET60": ["Central European", ""], "EET120": ["Eastern European", ""], "WET0": ["Western European", ""],
    "MSK180": ["Moscow", ""], "IST330": ["India", ""], "JST540": ["Japan", ""], "KST540": ["Korean", ""],
    "CST480": ["China", ""], "HKT480": ["Hong Kong", ""], "PKT300": ["Pakistan", ""],
    "AEST600": ["Australian Eastern", ""], "ACST570": ["Australian Central", ""],
    "AWST480": ["Australian Western", ""], "NZST720": ["New Zealand", ""], "SAST120": ["South Africa", ""],
    "WIB420": ["Western Indonesia", ""], "PHT480": ["Philippine", ""], "IDT120": ["Israel", ""],
    "IST120": ["Israel", ""], "CAT120": ["Central Africa", ""], "EAT180": ["East Africa", ""],
    "WAT60": ["West Africa", ""], "SST-660": ["Samoa", ""], "ChST600": ["Chamorro", ""]
  };

  function gmtText(secs, long) {
    var mins = secs / 60;
    var sign = mins < 0 ? "-" : "+";
    mins = abs(mins);
    var h = floor(mins / 60), m = mins % 60;
    if (long) return "GMT" + sign + pad(h, 2) + ":" + pad(m, 2);
    return "GMT" + sign + h + (m !== 0 ? ":" + pad(m, 2) : "");
  }

  function zoneTitle(z, t, style) {
    var off = zoneOffset(z, t);
    if (z.offset === undefined) {
      var lower = toLower(z.name);
      if (lower === "utc" || lower === "etc/utc" || lower === "etc/uct" || lower === "uct" ||
          lower === "etc/universal" || lower === "universal" || lower === "etc/zulu" || lower === "zulu") {
        if (style === "long") return "Coordinated Universal Time";
        if (style === "short") return "UTC";
      }
      var r = zoneRule(z.rule);
      var key = r.std + floor(r.stdOffset / 60);
      var title = Obj.prototype.hasOwnProperty.call(ZONE_TITLES, key) ? ZONE_TITLES[key] : null;
      if (lower === "europe/london" && title === null) title = ["British", ""];
      if (title === null && r.std === "GMT" && r.dst === "") title = ["Greenwich Mean", ""];
      if (title !== null) {
        var us = title[1] !== "";
        var generic = style === "longGeneric" || style === "shortGeneric";
        if (style === "long" || (style === "longGeneric" && r.dst === "")) {
          if (title[0] === "British") return off[1] ? "British Summer Time" : "Greenwich Mean Time";
          if (title[0] === "Greenwich Mean") return "Greenwich Mean Time";
          var summer = strIndexOf(title[0], "European") >= 0 ? "Summer" : "Daylight";
          return title[0] + (off[1] ? " " + summer : " Standard") + " Time";
        }
        if (style === "longGeneric") return title[0] === "British" ? "United Kingdom Time" : title[0] + " Time";
        if (us && (style === "short" || (generic && r.dst === ""))) return off[1] && r.dst !== "" ? r.dst : r.std;
        if (style === "shortGeneric" && us) return title[1];
        if (title[0] === "Greenwich Mean" && (style === "short" || style === "shortGeneric")) return "GMT";
      }
    }
    if (style === "long" || style === "longOffset" || style === "longGeneric") return gmtText(off[0], true);
    return gmtText(off[0], false);
  }

  // ======== dates ========

  function isLeap(y) {
    return y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
  }

  function daysFromCivil(y, m, d) {
    y -= m <= 2 ? 1 : 0;
    var era = floor(y / 400);
    var yoe = y - era * 400;
    var doy = floor((153 * (m + (m > 2 ? -3 : 9)) + 2) / 5) + d - 1;
    var doe = yoe * 365 + floor(yoe / 4) - floor(yoe / 100) + doy;
    return era * 146097 + doe - 719468;
  }

  // the fields of a time (ms, already moved into the zone)
  function civil(t) {
    var days = floor(t / 86400000);
    var ms = t - days * 86400000;
    var z = days + 719468;
    var era = floor(z / 146097);
    var doe = z - era * 146097;
    var yoe = floor((doe - floor(doe / 1460) + floor(doe / 36524) - floor(doe / 146096)) / 365);
    var doy = doe - (365 * yoe + floor(yoe / 4) - floor(yoe / 100));
    var mp = floor((5 * doy + 2) / 153);
    var c = create(null);
    c.day = doy - floor((153 * mp + 2) / 5) + 1;
    c.month = mp < 10 ? mp + 3 : mp - 9;
    c.year = yoe + era * 400 + (c.month <= 2 ? 1 : 0);
    c.weekday = ((days + 4) % 7 + 7) % 7;
    c.hour = floor(ms / 3600000);
    c.minute = floor(ms / 60000) % 60;
    c.second = floor(ms / 1000) % 60;
    c.ms = ms % 1000;
    return c;
  }

  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
    "October", "November", "December"];
  var WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

  function monthText(m, style) {
    var name = MONTHS[m - 1];
    if (style === "long") return name;
    if (style === "short") return strSlice(name, 0, 3);
    return name[0];
  }

  function weekdayText(d, style) {
    var name = WEEKDAYS[d];
    if (style === "long") return name;
    if (style === "short") return strSlice(name, 0, 3);
    return name[0];
  }

  function eraText(year, style) {
    var ad = year > 0;
    if (style === "long") return ad ? "Anno Domini" : "Before Christ";
    if (style === "short") return ad ? "AD" : "BC";
    return ad ? "A" : "B";
  }

  function dayPeriodText(h, m, style) {
    if (h === 12 && m === 0) return style === "narrow" ? "n" : "noon";
    if (h < 12) return "in the morning";
    if (h < 18) return "in the afternoon";
    if (h < 21) return "in the evening";
    return "at night";
  }

  var DATE_FIELDS = [
    ["weekday", ["narrow", "short", "long"]],
    ["era", ["narrow", "short", "long"]],
    ["year", ["2-digit", "numeric"]],
    ["month", ["2-digit", "numeric", "narrow", "short", "long"]],
    ["day", ["2-digit", "numeric"]],
    ["dayPeriod", ["narrow", "short", "long"]],
    ["hour", ["2-digit", "numeric"]],
    ["minute", ["2-digit", "numeric"]],
    ["second", ["2-digit", "numeric"]],
    ["fractionalSecondDigits", null],
    ["timeZoneName", ["short", "long", "shortOffset", "longOffset", "shortGeneric", "longGeneric"]]
  ];

  var DATE_KEYS = ["ca", "hc", "nu"];
  var DATE_DATA = { ca: ["gregory"], hc: [null, "h11", "h12", "h23", "h24"], nu: ["latn"] };

  function DateTimeFormat() {
    var locales = arguments[0], options = arguments[1];
    var nt = new.target === undefined ? DateTimeFormat : new.target;
    var dtf = create(protoFrom(nt, DateTimeFormatProto));
    var o = newSlots(dtf, "DateTimeFormat");
    dateSetup(o, locales, options, "any", "date");
    if (new.target === undefined && ordinaryHasInstance(DateTimeFormat, this)) {
      defProp(this, FALLBACK, { value: dtf, writable: false, enumerable: false, configurable: false });
      return this;
    }
    return dtf;
  }

  // CreateDateTimeFormat: required is "any", "date" or "time"; defaults "date", "time" or "all"
  function dateSetup(o, locales, options, required, defaults) {
    var requested = localeList(locales);
    options = coerceOptions(options);
    var opt = create(null);
    opt.localeMatcher = getOption(options, "localeMatcher", "string", ["lookup", "best fit"], "best fit");
    var calendar = getOption(options, "calendar", "string", undefined, undefined);
    if (calendar !== undefined && !isTypeSequence(calendar)) throw new RangeErr("Invalid calendar");
    opt.ca = calendar === undefined ? undefined : toLower(calendar);
    var nu = getOption(options, "numberingSystem", "string", undefined, undefined);
    if (nu !== undefined && !isTypeSequence(nu)) throw new RangeErr("Invalid numberingSystem");
    opt.nu = nu === undefined ? undefined : toLower(nu);
    var hour12 = getOption(options, "hour12", "boolean", undefined, undefined);
    var hourCycle = getOption(options, "hourCycle", "string", ["h11", "h12", "h23", "h24"], undefined);
    if (hour12 !== undefined) hourCycle = null;
    opt.hc = hourCycle;
    var r = resolveLocale(requested, opt, DATE_KEYS, DATE_DATA);
    o.locale = r.locale;
    o.calendar = r.ca;
    o.numberingSystem = r.nu;
    var tz = options.timeZone;
    var zone;
    if (tz === undefined) {
      zone = defaultZone();
    } else {
      tz = toStr(tz);
      zone = findZone(tz);
      if (zone === undefined) throw new RangeErr("Invalid time zone specified: " + tz);
    }
    o.zone = zone;
    o.timeZone = zone.name;
    var f = create(null);
    var any = false;
    for (var i = 0; i < DATE_FIELDS.length; i++) {
      var name = DATE_FIELDS[i][0];
      var v;
      if (name === "fractionalSecondDigits") {
        v = getNumberOption(options, name, 1, 3, undefined);
      } else {
        v = getOption(options, name, "string", DATE_FIELDS[i][1], undefined);
      }
      f[name] = v;
      if (v !== undefined) any = true;
    }
    getOption(options, "formatMatcher", "string", ["basic", "best fit"], "best fit");
    var dateStyle = getOption(options, "dateStyle", "string", ["full", "long", "medium", "short"], undefined);
    var timeStyle = getOption(options, "timeStyle", "string", ["full", "long", "medium", "short"], undefined);
    o.dateStyle = dateStyle;
    o.timeStyle = timeStyle;
    var hc = r.hc;
    if (hour12 !== undefined) hc = hour12 ? "h12" : "h23";
    if (hc === null || hc === undefined) hc = "h12";
    if (dateStyle !== undefined || timeStyle !== undefined) {
      if (any) throw new TypeErr("Can't set option " + "dateStyle or timeStyle with other date and time options");
      if (required === "date" && timeStyle !== undefined) throw new TypeErr("Invalid option : timeStyle");
      if (required === "time" && dateStyle !== undefined) throw new TypeErr("Invalid option : dateStyle");
      o.fields = styleFields(dateStyle, timeStyle);
      if (timeStyle !== undefined) o.hourCycle = hc;
      o.styled = true;
      return;
    }
    var needDefaults = true;
    if ((required === "date" || required === "any") &&
        (f.weekday !== undefined || f.year !== undefined || f.month !== undefined || f.day !== undefined)) {
      needDefaults = false;
    }
    if ((required === "time" || required === "any") &&
        (f.dayPeriod !== undefined || f.hour !== undefined || f.minute !== undefined || f.second !== undefined ||
         f.fractionalSecondDigits !== undefined)) {
      needDefaults = false;
    }
    if (needDefaults && (defaults === "date" || defaults === "all")) {
      f.year = f.month = f.day = "numeric";
    }
    if (needDefaults && (defaults === "time" || defaults === "all")) {
      f.hour = f.minute = f.second = "numeric";
    }
    // what en-US's patterns make of them
    if (f.hour !== undefined) {
      o.hourCycle = hc;
      if (hc === "h23" || hc === "h24") f.hour = "2-digit";
      if (f.minute !== undefined) f.minute = "2-digit";
    }
    if (f.second !== undefined && (f.minute !== undefined || f.hour !== undefined)) f.second = "2-digit";
    if (f.minute !== undefined && f.hour === undefined && f.second !== undefined) f.minute = "2-digit";
    o.fields = f;
    o.styled = false;
  }

  function styleFields(dateStyle, timeStyle) {
    var f = create(null);
    if (dateStyle === "full") {
      f.weekday = "long";
      f.month = "long";
      f.day = "numeric";
      f.year = "numeric";
    } else if (dateStyle === "long") {
      f.month = "long";
      f.day = "numeric";
      f.year = "numeric";
    } else if (dateStyle === "medium") {
      f.month = "short";
      f.day = "numeric";
      f.year = "numeric";
    } else if (dateStyle === "short") {
      f.month = "numeric";
      f.day = "numeric";
      f.year = "2-digit";
    }
    if (timeStyle !== undefined) {
      f.hour = "numeric";
      f.minute = "2-digit";
      if (timeStyle !== "short") f.second = "2-digit";
      if (timeStyle === "full") f.timeZoneName = "long";
      else if (timeStyle === "long") f.timeZoneName = "short";
    }
    f.dateStyle = dateStyle;
    return f;
  }

  // the parts of a time (ms since 1970, UTC) as the format has it
  function dateParts(o, t) {
    var f = o.fields;
    var off = zoneOffset(o.zone, t);
    var c = civil(t + off[0] * 1000);
    var date = newList(), time = newList();
    var year = c.year <= 0 ? 1 - c.year : c.year;
    var yearText = f.year === "2-digit" ? pad(year % 100, 2) : toStr(year);
    var textMonth = f.month === "long" || f.month === "short" || f.month === "narrow";
    var i;
    function part(list, type, value) {
      add(list, { type: type, value: value });
    }
    if (textMonth) {
      if (f.weekday !== undefined) {
        part(date, "weekday", weekdayText(c.weekday, f.weekday));
        part(date, "literal", ", ");
      }
      part(date, "month", monthText(c.month, f.month));
      if (f.day !== undefined) {
        part(date, "literal", " ");
        part(date, "day", f.day === "2-digit" ? pad(c.day, 2) : toStr(c.day));
      }
      if (f.year !== undefined) {
        part(date, "literal", f.day !== undefined ? ", " : " ");
        part(date, "year", yearText);
      }
      if (f.era !== undefined) {
        part(date, "literal", " ");
        part(date, "era", eraText(c.year, f.era));
      }
    } else {
      var nums = newList();
      if (f.month !== undefined) add(nums, ["month", f.month === "2-digit" ? pad(c.month, 2) : toStr(c.month)]);
      if (f.day !== undefined) add(nums, ["day", f.day === "2-digit" ? pad(c.day, 2) : toStr(c.day)]);
      if (f.year !== undefined) add(nums, ["year", yearText]);
      if (f.weekday !== undefined) {
        part(date, "weekday", weekdayText(c.weekday, f.weekday));
        if (nums.length > 0) part(date, "literal", ", ");
      }
      for (i = 0; i < nums.length; i++) {
        if (i > 0) part(date, "literal", "/");
        part(date, nums[i][0], nums[i][1]);
      }
      if (f.era !== undefined) {
        if (date.length > 0) part(date, "literal", " ");
        part(date, "era", eraText(c.year, f.era));
      }
    }
    // the time
    var twelve = o.hourCycle === "h11" || o.hourCycle === "h12";
    if (f.hour !== undefined) {
      var h = c.hour;
      if (o.hourCycle === "h12") h = h % 12 === 0 ? 12 : h % 12;
      else if (o.hourCycle === "h11") h = h % 12;
      else if (o.hourCycle === "h24") h = h === 0 ? 24 : h;
      part(time, "hour", f.hour === "2-digit" ? pad(h, 2) : toStr(h));
    }
    if (f.minute !== undefined) {
      if (time.length > 0) part(time, "literal", ":");
      part(time, "minute", f.minute === "2-digit" || f.hour !== undefined ? pad(c.minute, 2) : toStr(c.minute));
    }
    if (f.second !== undefined) {
      if (time.length > 0) part(time, "literal", ":");
      part(time, "second", f.second === "2-digit" || time.length > 0 ? pad(c.second, 2) : toStr(c.second));
    }
    if (f.fractionalSecondDigits !== undefined) {
      if (time.length > 0) part(time, "literal", ".");
      part(time, "fractionalSecond", strSlice(pad(c.ms, 3), 0, f.fractionalSecondDigits));
    }
    if (f.hour !== undefined && twelve) {
      part(time, "literal", " ");
      if (f.dayPeriod !== undefined) part(time, "dayPeriod", dayPeriodText(c.hour, c.minute, f.dayPeriod));
      else part(time, "dayPeriod", c.hour < 12 ? "AM" : "PM");
    } else if (f.dayPeriod !== undefined && f.hour === undefined) {
      if (time.length > 0) part(time, "literal", " ");
      part(time, "dayPeriod", dayPeriodText(c.hour, c.minute, f.dayPeriod));
    }
    if (f.timeZoneName !== undefined) {
      if (time.length > 0) part(time, "literal", " ");
      part(time, "timeZoneName", zoneTitle(o.zone, t, f.timeZoneName));
    }
    var out = newList();
    for (i = 0; i < date.length; i++) add(out, date[i]);
    if (date.length > 0 && time.length > 0) {
      var onlyWeekday = date.length === 1 && date[0].type === "weekday";
      var joint = onlyWeekday ? " " : (f.dateStyle === "full" || f.dateStyle === "long") ? " at " : ", ";
      add(out, { type: "literal", value: joint });
    }
    for (i = 0; i < time.length; i++) add(out, time[i]);
    return out;
  }

  function timeValue(date) {
    var t = date === undefined ? dateNow() : toNum(date);
    if (t !== t || abs(t) > 8.64e15) throw new RangeErr("Invalid time value");
    return (t < 0 ? -floor(-t) : floor(t)) + 0;
  }

  function unwrapDateTimeFormat(dtf) {
    if (isObject(dtf) && (wmGet(SLOTS, dtf) === undefined || wmGet(SLOTS, dtf).kind !== "DateTimeFormat") &&
        ordinaryHasInstance(DateTimeFormat, dtf)) {
      dtf = dtf[FALLBACK];
    }
    return dtf;
  }

  function civilIn(o, t) {
    return civil(t + zoneOffset(o.zone, t)[0] * 1000);
  }

  function rangePush(out, parts, from, to, source) {
    for (var i = from; i < to; i++) add(out, { type: parts[i].type, value: parts[i].value, source: source });
  }

  function indexOfType(parts, type) {
    for (var i = 0; i < parts.length; i++) {
      if (parts[i].type === type) return i;
    }
    return -1;
  }

  // two dates, sharing what they have in common as en-US does ("Nov 21 – 24, 2026", "3:04 – 4:04 PM")
  function dateRangeParts(o, a, b) {
    var x = dateParts(o, a), y = dateParts(o, b);
    var out = newList();
    var i;
    var f = o.fields;
    var ca = civilIn(o, a), cb = civilIn(o, b);
    var sameDay = ca.year === cb.year && ca.month === cb.month && ca.day === cb.day;
    var hasTime = f.hour !== undefined || f.minute !== undefined || f.second !== undefined;
    var hasDate = f.year !== undefined || f.month !== undefined || f.day !== undefined || f.weekday !== undefined;
    var dash = { type: "literal", value: " \u2013 ", source: "shared" };
    // times on different days need their dates, and days in different years their years
    if ((hasTime && !sameDay && !hasDate) || (hasDate && f.year === undefined && ca.year !== cb.year)) {
      var o2 = create(null);
      var keys = keysOf(o);
      for (i = 0; i < keys.length; i++) o2[keys[i]] = o[keys[i]];
      var f2 = create(null);
      keys = keysOf(f);
      for (i = 0; i < keys.length; i++) f2[keys[i]] = f[keys[i]];
      if (!hasDate) f2.month = f2.day = "numeric";
      f2.year = "numeric";
      f2.dateStyle = undefined;
      o2.fields = f2;
      return dateRangeParts(o2, a, b);
    }
    if (joinParts(x) === joinParts(y)) {
      rangePush(out, x, 0, x.length, "shared");
      return out;
    }
    if (hasTime && sameDay) {
      var tx = indexOfType(x, "hour");
      if (tx < 0) tx = indexOfType(x, "minute");
      if (tx < 0) tx = 0;
      if (tx > 0) {
        rangePush(out, x, 0, tx - 1, "shared");
        add(out, { type: "literal", value: ", ", source: "shared" });
      }
      var px = indexOfType(x, "dayPeriod"), py = indexOfType(y, "dayPeriod");
      var cut = x.length;
      if (px > 0 && py > 0 && x[px].value === y[py].value && indexOfType(x, "timeZoneName") < 0) cut = px - 1;
      rangePush(out, x, tx, cut, "startRange");
      add(out, dash);
      rangePush(out, y, tx, y.length, "endRange");
      return out;
    }
    var textMonth = f.month === "long" || f.month === "short" || f.month === "narrow";
    if (!hasTime && textMonth && ca.year === cb.year && f.era === undefined) {
      var yx = indexOfType(x, "year");
      var startEnd = yx > 0 ? yx - 1 : x.length;
      rangePush(out, x, 0, startEnd, "startRange");
      add(out, dash);
      var from = 0;
      if (ca.month === cb.month && f.weekday === undefined && f.day !== undefined) from = indexOfType(y, "month") + 2;
      rangePush(out, y, from, y.length, "endRange");
      return out;
    }
    rangePush(out, x, 0, x.length, "startRange");
    add(out, dash);
    rangePush(out, y, 0, y.length, "endRange");
    return out;
  }

  function dateRangeValues(start, end) {
    if (start === undefined || end === undefined) throw new TypeErr("startDate and endDate are required");
    return [timeValue(start), timeValue(end)];
  }

  var DateTimeFormatProto = {};
  methods(DateTimeFormatProto, {
    get format() {
      var dtf = unwrapDateTimeFormat(this);
      var o = slotsOf(dtf, "DateTimeFormat", "get Intl.DateTimeFormat.prototype.format");
      if (o.bound === undefined) {
        o.bound = (0, (date) => joinParts(dateParts(o, timeValue(date))));
      }
      return o.bound;
    },
    formatToParts(date) {
      var o = slotsOf(this, "DateTimeFormat", "Intl.DateTimeFormat.prototype.formatToParts");
      return partsArray(dateParts(o, timeValue(date)));
    },
    formatRange(startDate, endDate) {
      var o = slotsOf(this, "DateTimeFormat", "Intl.DateTimeFormat.prototype.formatRange");
      var v = dateRangeValues(startDate, endDate);
      return joinParts(dateRangeParts(o, v[0], v[1]));
    },
    formatRangeToParts(startDate, endDate) {
      var o = slotsOf(this, "DateTimeFormat", "Intl.DateTimeFormat.prototype.formatRangeToParts");
      var v = dateRangeValues(startDate, endDate);
      return partsArray(dateRangeParts(o, v[0], v[1]), ["source", "shared"]);
    },
    resolvedOptions() {
      var dtf = unwrapDateTimeFormat(this);
      var o = slotsOf(dtf, "DateTimeFormat", "Intl.DateTimeFormat.prototype.resolvedOptions");
      var out = {};
      own(out, "locale", o.locale);
      own(out, "calendar", o.calendar);
      own(out, "numberingSystem", o.numberingSystem);
      own(out, "timeZone", o.timeZone);
      if (o.hourCycle !== undefined) {
        own(out, "hourCycle", o.hourCycle);
        own(out, "hour12", o.hourCycle === "h11" || o.hourCycle === "h12");
      }
      if (!o.styled) {
        for (var i = 0; i < DATE_FIELDS.length; i++) {
          var name = DATE_FIELDS[i][0];
          if (o.fields[name] !== undefined) own(out, name, o.fields[name]);
        }
      }
      if (o.dateStyle !== undefined) own(out, "dateStyle", o.dateStyle);
      if (o.timeStyle !== undefined) own(out, "timeStyle", o.timeStyle);
      return out;
    }
  });
  tag(DateTimeFormatProto, "Intl.DateTimeFormat");
  constructorFn(DateTimeFormat, DateTimeFormatProto, {
    supportedLocalesOf(locales) {
      return supportedLocales(locales, arguments[1]);
    }
  });

  // ======== Collator ========

  var foldTable = null;      // a letter with marks -> [the letter, its marks]
  // marks in the order the Unicode collation algorithm gives them weight
  var MARK_ORDER = "̵̸̨̧̛̣̱̦̥̭̰̤̮́̀̆̂̌̊̈̋̃̇̄̉̏̑";

  function folds() {
    if (foldTable !== null) return foldTable;
    foldTable = create(null);
    var items = splitOn(FOLDS, "|");
    for (var i = 0; i < items.length; i++) {
      var s = items[i];
      if (s.length < 3) continue;
      foldTable[s[0]] = [s[1], strSlice(s, 2)];
    }
    // letters Unicode doesn't take apart, but sorts with others
    var extra = [["ß", "ss", ""], ["æ", "ae", ""], ["Æ", "AE", ""], ["œ", "oe", ""],
      ["Œ", "OE", ""], ["ø", "o", "̸"], ["Ø", "O", "̸"], ["đ", "d", "̵"],
      ["Đ", "D", "̵"], ["ł", "l", "̸"], ["Ł", "L", "̸"], ["ı", "i", "̇"],
      ["ð", "d", "̉"], ["Ð", "D", "̉"]];
    for (i = 0; i < extra.length; i++) foldTable[extra[i][0]] = [extra[i][1], extra[i][2]];
    return foldTable;
  }

  var PUNCTUATION = " _-,;:!?.'\"()[]{}@*/\\&#%`^+<=>|~$";

  function isMark(cp) {
    if (cp >= 0x300 && cp <= 0x36f) return true;
    if (cp >= 0x1ab0 && cp <= 0x1aff) return true;
    if (cp >= 0x1dc0 && cp <= 0x1dff) return true;
    if (cp >= 0x20d0 && cp <= 0x20ff) return true;
    if (cp >= 0xfe20 && cp <= 0xfe2f) return true;
    if (cp >= 0xfe00 && cp <= 0xfe0f) return true;
    if (cp === 0x200d || cp === 0x200c) return true;
    if (cp >= 0xe0100 && cp <= 0xe01ef) return true;
    if (cp >= 0x483 && cp <= 0x489) return true;
    if (cp >= 0x591 && cp <= 0x5c7) return cp !== 0x5be && cp !== 0x5c0 && cp !== 0x5c3 && cp !== 0x5c6;
    if (cp >= 0x610 && cp <= 0x61a) return true;
    if (cp >= 0x64b && cp <= 0x65f) return true;
    if (cp === 0x670 || (cp >= 0x6d6 && cp <= 0x6dc) || (cp >= 0x6df && cp <= 0x6e4) || cp === 0x6e7 ||
        cp === 0x6e8 || (cp >= 0x6ea && cp <= 0x6ed)) return true;
    if ((cp >= 0x900 && cp <= 0xdff) || (cp >= 0xe00 && cp <= 0xeff) || (cp >= 0x1000 && cp <= 0x109f)) {
      var c = fromCodePoint(cp);
      return !reTest(/[\p{L}\p{N}\p{P}\p{S}\p{Z}]/u, c);
    }
    return false;
  }

  // the three levels of a string's sort key
  function sortKey(text, o) {
    var table = folds();
    var p = newList(), s = newList(), t = newList();
    var i = 0, n = text.length;
    while (i < n) {
      var cp = codePointAt(text, i);
      var ch = fromCodePoint(cp);
      i += ch.length;
      if (isMark(cp)) {
        var mi = strIndexOf(MARK_ORDER, ch);
        if (s.length > 0) s[s.length - 1] = s[s.length - 1] * 64 + (mi < 0 ? 40 : mi + 1);
        continue;
      }
      if (o.numeric && isDigit(ch)) {
        var start = i - 1;
        while (i < n && isDigit(text[i])) i++;
        var digits = strSlice(text, start, i);
        var z = 0;
        while (z < digits.length - 1 && digits[z] === "0") z++;
        digits = strSlice(digits, z);
        add(p, 2000 + digits.length);
        for (var k = 0; k < digits.length; k++) {
          add(p, 1000 + charCodeAt(digits, k));
          add(s, 0);
          add(t, 0);
        }
        continue;
      }
      var base = ch, marks = "";
      var f = table[ch];
      if (f !== undefined) {
        base = f[0];
        marks = f[1];
      }
      for (var j = 0; j < base.length; j++) {
        var b = base[j];
        var lower = toLower(b);
        var weight;
        var pi = strIndexOf(PUNCTUATION, b);
        if (pi >= 0 || reTest(/[\p{P}\p{S}\p{Z}]/u, b)) {
          if (o.ignorePunctuation) continue;
          weight = pi >= 0 ? 100 + pi : 200 + charCodeAt(b, 0) % 700;
        } else if (isDigit(b)) {
          weight = 1000 + charCodeAt(b, 0);
        } else if (lower >= "a" && lower <= "z") {
          weight = 3000 + charCodeAt(lower, 0);
        } else {
          weight = 4000 + codePointAt(lower, 0);
        }
        add(p, weight);
        var mark = 0;
        if (j === base.length - 1 && base.length > 1) mark = 50;
        if (j === base.length - 1) {
          for (var q = 0; q < marks.length; q++) {
            var w = strIndexOf(MARK_ORDER, marks[q]);
            mark = mark * 64 + (w < 0 ? 40 : w + 1);
          }
        }
        add(s, mark);
        var upper = lower !== b;
        add(t, o.caseFirst === "upper" ? (upper ? 0 : 1) : (upper ? 1 : 0));
      }
    }
    return [p, s, t];
  }

  function compareLists(a, b) {
    var n = min(a.length, b.length);
    for (var i = 0; i < n; i++) {
      if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
    }
    return a.length === b.length ? 0 : a.length < b.length ? -1 : 1;
  }

  function collate(o, x, y) {
    if (x === y) return 0;
    var a = sortKey(x, o), b = sortKey(y, o);
    var r = compareLists(a[0], b[0]);
    if (r !== 0) return r;
    if (o.sensitivity === "accent" || o.sensitivity === "variant") {
      r = compareLists(a[1], b[1]);
      if (r !== 0) return r;
    }
    if (o.sensitivity === "case" || o.sensitivity === "variant") {
      r = compareLists(a[2], b[2]);
      if (r !== 0) return r;
    }
    return 0;
  }

  var COLLATOR_KEYS = ["co", "kf", "kn"];
  var COLLATOR_DATA = { co: [null, "emoji", "eor"], kf: ["false", "lower", "upper"], kn: ["false", "true"] };

  function Collator() {
    var locales = arguments[0], options = arguments[1];
    var nt = new.target === undefined ? Collator : new.target;
    var c = create(protoFrom(nt, CollatorProto));
    collatorSetup(newSlots(c, "Collator"), locales, options);
    return c;
  }

  function collatorSetup(o, locales, options) {
    var requested = localeList(locales);
    options = coerceOptions(options);
    o.usage = getOption(options, "usage", "string", ["sort", "search"], "sort");
    var opt = create(null);
    opt.localeMatcher = getOption(options, "localeMatcher", "string", ["lookup", "best fit"], "best fit");
    var co = getOption(options, "collation", "string", undefined, undefined);
    if (co !== undefined && !isTypeSequence(co)) throw new RangeErr("Invalid collation");
    opt.co = co === undefined ? undefined : toLower(co);
    var kn = getOption(options, "numeric", "boolean", undefined, undefined);
    opt.kn = kn === undefined ? undefined : toStr(kn);
    opt.kf = getOption(options, "caseFirst", "string", ["upper", "lower", "false"], undefined);
    var r = resolveLocale(requested, opt, COLLATOR_KEYS, COLLATOR_DATA);
    o.locale = r.locale;
    o.collation = r.co === null || r.co === undefined ? "default" : r.co;
    o.numeric = r.kn === "true";
    o.caseFirst = r.kf;
    o.sensitivity = getOption(options, "sensitivity", "string", ["base", "accent", "case", "variant"], "variant");
    o.ignorePunctuation = getOption(options, "ignorePunctuation", "boolean", undefined, false);
  }

  var CollatorProto = {};
  methods(CollatorProto, {
    get compare() {
      var o = slotsOf(this, "Collator", "get Intl.Collator.prototype.compare");
      if (o.bound === undefined) {
        o.bound = (0, (x, y) => collate(o, toStr(x), toStr(y)));
      }
      return o.bound;
    },
    resolvedOptions() {
      var o = slotsOf(this, "Collator", "Intl.Collator.prototype.resolvedOptions");
      var out = {};
      own(out, "locale", o.locale);
      own(out, "usage", o.usage);
      own(out, "sensitivity", o.sensitivity);
      own(out, "ignorePunctuation", o.ignorePunctuation);
      own(out, "collation", o.collation);
      own(out, "numeric", o.numeric);
      own(out, "caseFirst", o.caseFirst);
      return out;
    }
  });
  tag(CollatorProto, "Intl.Collator");
  constructorFn(Collator, CollatorProto, {
    supportedLocalesOf(locales) {
      return supportedLocales(locales, arguments[1]);
    }
  });

  // ======== ListFormat ========

  function listPattern(o, n) {
    // [between two, between the first ones, before the last]
    if (o.type === "disjunction") return [" or ", ", ", ", or "];
    if (o.type === "unit") {
      if (o.style === "narrow") return [" ", " ", " "];
      return [", ", ", ", ", "];
    }
    if (o.style === "short") return [" & ", ", ", ", & "];
    if (o.style === "narrow") return [", ", ", ", ", "];
    return [" and ", ", ", ", and "];
  }

  function listParts(o, list) {
    var out = newList();
    var n = list.length;
    var pat = listPattern(o, n);
    for (var i = 0; i < n; i++) {
      if (i > 0) {
        var lit = n === 2 ? pat[0] : i === n - 1 ? pat[2] : pat[1];
        add(out, { type: "literal", value: lit });
      }
      add(out, { type: "element", value: list[i] });
    }
    return out;
  }

  // StringListFromIterable
  function stringList(iterable) {
    var out = newList();
    if (iterable === undefined) return out;
    var it = iterable[symIterator]();
    for (;;) {
      var step = it.next();
      if (!isObject(step)) throw new TypeErr("Iterator result is not an object");
      if (step.done) break;
      var v = step.value;
      if (typeof v !== "string") {
        var ret = it["return"];
        if (ret !== undefined && ret !== null) apply(ret, it, []);
        throw new TypeErr("Iterable yielded " + (typeof v) + " which is not a string");
      }
      add(out, v);
    }
    return out;
  }

  class ListFormat {
    constructor() {
      var locales = arguments[0], options = arguments[1];
      var lf = create(protoFrom(new.target, ListFormatProto));
      var o = newSlots(lf, "ListFormat");
      var requested = localeList(locales);
      options = optionsObject(options);
      var opt = create(null);
      opt.localeMatcher = getOption(options, "localeMatcher", "string", ["lookup", "best fit"], "best fit");
      o.locale = resolveLocale(requested, opt, [], {}).locale;
      o.type = getOption(options, "type", "string", ["conjunction", "disjunction", "unit"], "conjunction");
      o.style = getOption(options, "style", "string", ["long", "short", "narrow"], "long");
      return lf;
    }
    static supportedLocalesOf(locales) {
      return supportedLocales(locales, arguments[1]);
    }
  }
  var ListFormatProto = ListFormat.prototype;
  methods(ListFormatProto, {
    format(list) {
      var o = slotsOf(this, "ListFormat", "Intl.ListFormat.prototype.format");
      return joinParts(listParts(o, stringList(list)));
    },
    formatToParts(list) {
      var o = slotsOf(this, "ListFormat", "Intl.ListFormat.prototype.formatToParts");
      return partsArray(listParts(o, stringList(list)));
    },
    resolvedOptions() {
      var o = slotsOf(this, "ListFormat", "Intl.ListFormat.prototype.resolvedOptions");
      var out = {};
      own(out, "locale", o.locale);
      own(out, "type", o.type);
      own(out, "style", o.style);
      return out;
    }
  });
  tag(ListFormatProto, "Intl.ListFormat");

  // ======== RelativeTimeFormat ========

  var TIME_UNITS = ["second", "minute", "hour", "day", "week", "month", "quarter", "year"];
  // short forms: one, other
  var TIME_SHORT = {
    second: ["sec.", "sec."], minute: ["min.", "min."], hour: ["hr.", "hr."], day: ["day", "days"],
    week: ["wk.", "wk."], month: ["mo.", "mo."], quarter: ["qtr.", "qtrs."], year: ["yr.", "yr."]
  };
  var TIME_NARROW = { second: "s", minute: "m", hour: "h", day: "d", week: "w", month: "mo", quarter: "q", year: "y" };
  var TIME_WORDS = {
    day: ["yesterday", "today", "tomorrow"],
    week: ["last week", "this week", "next week"],
    month: ["last month", "this month", "next month"],
    quarter: ["last quarter", "this quarter", "next quarter"],
    year: ["last year", "this year", "next year"],
    hour: [null, "this hour", null],
    minute: [null, "this minute", null],
    second: [null, "now", null]
  };
  var TIME_WORDS_SHORT = {
    week: ["last wk.", "this wk.", "next wk."],
    month: ["last mo.", "this mo.", "next mo."],
    quarter: ["last qtr.", "this qtr.", "next qtr."],
    year: ["last yr.", "this yr.", "next yr."]
  };

  function relativeParts(o, value, unit) {
    value = toNum(value);
    unit = toStr(unit);
    if (value !== value || value === Infinity || value === -Infinity) throw new RangeErr("Invalid value");
    var u = unit;
    if (u.length > 1 && u[u.length - 1] === "s") u = strSlice(u, 0, -1);
    if (!has(TIME_UNITS, u)) throw new RangeErr("Invalid unit argument for format() '" + unit + "'");
    var out = newList();
    var neg = value < 0 || (value === 0 && 1 / value < 0);
    if (o.numeric === "auto" && (value === -1 || value === 0 || value === 1)) {
      var words = o.style !== "long" && Obj.prototype.hasOwnProperty.call(TIME_WORDS_SHORT, u) ? TIME_WORDS_SHORT[u] : TIME_WORDS[u];
      var w = words[value === 0 ? 1 : value + 1];
      if (w !== null && w !== undefined) {
        add(out, { type: "literal", value: w });
        return out;
      }
    }
    var x = decFromNumber(abs(value));
    var num = numberParts(o.nf, x);
    var one = pluralCategory(o.nf, x) === "one";
    var name = o.style === "long" ? " " + (one ? u : u + "s") : o.style === "short" ? " " + TIME_SHORT[u][one ? 0 : 1] : TIME_NARROW[u];
    if (!neg) add(out, { type: "literal", value: "in " });
    for (var i = 0; i < num.length; i++) add(out, { type: num[i].type, value: num[i].value, unit: u });
    add(out, { type: "literal", value: name + (neg ? " ago" : "") });
    return out;
  }

  class RelativeTimeFormat {
    constructor() {
      var locales = arguments[0], options = arguments[1];
      var rtf = create(protoFrom(new.target, RelativeTimeFormatProto));
      var o = newSlots(rtf, "RelativeTimeFormat");
      var requested = localeList(locales);
      options = coerceOptions(options);
      var opt = create(null);
      opt.localeMatcher = getOption(options, "localeMatcher", "string", ["lookup", "best fit"], "best fit");
      var nu = getOption(options, "numberingSystem", "string", undefined, undefined);
      if (nu !== undefined && !isTypeSequence(nu)) throw new RangeErr("Invalid numberingSystem");
      opt.nu = nu === undefined ? undefined : toLower(nu);
      var r = resolveLocale(requested, opt, NUMBER_KEYS, NUMBER_DATA);
      o.locale = r.locale;
      o.numberingSystem = r.nu;
      o.style = getOption(options, "style", "string", ["long", "short", "narrow"], "long");
      o.numeric = getOption(options, "numeric", "string", ["always", "auto"], "always");
      o.nf = create(null);
      numberSetup(o.nf, o.locale, undefined, false);
      return rtf;
    }
    static supportedLocalesOf(locales) {
      return supportedLocales(locales, arguments[1]);
    }
  }
  var RelativeTimeFormatProto = RelativeTimeFormat.prototype;
  methods(RelativeTimeFormatProto, {
    format(value, unit) {
      var o = slotsOf(this, "RelativeTimeFormat", "Intl.RelativeTimeFormat.prototype.format");
      return joinParts(relativeParts(o, value, unit));
    },
    formatToParts(value, unit) {
      var o = slotsOf(this, "RelativeTimeFormat", "Intl.RelativeTimeFormat.prototype.formatToParts");
      var parts = relativeParts(o, value, unit);
      var out = [];
      for (var i = 0; i < parts.length; i++) {
        var p = {};
        own(p, "type", parts[i].type);
        own(p, "value", parts[i].value);
        if (parts[i].unit !== undefined) own(p, "unit", parts[i].unit);
        push(out, p);
      }
      return out;
    },
    resolvedOptions() {
      var o = slotsOf(this, "RelativeTimeFormat", "Intl.RelativeTimeFormat.prototype.resolvedOptions");
      var out = {};
      own(out, "locale", o.locale);
      own(out, "style", o.style);
      own(out, "numeric", o.numeric);
      own(out, "numberingSystem", o.numberingSystem);
      return out;
    }
  });
  tag(RelativeTimeFormatProto, "Intl.RelativeTimeFormat");

  // ======== Locale ========

  // likely subtags: language (or language-region, or und-script) -> language-script-region
  var LIKELY = {
    und: "en-Latn-US", en: "en-Latn-US", "en-Shaw": "en-Shaw-GB", "und-419": "es-Latn-419", fr: "fr-Latn-FR", de: "de-Latn-DE", es: "es-Latn-ES",
    it: "it-Latn-IT", pt: "pt-Latn-BR", nl: "nl-Latn-NL", sv: "sv-Latn-SE", da: "da-Latn-DK",
    nb: "nb-Latn-NO", no: "no-Latn-NO", fi: "fi-Latn-FI", pl: "pl-Latn-PL", cs: "cs-Latn-CZ",
    sk: "sk-Latn-SK", hu: "hu-Latn-HU", ro: "ro-Latn-RO", tr: "tr-Latn-TR", el: "el-Grek-GR",
    ru: "ru-Cyrl-RU", uk: "uk-Cyrl-UA", bg: "bg-Cyrl-BG", sr: "sr-Cyrl-RS", hr: "hr-Latn-HR",
    he: "he-Hebr-IL", ar: "ar-Arab-EG", fa: "fa-Arab-IR", hi: "hi-Deva-IN", bn: "bn-Beng-BD",
    th: "th-Thai-TH", vi: "vi-Latn-VN", id: "id-Latn-ID", ms: "ms-Latn-MY", ja: "ja-Jpan-JP",
    ko: "ko-Kore-KR", zh: "zh-Hans-CN", "zh-TW": "zh-Hant-TW", "zh-HK": "zh-Hant-HK", "zh-MO": "zh-Hant-MO",
    "zh-Hant": "zh-Hant-TW", "und-Hant": "zh-Hant-TW", "und-Hans": "zh-Hans-CN", "und-Latn": "en-Latn-US",
    "und-Cyrl": "ru-Cyrl-RU", "und-Arab": "ar-Arab-EG", "und-Jpan": "ja-Jpan-JP", "und-Kore": "ko-Kore-KR",
    "und-Grek": "el-Grek-GR", "und-Hebr": "he-Hebr-IL", "und-Deva": "hi-Deva-IN", "und-Thai": "th-Thai-TH",
    "und-US": "en-Latn-US", "und-GB": "en-Latn-GB", "und-FR": "fr-Latn-FR", "und-DE": "de-Latn-DE",
    "und-JP": "ja-Jpan-JP", "und-CN": "zh-Hans-CN", "und-TW": "zh-Hant-TW", "und-RU": "ru-Cyrl-RU",
    "und-ES": "es-Latn-ES", "und-IT": "it-Latn-IT", "und-BR": "pt-Latn-BR", "und-IN": "hi-Deva-IN",
    "und-KR": "ko-Kore-KR", "sr-ME": "sr-Latn-ME", "pa-PK": "pa-Arab-PK", "pa": "pa-Guru-IN",
    "ca": "ca-Latn-ES", "eu": "eu-Latn-ES", "gl": "gl-Latn-ES", "et": "et-Latn-EE", "lv": "lv-Latn-LV",
    "lt": "lt-Latn-LT", "sl": "sl-Latn-SI", "is": "is-Latn-IS", "ga": "ga-Latn-IE", "cy": "cy-Latn-GB",
    "sw": "sw-Latn-TZ", "af": "af-Latn-ZA", "ta": "ta-Taml-IN", "te": "te-Telu-IN", "ur": "ur-Arab-PK",
    "fil": "fil-Latn-PH", "km": "km-Khmr-KH", "my": "my-Mymr-MM", "ka": "ka-Geor-GE", "hy": "hy-Armn-AM",
    "mn": "mn-Cyrl-MN", "kk": "kk-Cyrl-KZ", "az": "az-Latn-AZ", "uz": "uz-Latn-UZ", "am": "am-Ethi-ET"
  };

  function likelyFor(lang, script, region) {
    var tries = newList();
    if (script !== "" && region !== "") add(tries, lang + "-" + script + "-" + region);
    if (region !== "") add(tries, lang + "-" + region);
    if (script !== "") add(tries, lang + "-" + script);
    add(tries, lang);
    if (script !== "") add(tries, "und-" + script);
    if (region !== "") add(tries, "und-" + region);
    for (var i = 0; i < tries.length; i++) {
      var v = LIKELY[tries[i]];
      if (typeof v === "string" && Obj.prototype.hasOwnProperty.call(LIKELY, tries[i])) {
        var p = splitOn(v, "-");
        return [lang === "und" ? p[0] : lang, script !== "" ? script : p[1], region !== "" ? region : p[2]];
      }
    }
    return null;
  }

  function maximized(t) {
    var m = likelyFor(t.language, t.script, t.region);
    if (m === null) return [t.language, t.script, t.region];
    return m;
  }

  function withBase(s, lang, script, region) {
    var t = parseTag(s.locale);
    t.language = lang;
    t.script = script === "" ? "" : toLower(script);
    t.region = region === "" ? "" : toLower(region);
    return tagText(canonicalParts(t));
  }

  var LOCALE_KEYS = [["calendar", "ca"], ["collation", "co"], ["hourCycle", "hc"], ["caseFirst", "kf"],
    ["numeric", "kn"], ["numberingSystem", "nu"], ["firstDayOfWeek", "fw"]];

  function localeKeyword(s, key) {
    var e = unicodeExtOf(s.locale);
    if (e === null) return undefined;
    for (var i = 0; i < e.keywords.length; i++) {
      if (e.keywords[i][0] === key) return e.keywords[i][1];
    }
    return undefined;
  }

  var WEEKDAY_KEYS = ["", "mon", "tue", "wed", "thu", "fri", "sat", "sun"];

  class Locale {
    constructor(tagArg) {
      var options = arguments[1];
      if (new.target === undefined) throw new TypeErr("Constructor Intl.Locale requires 'new'");
      var loc = create(protoFrom(new.target, LocaleProto));
      if (typeof tagArg !== "string" && !isObject(tagArg)) throw new TypeErr("First argument to Intl.Locale must be a string or Locale");
      var ls = localeSlots(tagArg);
      var text = ls !== undefined ? ls.locale : toStr(tagArg);
      options = coerceOptions(options);
      var t = parseTag(text);
      if (t === null) throw new RangeErr("Incorrect locale information provided");
      t = canonicalParts(t);
      // the base, as the options have it
      var language = getOption(options, "language", "string", undefined, undefined);
      if (language !== undefined && !reTest(/^([a-zA-Z]{2,3}|[a-zA-Z]{5,8})$/, language)) throw new RangeErr("Invalid language");
      var script = getOption(options, "script", "string", undefined, undefined);
      if (script !== undefined && !reTest(/^[a-zA-Z]{4}$/, script)) throw new RangeErr("Invalid script");
      var region = getOption(options, "region", "string", undefined, undefined);
      if (region !== undefined && !reTest(/^([a-zA-Z]{2}|[0-9]{3})$/, region)) throw new RangeErr("Invalid region");
      var variants = getOption(options, "variants", "string", undefined, undefined);
      if (variants !== undefined) {
        var vs = splitOn(toLower(variants), "-");
        var seenV = newList();
        for (var vi = 0; vi < vs.length; vi++) {
          if (!reTest(/^([a-z0-9]{5,8}|[0-9][a-z0-9]{3})$/, vs[vi]) || has(seenV, vs[vi])) throw new RangeErr("Invalid variants");
          add(seenV, vs[vi]);
        }
        t.variants = seenV;
      }
      if (language !== undefined) t.language = toLower(language);
      if (script !== undefined) t.script = toLower(script);
      if (region !== undefined) t.region = toLower(region);
      t = canonicalParts(t);
      // then the keywords
      var kws = newList();
      var values = newList();
      var cal = getOption(options, "calendar", "string", undefined, undefined);
      if (cal !== undefined && !isTypeSequence(cal)) throw new RangeErr("Invalid calendar");
      var col = getOption(options, "collation", "string", undefined, undefined);
      if (col !== undefined && !isTypeSequence(col)) throw new RangeErr("Invalid collation");
      var fw = getOption(options, "firstDayOfWeek", "string", undefined, undefined);
      if (fw !== undefined) {
        if (reTest(/^[0-7]$/, fw)) fw = WEEKDAY_KEYS[toNum(fw)] || "sun";
        if (!isTypeSequence(fw)) throw new RangeErr("Invalid firstDayOfWeek");
      }
      var hc = getOption(options, "hourCycle", "string", ["h11", "h12", "h23", "h24"], undefined);
      var kf = getOption(options, "caseFirst", "string", ["upper", "lower", "false"], undefined);
      var kn = options.numeric;
      if (kn !== undefined) kn = toStr(!!kn);
      var nu = getOption(options, "numberingSystem", "string", undefined, undefined);
      if (nu !== undefined && !isTypeSequence(nu)) throw new RangeErr("Invalid numberingSystem");
      var given = { ca: cal, co: col, fw: fw, hc: hc, kf: kf, kn: kn, nu: nu };
      var ext = null;
      for (var i = 0; i < t.extensions.length; i++) {
        if (t.extensions[i].singleton === "u") ext = t.extensions[i];
      }
      var keys = ["ca", "co", "fw", "hc", "kf", "kn", "nu"];
      for (i = 0; i < keys.length; i++) {
        var v = given[keys[i]];
        if (v === undefined) continue;
        v = toLower(v);
        if (ext === null) {
          ext = { singleton: "u", attributes: [], keywords: [] };
          add(t.extensions, ext);
        }
        var found = false;
        for (var j = 0; j < ext.keywords.length; j++) {
          if (ext.keywords[j][0] === keys[i]) {
            ext.keywords[j] = [keys[i], v];
            found = true;
          }
        }
        if (!found) add(ext.keywords, [keys[i], v]);
      }
      t = canonicalParts(t);
      var o = newSlots(loc, "Locale");
      o.locale = tagText(t);
      return loc;
    }
  }
  var LocaleProto = Locale.prototype;

  function parsed(locale) {
    return canonicalParts(parseTag(locale));
  }

  function localeOf(self, what) {
    return slotsOf(self, "Locale", "Intl.Locale.prototype." + what);
  }

  methods(LocaleProto, {
    maximize() {
      var s = localeOf(this, "maximize");
      var t = parsed(s.locale);
      var m = maximized(t);
      return new Locale(withBase(s, m[0], m[1], m[2]));
    },
    minimize() {
      var s = localeOf(this, "minimize");
      var t = parsed(s.locale);
      var max = maximized(t);
      var tries = [[max[0], "", ""], [max[0], "", max[2]], [max[0], max[1], ""]];
      for (var i = 0; i < tries.length; i++) {
        var m = likelyFor(tries[i][0], tries[i][1], tries[i][2]);
        if (m !== null && m[0] === max[0] && m[1] === max[1] && m[2] === max[2]) {
          return new Locale(withBase(s, tries[i][0], tries[i][1], tries[i][2]));
        }
      }
      return new Locale(withBase(s, max[0], max[1], max[2]));
    },
    toString() {
      return localeOf(this, "toString").locale;
    },
    toJSON() {
      return localeOf(this, "toJSON").locale;
    },
    get baseName() {
      return baseText(parsed(localeOf(this, "baseName").locale));
    },
    get calendar() {
      return localeKeyword(localeOf(this, "calendar"), "ca");
    },
    get caseFirst() {
      return localeKeyword(localeOf(this, "caseFirst"), "kf");
    },
    get collation() {
      return localeKeyword(localeOf(this, "collation"), "co");
    },
    get firstDayOfWeek() {
      return localeKeyword(localeOf(this, "firstDayOfWeek"), "fw");
    },
    get hourCycle() {
      return localeKeyword(localeOf(this, "hourCycle"), "hc");
    },
    get numeric() {
      var v = localeKeyword(localeOf(this, "numeric"), "kn");
      return v === "" || v === "true";
    },
    get numberingSystem() {
      return localeKeyword(localeOf(this, "numberingSystem"), "nu");
    },
    get language() {
      return parsed(localeOf(this, "language").locale).language;
    },
    get script() {
      var t = parsed(localeOf(this, "script").locale);
      return t.script === "" ? undefined : t.script;
    },
    get region() {
      var t = parsed(localeOf(this, "region").locale);
      return t.region === "" ? undefined : t.region;
    },
    get variants() {
      var t = parseTag(localeOf(this, "variants").locale);
      return t.variants.length === 0 ? undefined : arrayJoin(t.variants, "-");
    },
    getCalendars() {
      var c = localeKeyword(localeOf(this, "getCalendars"), "ca");
      return [c !== undefined ? c : "gregory"];
    },
    getCollations() {
      var c = localeKeyword(localeOf(this, "getCollations"), "co");
      return [c !== undefined ? c : "emoji"];
    },
    getHourCycles() {
      var s = localeOf(this, "getHourCycles");
      var c = localeKeyword(s, "hc");
      return [c !== undefined ? c : "h12"];
    },
    getNumberingSystems() {
      var c = localeKeyword(localeOf(this, "getNumberingSystems"), "nu");
      return [c !== undefined ? c : "latn"];
    },
    getTimeZones() {
      var s = localeOf(this, "getTimeZones");
      var t = parsed(s.locale);
      if (t.region === "") return undefined;
      if (t.region === "US") {
        return ["America/Adak", "America/Anchorage", "America/Boise", "America/Chicago", "America/Denver",
          "America/Detroit", "America/Los_Angeles", "America/New_York", "America/Phoenix", "Pacific/Honolulu"];
      }
      return [];
    },
    getTextInfo() {
      var s = localeOf(this, "getTextInfo");
      var t = parsed(s.locale);
      var script = t.script !== "" ? t.script : maximized(t)[1];
      var out = {};
      var dir;
      if (has(["Arab", "Hebr", "Thaa", "Syrc", "Nkoo", "Adlm", "Rohg", "Mand", "Samr"], script)) dir = "rtl";
      else if (script !== "" && Obj.prototype.hasOwnProperty.call(SCRIPT_NAMES, script)) dir = "ltr";
      own(out, "direction", dir);
      return out;
    },
    getWeekInfo() {
      var s = localeOf(this, "getWeekInfo");
      var t = parsed(s.locale);
      var region = t.region === "" ? maximized(t)[2] : t.region;
      var sundayFirst = has(["US", "CA", "JP", "BR", "MX", "IL", "IN", "KR", "TW", "HK", "PH", "ZA", "SA"], region);
      var fw = localeKeyword(s, "fw");
      var first = sundayFirst ? 7 : 1;
      if (fw !== undefined) {
        var k = strIndexOf("montuewedthufrisatsun", fw);
        if (k >= 0 && k % 3 === 0) first = k / 3 + 1;
      }
      var out = {};
      own(out, "firstDay", first);
      own(out, "weekend", [6, 7]);
      return out;
    }
  });
  tag(LocaleProto, "Intl.Locale");

  // ======== DisplayNames ========

  var LANGUAGE_NAMES = {
    en: "English", "en-US": "American English", "en-GB": "British English", "en-AU": "Australian English",
    "en-CA": "Canadian English", "de-AT": "Austrian German", "de-CH": "Swiss High German",
    "fr-CH": "Swiss French", "es-ES": "European Spanish", "nl-BE": "Flemish", fr: "French", "fr-CA": "Canadian French", de: "German", es: "Spanish",
    "es-MX": "Mexican Spanish", "es-419": "Latin American Spanish", it: "Italian", pt: "Portuguese",
    "pt-BR": "Brazilian Portuguese", "pt-PT": "European Portuguese", nl: "Dutch", sv: "Swedish",
    da: "Danish", nb: "Norwegian Bokmål", no: "Norwegian", fi: "Finnish", pl: "Polish", cs: "Czech",
    sk: "Slovak", hu: "Hungarian", ro: "Romanian", tr: "Turkish", el: "Greek", ru: "Russian",
    uk: "Ukrainian", bg: "Bulgarian", sr: "Serbian", hr: "Croatian", he: "Hebrew", ar: "Arabic",
    fa: "Persian", hi: "Hindi", bn: "Bangla", th: "Thai", vi: "Vietnamese", id: "Indonesian",
    ms: "Malay", ja: "Japanese", ko: "Korean", zh: "Chinese", "zh-Hans": "Simplified Chinese",
    "zh-Hant": "Traditional Chinese", ca: "Catalan", eu: "Basque", et: "Estonian", lv: "Latvian",
    lt: "Lithuanian", sl: "Slovenian", is: "Icelandic", ga: "Irish", cy: "Welsh", sw: "Swahili",
    af: "Afrikaans", ta: "Tamil", te: "Telugu", ur: "Urdu", fil: "Filipino", la: "Latin", eo: "Esperanto"
  };
  var REGION_NAMES = {
    US: "United States", GB: "United Kingdom", CA: "Canada", AU: "Australia", NZ: "New Zealand",
    IE: "Ireland", FR: "France", DE: "Germany", ES: "Spain", IT: "Italy", PT: "Portugal", NL: "Netherlands",
    BE: "Belgium", CH: "Switzerland", AT: "Austria", SE: "Sweden", NO: "Norway", DK: "Denmark",
    FI: "Finland", PL: "Poland", CZ: "Czechia", HU: "Hungary", RO: "Romania", GR: "Greece", TR: "Türkiye",
    RU: "Russia", UA: "Ukraine", IL: "Israel", EG: "Egypt", SA: "Saudi Arabia", AE: "United Arab Emirates",
    IN: "India", PK: "Pakistan", CN: "China", TW: "Taiwan", HK: "Hong Kong SAR China", JP: "Japan",
    KR: "South Korea", TH: "Thailand", VN: "Vietnam", ID: "Indonesia", MY: "Malaysia", SG: "Singapore",
    PH: "Philippines", BR: "Brazil", MX: "Mexico", AR: "Argentina", CL: "Chile", CO: "Colombia",
    PE: "Peru", ZA: "South Africa", NG: "Nigeria", KE: "Kenya", "001": "world", "150": "Europe",
    "419": "Latin America", "002": "Africa", "019": "Americas", "142": "Asia", "009": "Oceania"
  };
  var SCRIPT_NAMES = {
    Latn: "Latin", Cyrl: "Cyrillic", Grek: "Greek", Arab: "Arabic", Hebr: "Hebrew", Hans: "Simplified Han",
    Hant: "Traditional Han", Hani: "Han", Jpan: "Japanese", Kore: "Korean", Deva: "Devanagari", Thai: "Thai",
    Beng: "Bangla", Taml: "Tamil", Geor: "Georgian", Armn: "Armenian", Ethi: "Ethiopic", Hira: "Hiragana",
    Kana: "Katakana", Hang: "Hangul"
  };
  var CALENDAR_NAMES = {
    gregory: "Gregorian Calendar", buddhist: "Buddhist Calendar", chinese: "Chinese Calendar",
    hebrew: "Hebrew Calendar", islamic: "Hijri Calendar", iso8601: "ISO-8601 Calendar",
    japanese: "Japanese Calendar", persian: "Persian Calendar", roc: "Minguo Calendar"
  };
  var FIELD_NAMES = {
    era: "era", year: "year", quarter: "quarter", month: "month", weekOfYear: "week",
    weekday: "day of the week", day: "day", dayPeriod: "AM/PM", hour: "hour", minute: "minute",
    second: "second", timeZoneName: "time zone"
  };

  function lookupName(table, key) {
    return Obj.prototype.hasOwnProperty.call(table, key) ? table[key] : undefined;
  }

  class DisplayNames {
    constructor(locales, options) {
      var dn = create(protoFrom(new.target, DisplayNamesProto));
      var o = newSlots(dn, "DisplayNames");
      var requested = localeList(locales);
      options = optionsObject(options);
      var opt = create(null);
      opt.localeMatcher = getOption(options, "localeMatcher", "string", ["lookup", "best fit"], "best fit");
      o.locale = resolveLocale(requested, opt, [], {}).locale;
      o.style = getOption(options, "style", "string", ["narrow", "short", "long"], "long");
      var type = getOption(options, "type", "string", ["language", "region", "script", "currency", "calendar", "dateTimeField"], undefined);
      if (type === undefined) throw new TypeErr("Required option 'type' is missing");
      o.type = type;
      o.fallback = getOption(options, "fallback", "string", ["code", "none"], "code");
      var ld = getOption(options, "languageDisplay", "string", ["dialect", "standard"], "dialect");
      if (type === "language") o.languageDisplay = ld;
      return dn;
    }
    static supportedLocalesOf(locales) {
      return supportedLocales(locales, arguments[1]);
    }
  }
  var DisplayNamesProto = DisplayNames.prototype;
  methods(DisplayNamesProto, {
    of(code) {
      var o = slotsOf(this, "DisplayNames", "Intl.DisplayNames.prototype.of");
      code = toStr(code);
      var name, canonical = code;
      switch (o.type) {
        case "language": {
          var t = parseTag(code);
          if (t === null || t.extensions.length > 0 || t.privateUse !== "" || !reTest(/^[a-zA-Z0-9-]+$/, code)) {
            throw new RangeErr("invalid_argument");
          }
          canonical = tagText(canonicalParts(t));
          name = o.languageDisplay === "dialect" ? lookupName(LANGUAGE_NAMES, canonical) : undefined;
          if (name === undefined) {
            var base = lookupName(LANGUAGE_NAMES, t.language);
            if (base !== undefined) {
              var more = newList();
              if (t.script !== "") add(more, lookupName(SCRIPT_NAMES, t.script) || t.script);
              if (t.region !== "") add(more, lookupName(REGION_NAMES, t.region) || t.region);
              name = more.length > 0 ? base + " (" + arrayJoin(more, ", ") + ")" : base;
            }
          }
          break;
        }
        case "region":
          if (!reTest(/^([a-zA-Z]{2}|[0-9]{3})$/, code)) throw new RangeErr("invalid_argument");
          canonical = toUpper(code);
          name = lookupName(REGION_NAMES, canonical);
          break;
        case "script":
          if (!reTest(/^[a-zA-Z]{4}$/, code)) throw new RangeErr("invalid_argument");
          canonical = toUpper(code[0]) + toLower(strSlice(code, 1));
          name = lookupName(SCRIPT_NAMES, canonical);
          break;
        case "currency":
          if (!reTest(/^[a-zA-Z]{3}$/, code)) throw new RangeErr("invalid_argument");
          canonical = toUpper(code);
          var c = lookupName(CURRENCIES, canonical);
          name = c !== undefined ? c[4] : undefined;
          break;
        case "calendar":
          if (!isTypeSequence(code)) throw new RangeErr("invalid_argument");
          canonical = toLower(code);
          if (canonical === "gregorian") canonical = "gregory";
          name = lookupName(CALENDAR_NAMES, canonical);
          break;
        default:
          if (!Obj.prototype.hasOwnProperty.call(FIELD_NAMES, code)) throw new RangeErr("invalid_argument");
          name = FIELD_NAMES[code];
      }
      if (name !== undefined) return name;
      return o.fallback === "code" ? canonical : undefined;
    },
    resolvedOptions() {
      var o = slotsOf(this, "DisplayNames", "Intl.DisplayNames.prototype.resolvedOptions");
      var out = {};
      own(out, "locale", o.locale);
      own(out, "style", o.style);
      own(out, "type", o.type);
      own(out, "fallback", o.fallback);
      if (o.languageDisplay !== undefined) own(out, "languageDisplay", o.languageDisplay);
      return out;
    }
  });
  tag(DisplayNamesProto, "Intl.DisplayNames");

  // ======== Segmenter ========

  function isLetterOrDigit(ch) {
    return reTest(/[\p{L}\p{N}_]/u, ch);
  }

  function isPictographic(cp) {
    return (cp >= 0x1f000 && cp <= 0x1faff) || (cp >= 0x2600 && cp <= 0x27bf) || (cp >= 0x2300 && cp <= 0x23ff) ||
      (cp >= 0x2b00 && cp <= 0x2bff) || cp === 0xa9 || cp === 0xae || cp === 0x203c || cp === 0x2049 ||
      (cp >= 0x2190 && cp <= 0x21ff);
  }

  // 1 a leading consonant, 2 a vowel, 3 a trailing consonant, 4 an LV syllable, 5 an LVT one
  function hangulKind(cp) {
    if ((cp >= 0x1100 && cp <= 0x115f) || (cp >= 0xa960 && cp <= 0xa97c)) return 1;
    if ((cp >= 0x1160 && cp <= 0x11a7) || (cp >= 0xd7b0 && cp <= 0xd7c6)) return 2;
    if ((cp >= 0x11a8 && cp <= 0x11ff) || (cp >= 0xd7cb && cp <= 0xd7fb)) return 3;
    if (cp >= 0xac00 && cp <= 0xd7a3) return (cp - 0xac00) % 28 === 0 ? 4 : 5;
    return 0;
  }

  // the end of the grapheme cluster starting at i
  function graphemeEnd(s, i) {
    var n = s.length;
    var cp = codePointAt(s, i);
    var j = i + (cp > 0xffff ? 2 : 1);
    if (cp === 13 && j < n && charCodeAt(s, j) === 10) return j + 1;
    if (cp === 10 || cp === 13) return j;
    var regional = cp >= 0x1f1e6 && cp <= 0x1f1ff;
    if (regional && j < n) {
      var next = codePointAt(s, j);
      if (next >= 0x1f1e6 && next <= 0x1f1ff) j += 2;
    }
    var hangul = hangulKind(cp);
    while (j < n) {
      var c = codePointAt(s, j);
      var size = c > 0xffff ? 2 : 1;
      if (isMark(c) || (c >= 0x1f3fb && c <= 0x1f3ff) || (c >= 0xe0020 && c <= 0xe007f)) {
        j += size;
        if (c === 0x200d && j < n) {
          var after = codePointAt(s, j);
          if (isPictographic(after)) j += after > 0xffff ? 2 : 1;
        }
        continue;
      }
      // Hangul: L before L, V, LV or LVT; LV or V before V or T; LVT or T before T
      var next = hangulKind(c);
      if (next !== 0 && ((hangul === 1 && next !== 3) || ((hangul === 2 || hangul === 4) && (next === 2 || next === 3)) ||
          ((hangul === 3 || hangul === 5) && next === 3))) {
        hangul = next;
        j += size;
        continue;
      }
      break;
    }
    return j;
  }

  function isIdeograph(cp) {
    return (cp >= 0x3040 && cp <= 0x30ff) || (cp >= 0x3400 && cp <= 0x9fff) || (cp >= 0xf900 && cp <= 0xfaff) ||
      (cp >= 0x20000 && cp <= 0x3134f);
  }

  function cjkKind(cp) {
    if (cp >= 0x3040 && cp <= 0x309f) return 1;
    if ((cp >= 0x30a0 && cp <= 0x30ff) || cp === 0x30fc) return 2;
    return isIdeograph(cp) ? 3 : 0;
  }

  // the end of the word (or the run of spaces, or the one other character) starting at i
  function wordEnd(s, i) {
    var n = s.length;
    var first = codePointAt(s, i);
    var j = graphemeEnd(s, i);
    var ch = fromCodePoint(first);
    if (isIdeograph(first)) {
      // with no dictionary: a run of one script (Han, hiragana or katakana) is a word
      var kind = cjkKind(first);
      while (j < n && cjkKind(codePointAt(s, j)) === kind) j = graphemeEnd(s, j);
      return [j, true];
    }
    if (isLetterOrDigit(ch)) {
      while (j < n) {
        var c = codePointAt(s, j);
        var cs = fromCodePoint(c);
        if (isIdeograph(c)) break;
        if (isLetterOrDigit(cs)) {
          j = graphemeEnd(s, j);
          continue;
        }
        // an apostrophe or a point between letters, a point or comma between digits
        if ((cs === "'" || cs === "’" || cs === "." || cs === ":" || cs === ",") && j + 1 < n) {
          var nx = fromCodePoint(codePointAt(s, j + 1));
          var prev = s[j - 1];
          var digits = isDigit(prev) && isDigit(nx);
          var letters = isLetterOrDigit(prev) && !isDigit(prev) && isLetterOrDigit(nx) && !isDigit(nx);
          if ((digits && (cs === "." || cs === ",")) || (letters && cs !== ",")) {
            j += 1;
            continue;
          }
        }
        break;
      }
      return [j, true];
    }
    if (reTest(/\s/, ch)) {
      while (j < n && reTest(/\s/, s[j]) && s[j] !== "\n" && ch !== "\n") j++;
    }
    return [j, false];
  }

  // the end of the sentence starting at i: after its stop, closing marks and spaces
  function sentenceEnd(s, i) {
    var n = s.length;
    var j = i;
    while (j < n) {
      var c = s[j];
      j++;
      if (c === "\n" || c === "\r" || c === " ") {
        if (c === "\r" && s[j] === "\n") j++;
        return j;
      }
      if (c === "." || c === "!" || c === "?" || c === "。") {
        while (j < n && (s[j] === "." || s[j] === "!" || s[j] === "?")) j++;
        while (j < n && reTest(/["'”’)\]]/, s[j])) j++;
        if (j >= n) return n;
        if (!reTest(/\s/, s[j])) {
          if (c === "。") return j;
          continue;
        }
        var k = j;
        while (k < n && reTest(/\s/, s[k])) k++;
        // a lower-case letter next means the point wasn't the end ("e.g. this")
        if (c === "." && k < n && reTest(/\p{Ll}/u, s[k])) continue;
        return k;
      }
    }
    return n;
  }

  function segmentAt(o, s, i) {
    if (o.granularity === "grapheme") return [graphemeEnd(s, i), undefined];
    if (o.granularity === "word") return wordEnd(s, i);
    return [sentenceEnd(s, i), undefined];
  }

  function segmentData(o, s, start, end, wordLike) {
    var d = {};
    own(d, "segment", strSlice(s, start, end));
    own(d, "index", start);
    own(d, "input", s);
    if (o.granularity === "word") own(d, "isWordLike", wordLike);
    return d;
  }

  // the segment holding index n: segments start where the last one ended, from the start
  function segmentContaining(o, s, n) {
    var i = 0;
    while (i < s.length) {
      var r = segmentAt(o, s, i);
      if (n < r[0]) return [i, r[0], r[1]];
      i = r[0];
    }
    return null;
  }

  class Segmenter {
    constructor() {
      var locales = arguments[0], options = arguments[1];
      var sg = create(protoFrom(new.target, SegmenterProto));
      var o = newSlots(sg, "Segmenter");
      var requested = localeList(locales);
      options = optionsObject(options);
      var opt = create(null);
      opt.localeMatcher = getOption(options, "localeMatcher", "string", ["lookup", "best fit"], "best fit");
      o.locale = resolveLocale(requested, opt, [], {}).locale;
      o.granularity = getOption(options, "granularity", "string", ["grapheme", "word", "sentence"], "grapheme");
      return sg;
    }
    static supportedLocalesOf(locales) {
      return supportedLocales(locales, arguments[1]);
    }
  }
  var SegmenterProto = Segmenter.prototype;

  var SegmentsProto = {};
  var SegmentIteratorProto = create(getProto(getProto([][symIterator]())));

  methods(SegmenterProto, {
    segment(string) {
      var o = slotsOf(this, "Segmenter", "Intl.Segmenter.prototype.segment");
      var s = toStr(string);
      var segs = create(SegmentsProto);
      var so = newSlots(segs, "Segments");
      so.segmenter = o;
      so.string = s;
      return segs;
    },
    resolvedOptions() {
      var o = slotsOf(this, "Segmenter", "Intl.Segmenter.prototype.resolvedOptions");
      var out = {};
      own(out, "locale", o.locale);
      own(out, "granularity", o.granularity);
      return out;
    }
  });
  tag(SegmenterProto, "Intl.Segmenter");

  methods(SegmentsProto, {
    containing(index) {
      var so = slotsOf(this, "Segments", "%Segments.prototype%.containing");
      var n = index === undefined ? 0 : toNum(index);
      n = n !== n ? 0 : n < 0 ? -floor(-n) : floor(n);
      if (n < 0 || n >= so.string.length) return undefined;
      var r = segmentContaining(so.segmenter, so.string, n);
      return segmentData(so.segmenter, so.string, r[0], r[1], r[2]);
    },
    [symIterator]() {
      var so = slotsOf(this, "Segments", "%Segments.prototype%[@@iterator]");
      var it = create(SegmentIteratorProto);
      var io = newSlots(it, "SegmentIterator");
      io.segmenter = so.segmenter;
      io.string = so.string;
      io.at = 0;
      return it;
    }
  });

  methods(SegmentIteratorProto, {
    next() {
      var io = slotsOf(this, "SegmentIterator", "%SegmentIterator.prototype%.next");
      var result = {};
      if (io.at >= io.string.length) {
        own(result, "value", undefined);
        own(result, "done", true);
        return result;
      }
      var start = io.at;
      var r = segmentAt(io.segmenter, io.string, start);
      io.at = r[0];
      own(result, "value", segmentData(io.segmenter, io.string, start, r[0], r[1]));
      own(result, "done", false);
      return result;
    }
  });
  tag(SegmentIteratorProto, "Segmenter String Iterator");

  // ======== DurationFormat ========

  var DURATION_UNITS = ["years", "months", "weeks", "days", "hours", "minutes", "seconds", "milliseconds",
    "microseconds", "nanoseconds"];
  var DURATION_SINGULAR = ["year", "month", "week", "day", "hour", "minute", "second", "millisecond",
    "microsecond", "nanosecond"];

  class DurationFormat {
    constructor() {
      var locales = arguments[0], options = arguments[1];
      var df = create(protoFrom(new.target, DurationFormatProto));
      var o = newSlots(df, "DurationFormat");
      var requested = localeList(locales);
      options = optionsObject(options);
      var opt = create(null);
      opt.localeMatcher = getOption(options, "localeMatcher", "string", ["lookup", "best fit"], "best fit");
      var nu = getOption(options, "numberingSystem", "string", undefined, undefined);
      if (nu !== undefined && !isTypeSequence(nu)) throw new RangeErr("Invalid numberingSystem");
      opt.nu = nu === undefined ? undefined : toLower(nu);
      var r = resolveLocale(requested, opt, NUMBER_KEYS, NUMBER_DATA);
      o.locale = r.locale;
      o.numberingSystem = r.nu;
      var style = getOption(options, "style", "string", ["long", "short", "narrow", "digital"], "short");
      o.style = style;
      var prev = "";
      for (var i = 0; i < 10; i++) {
        var unit = DURATION_UNITS[i];
        var styles = i < 4 ? ["long", "short", "narrow"] : i < 7 ? ["long", "short", "narrow", "numeric", "2-digit"] :
          ["long", "short", "narrow", "numeric"];
        var digitalBase = i < 4 ? "short" : "numeric";
        // GetDurationUnitOptions
        var us = getOption(options, unit, "string", styles, undefined);
        var displayDefault = "always";
        if (us === undefined) {
          if (style === "digital") {
            if (unit !== "hours" && unit !== "minutes" && unit !== "seconds") displayDefault = "auto";
            us = digitalBase;
          } else if (prev === "fractional" || prev === "numeric" || prev === "2-digit") {
            if (unit !== "minutes" && unit !== "seconds") displayDefault = "auto";
            us = "numeric";
          } else {
            displayDefault = "auto";
            us = style;
          }
        }
        if (us === "numeric" && i >= 7) {
          us = "fractional";
          displayDefault = "auto";
        }
        var display = getOption(options, unit + "Display", "string", ["auto", "always"], displayDefault);
        if (display === "always" && us === "fractional") throw new RangeErr(unit + "Display can't be always when " + unit + " is numeric");
        if (prev === "fractional" && us !== "fractional") throw new RangeErr(unit + " must be numeric");
        if (prev === "numeric" || prev === "2-digit") {
          if (us !== "fractional" && us !== "numeric" && us !== "2-digit") throw new RangeErr(unit + " must be numeric or 2-digit");
          if (unit === "minutes" || unit === "seconds") us = "2-digit";
        }
        o[unit] = us;
        o[unit + "Display"] = display;
        prev = us;
      }
      o.fractionalDigits = getNumberOption(options, "fractionalDigits", 0, 9, undefined);
      o.formats = create(null);
      return df;
    }
    static supportedLocalesOf(locales) {
      return supportedLocales(locales, arguments[1]);
    }
  }
  var DurationFormatProto = DurationFormat.prototype;

  // ToDurationRecord, and IsValidDuration
  function durationRecord(input) {
    if (!isObject(input)) {
      if (typeof input === "string") throw new RangeErr("A duration as a string isn't taken here");
      throw new TypeErr("A duration must be an object");
    }
    var fields = ["days", "hours", "microseconds", "milliseconds", "minutes", "months", "nanoseconds", "seconds", "weeks", "years"];
    var d = create(null);
    var any = false;
    for (var i = 0; i < fields.length; i++) {
      var v = input[fields[i]];
      if (v === undefined) {
        v = 0;
      } else {
        any = true;
        v = toNum(v);
        if (v !== v || v === Infinity || v === -Infinity || floor(v) !== v) throw new RangeErr("Duration fields must be integers");
      }
      d[fields[i]] = v + 0;
    }
    if (!any) throw new TypeErr("A duration needs at least one field");
    var sign = 0;
    for (i = 0; i < fields.length; i++) {
      var f = d[fields[i]];
      if (f < 0) {
        if (sign > 0) throw new RangeErr("Duration fields must have the same sign");
        sign = -1;
      } else if (f > 0) {
        if (sign < 0) throw new RangeErr("Duration fields must have the same sign");
        sign = 1;
      }
    }
    if (abs(d.years) >= 4294967296 || abs(d.months) >= 4294967296 || abs(d.weeks) >= 4294967296) {
      throw new RangeErr("Duration out of range");
    }
    // the days and smaller, in nanoseconds, exactly: under 2 to the 53 seconds
    var ns = ((BigIntCtor(abs(d.days)) * 24n + BigIntCtor(abs(d.hours))) * 60n + BigIntCtor(abs(d.minutes))) * 60n +
      BigIntCtor(abs(d.seconds));
    ns = ns * 1000000000n + BigIntCtor(abs(d.milliseconds)) * 1000000n + BigIntCtor(abs(d.microseconds)) * 1000n +
      BigIntCtor(abs(d.nanoseconds));
    if (ns >= 9007199254740992000000000n) throw new RangeErr("Duration out of range");
    d.sign = sign;
    return d;
  }

  // a NumberFormat record, kept by its options
  function durationNumberFormat(o, key, options) {
    var nf = o.formats[key];
    if (nf === undefined) {
      nf = create(null);
      numberSetup(nf, o.locale, options, false);
      o.formats[key] = nf;
    }
    return nf;
  }

  // the value of unit i, with the units after it that are fractional as its fraction: [decimal, has fraction]
  function durationValue(o, d, i) {
    var unit = DURATION_UNITS[i];
    var v = d[unit];
    if (i >= 6 && i < 9 && o[DURATION_UNITS[i + 1]] === "fractional") {
      var big = BigIntCtor(v);
      var scale = 0;
      for (var j = i + 1; j < 10 && o[DURATION_UNITS[j]] === "fractional"; j++) {
        big = big * 1000n + BigIntCtor(d[DURATION_UNITS[j]]);
        scale += 3;
      }
      var x = decScale(decFromBigInt(big), -scale);
      if (x.d === "" && (v < 0 || (v === 0 && 1 / v < 0))) x = decZero(true);
      return [x, true];
    }
    return [decFromNumber(v), false];
  }

  function durationNumber(o, x, unit, style, fraction, signed, digits) {
    var options = create(null);
    options.useGrouping = style === "numeric" || style === "2-digit" ? false : "auto";
    if (style !== "numeric" && style !== "2-digit") {
      options.style = "unit";
      options.unit = unit;
      options.unitDisplay = style;
    }
    if (digits === 2) options.minimumIntegerDigits = 2;
    if (fraction) {
      options.minimumFractionDigits = o.fractionalDigits === undefined ? 0 : o.fractionalDigits;
      options.maximumFractionDigits = o.fractionalDigits === undefined ? 9 : o.fractionalDigits;
      options.roundingMode = "trunc";
    }
    options.signDisplay = signed ? "auto" : "never";
    var key = unit + "/" + style + "/" + fraction + "/" + signed + "/" + digits;
    var parts = numberParts(durationNumberFormat(o, key, options), x);
    for (var i = 0; i < parts.length; i++) parts[i].unit = unit;
    return parts;
  }

  // PartitionDurationFormatPattern
  function durationParts(o, d) {
    var groups = newList();
    var negative = d.sign < 0;
    var signShown = false;
    for (var i = 0; i < 10; i++) {
      var unit = DURATION_UNITS[i];
      var us = o[unit];
      if (us === "fractional") continue;
      if (us === "numeric" || us === "2-digit") {
        // the units from here on that are numbers, with colons
        var shown = newList();
        var h = d.hours, m = d.minutes, sv = durationValue(o, d, 6);
        var secondsZero = decIsZero(sv[0]);
        var hoursOn = i === 4 && (h !== 0 || o.hoursDisplay === "always");
        var secondsOn = !secondsZero || o.secondsDisplay === "always";
        var minutesOn = i <= 5 && ((hoursOn && secondsOn) || m !== 0 || o.minutesDisplay === "always");
        if (hoursOn) add(shown, [4, decFromNumber(h), false]);
        if (minutesOn) add(shown, [5, decFromNumber(m), false]);
        if (secondsOn) add(shown, [6, sv[0], sv[1]]);
        var group = newList();
        for (var k = 0; k < shown.length; k++) {
          var ui = shown[k][0];
          var x = shown[k][1];
          if (k > 0) add(group, { type: "literal", value: ":" });
          var signed = !signShown && negative;
          if (signed && x.d === "") x = decZero(true);
          var two = o[DURATION_UNITS[ui]] === "2-digit" ? 2 : 1;
          var np = durationNumber(o, x, DURATION_SINGULAR[ui], "numeric", shown[k][2], !signShown, two);
          signShown = true;
          for (var q = 0; q < np.length; q++) add(group, np[q]);
        }
        if (group.length > 0) add(groups, group);
        break;
      }
      var val = durationValue(o, d, i);
      if (decIsZero(val[0]) && o[unit + "Display"] === "auto") continue;
      var xv = val[0];
      if (!signShown && negative && xv.d === "") xv = decZero(true);
      add(groups, durationNumber(o, xv, DURATION_SINGULAR[i], us, val[1], !signShown, 1));
      signShown = true;
    }
    // the groups as a list of units
    var lf = create(null);
    lf.type = "unit";
    lf.style = o.style === "digital" ? "short" : o.style;
    var pat = listPattern(lf);
    var out = newList();
    var n = groups.length;
    for (i = 0; i < n; i++) {
      if (i > 0) add(out, { type: "literal", value: n === 2 ? pat[0] : i === n - 1 ? pat[2] : pat[1] });
      for (var j = 0; j < groups[i].length; j++) add(out, groups[i][j]);
    }
    return out;
  }

  methods(DurationFormatProto, {
    format(duration) {
      var o = slotsOf(this, "DurationFormat", "Intl.DurationFormat.prototype.format");
      return joinParts(durationParts(o, durationRecord(duration)));
    },
    formatToParts(duration) {
      var o = slotsOf(this, "DurationFormat", "Intl.DurationFormat.prototype.formatToParts");
      var parts = durationParts(o, durationRecord(duration));
      var out = [];
      for (var i = 0; i < parts.length; i++) {
        var p = {};
        own(p, "type", parts[i].type);
        own(p, "value", parts[i].value);
        if (parts[i].unit !== undefined) own(p, "unit", parts[i].unit);
        push(out, p);
      }
      return out;
    },
    resolvedOptions() {
      var o = slotsOf(this, "DurationFormat", "Intl.DurationFormat.prototype.resolvedOptions");
      var out = {};
      own(out, "locale", o.locale);
      own(out, "numberingSystem", o.numberingSystem);
      own(out, "style", o.style);
      for (var i = 0; i < 10; i++) {
        var unit = DURATION_UNITS[i];
        own(out, unit, o[unit] === "fractional" ? "numeric" : o[unit]);
        own(out, unit + "Display", o[unit + "Display"]);
      }
      if (o.fractionalDigits !== undefined) own(out, "fractionalDigits", o.fractionalDigits);
      return out;
    }
  });
  tag(DurationFormatProto, "Intl.DurationFormat");

  // ======== Intl itself ========

  methods(Intl, {
    getCanonicalLocales(locales) {
      var list = localeList(locales);
      var out = [];
      for (var i = 0; i < list.length; i++) push(out, list[i]);
      return out;
    },
    supportedValuesOf(key) {
      key = toStr(key);
      var list;
      if (key === "calendar") list = ["gregory"];
      else if (key === "collation") list = ["emoji", "eor"];
      else if (key === "currency") {
        list = keysOf(CURRENCIES);
      } else if (key === "numberingSystem") list = ["latn"];
      else if (key === "timeZone") {
        zones();
        list = [];
        for (var i = 0; i < zoneList.length; i++) {
          if (!zoneLinks[zoneList[i]]) push(list, zoneList[i]);
        }
      } else if (key === "unit") list = keysOf(UNITS);
      else throw new RangeErr("Invalid key : " + key);
      arraySort(list);
      return list;
    }
  });

  var services = [["Collator", Collator], ["DateTimeFormat", DateTimeFormat], ["DisplayNames", DisplayNames],
    ["DurationFormat", DurationFormat],
    ["ListFormat", ListFormat], ["Locale", Locale], ["NumberFormat", NumberFormat], ["PluralRules", PluralRules],
    ["RelativeTimeFormat", RelativeTimeFormat], ["Segmenter", Segmenter]];
  for (var si = 0; si < services.length; si++) hidden(Intl, services[si][0], services[si][1]);

  // ======== the locale-sensitive methods of other built-ins ========

  var defaultNumber = null, defaultCollator = null;

  function quickNumber(locales, options) {
    if (locales === undefined && options === undefined) {
      if (defaultNumber === null) defaultNumber = wmGet(SLOTS, new NumberFormat());
      return defaultNumber;
    }
    return wmGet(SLOTS, new NumberFormat(locales, options));
  }

  function thisNumber(v) {
    return typeof v === "number" ? v : numValueOf(v);
  }

  function thisBigInt(v) {
    return typeof v === "bigint" ? v : bigValueOf(v);
  }

  function dateLocale(self, locales, options, required, defaults) {
    var t = dateTime(self);
    if (t !== t) return "Invalid Date";
    var o = create(null);
    dateSetup(o, locales, options, required, defaults);
    return joinParts(dateParts(o, t));
  }

  methods(Number.prototype, {
    toLocaleString() {
      var x = thisNumber(this);
      return formatNumber(quickNumber(arguments[0], arguments[1]), decFromNumber(x));
    }
  });
  methods(BigInt.prototype, {
    toLocaleString() {
      var x = thisBigInt(this);
      return formatNumber(quickNumber(arguments[0], arguments[1]), decFromBigInt(x));
    }
  });
  methods(Date.prototype, {
    toLocaleString() {
      return dateLocale(this, arguments[0], arguments[1], "any", "all");
    },
    toLocaleDateString() {
      return dateLocale(this, arguments[0], arguments[1], "date", "date");
    },
    toLocaleTimeString() {
      return dateLocale(this, arguments[0], arguments[1], "time", "time");
    }
  });
  methods(String.prototype, {
    localeCompare(that) {
      if (this === undefined || this === null) throw new TypeErr("String.prototype.localeCompare called on null or undefined");
      var s = toStr(this), t = toStr(that);
      var locales = arguments[1], options = arguments[2];
      var o;
      if (locales === undefined && options === undefined) {
        if (defaultCollator === null) defaultCollator = wmGet(SLOTS, new Collator());
        o = defaultCollator;
      } else {
        o = wmGet(SLOTS, new Collator(locales, options));
      }
      return collate(o, s, t);
    }
  });

  // Turkish and Azeri dotted and dotless i; otherwise as toLowerCase and toUpperCase
  function caseLanguage(locales) {
    var list = localeList(locales);
    var lang = list.length > 0 ? parseTag(list[0]).language : "en";
    return lang === "tr" || lang === "az" ? lang : "";
  }

  methods(String.prototype, {
    toLocaleLowerCase() {
      if (this === undefined || this === null) throw new TypeErr("String.prototype.toLocaleLowerCase called on null or undefined");
      var s = toStr(this);
      if (caseLanguage(arguments[0]) === "") return toLower(s);
      var out = "";
      for (var i = 0; i < s.length; i++) {
        var c = s[i];
        if (c === "I" && s[i + 1] === "\u0307") {
          out += "i";
          i++;
        } else if (c === "I") {
          out += "\u0131";
        } else if (c === "İ") {
          out += "i";
        } else {
          out += toLower(c);
        }
      }
      return out;
    },
    toLocaleUpperCase() {
      if (this === undefined || this === null) throw new TypeErr("String.prototype.toLocaleUpperCase called on null or undefined");
      var s = toStr(this);
      if (caseLanguage(arguments[0]) === "") return toUpper(s);
      var out = "";
      for (var i = 0; i < s.length; i++) {
        out += s[i] === "i" ? "İ" : toUpper(s[i]);
      }
      return out;
    }
  });

  // Array.prototype.toLocaleString passes locales and options on to each element
  methods(Array.prototype, {
    toLocaleString() {
      var locales = arguments[0], options = arguments[1];
      var a = toObject(this);
      var len = toLength(a.length);
      var out = "";
      for (var k = 0; k < len; k++) {
        if (k > 0) out += ",";
        var e = a[k];
        if (e !== undefined && e !== null) {
          var f = toObject(e).toLocaleString;
          if (typeof f !== "function") throw new TypeErr("toLocaleString is not a function");
          out += toStr(apply(f, e, [locales, options]));
        }
      }
      return out;
    }
  });
})(globalThis);
