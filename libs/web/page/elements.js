// Custom elements, and the DOM's tree walkers, for every page: run once, after the window is set up
// (page/elements.phi holds it, made by tools/web/make_page_js.py).
//
// Custom elements are the HTML standard's: customElements.define(name, class) makes the class what
// elements of that name are. HTMLElement here is a function a class can extend: a class made with
// `new` gets a new element (natives %ceNew), and one made to upgrade an element the parser or
// innerHTML made earlier gets that element (the standard's construction stack, one deep). The page
// tells %ceReact what the DOM did, in order, after each DOM method and between the parser's tokens:
//   0, el: el is connected (upgrade it, or tell it connectedCallback)
//   1, el: el was disconnected (disconnectedCallback)
//   2, el, name, old: an attribute changed (attributeChangedCallback, if it's observed)
//   3, el: el was made by cloneNode or importNode (upgrade it, connected or not)
// Not kept: customized built-ins (define's `extends`), form-associated callbacks, and adoptedCallback.
//
// TreeWalker, NodeIterator and NodeFilter are the DOM standard's, over the nodes' own properties.
(function (global) {
  "use strict";
  var ceNew = global["%ceNew"];
  var ceWatch = global["%ceWatch"];
  var ceFind = global["%ceFind"];
  var ceDefined = global["%ceDefined"];
  delete global["%ceNew"];
  delete global["%ceWatch"];
  delete global["%ceFind"];
  delete global["%ceDefined"];

  function report(error) {
    setTimeout(function () { throw error; }, 0);
  }

  function hidden(o, name, value) {
    Object.defineProperty(o, name, { value: value, writable: true, configurable: true, enumerable: false });
  }

  // ---- custom elements ----

  var defs = new Map();        // name -> definition
  var byClass = new Map();     // constructor -> definition
  var states = new WeakMap();  // element -> its definition, once it's custom; false if it failed
  var waiting = new Map();     // name -> { promise, resolve } for whenDefined
  var upgrading = null;        // the element an upgrade's constructor is to get from HTMLElement
  var defining = false;

  var reserved = ["annotation-xml", "color-profile", "font-face", "font-face-src", "font-face-uri",
    "font-face-format", "font-face-name", "missing-glyph"];
  var validName = /^[a-z][\-.0-9_a-z·À-ÖØ-öø-ͽͿ-῿‌‍‿⁀⁰-↏Ⰰ-⿯、-퟿豈-﷏ﷰ-�]*-[\-.0-9_a-z·À-ÖØ-öø-ͽͿ-῿‌‍‿⁀⁰-↏Ⰰ-⿯、-퟿豈-﷏ﷰ-�]*$/;

  function isValidName(name) {
    return validName.test(name) && reserved.indexOf(name) < 0;
  }

  function domError(name, message) {
    var e = new Error(message);
    e.name = name;
    return e;
  }

  var htmlProto = global.HTMLElement.prototype;
  var ElementCtor = global.Element;

  function HTMLElement() {
    var nt = new.target;
    if (nt === undefined) throw new TypeError("Illegal constructor");
    var def = byClass.get(nt);
    if (!def) throw new TypeError("Illegal constructor");
    if (upgrading !== null) {
      var el = upgrading;
      upgrading = null;
      return el;
    }
    var made = ceNew(def.name);
    Object.setPrototypeOf(made, nt.prototype);
    states.set(made, def);
    ceDefined(made);
    return made;
  }
  HTMLElement.prototype = htmlProto;
  hidden(htmlProto, "constructor", HTMLElement);
  Object.setPrototypeOf(HTMLElement, ElementCtor);
  hidden(global, "HTMLElement", HTMLElement);

  function call(el, fn, args) {
    if (typeof fn !== "function") return;
    try { fn.apply(el, args); } catch (e) { report(e); }
  }

  function upgrade(el, def) {
    if (states.has(el)) return;
    var proto = def.ctor.prototype;
    upgrading = el;
    try {
      Object.setPrototypeOf(el, proto);
      var made = new def.ctor();
      if (made !== el) throw domError("TypeError", "A custom element's constructor must return the element");
    } catch (e) {
      upgrading = null;
      states.set(el, false);
      report(e);
      return;
    }
    upgrading = null;
    states.set(el, def);
    ceDefined(el);
    if (def.attributeChanged && def.observed.size) {
      var names = el.getAttributeNames();
      for (var i = 0; i < names.length; i++) {
        if (def.observed.has(names[i])) call(el, def.attributeChanged, [names[i], null, el.getAttribute(names[i]), null]);
      }
    }
    if (el.isConnected) call(el, def.connected, []);
  }

  function tryUpgrade(el) {
    if (states.has(el)) return;
    var def = defs.get(el.localName);
    if (def && el.namespaceURI === "http://www.w3.org/1999/xhtml") upgrade(el, def);
  }

  global["%ceReact"] = function (list) {
    for (var i = 0; i < list.length; i += 4) {
      var kind = list[i], el = list[i + 1];
      var def = states.get(el);
      if (kind === 0) {
        if (def) call(el, def.connected, []);
        else if (def === undefined) tryUpgrade(el);
      } else if (kind === 1) {
        if (def) call(el, def.disconnected, []);
      } else if (kind === 2) {
        var name = list[i + 2];
        if (def && def.attributeChanged && def.observed.has(name)) {
          call(el, def.attributeChanged, [name, list[i + 3], el.getAttribute(name), null]);
        }
      } else if (kind === 3) {
        if (def === undefined) tryUpgrade(el);
      }
    }
  };

  // document.createElement(name) for a defined name: the class, made with new
  global["%ceCreate"] = function (name) {
    var def = defs.get(name);
    if (!def) return undefined;
    try {
      var el = new def.ctor();
      if (!(el instanceof ElementCtor) || el.localName !== name) throw domError("NotSupportedError", "A custom element's constructor made the wrong thing");
      return el;
    } catch (e) {
      report(e);
      return undefined;
    }
  };

  function callbacks(ctor) {
    var proto = ctor.prototype;
    if (proto === null || (typeof proto !== "object" && typeof proto !== "function")) {
      throw new TypeError("A custom element's class needs a prototype");
    }
    function get(name) {
      var v = proto[name];
      if (v !== undefined && typeof v !== "function") throw new TypeError(name + " must be a function");
      return v;
    }
    var def = {
      connected: get("connectedCallback"),
      disconnected: get("disconnectedCallback"),
      adopted: get("adoptedCallback"),
      attributeChanged: get("attributeChangedCallback"),
      observed: new Set()
    };
    if (def.attributeChanged) {
      var names = ctor.observedAttributes;
      if (names !== undefined && names !== null) {
        for (var name of names) def.observed.add(String(name));
      }
    }
    return def;
  }

  class CustomElementRegistry {
    define(name, ctor, options) {
      name = String(name);
      if (typeof ctor !== "function") throw new TypeError("customElements.define needs a class");
      if (!isValidName(name)) throw domError("SyntaxError", "'" + name + "' is not a valid custom element name");
      if (defs.has(name)) throw domError("NotSupportedError", "'" + name + "' has already been defined");
      if (byClass.has(ctor)) throw domError("NotSupportedError", "This class has already been defined");
      if (defining) throw domError("NotSupportedError", "customElements.define was called while defining");
      if (options && options.extends !== undefined) return;    // customized built-ins aren't kept
      defining = true;
      var def;
      try { def = callbacks(ctor); } finally { defining = false; }
      def.name = name;
      def.ctor = ctor;
      defs.set(name, def);
      byClass.set(ctor, def);
      ceWatch(true);
      var found = ceFind(name);
      for (var i = 0; i < found.length; i++) upgrade(found[i], def);
      var w = waiting.get(name);
      if (w) {
        waiting.delete(name);
        w.resolve(ctor);
      }
    }
    get(name) {
      var def = defs.get(String(name));
      return def ? def.ctor : undefined;
    }
    getName(ctor) {
      var def = byClass.get(ctor);
      return def ? def.name : null;
    }
    whenDefined(name) {
      name = String(name);
      if (!isValidName(name)) return Promise.reject(domError("SyntaxError", "'" + name + "' is not a valid custom element name"));
      var def = defs.get(name);
      if (def) return Promise.resolve(def.ctor);
      var w = waiting.get(name);
      if (!w) {
        w = {};
        w.promise = new Promise(function (resolve) { w.resolve = resolve; });
        waiting.set(name, w);
      }
      return w.promise;
    }
    upgrade(root) {
      var walker = [root];
      while (walker.length) {
        var n = walker.pop();
        if (n.nodeType === 1) tryUpgrade(n);
        if (n.shadowRoot) walker.push(n.shadowRoot);
        for (var c = n.lastChild; c; c = c.previousSibling) walker.push(c);
      }
    }
  }
  var registry = new CustomElementRegistry();
  hidden(global, "CustomElementRegistry", CustomElementRegistry);
  Object.defineProperty(global, "customElements", { get: function () { return registry; }, configurable: true, enumerable: true });

  // ElementInternals: what a custom element can say for itself. Kept, but said to nothing.
  class CustomStateSet extends Set { }
  class ElementInternals {
    constructor(el) {
      hidden(this, "_el", el);
      hidden(this, "states", new CustomStateSet());
      this.role = null;
    }
    get shadowRoot() { return this._el.shadowRoot; }
    get form() { return null; }
    get labels() { return []; }
    get willValidate() { return false; }
    get validity() { return { valid: true }; }
    get validationMessage() { return ""; }
    setFormValue() { }
    setValidity() { }
    checkValidity() { return true; }
    reportValidity() { return true; }
  }
  hidden(global, "ElementInternals", ElementInternals);
  hidden(global, "CustomStateSet", CustomStateSet);
  var internals = new WeakMap();
  hidden(htmlProto, "attachInternals", function attachInternals() {
    if (internals.has(this)) throw domError("NotSupportedError", "attachInternals was called twice");
    var i = new ElementInternals(this);
    internals.set(this, i);
    return i;
  });

  // ---- messages: MessageEvent, MessageChannel, window.postMessage, structuredClone ----
  // A message is delivered as a task of its own (a timer of 0), as browsers deliver them. What's
  // sent is copied as structuredClone copies (objects, arrays, dates, maps, sets, regular
  // expressions, typed arrays and buffers, cycles kept).

  function clone(v, seen) {
    if (v === null || (typeof v !== "object" && typeof v !== "function")) return v;
    if (typeof v === "function") throw domError("DataCloneError", "A function cannot be cloned");
    if (seen.has(v)) return seen.get(v);
    var out, i;
    if (Array.isArray(v)) {
      out = [];
      seen.set(v, out);
      for (i = 0; i < v.length; i++) out[i] = clone(v[i], seen);
      return out;
    }
    if (v instanceof Date) { out = new Date(v.getTime()); seen.set(v, out); return out; }
    if (v instanceof RegExp) { out = new RegExp(v.source, v.flags); seen.set(v, out); return out; }
    if (v instanceof ArrayBuffer) { out = v.slice(0); seen.set(v, out); return out; }
    if (ArrayBuffer.isView(v)) { out = new v.constructor(v); seen.set(v, out); return out; }
    if (v instanceof Map) {
      out = new Map();
      seen.set(v, out);
      v.forEach(function (value, key) { out.set(clone(key, seen), clone(value, seen)); });
      return out;
    }
    if (v instanceof Set) {
      out = new Set();
      seen.set(v, out);
      v.forEach(function (value) { out.add(clone(value, seen)); });
      return out;
    }
    if (v instanceof Error) {
      out = new Error(v.message);
      out.name = v.name;
      seen.set(v, out);
      return out;
    }
    if (v instanceof global.Node) throw domError("DataCloneError", "A node cannot be cloned");
    out = {};
    seen.set(v, out);
    var keys = Object.keys(v);
    for (i = 0; i < keys.length; i++) out[keys[i]] = clone(v[keys[i]], seen);
    return out;
  }
  function structuredClone(v) { return clone(v, new Map()); }
  hidden(global, "structuredClone", structuredClone);

  class MessageEvent extends Event {
    constructor(type, init) {
      super(type, init);
      init = init || {};
      Object.defineProperty(this, "data", { value: init.data === undefined ? null : init.data, enumerable: true, configurable: true });
      Object.defineProperty(this, "origin", { value: init.origin === undefined ? "" : String(init.origin), enumerable: true, configurable: true });
      Object.defineProperty(this, "lastEventId", { value: init.lastEventId === undefined ? "" : String(init.lastEventId), enumerable: true, configurable: true });
      Object.defineProperty(this, "source", { value: init.source === undefined ? null : init.source, enumerable: true, configurable: true });
      Object.defineProperty(this, "ports", { value: init.ports === undefined ? [] : Array.from(init.ports), enumerable: true, configurable: true });
    }
  }
  hidden(global, "MessageEvent", MessageEvent);

  function deliver(target, data, origin, source) {
    setTimeout(function () {
      target.dispatchEvent(new MessageEvent("message", { data: data, origin: origin, source: source }));
    }, 0);
  }

  class MessagePort extends EventTarget {
    constructor() {
      super();
      hidden(this, "_other", null);
      this.onmessage = null;
      this.onmessageerror = null;
    }
    postMessage(message) {
      var other = this._other;
      if (other === null) return;
      deliver(other, structuredClone(message), "", null);
    }
    start() { }
    close() {
      if (this._other !== null) this._other._other = null;
      this._other = null;
    }
  }
  hidden(global, "MessagePort", MessagePort);

  class MessageChannel {
    constructor() {
      var a = new MessagePort(), b = new MessagePort();
      a._other = b;
      b._other = a;
      Object.defineProperty(this, "port1", { value: a, enumerable: true, configurable: true });
      Object.defineProperty(this, "port2", { value: b, enumerable: true, configurable: true });
    }
  }
  hidden(global, "MessageChannel", MessageChannel);

  hidden(global, "postMessage", function postMessage(message, targetOrigin) {
    var origin = "";
    try { origin = global.location.origin; } catch (e) { }
    deliver(global, structuredClone(message), origin, global);
  });

  // ---- Range and Selection ----
  // A range keeps its two boundary points and can make a fragment from markup; it has no box, and what
  // would take content out of the document or copy it isn't kept. Nothing is ever selected: the
  // browser has no selection of text.

  class AbstractRange {
    get startContainer() { return this._sc; }
    get startOffset() { return this._so; }
    get endContainer() { return this._ec; }
    get endOffset() { return this._eo; }
    get collapsed() { return this._sc === this._ec && this._so === this._eo; }
  }
  function nodeLength(n) {
    var t = n.nodeType;
    if (t === 3 || t === 4 || t === 7 || t === 8) return n.data.length;
    return n.childNodes.length;
  }
  function indexIn(n) {
    var i = 0;
    for (var c = n.previousSibling; c; c = c.previousSibling) i++;
    return i;
  }
  class Range extends AbstractRange {
    constructor() {
      super();
      var d = global.document;
      hidden(this, "_sc", d); hidden(this, "_so", 0);
      hidden(this, "_ec", d); hidden(this, "_eo", 0);
    }
    get commonAncestorContainer() {
      var a = this._sc;
      while (a && !a.contains(this._ec)) a = a.parentNode;
      return a;
    }
    setStart(n, o) {
      if (o > nodeLength(n)) throw domError("IndexSizeError", "The offset is past the node's end");
      this._sc = n; this._so = o;
      if (!this._ec || this._ec.getRootNode() !== n.getRootNode()) { this._ec = n; this._eo = o; }
    }
    setEnd(n, o) {
      if (o > nodeLength(n)) throw domError("IndexSizeError", "The offset is past the node's end");
      this._ec = n; this._eo = o;
      if (!this._sc || this._sc.getRootNode() !== n.getRootNode()) { this._sc = n; this._so = o; }
    }
    setStartBefore(n) { this.setStart(n.parentNode, indexIn(n)); }
    setStartAfter(n) { this.setStart(n.parentNode, indexIn(n) + 1); }
    setEndBefore(n) { this.setEnd(n.parentNode, indexIn(n)); }
    setEndAfter(n) { this.setEnd(n.parentNode, indexIn(n) + 1); }
    selectNode(n) { var p = n.parentNode, i = indexIn(n); this.setStart(p, i); this.setEnd(p, i + 1); }
    selectNodeContents(n) { this.setStart(n, 0); this.setEnd(n, nodeLength(n)); }
    collapse(toStart) {
      if (toStart) { this._ec = this._sc; this._eo = this._so; } else { this._sc = this._ec; this._so = this._eo; }
    }
    cloneRange() {
      var r = new Range();
      r._sc = this._sc; r._so = this._so; r._ec = this._ec; r._eo = this._eo;
      return r;
    }
    detach() { }
    createContextualFragment(markup) {
      var t = global.document.createElement("template");
      t.innerHTML = String(markup);
      return t.content;
    }
    getBoundingClientRect() { return { x: 0, y: 0, left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 }; }
    getClientRects() { return []; }
    toString() {
      if (this._sc === this._ec && this._sc.nodeType === 3) return this._sc.data.slice(this._so, this._eo);
      return "";
    }
    compareBoundaryPoints() { return 0; }
    isPointInRange() { return false; }
    intersectsNode() { return false; }
    deleteContents() { }
    insertNode(n) {
      var c = this._sc;
      if (c.nodeType === 3) c.parentNode.insertBefore(n, c.splitText ? c.splitText(this._so) : c.nextSibling);
      else c.insertBefore(n, c.childNodes[this._so] || null);
    }
  }
  Range.START_TO_START = 0; Range.START_TO_END = 1; Range.END_TO_END = 2; Range.END_TO_START = 3;
  class StaticRange extends AbstractRange {
    constructor(init) {
      super();
      hidden(this, "_sc", init.startContainer); hidden(this, "_so", init.startOffset);
      hidden(this, "_ec", init.endContainer); hidden(this, "_eo", init.endOffset);
    }
  }
  hidden(global, "AbstractRange", AbstractRange);
  hidden(global, "Range", Range);
  hidden(global, "StaticRange", StaticRange);
  hidden(global.Document.prototype, "createRange", function createRange() { return new Range(); });

  class Selection {
    get anchorNode() { return null; }
    get anchorOffset() { return 0; }
    get focusNode() { return null; }
    get focusOffset() { return 0; }
    get isCollapsed() { return true; }
    get rangeCount() { return 0; }
    get type() { return "None"; }
    getRangeAt() { throw domError("IndexSizeError", "Nothing is selected"); }
    addRange() { }
    removeRange() { }
    removeAllRanges() { }
    empty() { }
    collapse() { }
    collapseToStart() { }
    collapseToEnd() { }
    extend() { }
    selectAllChildren() { }
    setBaseAndExtent() { }
    containsNode() { return false; }
    deleteFromDocument() { }
    toString() { return ""; }
  }
  hidden(global, "Selection", Selection);
  var selection = new Selection();
  hidden(global, "getSelection", function getSelection() { return selection; });
  hidden(global.Document.prototype, "getSelection", function getSelection() { return selection; });

  // ---- document.implementation ----

  var newDocument = global["%newDocument"];
  delete global["%newDocument"];
  class DOMImplementation {
    createHTMLDocument(title) { return newDocument(title, true); }
    createDocument(ns, name) {
      var d = newDocument(undefined, false);
      if (name) d.appendChild(d.createElement(name));
      return d;
    }
    createDocumentType() { throw domError("NotSupportedError", "createDocumentType isn't kept"); }
    hasFeature() { return true; }
  }
  hidden(global, "DOMImplementation", DOMImplementation);
  var implementation = new DOMImplementation();
  Object.defineProperty(global.Document.prototype, "implementation", { get: function () { return implementation; }, configurable: true, enumerable: true });

  var parseDocument = global["%parseDocument"];
  delete global["%parseDocument"];
  class DOMParser {
    parseFromString(text, type) {
      type = String(type);
      if (["text/html", "text/xml", "application/xml", "application/xhtml+xml", "image/svg+xml"].indexOf(type) < 0) {
        throw new TypeError("DOMParser can't parse " + type);
      }
      return parseDocument(String(text));
    }
  }
  hidden(global, "DOMParser", DOMParser);

  // ---- NodeFilter, TreeWalker, NodeIterator ----

  var NodeFilter = {
    FILTER_ACCEPT: 1, FILTER_REJECT: 2, FILTER_SKIP: 3,
    SHOW_ALL: 0xFFFFFFFF, SHOW_ELEMENT: 0x1, SHOW_ATTRIBUTE: 0x2, SHOW_TEXT: 0x4,
    SHOW_CDATA_SECTION: 0x8, SHOW_ENTITY_REFERENCE: 0x10, SHOW_ENTITY: 0x20,
    SHOW_PROCESSING_INSTRUCTION: 0x40, SHOW_COMMENT: 0x80, SHOW_DOCUMENT: 0x100,
    SHOW_DOCUMENT_TYPE: 0x200, SHOW_DOCUMENT_FRAGMENT: 0x400, SHOW_NOTATION: 0x800
  };
  hidden(global, "NodeFilter", NodeFilter);

  function filter(w, node) {
    if (w._active) throw domError("InvalidStateError", "A NodeFilter ran the walker it's filtering for");
    if (!(w.whatToShow & (1 << (node.nodeType - 1)))) return 3;
    var f = w.filter;
    if (f === null) return 1;
    w._active = true;
    try {
      var r = typeof f === "function" ? f.call(undefined, node) : f.acceptNode(node);
      return +r;
    } finally {
      w._active = false;
    }
  }

  function start(o, root, whatToShow, f) {
    if (!(root instanceof global.Node)) throw new TypeError("A walker's root must be a Node");
    hidden(o, "_root", root);
    hidden(o, "_show", whatToShow === undefined ? 0xFFFFFFFF : whatToShow >>> 0);
    hidden(o, "_filter", f === undefined ? null : f);
    hidden(o, "_active", false);
  }

  class TreeWalker {
    get root() { return this._root; }
    get whatToShow() { return this._show; }
    get filter() { return this._filter; }
    get currentNode() { return this._current; }
    set currentNode(node) {
      if (!(node instanceof global.Node)) throw new TypeError("currentNode must be a Node");
      this._current = node;
    }
    parentNode() {
      var node = this._current;
      while (node !== null && node !== this._root) {
        node = node.parentNode;
        if (node !== null && filter(this, node) === 1) {
          this._current = node;
          return node;
        }
      }
      return null;
    }
    _children(first) {
      var node = first ? this._current.firstChild : this._current.lastChild;
      while (node !== null) {
        var r = filter(this, node);
        if (r === 1) {
          this._current = node;
          return node;
        }
        if (r === 3) {
          var child = first ? node.firstChild : node.lastChild;
          if (child !== null) {
            node = child;
            continue;
          }
        }
        while (node !== null) {
          var sibling = first ? node.nextSibling : node.previousSibling;
          if (sibling !== null) {
            node = sibling;
            break;
          }
          var parent = node.parentNode;
          if (parent === null || parent === this._root || parent === this._current) return null;
          node = parent;
        }
      }
      return null;
    }
    firstChild() { return this._children(true); }
    lastChild() { return this._children(false); }
    _siblings(next) {
      var node = this._current;
      if (node === this._root) return null;
      while (true) {
        var sibling = next ? node.nextSibling : node.previousSibling;
        while (sibling !== null) {
          node = sibling;
          var r = filter(this, node);
          if (r === 1) {
            this._current = node;
            return node;
          }
          sibling = next ? node.firstChild : node.lastChild;
          if (r === 2 || sibling === null) sibling = next ? node.nextSibling : node.previousSibling;
        }
        node = node.parentNode;
        if (node === null || node === this._root) return null;
        if (filter(this, node) === 1) return null;
      }
    }
    nextSibling() { return this._siblings(true); }
    previousSibling() { return this._siblings(false); }
    previousNode() {
      var node = this._current;
      while (node !== this._root) {
        var sibling = node.previousSibling;
        while (sibling !== null) {
          node = sibling;
          var r = filter(this, node);
          while (r !== 2 && node.lastChild !== null) {
            node = node.lastChild;
            r = filter(this, node);
          }
          if (r === 1) {
            this._current = node;
            return node;
          }
          sibling = node.previousSibling;
        }
        if (node === this._root || node.parentNode === null) return null;
        node = node.parentNode;
        if (filter(this, node) === 1) {
          this._current = node;
          return node;
        }
      }
      return null;
    }
    nextNode() {
      var node = this._current;
      var r = 1;
      while (true) {
        while (r !== 2 && node.firstChild !== null) {
          node = node.firstChild;
          r = filter(this, node);
          if (r === 1) {
            this._current = node;
            return node;
          }
        }
        var sibling = null;
        var temp = node;
        while (temp !== null) {
          if (temp === this._root) return null;
          sibling = temp.nextSibling;
          if (sibling !== null) {
            node = sibling;
            break;
          }
          temp = temp.parentNode;
        }
        if (sibling === null) return null;
        r = filter(this, node);
        if (r === 1) {
          this._current = node;
          return node;
        }
      }
    }
  }
  hidden(global, "TreeWalker", TreeWalker);

  function following(node, root) {
    if (node.firstChild !== null) return node.firstChild;
    while (node !== null && node !== root) {
      if (node.nextSibling !== null) return node.nextSibling;
      node = node.parentNode;
    }
    return null;
  }

  function preceding(node, root) {
    if (node === root) return null;
    var p = node.previousSibling;
    if (p !== null) {
      while (p.lastChild !== null) p = p.lastChild;
      return p;
    }
    return node.parentNode;
  }

  class NodeIterator {
    get root() { return this._root; }
    get whatToShow() { return this._show; }
    get filter() { return this._filter; }
    get referenceNode() { return this._ref; }
    get pointerBeforeReferenceNode() { return this._before; }
    _traverse(next) {
      var node = this._ref, before = this._before;
      while (true) {
        if (next) {
          if (!before) {
            node = following(node, this._root);
            if (node === null) return null;
          } else before = false;
        } else {
          if (before) {
            node = preceding(node, this._root);
            if (node === null) return null;
          } else before = true;
        }
        if (filter(this, node) === 1) break;
      }
      this._ref = node;
      this._before = before;
      return node;
    }
    nextNode() { return this._traverse(true); }
    previousNode() { return this._traverse(false); }
    detach() { }
  }
  hidden(global, "NodeIterator", NodeIterator);

  var docProto = global.Document.prototype;
  hidden(docProto, "createTreeWalker", function createTreeWalker(root, whatToShow, f) {
    var w = Object.create(TreeWalker.prototype);
    start(w, root, whatToShow, f);
    hidden(w, "_current", root);
    return w;
  });
  hidden(docProto, "createNodeIterator", function createNodeIterator(root, whatToShow, f) {
    var it = Object.create(NodeIterator.prototype);
    start(it, root, whatToShow, f);
    hidden(it, "_ref", root);
    hidden(it, "_before", true);
    return it;
  });
})(this);
