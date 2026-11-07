// things that must survive a collection at any moment, and things that are garbage
function churn(n) { var x; for (var i = 0; i < n; i++) x = { i: i, s: 'str' + i, a: [i, { deep: i }] }; return x; }
console.log(churn(300).a[1].deep);
gc();
// closures and scopes
var fs = []; for (let i = 0; i < 50; i++) { let v = { n: i }; fs.push(() => v.n); churn(3); }
gc();
var t = 0; for (var f of fs) t += f(); console.log(t);
// ropes, flat and half flat
var r = ''; for (var i = 0; i < 200; i++) { r += 'piece' + i; if (i % 40 == 0) { gc(); r.charCodeAt(0); } }
gc(); console.log(r.length, r.slice(0, 8));
// keys that are only held by the objects that use them
var o = {}; for (var i = 0; i < 100; i++) { o['dyn' + i] = i; } gc(); console.log(o.dyn42, o['dyn' + 99]);
for (var i = 0; i < 100; i++) delete o['dyn' + i]; gc(); o['dyn' + 42] = 'again'; console.log(o.dyn42);
// a chain deeper than any stack
var head = null; for (var i = 0; i < 1500; i++) head = { next: head }; gc();
var n = 0; for (var p = head; p; p = p.next) n++; console.log(n); head = null; gc();
// generators suspended, holding their frames
function* g() { var a = { v: 1 }; yield a; var b = { v: 2 }; yield a.v + b.v; }
var it = g(); it.next(); gc(); churn(50); console.log(it.next().value);
// promises and what's waiting on them
var saved = []; var pr = new Promise(function (res) { saved.push(res); }); var thenned = pr.then(function (v) { return { got: v }; }); gc(); churn(50); saved[0]({ a: 'resolved' });
thenned.then(function (v) { gc(); console.log(v.got.a); });
async function af() { var keep = { k: 'kept' }; await null; gc(); churn(50); await null; return keep.k; }
af().then(function (v) { console.log(v); });
// getters, toString and valueOf calling allocating code in the middle of operators
var side = { get a() { churn(20); gc(); return 'got' + 'a'; }, toString() { churn(20); gc(); return 'x' + 'y'; }, valueOf() { churn(20); gc(); return 40 + 2; } };
console.log(side.a, side + 1, '' + side, `${side}`, side * 1, side < 50, [side, side].join());
var ob = {}; ob[side] = 1; console.log(Object.keys(ob).join());
// exceptions in flight
function thrower() { churn(20); throw { payload: 'p' + 1 }; }
try { thrower(); } catch (e) { gc(); churn(20); console.log(e.payload); }
function fin() { try { return { r: 'ret' + 1 }; } finally { gc(); churn(20); } } console.log(fin().r);
// array growth, holes, sparse, arguments
var a = []; for (var i = 0; i < 500; i++) a.push({ i: i }); gc(); a.length = 10; gc(); console.log(a[9].i, a.length);
var sp = []; sp[100000] = { v: 'sparse' }; gc(); console.log(sp[100000].v);
function ar() { var x = arguments; gc(); return x[0].v; } console.log(ar({ v: 'arg' }));
function mapped(a) { var x = arguments; a = { v: 'changed' }; gc(); return x[0].v; } console.log(mapped({ v: 0 }));
// classes with fields, privates, statics
class C { #p = { v: 'private' }; f = { v: 'field' }; static s = { v: 'static' }; get() { gc(); return this.#p.v + this.f.v + C.s.v; } }
console.log(new C().get());
// spread and apply and bind and call
function all() { gc(); return arguments.length; } console.log(all(...[{}, {}, {}]), all.apply(null, [{}, {}]), all.bind(null, {})({}), all.call(null, {}));
// symbols as keys
var so = {}; so[Symbol('only')] = { v: 'by symbol' }; gc(); console.log(so[Object.getOwnPropertySymbols(so)[0]].v);
// a function returned while its code has no other holder
function maker() { return eval('(function () { return "from eval"; })'); } var made = maker(); gc(); churn(30); console.log(made());
var byCtor = new Function('a', 'return a + 1'); gc(); console.log(byCtor(1), byCtor.toString().length > 0);
// native iterators, in the middle
var arr2 = [{ v: 1 }, { v: 2 }]; for (var v of arr2.values()) { gc(); t = v.v; } console.log(t);
var [d1, d2] = arr2; gc(); console.log(d2.v);
console.log(gcCount() > 0);
