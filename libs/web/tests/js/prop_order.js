// integer keys ascending, then strings as made, then symbols
var s1 = Symbol('s1'), s2 = Symbol('s2');
var o = { b: 1, [s1]: 2, 2: 3, a: 4, 1: 5, [s2]: 6, '-1': 7, '01': 8, 4294967294: 9, 4294967295: 10, 1.5: 11 };
console.log(Object.keys(o).join());
console.log(Object.getOwnPropertyNames(o).join());
console.log(Object.getOwnPropertySymbols(o).length);
var keys = []; for (var k in o) keys.push(k); console.log(keys.join());
// deleting and adding again goes to the end
var d = { a: 1, b: 2, c: 3 }; delete d.a; d.a = 1; console.log(Object.keys(d).join());
// past where it would be dense
var a = []; a[1000000] = 1; a[3] = 1; a.x = 1; a[50] = 1; console.log(Object.keys(a).join());
var p = {}; p[100000] = 1; p[5] = 1; p[99] = 1; console.log(Object.keys(p).join());
// for-in: the chain, each name once, non-enumerable ones shadow
var base = { x: 1, y: 2 }; var ch = Object.create(base); ch.z = 3; Object.defineProperty(ch, 'y', { value: 1, enumerable: false });
keys = []; for (var k in ch) keys.push(k); console.log(keys.join());
// what's deleted during the loop isn't seen; what's added may not be
var del = { a: 1, b: 2, c: 3 }; keys = []; for (var k in del) { keys.push(k); delete del.b; del.added = 1; } console.log(keys.join());
// for-in over arrays, strings, nothing
keys = []; for (var k in [7, 8]) keys.push(typeof k + k); console.log(keys.join());
keys = []; for (var k in 'ab') keys.push(k); console.log(keys.join());
for (var k in null) console.log('never'); for (var k in undefined) console.log('never'); for (var k in 5) console.log('never');
// many properties: past the hash threshold, order holds
var big = {}; for (var i = 0; i < 40; i++) big['k' + i] = i; delete big.k5; delete big.k20; big.k5 = 'back';
var ks = Object.keys(big); console.log(ks.length, ks[0], ks[5], ks[37], ks[38], big.k39, big.k20, big.k5);
for (var i = 0; i < 40; i += 2) delete big['k' + i];
for (var i = 100; i < 140; i++) big['k' + i] = i;
ks = Object.keys(big); console.log(ks.length, ks[0], ks[ks.length - 1], big.k139, big.k1, big.k2);
// builtins' properties aren't enumerable
keys = []; for (var k in []) keys.push(k); for (var k in function () { }) keys.push(k); console.log(keys.length);
// arrays with holes
var h = [1, , 3]; console.log(h.length, 1 in h, Object.keys(h).join(), h.join()); h[1] = 2; console.log(h.join());
var h2 = [, ]; console.log(h2.length); var h3 = [, , 1]; console.log(h3.length, h3[0], h3.indexOf(undefined));
console.log(Object.prototype.hasOwnProperty.call(h, 1), [1, 2, 3].slice(1).join(), [1, 2, 3].slice(-1).join());
// the prototype's elements show through holes
Array.prototype[1] = 'proto'; console.log([0, , 2][1], [0, , 2].join()); delete Array.prototype[1];
// spread and arrays
console.log([...[1, 2], ...'ab', ...new_iter()].join(), Math_max(...[1, 3, 2]), [...[, 1]].length, 0 in [...[, 1]]);
function new_iter() { return { [Symbol.iterator]() { var n = 0; return { next() { return { done: n++ > 0, value: 'it' }; } }; } }; }
function Math_max() { var m = -Infinity; for (var i = 0; i < arguments.length; i++) if (arguments[i] > m) m = arguments[i]; return m; }
console.log(new Array(3).length, new Array(1, 2).length, new Array('3').length, Array(2).length, Array.isArray([]), Array.isArray({}));
var sp = { a: 1, ...{ b: 2, a: 3 }, c: 4, ...null, ...'hi' }; console.log(Object.keys(sp).join(), sp.a, sp[1]);
try { new Array(-1); } catch (e) { console.log(e.name); }
// array methods here
var st = []; console.log(st.push(1, 2), st.pop(), st.length, [].pop(), [1, 2, 3].indexOf(2), [1, 2, 3].indexOf(4), [NaN].indexOf(NaN), [1, 2].join(''), [null, undefined, 1].join('-'), [[1, 2], [3]].join(';'));
console.log(Array.prototype.join.call({ length: 2, 0: 'a', 1: 'b' }), Array.prototype.push.call({ length: 1 }, 'x'));
var obj = { length: 4294967295 }; try { Array.prototype.push.call(obj, 1); console.log(obj.length); } catch (e) { console.log(e.name); }
var iter = [1, 2].entries(); console.log(iter.next().value.join(), iter.next().value.join(), iter.next().done); console.log([...[5, 6].keys()].join());
console.log(Object.prototype.toString.call([].values()), Object.prototype.toString.call(''[Symbol.iterator]()));
console.log([1, 2, 3].toString(), String([]), [] + '', Object.prototype.toString.call(null), Object.prototype.toString.call(1), Object.prototype.toString.call(function () { }));
// optional chaining and nullish
var n = null, u, q = { a: { b() { return this === q.a; } }, z: 0 };
console.log(n?.x, u?.x.y.z, n?.[1], n?.(), q.a?.b(), q.nope?.(), q.a.b?.(), q?.a.b(), (q?.a).b(), q.z?.toFixed(1), delete n?.x);
console.log(n ?? 'd', u ?? 'd', 0 ?? 'd', '' ?? 'd', false ?? 'd', q.z ?? 'd', n?.a ?? 'after');
var la = null, lb = 1, lc = 0; la ??= 'set'; lb ??= 'no'; lb &&= 'and'; lc ||= 'or'; lc &&= 'and2'; console.log(la, lb, lc);
var lo = { get v() { console.log('read'); return 1; }, set v(x) { console.log('written'); } }; lo.v ||= 2; lo.v &&= 3;
try { q.nope(); } catch (e) { console.log(e.name, e.message); }
try { nope2(); } catch (e) { console.log(e.name, e.message); }
try { n.x; } catch (e) { console.log(e.name, e.message); }
try { u.x = 1; } catch (e) { console.log(e.name, e.message); }
try { new q.a.b(); } catch (e) { console.log(e.name, e.message); }
try { new (1)(); } catch (e) { console.log(e.name); }
try { [] instanceof 1; } catch (e) { console.log(e.name); }
try { 'x' in 1; } catch (e) { console.log(e.name); }
// symbols
var sy = Symbol('desc'); console.log(sy.toString(), sy.description, Symbol().description, typeof Object(sy), Object(sy) == sy, Symbol.for('r') === Symbol.for('r'), Symbol.keyFor(Symbol.for('r')), Symbol.keyFor(sy), Symbol.iterator.toString());
try { new Symbol(); } catch (e) { console.log(e.name); }
var hi = { [Symbol.hasInstance](v) { return v === 1; } }; console.log(1 instanceof hi, 2 instanceof hi);
var tag = { get [Symbol.toStringTag]() { return 'Mine'; } }; console.log(String(tag));
// comma, void, delete, in, instanceof, conditional
console.log((1, 2), void 0, 'a' in { a: 1 }, 1 in [1, 2], [] instanceof Array, [] instanceof Object, true ? 'y' : 'n', false ? 'y' : 0 ? 'n' : 'z');
