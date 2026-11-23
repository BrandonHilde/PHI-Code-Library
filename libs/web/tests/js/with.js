// with (object) statement: names are looked for on the object first, innermost with first
function t(n, f) { try { console.log(n + ": " + f()); } catch (e) { console.log(n + " threw " + e.name); } }
var outer = "outer", count = 0;
t("read", function () { var o = { a: 1 }; with (o) { return a + " " + outer; } });
t("write", function () { var o = { a: 1 }, b = 0; with (o) { a = 5; b = 7; } return o.a + " " + b + " " + ("b" in o); });
t("call this", function () { var o = { n: 3, get: function () { return this === o ? this.n : "wrong this"; } }; with (o) { return get(); } });
t("typeof", function () { var o = { f: function () {} }; with (o) { return typeof f + " " + typeof nothingHere; } });
t("nested", function () { var a = { x: "a" }, b = { y: "b" }; with (a) { with (b) { return x + y; } } });
t("inner wins", function () { var a = { x: "a" }, b = { x: "b" }; with (a) { with (b) { return x; } } });
t("closure", function () { var o = { v: 1 }, f; with (o) { f = function () { return v; }; } o.v = 2; return f(); });
t("declared inside", function () { var o = { k: "on o" }; with (o) { var r = (function () { var k = "local"; return k; })(); } return r; });
t("compound", function () { var o = { c: 1 }; with (o) { c += 2; c++; } return o.c; });
t("let inside", function () { var o = { z: "o" }; with (o) { let z = "let"; return z; } });
t("added later", function () { var o = {}; with (o) { var before = typeof late; o.late = 1; return before + " " + late; } });
t("function scope", function () { var scope = { open: false, toggle() { this.open = !this.open; } }; var fn = new Function("__self", "scope", "with (scope) { __self.result = (toggle(), open) }"); var self = {}; fn(self, scope); return self.result + " " + scope.open; });
t("strict", function () { try { new Function("'use strict'; with ({}) {}"); return "allowed"; } catch (e) { return e.name; } });
t("outside var", function () { with ({}) { count++; } return count; });
t("on null", function () { with (null) { return 1; } });
