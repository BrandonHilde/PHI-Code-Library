// the temporal dead zone: reading or writing before the declaration is a ReferenceError
function t(f) { try { return f(); } catch (e) { return e.name; } }
console.log(t(function () { x; let x = 1; }));
console.log(t(function () { x = 2; let x = 1; }));
console.log(t(function () { let x = x; }));
console.log(t(function () { typeof x; let x; }));
console.log(t(function () { return typeof neverDeclared; }));
console.log(t(function () { let f = () => y; let z = f(); let y = 3; return z; }));
console.log(t(function () { let f = () => y; let y = 3; return f(); }));
console.log(t(function () { { let a = 1; { console.log(a); let b = a; } } return 'ok'; }));
console.log(t(function () { const c = 1; c = 2; }));
console.log(t(function () { const c = 1; c++; }));
console.log(t(function () { for (let i = i; ;) { } }));
console.log(t(function () { for (let i of [i]) { } }));
console.log(t(function () { for (let i of [1]) { var q = i; } return q; }));
console.log(t(function () { class C { static x = C; } return typeof C.x; }));
console.log(t(function () { new D(); class D { } }));
console.log(t(function () { class E extends E { } }));
console.log(t(function (a = b, b) { }));
console.log(t(function (a = 1, b = a + 1) { return b; }));
// in a switch, reaching a case past the declaration doesn't initialize it
console.log(t(function () { switch (2) { case 1: let s = 1; case 2: return s; } }));
// each entry to a block starts over
console.log(t(function () { var out = []; for (var i = 0; i < 2; i++) { try { out.push(v); } catch (e) { out.push(e.name); } let v = i; out.push(v); } return out.join(); }));
// at the top of a script, later scripts see them
try { top; } catch (e) { console.log(e.name); }
let top = 1;
console.log(top);
// a named function expression's own name can't be assigned, silently unless strict
var nf = function me() { me = 1; return typeof me; };
console.log(nf());
var nfs = function me() { 'use strict'; try { me = 1; } catch (e) { return e.name; } };
console.log(nfs());
