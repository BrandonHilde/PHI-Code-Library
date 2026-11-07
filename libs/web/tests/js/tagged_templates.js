function tag(s) { return s.join('|') + '#' + s.raw.join('|') + '#' + Array.prototype.slice.call(arguments, 1).join(); }
console.log(tag`a${1}b${2}c`);
console.log(tag`\n${0}\t`);
console.log(tag``);
console.log(tag`${1}`);
// each site has one strings object, frozen
function sites() { return (function (s) { return s; })`x`; }
console.log(sites() === sites(), Object.isFrozen(sites()), Object.isFrozen(sites().raw));
function same(a) { return a; }
console.log(same`x` === same`x`);
// tags keep their this
var o = { t(s) { return this === o; } }; console.log(o.t`x`, o['t']`x`);
// bad escapes are fine in a tag, with undefined cooked
function cooked(s) { return String(s[0]) + '/' + s.raw[0]; }
console.log(cooked`\u{110000}`, cooked`\xg`, cooked`\01`);
// chains
function chain(s) { return function (t) { return s[0] + t[0]; }; }
console.log(chain`a``b`);
new (function (s) { console.log('new tag', this instanceof Object); return function () { }; })`x`;
// untagged
var n = 2;
console.log(`sum ${n + 1} and ${`nested ${n}`} and ${n * 2}`);
console.log(`line
break`.length, `a\
b`, `\u0041\x41`);

console.log(`${1}${2}${3}`, `$`, `$$`, `{}`, `\${}`, `}`);
console.log(`${{ toString() { return 'ts'; } }}`, `${[1, 2]}`, `${null}`, `${undefined}`);
try { `${Symbol()}`; } catch (e) { console.log(e.name); }
// line ends in raw
function rawOf(s) { return s.raw[0].length + ':' + s[0].length; }
console.log(rawOf`a
b`);
console.log(eval('rawOf`a\r\nb`'), eval('rawOf`a\rb`'));
