// Every native that keeps running while JS runs, with allocation in its callback, so that under GC stress a value
// it holds out of the collector's sight goes wrong at once. test_js runs this normally and with a collection at
// every safepoint, and insists on the same output.
function junk(n) { var a = []; for (var i = 0; i < 3; i++) a.push({ n: n, s: 'junk' + n + i }); return a[a.length - 1].s; }
function show(label, v) { console.log(label + ': ' + JSON.stringify(v)); }

var src = [5, 3, 9, 1, 7];
show('forEach', (function () { var out = []; src.forEach(function (x, i) { junk(i); out.push(x * 2); }); return out; })());
show('map', src.map(function (x) { junk(x); return { v: x + 1 }; }));
show('filter', src.map(function (x) { return { v: x }; }).filter(function (o) { junk(o.v); return o.v > 4; }));
show('some', src.some(function (x) { junk(x); return x === 9; }));
show('every', src.every(function (x) { junk(x); return x > 0; }));
show('find', src.map(function (x) { return { v: x }; }).find(function (o) { junk(o.v); return o.v === 9; }));
show('findIndex', src.findIndex(function (x) { junk(x); return x === 1; }));
show('findLast', src.map(function (x) { return { v: x }; }).findLast(function (o) { junk(o.v); return o.v < 6; }));
show('reduce', src.reduce(function (acc, x) { junk(x); return { sum: (acc.sum || 0) + x }; }, {}));
show('reduce no start', src.map(function (x) { return { v: x }; }).reduce(function (a, b) { junk(b.v); return { v: a.v + b.v }; }));
show('reduceRight', src.reduceRight(function (acc, x) { junk(x); return acc + ',' + x; }, 'start'));
show('flatMap', src.flatMap(function (x) { junk(x); return [x, { twice: x * 2 }]; }));
show('sort', src.map(function (x) { return { v: x }; }).sort(function (a, b) { junk(a.v); return a.v - b.v; }).map(function (o) { return o.v; }));
show('sort text', ['pear', 'apple', 'fig', 'date'].map(function (s) { return s + junk(1).length; }).sort());
show('sort numbers as text', [10, 9, 100, 1, 21].sort());
show('toSorted', src.toSorted(function (a, b) { junk(a); return b - a; }));
show('sort holes', (function () { var a = [3, , 1, undefined, 2]; a.sort(); return [a.length, 1 in a, a[0], a[3], 4 in a]; })());
show('Array.from iterable', Array.from(new Set(src), function (x) { junk(x); return { v: x }; }));
show('Array.from array-like', Array.from({ length: 3, 0: 'a', 1: 'b', 2: 'c' }, function (x, i) { junk(i); return x + i; }));
show('Array.from generator', Array.from((function* () { for (var i = 0; i < 4; i++) { junk(i); yield { i: i }; } })()));
show('replace fn', 'a1b22c333'.replace(/\d+/g, function (m) { junk(m.length); return '<' + m.length + '>'; }));
show('replace string fn', 'x-x-x'.replaceAll('x', function (m, at) { junk(at); return m + at; }));
show('split', 'a,b,,c'.split(','));
var m = new Map([['one', { v: 1 }], ['two', { v: 2 }], ['three', { v: 3 }]]);
var seen = [];
m.forEach(function (v, k) { junk(k.length); seen.push(k + v.v); });
show('Map.forEach', seen);
var s = new Set([{ a: 1 }, { a: 2 }]);
seen = [];
s.forEach(function (v) { junk(1); seen.push(v.a); });
show('Set.forEach', seen);
show('Map.groupBy', Array.from(Map.groupBy([1, 2, 3, 4, 5], function (x) { junk(x); return x % 2 ? 'odd' : 'even'; }).entries()));
show('Object.groupBy', Object.groupBy(['a', 'bb', 'cc', 'd'], function (x) { junk(1); return 'len' + x.length; }));
show('fromEntries', Object.fromEntries(new Map([['a', { v: 1 }], ['b', { v: 2 }]])));
show('Reflect.apply', Reflect.apply(function (a, b) { junk(a); return [this.t, a, b]; }, { t: 'this' }, [1, { two: 2 }]));
show('Reflect.construct', (function () { function C(x) { this.x = x; junk(x); } return Reflect.construct(C, [{ made: true }]).x; })());
show('Function.call', (function (a) { junk(a); return [this.q, a]; }).call({ q: 1 }, 2));
show('Function.apply', (function (a, b) { junk(a); return a + b; }).apply(null, [3, 4]));
show('new Map(iterable)', Array.from(new Map((function* () { for (var i = 0; i < 3; i++) { junk(i); yield [{ k: i }.k, 'v' + i]; } })())));
show('new Set(iterable)', new Set((function* () { for (var i = 0; i < 3; i++) { junk(i); yield i % 2; } })()).size);
show('JSON with toJSON', JSON.stringify({ a: { toJSON: function () { junk(1); return { b: [1, 2] }; } }, d: [new Date(0)] }));
show('JSON reviver', JSON.parse('{"a":[1,2],"b":{"c":3}}', function (k, v) { junk(1); return typeof v === 'number' ? v * 10 : v; }));
show('JSON replacer', JSON.stringify({ a: 1, b: 'x', c: [1] }, function (k, v) { junk(1); return typeof v === 'number' ? v + 1 : v; }, 1));
show('Proxy', (function () { var log = []; var p = new Proxy({ a: 1 }, { get: function (t, k) { junk(1); log.push(String(k)); return t[k]; }, has: function (t, k) { log.push('has ' + k); return k in t; }, ownKeys: function (t) { log.push('keys'); return Object.keys(t); } }); var v = p.a; var h = 'a' in p; var ks = Object.keys(p); return [v, h, ks, log]; })());
show('typed map', Array.from(new Uint8Array([1, 2, 3]).map(function (x) { junk(x); return x * 100; })));
show('typed filter', Array.from(new Int16Array([-1, 2, -3]).filter(function (x) { junk(x); return x < 0; })));
show('typed sort', Array.from(new Float64Array([3, -0, 0, NaN, -1]).sort()).map(function (x) { return Object.is(x, -0) ? '-0' : String(x); }));
show('typed views', (function () { var b = new ArrayBuffer(8); new Uint32Array(b)[0] = 0x01020304; var v = new DataView(b); return [new Uint8Array(b)[0], v.getUint8(0), v.getUint32(0), v.getUint32(0, true), b.slice(1, 3).byteLength]; })());
show('matchAll', Array.from('a1 b2'.matchAll(/([a-z])(\d)/g), function (x) { junk(1); return x[1] + x[2]; }));
show('promise chain', 1);
Promise.all([1, Promise.resolve({ v: 2 }), new Promise(function (r) { junk(1); r(3); })]).then(function (rs) { junk(2); show('Promise.all', rs); });
(async function () { var t = 0; for await (var x of (async function* () { for (var i = 0; i < 3; i++) { junk(i); yield i; } })()) { t += x; } show('for await', t); })();

