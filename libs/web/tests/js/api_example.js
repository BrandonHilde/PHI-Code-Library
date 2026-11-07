// the natives from docs/JS-INTERNALS.md's worked example, seen from JS
var c = new Counter(10);
console.log(c instanceof Counter, Object.prototype.toString.call(c), Counter.name, Counter.length);
console.log(c.add(5), c.add(), c.value);
c.value = 1; console.log(c.value);
c.label = { text: 'held by the host object' };
console.log(c.each(function (n, i) { return n + i; }).join());
gc();
console.log(c.label.text, c.held().text);
try { c.add('x'); } catch (e) { console.log(e.name, e.message, e instanceof TypeError); }
try { Counter.prototype.add.call({}, 1); } catch (e) { console.log(e.name, e.message); }
try { Counter(); } catch (e) { console.log(e.name, e.message); }
console.log(sum(1, 2, 3), sum(), sum.length, sum.name, typeof sum);
console.log(makeList(3).join(), makeList(0).length);
console.log(shapeOf({ w: 2, h: 3 }).area);
console.log(callTwice(function (x) { return x * 2; }, 4));
try { callTwice(function () { throw new RangeError('from JS'); }, 4); } catch (e) { console.log(e.name, e.message); }
console.log(callCatching(function () { throw 'caught in the native'; }), callCatching(function () { return 1; }));
// a PHI error in a native is a JS InternalError, and the engine carries on
try { crash(); } catch (e) { console.log(e.name, e instanceof Error, e.message.length > 0); }
console.log('still running');
// live collection: indexes and length from the host, not stored
var live = new Live(); console.log(live.length, live[0], live[2], live[9], 1 in live, 9 in live, Object.keys(live).join());
live[1] = 'written'; console.log(live[1], live.other); live.other = 'plain'; console.log(live.other);
console.log(delete live[1], delete live.other, live.other);
for (var k in live) console.log(k, live[k]);
// weak references: the host object lets go of what nothing else holds
var wr = new Weak({ v: 'alive' }); var keep = { v: 'kept' }; var wk = new Weak(keep);
churn(); gc(); gc(); console.log(wr.get(), wk.get());
function churn() { for (var i = 0; i < 100; i++) ({ i: i }); }
// a weak map, with a value that holds its key
var em = new Ephemeron(); var ek = {}; em.set(ek, { back: ek, v: 'value' }); em.set({}, { v: 'dead key' });
gc(); gc(); console.log(em.count(), em.get(ek).v);
ek = null; gc(); gc(); console.log(em.count());
// finalizers ran for what was collected
for (var i = 0; i < 5; i++) new Counter(i);
gc(); gc();
console.log(finalized() > 0);
// host roots
keepRooted({ v: 'rooted' }); churn(); gc(); console.log(readRooted().v);
