// labelled break and continue
a: for (var i = 0; i < 3; i++) { b: for (var j = 0; j < 3; j++) { if (j == 1) continue a; if (i == 2) break a; console.log(i, j); } }
c: { console.log('in block'); break c; console.log('never'); }
d: e: for (var k = 0; k < 2; k++) { continue d; }
console.log(k);
f: if (true) { break f; }
g: try { break g; } finally { console.log('finally on the way'); }
h: switch (1) { case 1: for (;;) { break h; } }
var n = 0; w: while (n < 5) { n++; do { if (n < 3) continue w; break w; } while (true); } console.log(n);
// a label can be the same name as a variable
var lbl = 1; lbl: for (;;) { break lbl; } console.log(lbl);
// asi: newlines end statements where the grammar needs them to
var x = 1
var y = 2
console.log(x + y)
var z = x
++y
console.log(z, y)
function ret() {
  return
  1
}
console.log(ret())
function brk() { for (;;) { break
  } return 'ok' }
console.log(brk())
var s = 'a'
;[1].forEach2 = 0
var t = x
/2/1
console.log(t)
do x++; while (x < 3) console.log(x)
if (x) { } else { }
var arrow = () => 1
console.log(arrow())
var u = 5
u
++
u
console.log(u)
let
letname = 1
console.log(letname)
var v = (1
  + 2)
console.log(v)
function th() { try { throw 1 } catch (e) { return e } }
console.log(th())
for (var q = 0
  ; q < 1
  ; q++) console.log('for lines')
var async = 2
async
function notAsync() { return 'plain' }
console.log(notAsync(), async)
// regex vs division needs a hook here, so only division
var aa = 4, b = 2, cc = 1
console.log(aa / b / cc, aa /b/ cc)
var o = { get: 1, set: 2, async: 3, static: 4, of: 5, let: 6, yield: 7, await: 8, new: 9, if: 10, class: 11, function: 12 }
console.log(o.get + o.set + o.async + o.static + o.of + o.let + o.yield + o.await + o.new + o.if + o.class + o.function)
// comments count as line ends if they hold one
var m = 1 /* one line */ + 1
console.log(m)
function mc() { return /* a
  line */ 1 }
console.log(mc())
// html-like comments
var hc = 3 <!-- 4
--> nothing here at all
console.log(hc)
// unicode escapes in names, non-ASCII names
var \u0061bc = 'escaped'; console.log(abc);
var caf\u00e9 = 1; console.log(café); var ñandú = 'bird', 变量 = 'var', 𝒳 = 'math'; console.log(ñandú, 变量, 𝒳);

var o2 = { \u0061: 1 }; console.log(o2.a, o2.\u0061);
// line and paragraph separators end lines
var ls = 1 ; var ps = 2;  console.log(ls + ps)