// a Map keeps its order, and an iterator carries on, through changes and a table that's rebuilt
var big = new Map();
for (var i = 0; i < 40; i++) big.set(i, 'v' + i);
var order = [];
var count = 0;
for (var e of big) {
  count++;
  if (e[0] % 2 === 0) big.delete(e[0]);
  if (count === 5) for (var j = 100; j < 160; j++) big.set(j, j);
  if (count > 200) break;
  if (e[0] < 12 || e[0] > 155) order.push(e[0]);
}
show('map through changes', [count, big.size, order]);
var st = new Set([1, 2, 3]);
var it = st.values();
it.next();
st.clear();
st.add(9);
show('set after clear', it.next());
show('map keys', (function () { var mk = new Map(); mk.set(NaN, 'nan').set(0, 'zero').set('0', 'text'); return [mk.get(NaN), mk.get(-0), mk.get('0'), mk.size]; })());
show('weak', (function () { var k = {}; var w = new WeakMap([[k, 1]]); var ws = new WeakSet([k]); gc(); return [w.get(k), w.has({}), ws.has(k), new WeakRef(k).deref() === k]; })());

// Set's newer methods
var A = new Set([1, 2, 3]), B = new Set([2, 3, 4]);
show('set algebra', [[...A.union(B)], [...A.intersection(B)], [...A.difference(B)], [...A.symmetricDifference(B)], A.isSubsetOf(B), new Set([2]).isSubsetOf(A), A.isSupersetOf(new Set([1])), A.isDisjointFrom(new Set([7]))]);

