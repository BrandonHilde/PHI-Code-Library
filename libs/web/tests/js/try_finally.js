function r1() { try { return 'try'; } finally { console.log('f1'); } }
console.log(r1());
function r2() { try { return 'try'; } finally { return 'finally'; } }
console.log(r2());
function r3() { try { throw 'x'; } catch (e) { return 'catch ' + e; } finally { console.log('f3'); } }
console.log(r3());
function r4() { try { throw 'x'; } finally { return 'swallowed'; } }
console.log(r4());
function r5() { for (var i = 0; i < 3; i++) { try { if (i == 1) continue; if (i == 2) break; console.log('body', i); } finally { console.log('f', i); } } return 'end'; }
console.log(r5());
function r6() { outer: for (var i = 0; i < 2; i++) { for (var j = 0; j < 2; j++) { try { try { continue outer; } finally { console.log('inner', i, j); } } finally { console.log('outer', i, j); } } } return 'done'; }
console.log(r6());
function r7() { var x = 1; try { return x; } finally { x = 2; } }
console.log(r7());
function r8() { try { try { throw 1; } finally { console.log('a'); } } catch (e) { console.log('b', e); return 'c'; } }
console.log(r8());
function r9() { try { try { throw 1; } catch (e) { throw e + 1; } finally { console.log('middle'); } } catch (e) { return e; } }
console.log(r9());
function r10() { while (true) { try { return 'in loop'; } finally { break; } } return 'broke out'; }
console.log(r10());
function r11() { do { try { throw 1; } catch (e) { continue; } finally { console.log('cont'); } } while (false); return 'after'; }
console.log(r11());
function r12() { try { return (function () { try { return 'deep'; } finally { console.log('deep finally'); } })(); } finally { console.log('outer finally'); } }
console.log(r12());
function r13() { var i = 0; try { i = 1; throw 0; } catch (e) { i = 2; return i; } finally { i = 3; console.log(i); } }
console.log(r13());
// a catch's scope is its own
var e = 'outer'; try { throw 'inner'; } catch (e) { var e2 = e; e = 'changed'; } console.log(e, e2);
try { throw 1; } catch { console.log('no binding'); }
// closures in catch and finally, with scopes pushed and restored
function r14() { var fs = []; for (let i = 0; i < 2; i++) { try { let k = i; fs.push(() => k); throw i; } catch (x) { fs.push(() => x); } finally { let z = i * 10; fs.push(() => z); } } return fs.map2(); }
Array.prototype.map2 = function () { var o = []; for (var f of this) o.push(f()); return o.join(); };
console.log(r14());
// a throw from deep inside, across scopes and frames
function deep(n) { let c = n; var g = () => c; if (n == 0) throw 'bottom'; return deep(n - 1) + g(); }
try { deep(50); } catch (x) { console.log(x); }
// labelled blocks with finally
function r15() { lbl: { try { break lbl; } finally { console.log('lbl finally'); } console.log('skipped'); } return 'past'; }
console.log(r15());
// what's thrown can be anything
for (var v of [1, 'two', null, undefined, { a: 3 }]) { try { throw v; } catch (x) { console.log(typeof x); } }
// iterator close through finally
function r16() { var closed = false; var it = { [Symbol.iterator]() { return this; }, next() { return { value: 1, done: false }; }, return() { closed = true; console.log('closed'); return {}; } }; try { for (var q of it) { try { return 'ret'; } finally { console.log('in'); } } } finally { console.log(closed); } }
console.log(r16());
// a return() that throws replaces normal completion, not an exception
var thrower = { [Symbol.iterator]() { return this; }, next() { return { value: 1, done: false }; }, return() { throw 'from return'; } };
try { for (var q of thrower) break; } catch (x) { console.log(x); }
try { for (var q of thrower) throw 'from body'; } catch (x) { console.log(x); }
