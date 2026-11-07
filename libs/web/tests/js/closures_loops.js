// closures capture a fresh binding per iteration, for let; one binding, for var
var fs = [];
for (let i = 0; i < 3; i++) fs.push(function () { return i; });
console.log(fs[0](), fs[1](), fs[2]());
var gs = [];
for (var j = 0; j < 3; j++) gs.push(function () { return j; });
console.log(gs[0](), gs[1](), gs[2]());
// the update sees the copy, and closures in the head see their own round's
var hs = [];
for (let i = 0, f = function () { return i; }; i < 2; i++) { hs.push(f); hs.push(function () { return i; }); }
console.log(hs[0](), hs[1](), hs[2](), hs[3]());
// changing it in the body affects the next round
var ks = [];
for (let i = 0; i < 6; i++) { ks.push(function () { return i; }); i++; }
console.log(ks[0](), ks[1](), ks[2]());
// while with a block let
var ws = [], n = 0;
while (n < 3) { let m = n * 10; ws.push(function () { return m; }); n++; }
console.log(ws[0](), ws[1](), ws[2]());
// for-of and for-in bindings
var os = [];
for (const v of [7, 8]) os.push(() => v);
for (let k in { a: 1, b: 2 }) os.push(() => k);
console.log(os[0](), os[1](), os[2](), os[3]());
// nested closures and counters
function counter() { var c = 0; return { inc: function () { return ++c; }, get: () => c }; }
var c1 = counter(), c2 = counter();
c1.inc(); c1.inc(); c2.inc();
console.log(c1.get(), c2.get());
// a closure over a parameter, changed afterwards
function p(a) { var f = () => a; a = a + 1; return f; }
console.log(p(1)());
// many levels up
function l1() { var a = 1; return function () { var b = 2; return function () { var c = 3; return function () { return a + b + c; }; }; }; }
console.log(l1()()()());
// continue and break with scopes pushed
var r = [];
for (let i = 0; i < 5; i++) {
  let d = i * 2;
  r.push(() => d);
  if (i == 1) continue;
  if (i == 3) break;
}
console.log(r.length, r[0](), r[1](), r[2](), r[3]());
// switch, with a closure in a case
function sw(x) { switch (x) { case 1: let y = 'one'; return () => y; default: return () => 'other'; } }
console.log(sw(1)(), sw(2)());
