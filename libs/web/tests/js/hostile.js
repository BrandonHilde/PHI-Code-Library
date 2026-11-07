// huge sizes are refused, not obeyed
function t(f) { try { return f(); } catch (e) { return e.name; } }
var s = 'xxxxxxxxxxxxxxxx'; console.log(t(function () { for (var i = 0; i < 40; i++) s = s + s; return s.length; }));
console.log(t(function () { return new Array(4294967295).length; }));
console.log(t(function () { return new Array(4294967296); }));
var a = []; a.length = 4294967295; console.log(a.length, a[4000000000]);
console.log(t(function () { a.push(1); return a.length; }));
var far = []; far[4000000000] = 1; console.log(far.length, Object.keys(far).join());
far.length = 0; console.log(far.length, far[4000000000]);
console.log(t(function () { var big = []; big.length = 3000000; return big.join.call({ length: 0 }); }) === '');
console.log(t(function () { return [].slice.call({ length: 5 }).length; }));
console.log(t(function () { function f() { } return f.apply(null, { length: 100000000 }); }));
console.log(t(function () { function f() { return arguments.length; } var b = []; b.length = 30000; return f.apply(null, b); }));
console.log(t(function () { function f() { return arguments.length; } var b = []; b.length = 100000; return f(...b); }));
// a getter on length that lies
console.log(t(function () { return [].join.call({ get length() { return -5; } }); }) === '');
// prototype cycles, chains
console.log(t(function () { var x = {}; var y = Object.create(x); Object.setPrototypeOf(x, y); }));
var chain = {}; for (var i = 0; i < 1500; i++) chain = Object.create(chain); console.log(chain.nothing);
console.log('nothing' in chain);
var keys = 0; for (var k in chain) keys++; console.log(keys);
// odd things as keys
var o = {}; o[{}] = 1; o[[1, 2]] = 2; o[null] = 3; o[undefined] = 4; o[true] = 5; o[1e21] = 6; o[-0] = 7; console.log(Object.keys(o).join());
// freezing the things the engine uses doesn't break it
var fp = Object.getOwnPropertyDescriptor(Array.prototype, Symbol.iterator); delete Array.prototype[Symbol.iterator];
console.log(t(function () { var [x] = []; }), t(function () { for (var v of []) { } }), t(function () { return [...[]]; }));
Object.defineProperty(Array.prototype, Symbol.iterator, fp);
for (var v of [1]) console.log('restored', v);
var an = Object.getOwnPropertyDescriptor(Object.getPrototypeOf([].values()), 'next').value;
Object.getPrototypeOf([].values()).next = function () { return { done: true }; };
for (var v of [1]) console.log('never');
console.log([...[1]].length);
Object.getPrototypeOf([].values()).next = an;
for (var v of [1]) console.log('back', v);
// changing an array while iterating it
var m = [1, 2, 3], seen = []; for (var v of m) { seen.push(v); if (v == 1) m.push(4); if (v == 2) m.length = 3; } console.log(seen.join());

// redefining a function's own properties
function pf() { } pf.name2 = 1; Object.defineProperty(pf, 'name', { value: 'renamed' }); console.log(pf.name); delete pf.length; console.log(pf.length, pf.hasOwnProperty('length'));
pf.prototype = 5; console.log(new pf() instanceof Object, Object.getPrototypeOf(new pf()) === Object.prototype);
// replacing globals
var savedObject = Object; Object = 1; var lit = {}; console.log(typeof lit, Object); Object = savedObject;
undefined = 1; console.log(undefined); NaN = 1; console.log(NaN === NaN);
console.log(typeof globalThis, globalThis === this, globalThis.globalThis === globalThis);
var viaWindow = 1; console.log(globalThis.viaWindow); globalThis.fromGlobal = 2; console.log(fromGlobal, delete globalThis.fromGlobal, typeof fromGlobal);
console.log(delete globalThis.viaWindow, delete globalThis.NaN);
