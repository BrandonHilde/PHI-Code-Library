// MutationObserver, IntersectionObserver and ResizeObserver, for every page: run once, after the
// window is set up (page/observers.phi holds it, made by tools/web/make_observers.py).
//
// MutationObserver is the DOM standard's: the document tells this script of each change (the native
// "%watchMutations" turns that on while anything is observed), records are made for the observers
// that want them, and they are delivered together in a microtask. Not kept: previousSibling and
// nextSibling (always null), and the parser's own text appended to a text node.
//
// IntersectionObserver: the browser shows the whole page and scrolls it itself, so every target is
// reported as wholly in view (lazy loading loads; nothing waits), soon after it is observed and
// again when its box changes from none to some (or back), as layout places it.
// ResizeObserver: each target's size after it is observed, and again whenever it changes, looked at
// each frame (sizes are where the browser's layout put things: PageHost.box).
(function (global) {
  "use strict";
  var watch = global["%watchMutations"];
  try { delete global["%watchMutations"]; } catch (e) { }
  var observers = [];
  var scheduled = false;

  function report(error) {
    setTimeout(function () { throw error; }, 0);
  }

  function list(items) {
    items.item = function (i) { return i < this.length ? this[i] : null; };
    return items;
  }

  function MutationRecord(type, target) {
    this.type = type;
    this.target = target;
    this.addedNodes = list([]);
    this.removedNodes = list([]);
    this.previousSibling = null;
    this.nextSibling = null;
    this.attributeName = null;
    this.attributeNamespace = null;
    this.oldValue = null;
  }

  function deliver() {
    scheduled = false;
    var all = observers.slice();
    for (var i = 0; i < all.length; i++) {
      var mo = all[i];
      var records = mo.takeRecords();
      if (records.length) {
        try { mo._callback.call(mo, records, mo); } catch (e) { report(e); }
      }
    }
  }

  function option(o, name) { return o !== undefined && o !== null && o[name] !== undefined; }

  class MutationObserver {
    constructor(callback) {
      if (typeof callback !== "function") throw new TypeError("MutationObserver needs a function");
      this._callback = callback;
      this._targets = [];
      this._records = [];
    }
    observe(target, options) {
      if (!target || typeof target.nodeType !== "number") throw new TypeError("observe needs a Node");
      var o = options || {};
      var attributes = option(o, "attributes") ? !!o.attributes : (option(o, "attributeOldValue") || option(o, "attributeFilter"));
      var characterData = option(o, "characterData") ? !!o.characterData : option(o, "characterDataOldValue");
      var wants = {
        childList: !!o.childList,
        attributes: attributes,
        characterData: characterData,
        subtree: !!o.subtree,
        attributeOldValue: !!o.attributeOldValue,
        characterDataOldValue: !!o.characterDataOldValue,
        attributeFilter: option(o, "attributeFilter") ? Array.from(o.attributeFilter, String) : null
      };
      if (!wants.childList && !wants.attributes && !wants.characterData)
        throw new TypeError("The options must ask for at least one of attributes, characterData and childList");
      if (wants.attributeOldValue && !wants.attributes) throw new TypeError("attributeOldValue needs attributes");
      if (wants.attributeFilter && !wants.attributes) throw new TypeError("attributeFilter needs attributes");
      if (wants.characterDataOldValue && !wants.characterData) throw new TypeError("characterDataOldValue needs characterData");
      for (var i = 0; i < this._targets.length; i++) {
        if (this._targets[i].node === target) { this._targets[i].wants = wants; return; }
      }
      this._targets.push({ node: target, wants: wants });
      if (observers.indexOf(this) < 0) observers.push(this);
      watch(true);
    }
    disconnect() {
      this._targets = [];
      this._records = [];
      var at = observers.indexOf(this);
      if (at >= 0) observers.splice(at, 1);
      if (!observers.length) watch(false);
    }
    takeRecords() {
      var records = this._records;
      this._records = [];
      return records;
    }
  }

  // the document's news of one change: kind 0 a node added to target, 1 one taken from it, 2 an
  // attribute of target (name; old: its value before, or null), 3 target's text (old: before)
  Object.defineProperty(global, "%mutated", { value: function (kind, target, node, name, old) {
    var any = false;
    for (var i = 0; i < observers.length; i++) {
      var mo = observers[i];
      for (var k = 0; k < mo._targets.length; k++) {
        var t = mo._targets[k];
        var w = t.wants;
        if (t.node !== target && !(w.subtree && t.node.contains(target))) continue;
        if (kind < 2 && !w.childList) continue;
        if (kind === 2 && (!w.attributes || (w.attributeFilter && w.attributeFilter.indexOf(name) < 0))) continue;
        if (kind === 3 && !w.characterData) continue;
        var r = new MutationRecord(kind < 2 ? "childList" : kind === 2 ? "attributes" : "characterData", target);
        if (kind === 0) r.addedNodes.push(node);
        if (kind === 1) r.removedNodes.push(node);
        if (kind === 2) {
          r.attributeName = name;
          if (w.attributeOldValue) r.oldValue = old;
        }
        if (kind === 3 && w.characterDataOldValue) r.oldValue = old;
        mo._records.push(r);
        any = true;
        break;
      }
    }
    if (any && !scheduled) {
      scheduled = true;
      queueMicrotask(deliver);
    }
  } });

  function rectOf(element) {
    var b = element ? element.getBoundingClientRect() : { left: 0, top: 0, width: 0, height: 0 };
    return { x: b.left, y: b.top, left: b.left, top: b.top, right: b.left + b.width, bottom: b.top + b.height,
             width: b.width, height: b.height, toJSON: function () { return this; } };
  }

  function view() {
    return { x: 0, y: 0, left: 0, top: 0, right: innerWidth, bottom: innerHeight, width: innerWidth, height: innerHeight };
  }

  // what each observer reports, as the classes a page can test for
  class IntersectionObserverEntry {
    constructor(init) {
      init = init || {};
      this.time = init.time || 0;
      this.target = init.target || null;
      this.rootBounds = init.rootBounds || null;
      this.boundingClientRect = init.boundingClientRect || rectOf(null);
      this.intersectionRect = init.intersectionRect || rectOf(null);
      this.isIntersecting = !!init.isIntersecting;
      this.isVisible = !!init.isVisible;
      this.intersectionRatio = init.intersectionRatio || 0;
    }
  }
  class ResizeObserverEntry {
    constructor(target, box) {
      var size = Object.freeze([Object.freeze({ inlineSize: box.width, blockSize: box.height })]);
      this.target = target;
      this.contentRect = { x: 0, y: 0, left: 0, top: 0, right: box.width, bottom: box.height, width: box.width, height: box.height };
      this.borderBoxSize = size;
      this.contentBoxSize = size;
      this.devicePixelContentBoxSize = size;
    }
  }

  // Every IntersectionObserver with targets is looked at each frame, as each target's ResizeObserver
  // is: a target is reported when it's first looked at, and again when what it shows changes (it
  // had no size and now has one, or the other way).
  var intersecting = [];
  var watching = false;
  function watchAgain() {
    if (watching || !intersecting.length) return;
    watching = true;
    requestAnimationFrame(function () {
      watching = false;
      var all = intersecting.slice();
      for (var i = 0; i < all.length; i++) all[i]._report();
      watchAgain();
    });
  }
  class IntersectionObserver {
    constructor(callback, options) {
      if (typeof callback !== "function") throw new TypeError("IntersectionObserver needs a function");
      var o = options || {};
      this._callback = callback;
      this._targets = [];
      this._shown = [];             // what was last reported for each target ("" before the first)
      this.root = o.root || null;
      this.rootMargin = o.rootMargin || "0px 0px 0px 0px";
      this.thresholds = Object.freeze([].concat(o.threshold === undefined ? 0 : o.threshold));
      this.scrollMargin = "0px 0px 0px 0px";
      this.delay = 0;
      this.trackVisibility = false;
    }
    observe(target) {
      if (!(target instanceof Element)) throw new TypeError("IntersectionObserver.observe needs an Element");
      if (this._targets.indexOf(target) >= 0) return;
      this._targets.push(target);
      this._shown.push("");
      if (intersecting.indexOf(this) < 0) intersecting.push(this);
      watchAgain();
    }
    _report() {
      var entries = [];
      var now = performance.now();
      for (var i = 0; i < this._targets.length; i++) {
        var target = this._targets[i];
        var box = rectOf(target);
        var seen = box.width > 0 && box.height > 0;
        var shown = seen ? "seen" : "flat";
        if (this._shown[i] === shown) continue;
        this._shown[i] = shown;
        entries.push(new IntersectionObserverEntry({ time: now, target: target, isIntersecting: true, isVisible: true, intersectionRatio: 1,
                                                     boundingClientRect: box, intersectionRect: box, rootBounds: view() }));
      }
      if (entries.length) {
        try { this._callback.call(this, entries, this); } catch (e) { report(e); }
      }
    }
    unobserve(target) {
      var at = this._targets.indexOf(target);
      if (at >= 0) {
        this._targets.splice(at, 1);
        this._shown.splice(at, 1);
      }
      if (!this._targets.length) this.disconnect();
    }
    disconnect() {
      this._targets = [];
      this._shown = [];
      var at = intersecting.indexOf(this);
      if (at >= 0) intersecting.splice(at, 1);
    }
    takeRecords() { return []; }
  }

  // Every ResizeObserver with targets is looked at each frame: a target whose size isn't the size
  // last reported for it (none, at first) is reported, as the standard's observations are.
  var resizing = [];
  var looking = false;
  function lookAgain() {
    if (looking || !resizing.length) return;
    looking = true;
    requestAnimationFrame(function () {
      looking = false;
      var all = resizing.slice();
      for (var i = 0; i < all.length; i++) all[i]._report();
      lookAgain();
    });
  }
  class ResizeObserver {
    constructor(callback) {
      if (typeof callback !== "function") throw new TypeError("ResizeObserver needs a function");
      this._callback = callback;
      this._targets = [];
      this._sizes = [];             // what was last reported for each target: [width, height], or null
    }
    observe(target) {
      if (!(target instanceof Element)) throw new TypeError("ResizeObserver.observe needs an Element");
      if (this._targets.indexOf(target) >= 0) return;
      this._targets.push(target);
      this._sizes.push(null);
      if (resizing.indexOf(this) < 0) resizing.push(this);
      lookAgain();
    }
    _report() {
      var entries = [];
      for (var i = 0; i < this._targets.length; i++) {
        var target = this._targets[i];
        var box = rectOf(target);
        var last = this._sizes[i];
        if (last && last[0] === box.width && last[1] === box.height) continue;
        this._sizes[i] = [box.width, box.height];
        entries.push(new ResizeObserverEntry(target, box));
      }
      if (entries.length) {
        try { this._callback.call(this, entries, this); } catch (e) { report(e); }
      }
    }
    unobserve(target) {
      var at = this._targets.indexOf(target);
      if (at >= 0) {
        this._targets.splice(at, 1);
        this._sizes.splice(at, 1);
      }
      if (!this._targets.length) this.disconnect();
    }
    disconnect() {
      this._targets = [];
      this._sizes = [];
      var at = resizing.indexOf(this);
      if (at >= 0) resizing.splice(at, 1);
    }
  }

  function define(name, value) {
    Object.defineProperty(global, name, { value: value, writable: true, configurable: true, enumerable: false });
  }
  define("MutationObserver", MutationObserver);
  define("WebKitMutationObserver", MutationObserver);
  define("MutationRecord", MutationRecord);
  define("IntersectionObserver", IntersectionObserver);
  define("ResizeObserver", ResizeObserver);
  define("IntersectionObserverEntry", IntersectionObserverEntry);
  define("ResizeObserverEntry", ResizeObserverEntry);
})(this);
