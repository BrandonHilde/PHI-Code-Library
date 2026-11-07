var o = { _v: 1, get v() { return this._v; }, set v(x) { this._v = x * 2; } };
o.v = 5; console.log(o.v);
var c = Object.create(o); c.v = 1; console.log(c.v, c.hasOwnProperty('_v'), c.hasOwnProperty('v'), o._v);
var d = Object.getOwnPropertyDescriptor(o, 'v');
console.log(typeof d.get, typeof d.set, d.enumerable, d.configurable, 'value' in d);
// getter only: assignment is ignored, or throws in strict
var g = { get a() { return 1; } }; g.a = 2; console.log(g.a);
(function () { 'use strict'; try { g.a = 2; } catch (e) { console.log(e.name); } })();
// defineProperty's rules
var p = {};
Object.defineProperty(p, 'x', { value: 1 });
console.log(Object.getOwnPropertyDescriptor(p, 'x').writable, Object.keys(p).length);
p.x = 2; console.log(p.x);
try { Object.defineProperty(p, 'x', { value: 2 }); } catch (e) { console.log(e.name); }
Object.defineProperty(p, 'x', { value: 1 }); console.log('same value is allowed');
Object.defineProperty(p, 'y', { get() { return 'gy'; }, configurable: true });
Object.defineProperty(p, 'y', { value: 'vy' }); console.log(p.y, Object.getOwnPropertyDescriptor(p, 'y').writable);
try { Object.defineProperty({}, 'z', { get() { }, value: 1 }); } catch (e) { console.log(e.name); }
// delete
var q = { a: 1 }; console.log(delete q.a, q.a, delete q.nothing);
console.log(delete p.x, p.x);
(function () { 'use strict'; try { delete p.x; } catch (e) { console.log(e.name); } })();
// frozen and non-extensible
var f = Object.freeze({ a: 1 }); f.a = 2; f.b = 3; console.log(f.a, f.b, Object.isFrozen(f));
(function () { 'use strict'; try { f.a = 2; } catch (e) { console.log(e.name); } try { f.b = 2; } catch (e) { console.log(e.name); } })();
var fa = Object.freeze([1, 2]); fa[0] = 9; fa.length = 0; console.log(fa[0], fa.length);
try { fa.push(3); } catch (e) { console.log(e.name); }
var ne = Object.preventExtensions({}); ne.x = 1; console.log(ne.x, Object.isExtensible(ne));
// __proto__ in literals and as an accessor
var pr = { base: 1 }; var ch = { __proto__: pr }; console.log(ch.base, Object.getPrototypeOf(ch) === pr);
var cq = {}; cq.__proto__ = pr; console.log(cq.base);
var ck = { ['__proto__']: 1 }; console.log(Object.keys(ck).join());
var noproto = Object.create(null); noproto.__proto__ = 1; console.log(Object.keys(noproto).join());
try { var cycle = {}; cycle.__proto__ = Object.create(cycle); } catch (e) { console.log(e.name); }
// setters on the chain get the receiver; primitives
var logged = []; var st = { set s(v) { logged.push(this === ch2); } }; var ch2 = Object.create(st); ch2.s = 1; console.log(logged[0]);
(5).x = 1; 'str'.y = 2; console.log((5).x, 'str'.y);
Object.defineProperty(Number.prototype, 'mine', { get() { return typeof this; }, configurable: true }); console.log((5).mine);
Object.defineProperty(Number.prototype, 'strictly', { get() { 'use strict'; return typeof this; }, configurable: true }); console.log((5).strictly);
// array length
var a = [1, 2, 3]; a.length = 1; console.log(a.join(), a[1]);
a[5] = 6; console.log(a.length, 3 in a, 5 in a);
try { a.length = -1; } catch (e) { console.log(e.name); }
try { a.length = 1.5; } catch (e) { console.log(e.name); }
a.length = '2'; console.log(a.length);
Object.defineProperty(a, 'length', { writable: false }); a[9] = 1; console.log(a.length, a[9]);
var sp = []; sp[4294967294] = 'last'; console.log(sp.length, sp[4294967294]); sp[4294967295] = 'not an index'; console.log(sp.length);
var dl = [1, 2, 3]; Object.defineProperty(dl, 1, { configurable: false }); dl.length = 0; console.log(dl.length, dl[1]);
// accessors on array indexes
var ac = [1, 2]; Object.defineProperty(ac, 0, { get() { return 'getter'; } }); console.log(ac[0], ac.join());
