function* g() { var a = yield 1; var b = yield a + 1; return a + b; }
var i = g();
console.log(JSON_(i.next()), JSON_(i.next(10)), JSON_(i.next(20)), JSON_(i.next()));
function JSON_(r) { return r.value + '/' + r.done; }
// return() and finally
function* f1() { try { yield 1; yield 2; } finally { console.log('cleanup'); } }
i = f1(); i.next(); console.log(JSON_(i.return(9)), JSON_(i.next()));
// a yield in finally can hold up the return
function* f2() { try { yield 1; } finally { yield 'in finally'; console.log('after'); } }
i = f2(); i.next(); console.log(JSON_(i.return(9))); console.log(JSON_(i.next()), JSON_(i.next()));
// return in finally overrides
function* f3() { try { yield 1; } finally { return 'override'; } }
i = f3(); i.next(); console.log(JSON_(i.return(9)));
// throw() is caught inside
function* f4() { try { yield 1; } catch (e) { yield 'caught ' + e; } yield 'on'; }
i = f4(); i.next(); console.log(JSON_(i.throw('x')), JSON_(i.next()), JSON_(i.next()));
// throw() on a generator not yet started, and return()
function* f5() { console.log('never runs'); }
i = f5(); try { i.throw(new Error('e')); } catch (e) { console.log(e.message); } console.log(JSON_(i.next()));
i = f5(); console.log(JSON_(i.return(4)), JSON_(i.next()));
// can't be re-entered
var self; function* f6() { self.next(); yield 1; }
self = f6(); try { self.next(); } catch (e) { console.log(e.name); }
// an exception ends it
function* f7() { yield 1; throw new Error('out'); }
i = f7(); i.next(); try { i.next(); } catch (e) { console.log(e.message); } console.log(JSON_(i.next()));
// yield*
function* inner() { var x = yield 'i1'; console.log('inner got', x); try { yield 'i2'; } finally { console.log('inner finally'); } return 'ret'; }
function* outer() { var r = yield* inner(); console.log('r', r); yield 'o'; }
i = outer(); console.log(i.next().value, i.next('a').value); console.log(i.next().value);
i = outer(); i.next(); i.next(); console.log(JSON_(i.return('early')));
function* star2() { yield* [1, 2]; yield* 'ab'; }
console.log([...star2()].join());
// delegate's throw goes in, and one with no throw method closes it
var closed = 0;
var noThrow = { [Symbol.iterator]() { return this; }, next() { return { value: 1, done: false }; }, return() { closed++; return {}; } };
function* f8() { yield* noThrow; }
i = f8(); i.next(); try { i.throw(1); } catch (e) { console.log(e.name, closed); }
// spread, for-of, destructuring over generators; break closes
function* nat() { var n = 0; try { while (true) yield n++; } finally { console.log('nat closed'); } }
for (var v of nat()) { if (v > 1) break; }
var [a, b] = nat(); console.log(a, b);
outerloop: for (var u of nat()) { for (var w of nat()) { if (u > 0) break outerloop; continue outerloop; } }

// arguments and this stay, through suspension
function* f9() { yield this.q; yield arguments[1]; yield arguments.length; }
i = f9.call({ q: 'this' }, 1, 2, 3); console.log(i.next().value, i.next().value, i.next().value);
// parameters are evaluated at the call, not the first next
function* f10(a = (console.log('params'), 1)) { console.log('body'); yield a; }
i = f10(); console.log('called'); i.next();
// the prototype's its function's
function* f11() { }
console.log(Object.getPrototypeOf(f11()) === f11.prototype, typeof f11.prototype, f11.prototype.constructor === undefined || f11.prototype.hasOwnProperty('constructor'));
console.log(Object.prototype.toString.call(f11()), f11() [Symbol.iterator]().toString());
try { new f11(); } catch (e) { console.log(e.name); }
// many at once, keeping their stacks apart
function* cnt(id, n) { for (var c = 0; c < n; c++) yield id + c; }
var gens = [cnt('a', 2), cnt('b', 3), cnt('c', 1)], out = [];
for (var round = 0; round < 3; round++) for (var g2 of gens) { var r = g2.next(); if (!r.done) out.push(r.value); }
console.log(out.join());
// deep expression stacks across a yield
function* f12() { return [1, 2, yield 'y', 4, { a: yield 'z' }].length + (yield 'w'); }
i = f12(); i.next(); i.next(3); i.next(5); console.log(i.next(10).value);
