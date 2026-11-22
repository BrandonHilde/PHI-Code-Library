// Iterator's helpers (ES2025), and Iterator.concat, Iterator.zip and Iterator.zipKeyed, includes, join,
// chunks and windows from the proposals test262 has. JsLazy (lazy.phi) runs this the first time a script
// calls one of them: it gets the global object and the object its natives look in, and fills that in.
// The natives stay the functions scripts see, so names, lengths and identity are the builtins' own.
//
// A helper is a generator underneath, which gives the states the standard asks for (a helper that's
// running can't be resumed, and one that's done stays done) and closes what it reads from when it's
// left early, through finally.
(function (global, exports) {
  "use strict";

  var ObjectCreate = Object.create;
  var defineProperty = Object.defineProperty;
  var getOwnPropertyDescriptor = Object.getOwnPropertyDescriptor;
  var ownKeys = Reflect.ownKeys;
  var apply = Reflect.apply;
  var WeakMapCtor = WeakMap;
  var weakGet = WeakMap.prototype.get;
  var weakSet = WeakMap.prototype.set;
  var isPrototypeOf = Object.prototype.isPrototypeOf;
  var IteratorPrototype = Object.getPrototypeOf(Object.getPrototypeOf([][exports["%Symbol.iterator"]]()));
  var GeneratorPrototype = Object.getPrototypeOf(function* () {}).prototype;
  var genNext = GeneratorPrototype.next;
  var genReturn = GeneratorPrototype["return"];
  var SymbolIterator = exports["%Symbol.iterator"];
  var StringCtor = String;
  var NumberIsNaN = Number.isNaN;
  var MathTrunc = Math.trunc;
  var MAX_SAFE = 9007199254740991;

  function isObject(v) {
    return (typeof v === "object" && v !== null) || typeof v === "function";
  }

  function isCallable(v) {
    return typeof v === "function";
  }

  // ToString, which a Symbol fails (String() would describe it)
  function toStr(v) {
    if (typeof v === "symbol") throw new TypeError("Cannot convert a Symbol to a string");
    return StringCtor(v);
  }

  function hidden(o, key, value) {
    defineProperty(o, key, { value: value, writable: true, enumerable: false, configurable: true });
  }

  // a function as a builtin method has it: its own name and length, and no prototype
  function method(o, key, name, length, f) {
    defineProperty(f, "name", { value: name, configurable: true });
    defineProperty(f, "length", { value: length, configurable: true });
    hidden(o, key, f);
  }

  function newList() {
    var a = [];
    Object.setPrototypeOf(a, null);
    return a;
  }

  function add(list, v) {
    defineProperty(list, list.length, { value: v, writable: true, enumerable: true, configurable: true });
  }

  function makeArray(list) {
    var a = [];
    for (var i = 0; i < list.length; i++) {
      defineProperty(a, i, { value: list[i], writable: true, enumerable: true, configurable: true });
    }
    return a;
  }

  // ---- the iterator protocol, as the standard's abstract operations ----

  function requireObject(o) {
    if (!isObject(o)) throw new TypeError("Iterator helper called on a non-object");
  }

  // GetIteratorDirect
  function direct(o) {
    return { iterator: o, next: o.next, done: false };
  }

  // IteratorStepValue: the next value, or DONE (after which the record is done)
  var DONE = {};
  function stepValue(r) {
    var result;
    try {
      result = apply(r.next, r.iterator, []);
    } catch (e) {
      r.done = true;
      throw e;
    }
    if (!isObject(result)) {
      r.done = true;
      throw new TypeError("Iterator result is not an object");
    }
    var finished;
    try {
      finished = !!result.done;
    } catch (e) {
      r.done = true;
      throw e;
    }
    if (finished) {
      r.done = true;
      return DONE;
    }
    try {
      return result.value;
    } catch (e) {
      r.done = true;
      throw e;
    }
  }

  // IteratorStep, which doesn't read the value
  function step(r) {
    var result;
    try {
      result = apply(r.next, r.iterator, []);
    } catch (e) {
      r.done = true;
      throw e;
    }
    if (!isObject(result)) {
      r.done = true;
      throw new TypeError("Iterator result is not an object");
    }
    var finished;
    try {
      finished = !!result.done;
    } catch (e) {
      r.done = true;
      throw e;
    }
    if (finished) r.done = true;
    return !finished;
  }

  // IteratorClose for a normal completion: what return() throws or a result that isn't an object counts
  function close(iterator) {
    var ret = iterator["return"];
    if (ret === undefined || ret === null) return;
    if (!isCallable(ret)) throw new TypeError("Iterator's return is not a function");
    var result = apply(ret, iterator, []);
    if (!isObject(result)) throw new TypeError("Iterator's return gave a non-object");
  }

  // IteratorClose for a throw completion: the error that's already on its way wins
  function closeQuietly(iterator) {
    try {
      var ret = iterator["return"];
      if (ret !== undefined && ret !== null) apply(ret, iterator, []);
    } catch (e) {}
  }

  // IteratorCloseAll, last first: for a normal completion when error is DONE, otherwise the error stays
  function closeAll(list, error) {
    var failed = error !== DONE;
    var thrown = error;
    for (var i = list.length - 1; i >= 0; i--) {
      if (failed) {
        closeQuietly(list[i].iterator);
      } else {
        try {
          close(list[i].iterator);
        } catch (e) {
          failed = true;
          thrown = e;
        }
      }
    }
    if (failed) throw thrown;
  }

  function removeFrom(list, r) {
    for (var i = 0; i < list.length; i++) {
      if (list[i] === r) {
        for (var j = i; j + 1 < list.length; j++) list[j] = list[j + 1];
        list.length = list.length - 1;
        return;
      }
    }
  }

  // GetIteratorFlattenable
  function flattenable(v, strings) {
    if (!isObject(v) && !(strings && typeof v === "string")) {
      throw new TypeError("Iterator.from takes an object or a string");
    }
    var m = v[SymbolIterator];
    var it;
    if (m === undefined || m === null) {
      it = v;
    } else {
      if (!isCallable(m)) throw new TypeError("Symbol.iterator is not a function");
      it = apply(m, v, []);
    }
    if (!isObject(it)) throw new TypeError("Iterator is not an object");
    return direct(it);
  }

  // GetIterator
  function getIterator(v) {
    var m = v[SymbolIterator];
    if (!isCallable(m)) throw new TypeError("Value is not iterable");
    var it = apply(m, v, []);
    if (!isObject(it)) throw new TypeError("Iterator is not an object");
    return direct(it);
  }

  // ---- %IteratorHelperPrototype%: each helper is a generator, with what it reads from ----

  var HELPERS = new WeakMapCtor();
  var HelperPrototype = ObjectCreate(IteratorPrototype);

  function slotOf(o) {
    var s = isObject(o) ? apply(weakGet, HELPERS, [o]) : undefined;
    if (s === undefined) throw new TypeError("Not an Iterator Helper");
    return s;
  }

  // underlying: what to close if it's returned before it starts (a list of records)
  function helper(gen, underlying) {
    var h = ObjectCreate(HelperPrototype);
    apply(weakSet, HELPERS, [h, { gen: gen, started: false, underlying: underlying }]);
    return h;
  }

  method(HelperPrototype, "next", "next", 0, {
    next() {
      var s = slotOf(this);
      s.started = true;
      return apply(genNext, s.gen, []);
    }
  }.next);
  method(HelperPrototype, "return", "return", 0, {
    return() {
      var s = slotOf(this);
      if (!s.started) {
        s.started = true;
        apply(genReturn, s.gen, [undefined]);
        closeAll(s.underlying, DONE);
        return { value: undefined, done: true };
      }
      return apply(genReturn, s.gen, [undefined]);
    }
  }.return);
  defineProperty(HelperPrototype, exports["%Symbol.toStringTag"], { value: "Iterator Helper", configurable: true });

  function one(r) {
    var list = newList();
    add(list, r);
    return list;
  }

  // a yield from a helper that closes r if the helper is left there
  // (written out in each generator, as yield can't be in a function of its own)

  // ---- argument checks that close the iterator when they fail ----

  function needCallable(o, f) {
    if (!isCallable(f)) {
      closeQuietly(o);
      throw new TypeError(StringCtor(typeof f) + " is not a function");
    }
  }

  function limitOf(o, limit) {
    var n;
    try {
      n = +limit;
    } catch (e) {
      closeQuietly(o);
      throw e;
    }
    if (NumberIsNaN(n)) {
      closeQuietly(o);
      throw new RangeError("The limit must be a number");
    }
    n = n === Infinity || n === -Infinity ? n : MathTrunc(n);
    if (n < 0 || (n > MAX_SAFE && n !== Infinity)) {
      closeQuietly(o);
      throw new RangeError("The limit must be from 0 to 2^53 - 1, or Infinity");
    }
    return n + 0;
  }

  // chunks' and windows' size: a whole Number from 1 to 2^32 - 1, not converted
  function sizeOf(o, size) {
    if (typeof size !== "number" || NumberIsNaN(size) || size === Infinity || size === -Infinity || MathTrunc(size) !== size) {
      closeQuietly(o);
      throw new TypeError("The size must be a number");
    }
    if (size < 1 || size > 4294967295) {
      closeQuietly(o);
      throw new RangeError("The size must be a whole number from 1 to 2^32 - 1");
    }
    return size;
  }

  // ---- Iterator.prototype's methods ----

  exports.map = function (mapper) {
    var o = this;
    requireObject(o);
    needCallable(o, mapper);
    var r = direct(o);
    return helper((function* () {
      var counter = 0;
      for (;;) {
        var value = stepValue(r);
        if (value === DONE) return;
        var mapped;
        try {
          mapped = mapper(value, counter);
        } catch (e) {
          closeQuietly(o);
          throw e;
        }
        counter++;
        var left = true;
        try {
          yield mapped;
          left = false;
        } finally {
          if (left) close(o);
        }
      }
    })(), one(r));
  };

  exports.filter = function (predicate) {
    var o = this;
    requireObject(o);
    needCallable(o, predicate);
    var r = direct(o);
    return helper((function* () {
      var counter = 0;
      for (;;) {
        var value = stepValue(r);
        if (value === DONE) return;
        var selected;
        try {
          selected = predicate(value, counter);
        } catch (e) {
          closeQuietly(o);
          throw e;
        }
        counter++;
        if (selected) {
          var left = true;
          try {
            yield value;
            left = false;
          } finally {
            if (left) close(o);
          }
        }
      }
    })(), one(r));
  };

  exports.take = function (limit) {
    var o = this;
    requireObject(o);
    var remaining = limitOf(o, limit);
    var r = direct(o);
    return helper((function* () {
      for (;;) {
        if (remaining === 0) {
          close(o);
          return;
        }
        if (remaining !== Infinity) remaining--;
        var value = stepValue(r);
        if (value === DONE) return;
        var left = true;
        try {
          yield value;
          left = false;
        } finally {
          if (left) close(o);
        }
      }
    })(), one(r));
  };

  exports.drop = function (limit) {
    var o = this;
    requireObject(o);
    var remaining = limitOf(o, limit);
    var r = direct(o);
    return helper((function* () {
      while (remaining > 0) {
        if (remaining !== Infinity) remaining--;
        if (!step(r)) return;
      }
      for (;;) {
        var value = stepValue(r);
        if (value === DONE) return;
        var left = true;
        try {
          yield value;
          left = false;
        } finally {
          if (left) close(o);
        }
      }
    })(), one(r));
  };

  exports.flatMap = function (mapper) {
    var o = this;
    requireObject(o);
    needCallable(o, mapper);
    var r = direct(o);
    return helper((function* () {
      var counter = 0;
      for (;;) {
        var value = stepValue(r);
        if (value === DONE) return;
        var inner;
        try {
          inner = flattenable(mapper(value, counter), false);
        } catch (e) {
          closeQuietly(o);
          throw e;
        }
        counter++;
        for (;;) {
          var innerValue;
          try {
            innerValue = stepValue(inner);
          } catch (e) {
            closeQuietly(o);
            throw e;
          }
          if (innerValue === DONE) break;
          var left = true;
          try {
            yield innerValue;
            left = false;
          } finally {
            if (left) {
              try {
                close(inner.iterator);
              } catch (e) {
                closeQuietly(o);
                throw e;
              }
              close(o);
            }
          }
        }
      }
    })(), one(r));
  };

  exports.reduce = function (reducer) {
    var o = this;
    requireObject(o);
    needCallable(o, reducer);
    var r = direct(o);
    var accumulator, counter;
    if (arguments.length < 2) {
      accumulator = stepValue(r);
      if (accumulator === DONE) throw new TypeError("Reduce of an empty iterator with no initial value");
      counter = 1;
    } else {
      accumulator = arguments[1];
      counter = 0;
    }
    for (;;) {
      var value = stepValue(r);
      if (value === DONE) return accumulator;
      try {
        accumulator = reducer(accumulator, value, counter);
      } catch (e) {
        closeQuietly(o);
        throw e;
      }
      counter++;
    }
  };

  exports.toArray = function () {
    var o = this;
    requireObject(o);
    var r = direct(o);
    var items = [];
    var i = 0;
    for (;;) {
      var value = stepValue(r);
      if (value === DONE) return items;
      defineProperty(items, i++, { value: value, writable: true, enumerable: true, configurable: true });
    }
  };

  exports.forEach = function (fn) {
    var o = this;
    requireObject(o);
    needCallable(o, fn);
    var r = direct(o);
    var counter = 0;
    for (;;) {
      var value = stepValue(r);
      if (value === DONE) return undefined;
      try {
        fn(value, counter);
      } catch (e) {
        closeQuietly(o);
        throw e;
      }
      counter++;
    }
  };

  // some, every and find: a predicate that settles it closes the iterator
  function search(o, predicate, want, found) {
    requireObject(o);
    needCallable(o, predicate);
    var r = direct(o);
    var counter = 0;
    for (;;) {
      var value = stepValue(r);
      if (value === DONE) return DONE;
      var result;
      try {
        result = !!predicate(value, counter);
      } catch (e) {
        closeQuietly(o);
        throw e;
      }
      if (result === want) {
        close(o);
        return found ? value : true;
      }
      counter++;
    }
  }

  exports.some = function (predicate) {
    return search(this, predicate, true, false) !== DONE;
  };

  exports.every = function (predicate) {
    return search(this, predicate, false, false) === DONE;
  };

  exports.find = function (predicate) {
    var v = search(this, predicate, true, true);
    return v === DONE ? undefined : v;
  };

  exports.includes = function (searchElement, skippedElements) {
    var o = this;
    requireObject(o);
    var toSkip = 0;
    if (skippedElements !== undefined) {
      if (typeof skippedElements !== "number" || NumberIsNaN(skippedElements) ||
          (skippedElements !== Infinity && skippedElements !== -Infinity && MathTrunc(skippedElements) !== skippedElements)) {
        closeQuietly(o);
        throw new TypeError("skippedElements must be a whole number");
      }
      if (skippedElements < 0 || (skippedElements > MAX_SAFE && skippedElements !== Infinity)) {
        closeQuietly(o);
        throw new RangeError("skippedElements is out of range");
      }
      toSkip = skippedElements;
    }
    var r = direct(o);
    var skipped = 0;
    for (;;) {
      var value = stepValue(r);
      if (value === DONE) return false;
      if (skipped < toSkip) {
        skipped++;
      } else if (value === searchElement || (value !== value && searchElement !== searchElement)) {
        close(o);
        return true;
      }
    }
  };

  exports.join = function (separator) {
    var o = this;
    requireObject(o);
    var sep = ",";
    if (separator !== undefined) {
      try {
        sep = toStr(separator);
      } catch (e) {
        closeQuietly(o);
        throw e;
      }
    }
    var r = direct(o);
    var out = "";
    var first = true;
    for (;;) {
      var value = stepValue(r);
      if (value === DONE) return out;
      if (!first) out += sep;
      first = false;
      if (value !== undefined && value !== null) {
        try {
          out += toStr(value);
        } catch (e) {
          closeQuietly(o);
          throw e;
        }
      }
    }
  };

  exports.chunks = function (chunkSize) {
    var o = this;
    requireObject(o);
    var size = sizeOf(o, chunkSize);
    var r = direct(o);
    return helper((function* () {
      var buffer = [];
      for (;;) {
        var value = stepValue(r);
        if (value === DONE) {
          if (buffer.length > 0) yield buffer;
          return;
        }
        defineProperty(buffer, buffer.length, { value: value, writable: true, enumerable: true, configurable: true });
        if (buffer.length === size) {
          var left = true;
          try {
            yield buffer;
            left = false;
          } finally {
            if (left) close(o);
          }
          buffer = [];
        }
      }
    })(), one(r));
  };

  exports.windows = function (windowSize, undersized) {
    var o = this;
    requireObject(o);
    var size = sizeOf(o, windowSize);
    if (undersized === undefined) undersized = "only-full";
    if (undersized !== "only-full" && undersized !== "allow-partial") {
      closeQuietly(o);
      throw new TypeError("undersized must be \"only-full\" or \"allow-partial\"");
    }
    var r = direct(o);
    return helper((function* () {
      var buffer = newList();
      for (;;) {
        var value = stepValue(r);
        if (value === DONE) {
          if (undersized === "allow-partial" && buffer.length > 0 && buffer.length < size) yield makeArray(buffer);
          return;
        }
        if (buffer.length === size) {
          for (var i = 0; i + 1 < buffer.length; i++) buffer[i] = buffer[i + 1];
          buffer.length = buffer.length - 1;
        }
        add(buffer, value);
        if (buffer.length === size) {
          var left = true;
          try {
            yield makeArray(buffer);
            left = false;
          } finally {
            if (left) close(o);
          }
        }
      }
    })(), one(r));
  };

  exports.dispose = function () {
    var ret = this["return"];
    if (ret !== undefined && ret !== null) {
      if (!isCallable(ret)) throw new TypeError("Iterator's return is not a function");
      apply(ret, this, []);
    }
    return undefined;
  };

  // Iterator.prototype.constructor's and [Symbol.toStringTag]'s setters: SetterThatIgnoresPrototypeProperties
  function ignoringPrototype(key) {
    return function (v) {
      if (!isObject(this)) throw new TypeError("Iterator.prototype setter called on a non-object");
      if (this === IteratorPrototype) throw new TypeError("Cannot set this on Iterator.prototype");
      if (getOwnPropertyDescriptor(this, key) === undefined) {
        defineProperty(this, key, { value: v, writable: true, enumerable: true, configurable: true });
      } else {
        this[key] = v;
      }
    };
  }
  exports.setConstructor = ignoringPrototype("constructor");
  exports.setToStringTag = ignoringPrototype(exports["%Symbol.toStringTag"]);

  // ---- Iterator.from, and %WrapForValidIteratorPrototype% ----

  var WRAPPED = new WeakMapCtor();
  var WrapPrototype = ObjectCreate(IteratorPrototype);

  function wrapped(o) {
    var r = isObject(o) ? apply(weakGet, WRAPPED, [o]) : undefined;
    if (r === undefined) throw new TypeError("Not a wrapped iterator");
    return r;
  }

  method(WrapPrototype, "next", "next", 0, {
    next() {
      var r = wrapped(this);
      return apply(r.next, r.iterator, []);
    }
  }.next);
  method(WrapPrototype, "return", "return", 0, {
    return() {
      var r = wrapped(this);
      var ret = r.iterator["return"];
      if (ret === undefined || ret === null) return { value: undefined, done: true };
      if (!isCallable(ret)) throw new TypeError("Iterator's return is not a function");
      return apply(ret, r.iterator, []);
    }
  }.return);

  exports.from = function (o) {
    var r = flattenable(o, true);
    if (apply(isPrototypeOf, IteratorPrototype, [r.iterator])) return r.iterator;
    var w = ObjectCreate(WrapPrototype);
    apply(weakSet, WRAPPED, [w, r]);
    return w;
  };

  // ---- Iterator.concat ----

  exports.concat = function () {
    var iterables = newList();
    for (var i = 0; i < arguments.length; i++) {
      var item = arguments[i];
      if (!isObject(item)) throw new TypeError("Iterator.concat takes iterable objects");
      var m = item[SymbolIterator];
      if (!isCallable(m)) throw new TypeError("Iterator.concat takes iterable objects");
      add(iterables, { open: m, iterable: item });
    }
    var open = newList();
    return helper((function* () {
      for (var k = 0; k < iterables.length; k++) {
        var it = apply(iterables[k].open, iterables[k].iterable, []);
        if (!isObject(it)) throw new TypeError("Iterator is not an object");
        var r = direct(it);
        for (;;) {
          var value = stepValue(r);
          if (value === DONE) break;
          var left = true;
          try {
            yield value;
            left = false;
          } finally {
            if (left) close(it);
          }
        }
      }
    })(), open);
  };

  // ---- Iterator.zip and Iterator.zipKeyed ----

  function optionsOf(options) {
    if (options === undefined) return ObjectCreate(null);
    if (!isObject(options)) throw new TypeError("options must be an object");
    return options;
  }

  function modeOf(options) {
    var mode = options.mode;
    if (mode === undefined) return "shortest";
    if (mode !== "shortest" && mode !== "longest" && mode !== "strict") {
      throw new TypeError("mode must be \"shortest\", \"longest\" or \"strict\"");
    }
    return mode;
  }

  function zip(iters, mode, padding, finish) {
    var count = iters.length;
    var open = newList();
    for (var i = 0; i < count; i++) add(open, iters[i]);
    return helper((function* () {
      if (count === 0) return;
      for (;;) {
        var results = newList();
        for (var i = 0; i < count; i++) {
          var r = iters[i];
          var result;
          if (r === null) {
            result = padding[i];
          } else {
            try {
              result = stepValue(r);
            } catch (e) {
              removeFrom(open, r);
              closeAll(open, e);
            }
            if (result === DONE) {
              removeFrom(open, r);
              if (mode === "shortest") {
                closeAll(open, DONE);
                return;
              } else if (mode === "strict") {
                if (i !== 0) closeAll(open, new TypeError("Iterator.zip: the iterators are of different lengths"));
                for (var k = 1; k < count; k++) {
                  var more;
                  try {
                    more = step(iters[k]);
                  } catch (e) {
                    removeFrom(open, iters[k]);
                    closeAll(open, e);
                  }
                  if (more) closeAll(open, new TypeError("Iterator.zip: the iterators are of different lengths"));
                  removeFrom(open, iters[k]);
                }
                return;
              } else {
                if (open.length === 0) return;
                iters[i] = null;
                result = padding[i];
              }
            }
          }
          add(results, result);
        }
        var left = true;
        try {
          yield finish(results);
          left = false;
        } finally {
          if (left) closeAll(open, DONE);
        }
      }
    })(), open);
  }

  exports.zip = function (iterables, options) {
    if (!isObject(iterables)) throw new TypeError("Iterator.zip takes an iterable object");
    options = optionsOf(options);
    var mode = modeOf(options);
    var paddingOption;
    if (mode === "longest") {
      paddingOption = options.padding;
      if (paddingOption !== undefined && !isObject(paddingOption)) throw new TypeError("padding must be an object");
    }
    var iters = newList();
    var input = getIterator(iterables);
    for (;;) {
      var next;
      try {
        next = stepValue(input);
      } catch (e) {
        closeAll(iters, e);
      }
      if (next === DONE) break;
      var it;
      try {
        it = flattenable(next, false);
      } catch (e) {
        closeQuietly(input.iterator);
        closeAll(iters, e);
      }
      add(iters, it);
    }
    var padding = newList();
    if (mode === "longest") {
      if (paddingOption === undefined) {
        for (var i = 0; i < iters.length; i++) add(padding, undefined);
      } else {
        var pad;
        try {
          pad = getIterator(paddingOption);
        } catch (e) {
          closeAll(iters, e);
        }
        var using = true;
        for (var j = 0; j < iters.length; j++) {
          var v = undefined;
          if (using) {
            try {
              v = stepValue(pad);
            } catch (e) {
              closeAll(iters, e);
            }
            if (v === DONE) {
              using = false;
              v = undefined;
            }
          }
          add(padding, v);
        }
        if (using) {
          try {
            close(pad.iterator);
          } catch (e) {
            closeAll(iters, e);
          }
        }
      }
    }
    return zip(iters, mode, padding, makeArray);
  };

  exports.zipKeyed = function (iterables, options) {
    if (!isObject(iterables)) throw new TypeError("Iterator.zipKeyed takes an object");
    options = optionsOf(options);
    var mode = modeOf(options);
    var paddingOption;
    if (mode === "longest") {
      paddingOption = options.padding;
      if (paddingOption !== undefined && !isObject(paddingOption)) throw new TypeError("padding must be an object");
    }
    var iters = newList();
    var keys = newList();
    var all = ownKeys(iterables);
    for (var i = 0; i < all.length; i++) {
      var key = all[i];
      var value;
      try {
        var desc = getOwnPropertyDescriptor(iterables, key);
        if (desc === undefined || !desc.enumerable) continue;
        value = iterables[key];
        if (value === undefined) continue;
        var it = flattenable(value, false);
      } catch (e) {
        closeAll(iters, e);
      }
      add(keys, key);
      add(iters, it);
    }
    var padding = newList();
    if (mode === "longest") {
      for (var j = 0; j < keys.length; j++) {
        var v = undefined;
        if (paddingOption !== undefined) {
          try {
            v = paddingOption[keys[j]];
          } catch (e) {
            closeAll(iters, e);
          }
        }
        add(padding, v);
      }
    }
    return zip(iters, mode, padding, function (results) {
      var obj = ObjectCreate(null);
      for (var k = 0; k < keys.length; k++) {
        defineProperty(obj, keys[k], { value: results[k], writable: true, enumerable: true, configurable: true });
      }
      return obj;
    });
  };
})
