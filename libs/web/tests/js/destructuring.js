function t(f) { try { return f(); } catch (e) { return e.name; } }
var [a, b = 2, , ...c] = [1, undefined, 3, 4, 5];
console.log(a, b, c.join());
var { x, y: { z = 9 } = {}, ...rest } = { x: 1, p: 2, q: 3 };
console.log(x, z, Object.keys(rest).join());
// order of evaluation of assignment targets
var log = [];
function o(n) { log.push(n); return {}; }
[o(1).a, o(2).b] = [1, 2];
console.log(log.join());
// defaults only for undefined, and lazily
var calls = 0; function d() { calls++; return 'd'; }
var [p = d(), q = d(), r = d()] = [null, undefined, 0];
console.log(p, q, r, calls);
// iterators are closed when the pattern doesn't use them up
function it() { var closed = 0; return { closed: () => closed, [Symbol.iterator]() { return this; }, next() { return { value: 1, done: false }; }, return() { closed++; return {}; } }; }
var i1 = it(); var [e1] = i1; console.log(i1.closed());
var i2 = it(); var [...e2] = { [Symbol.iterator]() { var n = 0; return { next() { return { done: n++ > 1, value: n }; } }; } }; console.log(e2.join());
var i3 = it(); try { var [e3 = (function () { throw 1; })()] = { [Symbol.iterator]() { return { next() { return { value: undefined, done: false }; }, return() { console.log('closed on throw'); return {}; } }; } }; } catch (e) { console.log('caught', e); }
// errors
console.log(t(() => { var { a } = null; }));
console.log(t(() => { var [a] = undefined; }));
console.log(t(() => { var [a] = 1; }));
console.log(t(() => { var [a] = { [Symbol.iterator]() { return 1; } }; }));
// in parameters, catch, for
function f1({ a, b: [c2, d2] }, [e, f] = [5, 6], ...g) { return [a, c2, d2, e, f, g.length].join(); }
console.log(f1({ a: 1, b: [2, 3] }), f1({ a: 1, b: [2, 3] }, [7, 8], 9, 10));
console.log(f1.length);
try { throw { m: 'msg', n: [1, 2] }; } catch ({ m, n: [n1, n2] }) { console.log(m, n1, n2); }
for (var [k, v] of [['a', 1], ['b', 2]]) console.log(k, v);
for (let { length } of ['abc', 'de']) console.log(length);
for (const [i, j] of [[1, 2]]) console.log(i + j);
// assignment form: it gives back the right side
var aa, bb;
console.log(([aa, bb] = [1, 2]).length, aa, bb);
({ aa, bb = 5 } = { aa: 3 });
console.log(aa, bb);
({ aa: bb, bb: aa } = { aa: 8, bb: 9 });
console.log(aa, bb);
// computed keys, and rest skipping them
var key = 'kk';
var { [key]: got, ...others } = { kk: 1, ll: 2 };
console.log(got, JSON_(others));
function JSON_(o) { var r = []; for (var k of Object.keys(o)) r.push(k + '=' + o[k]); return r.join(); }
// holes, strings
var [, second] = 'xy'; console.log(second);
var [s1, s2] = '\u{1F600}z'; console.log(s1.length, s2);
// swap
var m = 1, n = 2; [m, n] = [n, m]; console.log(m, n);
// nested defaults see earlier bindings
var { u, w = u + 1 } = { u: 1 }; console.log(u, w);
// member targets through rest
var tgt = {}; [tgt.first, ...tgt.others] = [1, 2, 3]; console.log(tgt.first, tgt.others.join());
var obj2 = {}; ({ a: obj2.x, ...obj2.y } = { a: 1, b: 2 }); console.log(obj2.x, obj2.y.b);
