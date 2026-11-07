console.log(0.1 + 0.2, 1e21, 1e-7, -0, 0, 1 / -0, 5e-324, 1.7976931348623157e308);
console.log(String(-0), (-0).toString(), `${-0}`, [-0].join(), JSON_(-0));
function JSON_(x) { return Object.is(x, -0) ? 'minus zero' : 'other'; }
console.log(123456789012345680000, 1e20, 100, 1.5, .5, 5., 0x10, 0o17, 0b11, 017, 019, 1_000, 1e3, 1E3, 1e+3, 1.5e-3);
console.log(2 ** 53, 2 ** 53 + 1, -(2 ** 31), 2 ** 31, 2 ** -1, (-2) ** 3, 2 ** 3 ** 2, NaN ** 0, 0 ** 0);
console.log(Infinity, -Infinity, NaN, 1 / 0, -1 / 0, 0 / 0, Infinity - Infinity, Infinity * 0);
// integer overflow into doubles
var m = 2147483647; console.log(m + 1, m * 2, m * m, -m - 2, m + m);
var n = -2147483648; console.log(n - 1, n * -1, -n, n / -1, n % -1, Math_abs(n));
function Math_abs(x) { return x < 0 ? -x : x; }
var c = 2147483646; c++; console.log(c); c++; console.log(c); c++; console.log(c);
var d = -2147483647; d--; console.log(d); d--; console.log(d);
for (var i = 2147483646, k = 0; k < 3; i++, k++); console.log(i);
var e = 65536; console.log(e * e, 46341 * 46341, 46340 * 46340, 0 * -1, -1 * 0, 5 % 3, -5 % 3, 5 % -3, 5.5 % 2, -0 % 5, 1 % 0, 0 % 5);
// bit operations
console.log(1 << 31, 1 << 32, 1 << 33, -1 >>> 0, -1 >>> 28, -8 >> 1, 8 >> 1, ~5, ~-1, 5 & 3, 5 | 3, 5 ^ 3);
console.log(2147483648 | 0, 4294967296 | 0, 4294967297 | 0, 1.9 | 0, -1.9 | 0, NaN | 0, Infinity | 0, 1e21 | 0, -2147483649 | 0);
console.log(1 << 31 >>> 0, 2147483648 >> 0, 4294967295 >> 0, 4294967295 >>> 0);
// comparing
console.log(1 < 2, 2 < 1, 1 <= 1, NaN < 1, NaN >= 1, 'a' < 'b', 'a' < 'B', '10' < '9', '10' < 9, null >= 0, undefined >= 0, null == 0, null == undefined, NaN == NaN, 0 === -0, '1' == 1, true == 1, [] == 0, [1] == 1, ({}) == '[object Object]');
// converting
console.log(+'', +' 12 ', +'1e3', +'0x10', +'0b11', +'0o7', +'1_000', +'abc', +'-5', +'+5', +'.5', +'5.', +'Infinity', +'-Infinity', +'infinity', +null, +undefined, +true, +[], +[5], +[1, 2], +{});
console.log(+' \n\t\u00a0\ufeff7\u2029 ', +'0x', +'-0x10', +'1e', +'.', +'e1');
console.log(String(1e21), String(1e-6), String(1e-7), String(123.456), String(1.7976931348623157e308), String(2 ** 64));
console.log(1e21 + '', 1.5 + '', 0.000001 + '', 1e-7 + '', 100 + '');
// toString with a radix, and formatting
console.log((255).toString(16), (255).toString(2), (-255).toString(36), (0.5).toString(2), (0.1).toString(2).length, (1e21).toString(7));
console.log((1.005).toFixed(2), (1.45).toFixed(1), (0).toFixed(2), (1e21).toFixed(2), (-1.5).toFixed(0), (123.456).toFixed(0));
console.log((12.5).toExponential(), (12.5).toExponential(1), (0).toExponential(), (1.5e300).toExponential(2));
console.log((123.456).toPrecision(4), (0.000123).toPrecision(2), (1e21).toPrecision(3), (0).toPrecision(1), (123).toPrecision());
try { (1).toFixed(101); } catch (x) { console.log(x.name); }
try { (1).toString(1); } catch (x) { console.log(x.name); }
// constants and boxes
console.log(Number.MAX_SAFE_INTEGER, Number.EPSILON, Number.MIN_VALUE, Number.MAX_VALUE);
console.log(Number('12'), Number(), new Number(5) + 1, typeof new Number(5), typeof Number('5'), new Boolean(false) ? 'truthy' : 'falsy', Boolean(''), Boolean('x'), !!NaN);
// a large literal, and one that needs exact parsing
console.log(9007199254740993, 1.00000000000000011102230246251565404236316680908203125, 1.00000000000000011102230246251565404236316680908203126, 2.2250738585072011e-308, 1e400, 1e-400);
// ++ and -- on other kinds
var s = '5'; s++; console.log(s, typeof s); var u; u++; console.log(u); var nl = null; nl--; console.log(nl); var ob = { valueOf() { return 2; } }; console.log(ob++, ob);
console.log('5' * '2', '5' - 2, '5' + 2, 5 + '2', 1 + null, 1 + undefined, 1 + true, [] + [], [] + {}, 1 + [2], null + null);
console.log(typeof 1, typeof 'a', typeof true, typeof undefined, typeof null, typeof {}, typeof [], typeof function () { }, typeof Symbol(), typeof class { });
// valueOf and toString order
var both = { valueOf() { return 1; }, toString() { return 'str'; } };
console.log(both + 1, `${both}`, both * 2, String(both), both + '');
var prim = { [Symbol.toPrimitive](h) { return h; } }; console.log(`${prim}`, prim + '', +prim !== +prim);
try { ({ valueOf() { return {}; }, toString() { return {}; } }) + 1; } catch (x) { console.log(x.name); }
try { Symbol() + 1; } catch (x) { console.log(x.name); }
