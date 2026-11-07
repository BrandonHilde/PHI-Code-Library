// the error kinds, their names, and what they inherit
for (var E of [Error, TypeError, RangeError, ReferenceError, SyntaxError, EvalError, URIError]) {
  var e = new E('m');
  console.log(e.name, e.message, e instanceof E, e instanceof Error, Object.prototype.toString.call(e), String(e), E.prototype.name, E.length, Object.keys(e).length);
}
console.log(new Error().message === '', Error('no new') instanceof Error, new Error(undefined).hasOwnProperty('message'), new Error('x').hasOwnProperty('message'));
console.log(new Error('c', { cause: 1 }).cause, 'cause' in new Error('c'));
console.log(Object.getPrototypeOf(TypeError) === Error, Error.prototype.toString.call({ name: 'N', message: 'M' }), Error.prototype.toString.call({}));
var ag = new AggregateError([1, 2], 'many'); console.log(ag.errors.length, ag.message, ag.name);
// a stack with function names and lines
String.prototype.split2 = function () { var r = [], from = 0, s = String(this); for (;;) { var i = s.indexOf('\n', from); if (i < 0) break; r.push(s.slice(from, i)); from = i + 1; } r.push(s.slice(from)); return r; };
function inner() { throw new Error('deep'); }
function middle() { inner(); }
function outer() { middle(); }
try { outer(); } catch (x) {
  var lines = x.stack.split2();
  console.log(lines[0]); console.log(lines[1]); console.log(lines[2]); console.log(lines[3]);
}
try { null.x; } catch (x) { console.log(x.stack.split2()[0]); console.log(x.stack.split2()[1]); }
try { undefinedName; } catch (x) { console.log(x.name, x.message); }
// recursion ends in a RangeError that can be caught, again and again
function f() { f(); }
for (var i = 0; i < 3; i++) { try { f(); } catch (x) { console.log(x.name, x instanceof RangeError); } }
function g(n) { return n == 0 ? 0 : 1 + g(n - 1); } console.log(g(3000));
// through natives: every level costs real stack, which is budgeted
function viaNative() { [1].forEach3(viaNative); }
Array.prototype.forEach3 = function (f) { f.call(null, this[0]); };
try { viaNative(); } catch (x) { console.log(x.name); }
var getter = { get g() { return this.g; } }; try { getter.g; } catch (x) { console.log(x.name); }
var ts = { toString() { return '' + this; } }; try { '' + ts; } catch (x) { console.log(x.name); }
var nest = []; nest[0] = nest; console.log(nest.length); try { nest.join(); console.log('joined'); } catch (x) { console.log(x.name); }
function* gr() { yield* gr(); } try { gr().next(); } catch (x) { console.log(x.name); }
class K { constructor() { new K(); } } try { new K(); } catch (x) { console.log(x.name); }
var pc = function () { return pc.apply(null, arguments); }; try { pc(); } catch (x) { console.log(x.name); }
// source that's nested too deeply is a SyntaxError, not a crash
function deep(open, close, n) { return repeat(open, n) + '1' + repeat(close, n); }
for (var pair of [['(', ')'], ['[', ']'], ['{a:', '}'], ['!', ''], ['-', ''], ['f(', ')'], ['a?', ':1'], ['x=>', '']]) {
  try { eval(deep(pair[0], pair[1], 200000)); console.log('it ran'); } catch (x) { console.log(pair[0], x.name); }
}
try { eval(deep('{', '}', 200000)); } catch (x) { console.log('{', x.name); }
try { eval(deep('function f(){', '}', 100000)); } catch (x) { console.log('function', x.name); }
try { eval(deep('if(1)', '', 200000)); } catch (x) { console.log('if', x.name); }
try { eval(deep('class A extends (', '){}', 100000)); } catch (x) { console.log('class', x.name); }
// but a long flat one isn't nested, and works
var sum = '1' + repeat('+1', 20000); console.log(eval(sum));
var elseif = 'var z=0;if(z==1){}' + repeat('else if(z==2){}', 3000); console.log(eval(elseif + ';"chain"'));
console.log(eval(repeat('false?0:', 3000) + '"end"'));
// syntax errors say so, from eval and Function
for (var bad of ['var', '1 +', 'if', 'function', '{', '(', 'a b', 'let let', 'class', '`', '"', '/*', 'return', 'break', '1=1', 'for(', 'let a; let a', 'x = {a=1}', 'new.target', 'super.x', 'yield: 1; function*g(){yield: 1}']) {
  try { eval(bad); console.log('parsed:', bad); } catch (x) { console.log(x.name); }
}
try { new Function('}, function(){'); } catch (x) { console.log(x.name); }
try { new Function('a,', 'return 1'); console.log('trailing comma ok'); } catch (x) { console.log(x.name); }
console.log(new Function('a', 'b', 'return a+b')(1, 2), new Function('return this')() === globalThis, typeof new Function());
console.log(eval('1;2;3'), eval(''), eval('var ev=1'), ev, eval('if(1){4}'), eval('do{5;break}while(0)'), eval(5), eval());
