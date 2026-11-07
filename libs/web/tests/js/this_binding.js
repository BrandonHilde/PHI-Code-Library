function sloppy() { return this; }
function strict() { 'use strict'; return this; }
console.log(sloppy() === globalThis, strict() === undefined);
console.log(typeof sloppy.call(5), typeof strict.call(5), sloppy.call(null) === globalThis, strict.call(null));
var o = { f: sloppy, g: strict, a: () => this, n: { f: sloppy } };
console.log(o.f() === o, o.g() === o, o.a() === globalThis, o.n.f() === o.n);
var m = o.f; console.log(m() === globalThis);
console.log((o.f)() === o, (0, o.f)() === globalThis, (o.f = o.f)() === globalThis);
console.log(o['f']() === o);
var bound = sloppy.bind('b'); console.log(typeof bound(), bound.call('x').toString(), bound.name, bound.length);
var bb = strict.bind(1).bind(2); console.log(bb());
function args() { return Array.prototype.slice.call(arguments).join(); }
console.log(args.bind(null, 1, 2)(3), args.apply(null, [4, 5]), args.call(null, 6), args.apply(null));
console.log(args.apply(null, { length: 2, 0: 'x', 1: 'y' }));
new (function () { console.log(this instanceof Object, (() => this)() === this); })();
function arrowInMethod() { return [1].map2(() => this); }
Array.prototype.map2 = function (f) { return f(); };
console.log(arrowInMethod.call('t').toString());
// new and bound
function Ctor(a) { this.a = a; }
var BC = Ctor.bind({ ignored: 1 }, 'bound arg'); var bi = new BC(); console.log(bi.a, bi instanceof Ctor, bi instanceof BC);
// constructors' results
function RetObj() { return { r: 1 }; } function RetPrim() { this.p = 1; return 5; }
console.log(new RetObj().r, new RetPrim().p);
// arguments object: mapped in sloppy, not in strict
function mapped(a, b) { arguments[0] = 'x'; b = 'y'; return [a, arguments[1], arguments.length].join(); }
console.log(mapped(1, 2), mapped(1));
function unmapped(a) { 'use strict'; arguments[0] = 'x'; return a; }
console.log(unmapped(1));
function defaulted(a = 0) { arguments[0] = 'x'; return a; }
console.log(defaulted(1));
function callee() { return arguments.callee === callee; } console.log(callee());
function strictCallee() { 'use strict'; try { return arguments.callee; } catch (e) { return e.name; } } console.log(strictCallee());
function shadow(arguments) { return arguments; } console.log(shadow(1));
function shadow2() { var arguments; return typeof arguments; } console.log(shadow2());
function shadow3() { var arguments = 1; return arguments; } console.log(shadow3());
function arrowArgs() { return (() => arguments[0])(); } console.log(arrowArgs('outer args'));
function iter() { var o = []; for (var v of arguments) o.push(v); return o.join(); } console.log(iter(1, 2));
function dup(a, a) { return a; } console.log(dup(1, 2));
function dupArgs(a, a) { arguments[0] = 'x'; return a; } console.log(dupArgs(1, 2));
function delMapped(a) { delete arguments[0]; arguments[0] = 'new'; return a; } console.log(delMapped(1));
function extra(a) { return arguments.length + ':' + arguments[1]; } console.log(extra(1, 2, 3));
function rest(a, ...r) { return r.length + ':' + r.join(); } console.log(rest(), rest(1), rest(1, 2, 3));
// function properties
console.log(args.name, args.length, (function (a, b = 1, c) { }).length, ((a, ...b) => 1).length);
console.log((function () { }).name === '', (() => { }).name === '');
var named = function () { }, arrowed = () => { }, obj = { m() { }, f: function () { }, get g() { return 1; } };
console.log(named.name, arrowed.name, obj.m.name, obj.f.name, Object.getOwnPropertyDescriptor(obj, 'g').get.name);
console.log(sloppy.hasOwnProperty('prototype'), o.a.hasOwnProperty('prototype'), obj.m.hasOwnProperty('prototype'));
console.log(Object.getOwnPropertyNames(function f(a) { }).join());
console.log(Object.getOwnPropertyDescriptor(sloppy, 'prototype').writable, Object.getOwnPropertyDescriptor(sloppy, 'name').writable);
console.log(sloppy.prototype.constructor === sloppy);
// toString keeps the source
console.log(function  foo ( a ) { return a ; }.toString());
console.log((a  =>  a).toString(), ({ m ( ) { } }).m.toString(), (class  Z { }).toString());
console.log(Math_().toString());
function Math_() { return Object.prototype.hasOwnProperty; }
