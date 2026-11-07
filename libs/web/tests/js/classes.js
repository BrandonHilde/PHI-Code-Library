class A {
  constructor(x) { this.x = x; }
  get double() { return this.x * 2; }
  set double(v) { this.x = v / 2; }
  static make(x) { return new this(x); }
  who() { return 'A'; }
  toString() { return 'A(' + this.x + ')'; }
}
class B extends A {
  constructor(x, y) { super(x); this.y = y; }
  who() { return 'B' + super.who(); }
  get double() { return super.double + 1; }
  set double(v) { super.double = v; }
  static make(x) { var o = super.make(x); o.made = true; return o; }
}
var b = new B(2, 3);
console.log(b.x, b.y, b.double, b.who(), '' + b);
b.double = 10; console.log(b.x);
console.log(B.make(4).made, B.make(4) instanceof B, B.make(4) instanceof A);
console.log(typeof A, A.name, B.name, A.length, B.length);
console.log(Object.getOwnPropertyNames(A.prototype).join());
console.log(Object.getPrototypeOf(B) === A, Object.getPrototypeOf(B.prototype) === A.prototype);
function t(f) { try { return f(); } catch (e) { return e.name + ': ' + e.message; } }
console.log(t(() => A()));
console.log(t(() => { class C extends A { constructor() { this.x = 1; } } new C(); }));
console.log(t(() => { class C extends A { constructor() { super(); super(); } } new C(); }));
console.log(t(() => { class C extends A { constructor() { } } new C(); }));
console.log(t(() => { class C extends A { constructor() { return 1; } } new C(); }));
console.log(t(() => { class C extends A { constructor() { return { own: 1 }; } } return new C().own; }));
console.log(t(() => { class C extends null { } new C(); }));
console.log(t(() => { class C extends 5 { } }));
// fields, in order, with this; computed keys evaluated once, in order
var order = [];
function k(n) { order.push('key' + n); return 'f' + n; }
class F {
  [k(1)] = order.push('init1');
  static [k(2)] = order.push('static2');
  [k(3)] = order.push('init3');
  z = this.f1 + 1;
  arrow = () => this;
}
order.push('defined');
var f = new F();
console.log(order.join());
console.log(f.f1, f.f3, f.z, f.arrow() === f, F.f2);
// fields go on before a derived constructor's body sees this, after super returns
class G extends A { own = this.x * 3; constructor() { super(7); console.log(this.own); } }
new G();
// privates
class P {
  #v = 1;
  static #count = 0;
  #secret() { return this.#v + 100; }
  get #acc() { return this.#v * 2; }
  set #acc(n) { this.#v = n; }
  static bump() { return ++P.#count; }
  read() { return [this.#v, this.#secret(), this.#acc].join(); }
  write(n) { this.#acc = n; }
  has(o) { return #v in o; }
  static read(o) { return o.#v; }
}
var p = new P(); p.write(5);
console.log(p.read(), P.bump(), P.bump(), p.has(p), p.has({}));
console.log(t(() => P.read({})));
console.log(Object.getOwnPropertyNames(p).length);
// a private method can't be overwritten
console.log(t(() => { class Q { #m() { } w() { this.#m = 1; } } new Q().w(); }));
// static blocks, this and super in them
class S { static a = 1; static { this.b = this.a + 1; } static c = this.b + 1; }
console.log(S.a, S.b, S.c);
// accessors and methods aren't enumerable, and have no prototype
console.log(Object.keys(A.prototype).length, A.prototype.who.hasOwnProperty('prototype'));
console.log(t(() => new (A.prototype.who)()));
// generators and async as methods, computed names
var nm = 'dyn';
class M { *gen() { yield 1; } async am() { return 1; } static *[Symbol.iterator]() { yield 'si'; } [nm]() { return nm; } get [nm + 'g']() { return 'g'; } }
console.log(new M().gen().next().value, [...M].join(), new M().dyn(), new M().dyng, M.prototype.dyn.name);
// class expressions and their names
var E1 = class { }; var E2 = class Named { me() { return Named; } };
console.log(E1.name, E2.name, new E2().me() === E2);
console.log(t(() => { class X { m() { X = 1; } } new X().m(); }));
// new.target
function NT() { return new.target; }
console.log(NT() === undefined, new NT() instanceof NT, typeof new NT());
class NB { constructor() { this.t = new.target.name; } }
class ND extends NB { }
console.log(new ND().t);
// extending builtins
class MyErr extends Error { constructor(m) { super(m); this.extra = 1; } }
var me = new MyErr('boom');
console.log(me instanceof Error, me.message, me.extra, Object.prototype.toString.call(me));
class MyArr extends Array { sum() { var s = 0; for (var v of this) s += v; return s; } }
var ma = new MyArr(); ma.push(1, 2, 3); console.log(ma.length, ma.sum(), Array.isArray(ma));
// object-literal super
var base = { hi() { return 'base hi'; } };
var derived = { __proto__: base, hi() { return super.hi() + '!'; }, arrow() { return (() => super.hi())(); } };
console.log(derived.hi(), derived.arrow());
