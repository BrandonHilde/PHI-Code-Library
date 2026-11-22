// DisposableStack, AsyncDisposableStack (explicit resource management) and Array.fromAsync. JsLazy
// (lazy.phi) runs this the first time one is called; extrasx.phi makes the natives scripts see, and the
// two constructors, whose prototypes' methods are here.
(function (global, exports) {
  "use strict";

  var apply = Reflect.apply;
  var construct = Reflect.construct;
  var defineProperty = Object.defineProperty;
  var WeakMapCtor = WeakMap;
  var weakGet = WeakMap.prototype.get;
  var weakSet = WeakMap.prototype.set;
  var SuppressedErrorCtor = SuppressedError;
  var PromiseCtor = Promise;
  var promiseThen = Promise.prototype.then;
  var isConstructor = exports["%isConstructor"];
  var SymbolDispose = exports["%Symbol.dispose"];
  var SymbolAsyncDispose = exports["%Symbol.asyncDispose"];
  var SymbolIterator = exports["%Symbol.iterator"];
  var SymbolAsyncIterator = exports["%Symbol.asyncIterator"];
  var MAX_SAFE = 9007199254740991;

  function isObject(v) {
    return (typeof v === "object" && v !== null) || typeof v === "function";
  }

  function isCallable(v) {
    return typeof v === "function";
  }

  function getMethod(v, key) {
    var m = v[key];
    if (m === undefined || m === null) return undefined;
    if (!isCallable(m)) throw new TypeError("Not a function");
    return m;
  }

  function dataProperty(o, key, v) {
    defineProperty(o, key, { value: v, writable: true, enumerable: true, configurable: true });
  }

  // ---- what both stacks keep: resources, last first, each { value, async, method } ----

  function newCapability() {
    return { list: [], count: 0 };
  }

  function addResource(cap, value, async, method) {
    var r = { value: value, async: async, method: method };
    dataProperty(cap.list, cap.count, r);
    cap.count++;
  }

  // GetDisposeMethod
  function disposeMethod(v, async) {
    if (async) {
      var m = getMethod(v, SymbolAsyncDispose);
      if (m === undefined) {
        var sync = getMethod(v, SymbolDispose);
        if (sync !== undefined) {
          // what it returns isn't waited for; what it throws is a rejection
          m = function () {
            var o = this;
            return new PromiseCtor(function (resolve, reject) {
              try {
                apply(sync, o, []);
                resolve(undefined);
              } catch (e) {
                reject(e);
              }
            });
          };
        }
      }
      return m;
    }
    return getMethod(v, SymbolDispose);
  }

  // AddDisposableResource for a value: null and undefined are nothing to dispose of (but an
  // asynchronous one still waits once)
  function useValue(cap, v, async) {
    if (v === null || v === undefined) {
      if (async) addResource(cap, undefined, true, undefined);
      return;
    }
    if (!isObject(v)) throw new TypeError("Only an object can be disposed of");
    var m = disposeMethod(v, async);
    if (m === undefined) throw new TypeError("This object has no Symbol." + (async ? "asyncDispose or Symbol.dispose" : "dispose") + " method");
    addResource(cap, v, async, m);
  }

  function suppressed(error, earlier) {
    var e = construct(SuppressedErrorCtor, [error, earlier]);
    return e;
  }

  // DisposeResources, for a stack of synchronous ones: { threw, value } in, and out
  function disposeAll(cap, completion) {
    var list = cap.list;
    for (var i = cap.count - 1; i >= 0; i--) {
      var r = list[i];
      if (r.method === undefined) continue;
      try {
        apply(r.method, r.value, []);
      } catch (e) {
        completion = completion.threw ? { threw: true, value: suppressed(e, completion.value) } : { threw: true, value: e };
      }
    }
    cap.list = [];
    cap.count = 0;
    return completion;
  }

  // the same where some can be asynchronous: each one's result is waited for, and a stack with only
  // nulls in it still waits once. What it ends with is thrown, so its promise is the one to give back.
  async function disposeAllAsync(cap, completion) {
    var list = cap.list;
    var needsAwait = false;
    var hasAwaited = false;
    for (var i = cap.count - 1; i >= 0; i--) {
      var r = list[i];
      if (!r.async && needsAwait && !hasAwaited) {
        await undefined;
        needsAwait = false;
      }
      if (r.method !== undefined) {
        try {
          var result = apply(r.method, r.value, []);
          if (r.async) {
            hasAwaited = true;
            await result;
          }
        } catch (e) {
          completion = completion.threw ? { threw: true, value: suppressed(e, completion.value) } : { threw: true, value: e };
        }
      } else {
        needsAwait = true;
      }
    }
    if (needsAwait && !hasAwaited) await undefined;
    cap.list = [];
    cap.count = 0;
    if (completion.threw) throw completion.value;
  }

  // ---- DisposableStack ----

  var STACKS = new WeakMapCtor();

  function stackOf(o, async) {
    var s = isObject(o) ? apply(weakGet, STACKS, [o]) : undefined;
    if (s === undefined || s.async !== async) {
      throw new TypeError("Not a" + (async ? "n AsyncDisposableStack" : " DisposableStack"));
    }
    return s;
  }

  function pending(s) {
    if (s.disposed) throw new ReferenceError("This stack has been disposed of");
  }

  // the constructors are natives, which call this with the new object
  exports.initStack = function (o, async) {
    apply(weakSet, STACKS, [o, { async: async, disposed: false, cap: newCapability() }]);
  };

  exports.stackUse = function (value) {
    var s = stackOf(this, false);
    pending(s);
    useValue(s.cap, value, false);
    return value;
  };

  exports.stackAdopt = function (value, onDispose) {
    var s = stackOf(this, false);
    pending(s);
    if (!isCallable(onDispose)) throw new TypeError("onDispose is not a function");
    addResource(s.cap, undefined, false, function () { onDispose(value); });
    return value;
  };

  exports.stackDefer = function (onDispose) {
    var s = stackOf(this, false);
    pending(s);
    if (!isCallable(onDispose)) throw new TypeError("onDispose is not a function");
    addResource(s.cap, undefined, false, onDispose);
    return undefined;
  };

  exports.stackDispose = function () {
    var s = stackOf(this, false);
    if (s.disposed) return undefined;
    s.disposed = true;
    var c = disposeAll(s.cap, { threw: false, value: undefined });
    if (c.threw) throw c.value;
    return undefined;
  };

  exports.stackDisposed = function () {
    return stackOf(this, false).disposed;
  };

  // move: what's here goes to a new stack, and this one is done
  function move(o, async, Ctor) {
    var s = stackOf(o, async);
    pending(s);
    var n = construct(Ctor, []);
    var t = stackOf(n, async);
    t.cap = s.cap;
    s.cap = newCapability();
    s.disposed = true;
    return n;
  }

  exports.stackMove = function () {
    return move(this, false, exports["%DisposableStack"]);
  };

  // ---- AsyncDisposableStack ----

  exports.asyncUse = function (value) {
    var s = stackOf(this, true);
    pending(s);
    useValue(s.cap, value, true);
    return value;
  };

  exports.asyncAdopt = function (value, onDisposeAsync) {
    var s = stackOf(this, true);
    pending(s);
    if (!isCallable(onDisposeAsync)) throw new TypeError("onDisposeAsync is not a function");
    addResource(s.cap, undefined, true, function () { return onDisposeAsync(value); });
    return value;
  };

  exports.asyncDefer = function (onDisposeAsync) {
    var s = stackOf(this, true);
    pending(s);
    if (!isCallable(onDisposeAsync)) throw new TypeError("onDisposeAsync is not a function");
    addResource(s.cap, undefined, true, onDisposeAsync);
    return undefined;
  };

  exports.asyncDispose = function () {
    var s;
    try {
      s = stackOf(this, true);
    } catch (e) {
      return new PromiseCtor(function (resolve, reject) { reject(e); });
    }
    if (s.disposed) return new PromiseCtor(function (resolve) { resolve(undefined); });
    s.disposed = true;
    return disposeAllAsync(s.cap, { threw: false, value: undefined });
  };

  exports.asyncDisposed = function () {
    return stackOf(this, true).disposed;
  };

  exports.asyncMove = function () {
    return move(this, true, exports["%AsyncDisposableStack"]);
  };

  // ---- `using` and `await using`: the compiler's code keeps a capability for each block that has them

  exports.usingNew = function () {
    return newCapability();
  };

  exports.usingAdd = function (cap, value, async) {
    useValue(cap, value, async);
    return value;
  };

  // at the block's end: threw says whether it's ending with an exception, and value is it
  exports.usingEnd = function (cap, threw, value) {
    var c = disposeAll(cap, { threw: threw, value: value });
    if (c.threw) throw c.value;
  };

  // for await using: a promise to wait for, or undefined if no await using was reached
  exports.usingEndAsync = function (cap, threw, value) {
    if (cap.count === 0) {
      if (threw) throw value;
      return undefined;
    }
    return disposeAllAsync(cap, { threw: threw, value: value });
  };

  // ---- Array.fromAsync ----

  async function closeAsync(it) {
    var ret = it["return"];
    if (ret === undefined || ret === null) return;
    await apply(ret, it, []);
  }

  exports.fromAsync = function (asyncItems, mapfn, thisArg) {
    var C = this;
    return (async function () {
      var mapping = mapfn !== undefined;
      if (mapping && !isCallable(mapfn)) throw new TypeError("Array.fromAsync: the mapper is not a function");
      var usingAsync = getMethod(asyncItems, SymbolAsyncIterator);
      var usingSync = usingAsync === undefined ? getMethod(asyncItems, SymbolIterator) : undefined;
      var A, k = 0;
      if (usingAsync !== undefined || usingSync !== undefined) {
        var it = apply(usingAsync !== undefined ? usingAsync : usingSync, asyncItems, []);
        if (!isObject(it)) throw new TypeError("Result of the iterator method is not an object");
        var next = it.next;
        A = isConstructor(C) ? construct(C, []) : [];
        for (;;) {
          if (k >= MAX_SAFE) {
            var tooMany = new TypeError("Too many elements");
            try { await closeAsync(it); } catch (e) {}
            throw tooMany;
          }
          var result = apply(next, it, []);
          if (usingAsync !== undefined) result = await result;
          if (!isObject(result)) throw new TypeError("Iterator result is not an object");
          var done = !!result.done;
          var value = result.value;
          if (usingAsync === undefined) {
            // a sync iterator's values are waited for, as if it were async; a rejection closes it
            if (done) {
              await value;
            } else {
              try {
                value = await value;
              } catch (e) {
                try { var r = it["return"]; if (r !== undefined && r !== null) apply(r, it, []); } catch (e2) {}
                throw e;
              }
            }
          }
          if (done) {
            A.length = k;
            return A;
          }
          if (mapping) {
            try {
              value = await apply(mapfn, thisArg, [value, k]);
            } catch (e) {
              try { await closeAsync(it); } catch (e2) {}
              throw e;
            }
          }
          try {
            defineProperty(A, k, { value: value, writable: true, enumerable: true, configurable: true });
          } catch (e) {
            try { await closeAsync(it); } catch (e2) {}
            throw e;
          }
          k++;
        }
      }
      var arrayLike = Object(asyncItems);
      var len = arrayLike.length;
      len = +len;
      len = len !== len || len <= 0 ? 0 : (len === Infinity ? MAX_SAFE : Math.min(Math.floor(len), MAX_SAFE));
      A = isConstructor(C) ? construct(C, [len]) : new Array(len);
      for (; k < len; k++) {
        var kValue = await arrayLike[k];
        if (mapping) kValue = await apply(mapfn, thisArg, [kValue, k]);
        defineProperty(A, k, { value: kValue, writable: true, enumerable: true, configurable: true });
      }
      A.length = len;
      return A;
    })();
  };
})