// numbers and text, by hand
show('math', [Math.max(1, 3, 2), Math.min(), Math.round(2.5), Math.round(-2.5), Math.floor(-0.5), Math.ceil(-0.5), Math.trunc(-1.5), Math.sign(-3), Math.hypot(3, 4), Math.cbrt(27), Math.clz32(1), Math.imul(3, 4), Math.fround(5.5), Math.abs(-2)]);
show('math 2', [Math.sqrt(16), Math.pow(2, 10), Math.exp(0), Math.log(1), Math.log2(8), Math.log10(1000), Math.sin(0), Math.cos(0), Math.atan2(0, 1), Math.floor(Math.PI * 1000), Math.floor(Math.E * 1000)]);
show('array', [[1, 2, 3].includes(2), [1, 2, 3].at(-1), [1, [2, [3, [4]]]].flat(2), [1, 2, 3].fill(0, 1), [1, 2, 3, 4, 5].copyWithin(0, 3), [1, 2, 3].lastIndexOf(3), Array.of(7, 8), [3, 2, 1].reverse(), [1, 2].concat(3, [4, [5]]), [1, 2, 3].shift(), [2].unshift(1), [1, 2, 3, 4].splice(1, 2), [1, 2, 3].toReversed(), [1, 2, 3].with(1, 9), [1, 2, 3].toSpliced(1, 1, 8, 9)]);
show('string', ['abc'.at(-1), 'abc'.padStart(5, 'xy'), 'abc'.padEnd(5), 'ab'.repeat(2), '  x '.trim(), 'Hello'.toUpperCase(), 'Hello'.toLowerCase(), 'abc'.includes('b'), 'abc'.startsWith('b', 1), 'abc'.endsWith('b', 2), 'a-b'.split('-'), 'abcdef'.substring(4, 1), 'abcdef'.substr(-3, 2), 'aXbX'.lastIndexOf('X'), 'abc'.codePointAt(1), String.fromCodePoint(97, 128512).length, 'x'.localeCompare('y'), String.raw`a\n${1}`]);
show('unicode', ['é'.toUpperCase(), 'É'.toLowerCase(), 'ß'.toUpperCase(), 'ΣΣ'.toLowerCase(), 'a\u{1F600}b'.length, [...'a\u{1F600}b'].length, 'a\u{1F600}b'.codePointAt(1), encodeURIComponent('é &'), decodeURIComponent('%C3%A9'), encodeURI('a b/c?d=e'), escape('a b'), unescape('a%20b')]);
show('object', [Object.entries({ a: 1 }), Object.values({ a: 1 }), Object.assign({}, { a: 1 }, { b: 2 }), Object.isSealed(Object.seal({})), Object.getOwnPropertyDescriptors({ a: 1 }), Object.hasOwn({ a: 1 }, 'a')]);
show('number', [Number.isInteger(5), Number.isSafeInteger(2 ** 53), Number.parseFloat('1.5x'), parseInt('12px'), parseInt('z', 36), parseFloat('.5'), parseFloat('-Infinity'), (255).toString(16), (0.5).toString(2), (1e21).toString(), (1.005).toFixed(2), (1234.5).toExponential(2), (0.00001).toPrecision(1)]);
show('date', [new Date(2020, 0, 31).getMonth(), new Date(Date.UTC(2000, 1, 29, 12)).toISOString(), new Date('2021-03-04T05:06:07Z').getTime(), new Date('2021-03-04').getUTCDate(), new Date(NaN).getTime() !== new Date(NaN).getTime(), new Date(0).toUTCString(), new Date('Mar 5, 2022 10:00:00 UTC').toISOString(), JSON.stringify(new Date(0)), typeof Date.now()]);
var dd = new Date(Date.UTC(2020, 0, 31));
dd.setUTCMonth(1);
show('date carry', dd.toISOString());
