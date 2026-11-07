// async functions against promise jobs: the order things happen in
var log = [];
function p(x) { log.push(x); }
async function a1() { p('a1 start'); await null; p('a1 after 1'); await null; p('a1 after 2'); return 'a1 done'; }
async function a2() { p('a2 start'); await a1().then(v => p(v)); p('a2 after'); }
Promise.resolve().then(() => p('then 1')).then(() => p('then 2')).then(() => p('then 3')).then(() => p('then 4'));
a2().then(() => p('a2 done'));
p('sync end');
Promise.resolve().then(function () { console.log(log.join(' | ')); });
// an already-native promise awaited takes one tick; a thenable three
var seq = [];
async function n1() { await Promise.resolve(); seq.push('native'); }
async function n2() { await { then(r) { r(); } }; seq.push('thenable'); }
n2(); n1();
Promise.resolve().then(() => seq.push('t1')).then(() => seq.push('t2')).then(() => seq.push('t3')).then(() => seq.push('t4')).then(() => console.log(seq.join()));
// errors reject, and are caught by try around await
async function e1() { throw new Error('thrown'); }
e1().catch(e => console.log('caught', e.message));
async function e2() { try { await Promise.reject('rej'); } catch (x) { console.log('in catch', x); return 'recovered'; } finally { console.log('finally'); } }
e2().then(v => console.log(v));
// default parameters that throw reject too
async function e3(a = (() => { throw 'param'; })()) { }
e3().catch(x => console.log('rejected with', x));
// an async arrow, and this and arguments through it
var o = { v: 1, async m() { var f = async () => { await 0; return this.v + arguments[0]; }; return f(); } };
o.m(2).then(v => console.log('m', v));
// async generators and for await
async function* ag() { var x = yield 1; console.log('got', x); try { yield 2; yield 3; } finally { console.log('ag finally'); } }
(async function () {
  var it = ag();
  console.log((await it.next()).value, (await it.next('hello')).value);
  console.log(await it.return('stop').then(r => r.value + '/' + r.done));
  console.log((await it.next()).done);
  for await (var v of [Promise.resolve('p1'), 'plain']) console.log(v);
  for await (var w of ag()) { console.log(w); if (w == 2) break; }
  async function* del() { var r = yield* ag(); yield 'after'; }
  var d = del(); console.log((await d.next()).value);
  // requests queue up
  var q = ag(); var ps = [q.next(), q.next(), q.next(), q.next(), q.next()];
  var rs = await Promise.all(ps); console.log(rs.map ? 'map' : rs.length);
  console.log(rs[0].value, rs[3].done, rs[4].done);
})().then(() => console.log('main done'), e => console.log('main failed', e && e.message));
