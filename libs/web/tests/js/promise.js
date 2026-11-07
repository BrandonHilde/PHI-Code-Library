function out(label) { return function (v) { console.log(label, v); return v; }; }
Promise.resolve(1).then(out('resolved'));
Promise.reject(2).catch(out('rejected'));
new Promise(function (res, rej) { res(3); res(4); rej(5); }).then(out('first wins'));
new Promise(function () { throw 6; }).catch(out('executor threw'));
Promise.resolve(7).finally(function () { console.log('finally 1'); return 'ignored'; }).then(out('through finally'));
Promise.reject(8).finally(function () { console.log('finally 2'); }).catch(out('rejection through finally'));
Promise.resolve(9).finally(function () { throw 10; }).catch(out('finally threw'));
// thenables and resolving with a promise
Promise.resolve({ then: function (r) { r('thenable'); } }).then(out('from thenable'));
new Promise(function (r) { r(Promise.resolve('inner')); }).then(out('from promise'));
var self; self = new Promise(function (r) { setTimeoutLess(function () { r(self); }); });
function setTimeoutLess(f) { Promise.resolve().then(f); }
self.catch(function (e) { console.log('self:', e.name); });
// all, allSettled, race, any
Promise.all([1, Promise.resolve(2), { then(r) { r(3); } }]).then(function (a) { console.log('all', a.join()); });
Promise.all([1, Promise.reject('no')]).catch(out('all rejected'));
Promise.all([]).then(function (a) { console.log('all empty', a.length); });
Promise.allSettled([1, Promise.reject(2)]).then(function (a) { console.log(a[0].status, a[0].value, a[1].status, a[1].reason); });
Promise.race([new Promise(function () { }), Promise.resolve('fast')]).then(out('race'));
Promise.any([Promise.reject(1), Promise.resolve(2)]).then(out('any'));
Promise.any([Promise.reject(1)]).catch(function (e) { console.log(e.name, e.errors.join()); });
Promise.all(5).catch(function (e) { console.log('not iterable:', e.name); });
// subclasses and species
class P2 extends Promise { static get [Symbol.species]() { return Promise; } }
console.log(new P2(function () { }).then() instanceof P2, new P2(function () { }) instanceof P2);
class P3 extends Promise { }
console.log(new P3(function () { }).then() instanceof P3, P3.resolve(1) instanceof P3, P3.reject(1).catch(function () { }) instanceof P3);
// then with something that isn't a function passes through
Promise.resolve('skip').then(1, 2).then(out('passed'));
// errors
try { Promise(); } catch (e) { console.log(e.name); }
try { new Promise(1); } catch (e) { console.log(e.name); }
try { Promise.prototype.then.call(1); } catch (e) { console.log(e.name); }
console.log(Object.prototype.toString.call(Promise.resolve()), typeof Promise.prototype.then, Promise.length, Promise.name);
