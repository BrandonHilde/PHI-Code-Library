var e = '\u{1F600}';
console.log(e.length, e.charCodeAt(0), e.charCodeAt(1), e.charCodeAt(2));
console.log('a' + e + 'b', ('a' + e + 'b').length, ('a' + e + 'b')[3].charCodeAt(0), ('a' + e + 'b').indexOf('b'));
console.log(e[0].length, e[0] + e[1] === e, e.slice(0, 1).charCodeAt(0), e.slice(1).charCodeAt(0));
// lone surrogates survive, and join up exactly when they should
var hi = '\uD83D', lo = '\uDE00';
console.log(hi.length, hi.charCodeAt(0), lo.charCodeAt(0), hi + lo === e, (hi + lo).length, String.fromCharCode(0xD83D, 0xDE00) === e);
console.log((lo + hi).length, (lo + hi).charCodeAt(0), (hi + hi).charCodeAt(1));
var built = ''; for (var i = 0; i < 3; i++) built += hi + lo; console.log(built.length, built === e + e + e);
// a rope whose parts meet at a surrogate pair
var long1 = 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' + hi; var joined = long1 + lo + 'yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy'; console.log(joined.length, joined.charCodeAt(46), joined.charCodeAt(47), joined.indexOf('y'), joined.slice(46, 48) === e);

// indexes in mixed text
var m = 'h\u00e9llo w\u00f6rld \u20ac 1';
console.log(m.length, m[1].charCodeAt(0), m.indexOf('w'), m.indexOf('\u20ac'), m.slice(6, 11), m.charCodeAt(m.length - 1));
for (var i = 0, s = 0; i < m.length; i++) s += m.charCodeAt(i); console.log(s);
for (var i = m.length - 1, s = 0; i >= 0; i--) s += m.charCodeAt(i); console.log(s);
console.log('abc'[1], 'abc'[5], 'abc'.length, 'abc'['length'], 'abc'[-1], 'abc'['1'], 'abc'[1.5]);
var str = new String('boxed'); console.log(str.length, str[0], str.hasOwnProperty('length'), str.hasOwnProperty(0), Object.keys(str).join(), typeof str, str + '!');
str[0] = 'x'; console.log(str[0], delete str[9]);
(function () { 'use strict'; try { str[0] = 'x'; } catch (x) { console.log(x.name); } try { 'abc'[0] = 'x'; } catch (x) { console.log(x.name); } try { 'abc'.foo = 1; } catch (x) { console.log(x.name); } })();
// iterating is by code point
var it = []; for (var c of 'a' + e + '\uD83D' + 'b') it.push(c.length); console.log(it.join());
console.log([...'ab'].join('-'), [...e].length);
// escapes
console.log('\x41\u0041\u{41}\101\0'.length, '\x41\u0041\u{41}\101', 'a\
b', '\a\'\"', '\u{10FFFF}'.length);
console.log("\u2028\u2029".length, '\n\t\r\b\v\f\\'.length);
// comparing is by UTF-16 units, not code points
console.log('\uFF5E' < '\uD83D\uDE00', '\u{10000}' < '\uFFFF', 'a' < 'ab', '' < 'a', 'b' > 'a', 'a' === 'a', 'a' === 'b', '\u00e9' === '\xe9');
// long concatenations stay fast and right
var big = ''; for (var i = 0; i < 2000; i++) big += 'ab'; console.log(big.length, big[3999], big.slice(1998, 2002));
var left = ''; for (var i = 0; i < 200; i++) left = 'z' + left + 'y'; console.log(left.length, left[199], left[200]);
var key = 'pro' + 'perty' + 'name-that-is-a-bit-longer-than-a-rope-needs-to-be'; var o = {}; o[key] = 1; console.log(o['propertyname-that-is-a-bit-longer-than-a-rope-needs-to-be']);
// numbers as text keys and strings
var nk = {}; nk[1] = 'a'; nk['1'] = 'b'; nk[1.5] = 'c'; nk['01'] = 'd'; console.log(nk[1], Object.keys(nk).join());
console.log('5'.length, String(5).length, (5 + '').length);
console.log(String(null), String(undefined), String(true), String([1, [2, 3]]), String({}), String(function () { }), String(Symbol('d')));
try { '' + Symbol(); } catch (x) { console.log(x.name); }
// methods here
console.log('abc'.charAt(1), 'abc'.charAt(9) === '', 'abcabc'.indexOf('c', 3), 'abc'.indexOf(''), 'abc'.indexOf('', 9), 'abc'.slice(-2), 'abc'.slice(1, -1), 'abc'.slice(2, 1) === '');
console.log(String.fromCharCode(65, 66), String.fromCharCode(0x10041), String.fromCharCode());
