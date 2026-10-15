/* Visual strategy editor — vanilla JS, no build step. */
(function () {
  "use strict";

  var NODE_W = 168;
  var PORT_Y = 22; // port centre offset from node top

  var state = {
    catalog: [],
    types: {},
    nodes: [],
    edges: [],
    seq: 0,
    selectedNode: null,
    selectedEdge: null,
    pendingFrom: null,
    strategyId: null
  };

  var canvas = null;
  var edgesSvg = null;
  var paletteEl = null;
  var inspectorEl = null;
  var statusEl = null;

  // ── helpers ─────────────────────────────────────────────
  function apiKey() {
    var el = document.getElementById("api-key");
    return el ? el.value.trim() : "";
  }

  function headers() {
    var h = { "Content-Type": "application/json" };
    var key = apiKey();
    if (key) h["X-API-Key"] = key;
    return h;
  }

  function esc(value) {
    if (value == null) return "";
    return String(value).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function setStatus(message, kind) {
    statusEl.textContent = message;
    statusEl.className = kind || "";
  }

  function nodeById(id) {
    for (var i = 0; i < state.nodes.length; i++) {
      if (state.nodes[i].id === id) return state.nodes[i];
    }
    return null;
  }

  // ── catalog & palette ───────────────────────────────────
  async function loadCatalog() {
    try {
      var res = await fetch("/strategies/node-types", { headers: headers() });
      var body = await res.json();
      if (!res.ok) throw new Error(body && body.error ? body.error.message : res.statusText);
      state.catalog = body.data || [];
      state.catalog.forEach(function (t) { state.types[t.type] = t; });
      renderPalette();
    } catch (err) {
      setStatus("Failed to load node types: " + err.message, "err");
    }
  }

  function renderPalette() {
    var groups = {};
    state.catalog.forEach(function (t) {
      (groups[t.category] = groups[t.category] || []).push(t);
    });
    paletteEl.innerHTML = "";
    Object.keys(groups).sort().forEach(function (cat) {
      var wrap = document.createElement("div");
      wrap.className = "palette-group";
      var title = document.createElement("h2");
      title.textContent = cat.replace(/_/g, " ");
      wrap.appendChild(title);
      groups[cat].forEach(function (t) {
        var btn = document.createElement("button");
        btn.className = "palette-item";
        btn.textContent = t.label;
        btn.title = t.description || "";
        btn.addEventListener("click", function () { addNode(t.type); });
        wrap.appendChild(btn);
      });
      paletteEl.appendChild(wrap);
    });
  }

  // ── nodes ───────────────────────────────────────────────
  function defaultParams(type) {
    var meta = state.types[type];
    var params = {};
    if (meta) {
      meta.params.forEach(function (p) { params[p.name] = p.default; });
    }
    return params;
  }

  function addNode(type, position) {
    var id = "node" + (++state.seq);
    var pos = position || { x: 40 + (state.nodes.length % 4) * 200, y: 40 + Math.floor(state.nodes.length / 4) * 140 };
    state.nodes.push({
      id: id,
      type: type,
      params: defaultParams(type),
      x: pos.x,
      y: pos.y
    });
    selectNode(id);
    render();
  }

  function deleteNode(id) {
    state.nodes = state.nodes.filter(function (n) { return n.id !== id; });
    state.edges = state.edges.filter(function (e) {
      return e.from !== id && e.to !== id;
    });
    if (state.selectedNode === id) state.selectedNode = null;
    render();
  }

  function render() {
    // remove existing node elements
    Array.prototype.slice.call(canvas.querySelectorAll(".node")).forEach(function (el) {
      el.remove();
    });

    state.nodes.forEach(function (node) {
      var meta = state.types[node.type] || { label: node.type, category: "" };
      var el = document.createElement("div");
      el.className = "node" + (state.selectedNode === node.id ? " selected" : "");
      el.style.left = node.x + "px";
      el.style.top = node.y + "px";
      el.dataset.id = node.id;

      var head = document.createElement("div");
      head.className = "node-head";
      head.innerHTML =
        '<div class="cat">' + esc(meta.category) + "</div>" +
        '<div class="label">' + esc(meta.label) + "</div>";
      head.addEventListener("mousedown", function (ev) { startDrag(ev, node); });
      el.appendChild(head);

      var body = document.createElement("div");
      body.className = "node-body";
      body.textContent = node.id + " · " + node.type;
      el.appendChild(body);

      var inPort = document.createElement("div");
      inPort.className = "port in";
      inPort.title = "input";
      inPort.addEventListener("mousedown", function (ev) {
        ev.stopPropagation();
        connectTo(node.id);
      });
      el.appendChild(inPort);

      var outPort = document.createElement("div");
      outPort.className = "port out" + (state.pendingFrom === node.id ? " pending" : "");
      outPort.title = "output (click, then click a target node)";
      outPort.addEventListener("mousedown", function (ev) {
        ev.stopPropagation();
        state.pendingFrom = node.id;
        setStatus("Connecting from " + node.id + " — click a target node's input port.", "");
        render();
      });
      el.appendChild(outPort);

      el.addEventListener("mousedown", function () {
        selectNode(node.id);
      });

      canvas.appendChild(el);
    });

    renderEdges();
  }

  function selectNode(id) {
    state.selectedNode = id;
    state.selectedEdge = null;
    Array.prototype.slice.call(canvas.querySelectorAll(".node")).forEach(function (el) {
      el.classList.toggle("selected", el.dataset.id === id);
    });
    renderInspector();
  }

  function startDrag(ev, node) {
    ev.preventDefault();
    var startX = ev.clientX;
    var startY = ev.clientY;
    var originX = node.x;
    var originY = node.y;

    function onMove(moveEv) {
      node.x = Math.max(0, originX + (moveEv.clientX - startX));
      node.y = Math.max(0, originY + (moveEv.clientY - startY));
      var el = canvas.querySelector('.node[data-id="' + node.id + '"]');
      if (el) {
        el.style.left = node.x + "px";
        el.style.top = node.y + "px";
      }
      renderEdges();
    }

    function onUp() {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    }

    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }

  // ── edges ───────────────────────────────────────────────
  function addEdge(from, to) {
    if (from === to) {
      setStatus("Cannot connect a node to itself.", "err");
      return;
    }
    var exists = state.edges.some(function (e) {
      return e.from === from && e.to === to;
    });
    if (exists) {
      setStatus("Connection already exists.", "err");
      return;
    }
    if (createsCycle(from, to)) {
      setStatus("Rejected: connection would create a cycle.", "err");
      return;
    }
    state.edges.push({ from: from, to: to });
    setStatus("Connected " + from + " → " + to + ".", "ok");
    render();
  }

  function connectTo(targetId) {
    if (!state.pendingFrom) {
      setStatus("Click a node's output port first.", "");
      return;
    }
    var from = state.pendingFrom;
    state.pendingFrom = null;
    addEdge(from, targetId);
  }

  function createsCycle(from, to) {
    // adding from -> to creates a cycle if `from` is reachable from `to`
    var stack = [to];
    var seen = {};
    while (stack.length) {
      var current = stack.pop();
      if (current === from) return true;
      if (seen[current]) continue;
      seen[current] = true;
      state.edges.forEach(function (e) {
        if (e.from === current) stack.push(e.to);
      });
    }
    return false;
  }

  function renderEdges() {
    edgesSvg.innerHTML = "";
    state.edges.forEach(function (edge, index) {
      var a = nodeById(edge.from);
      var b = nodeById(edge.to);
      if (!a || !b) return;
      var x1 = a.x + NODE_W;
      var y1 = a.y + PORT_Y;
      var x2 = b.x;
      var y2 = b.y + PORT_Y;

      var hit = document.createElementNS("http://www.w3.org/2000/svg", "line");
      hit.setAttribute("x1", x1); hit.setAttribute("y1", y1);
      hit.setAttribute("x2", x2); hit.setAttribute("y2", y2);
      hit.setAttribute("class", "hit");
      hit.style.pointerEvents = "stroke";
      hit.addEventListener("click", function (ev) {
        ev.stopPropagation();
        state.selectedEdge = index;
        state.selectedNode = null;
        renderEdges();
        renderInspector();
      });
      edgesSvg.appendChild(hit);

      var wire = document.createElementNS("http://www.w3.org/2000/svg", "line");
      wire.setAttribute("x1", x1); wire.setAttribute("y1", y1);
      wire.setAttribute("x2", x2); wire.setAttribute("y2", y2);
      wire.setAttribute("class", "wire" + (state.selectedEdge === index ? " selected" : ""));
      edgesSvg.appendChild(wire);
    });
  }

  function deleteSelectedEdge() {
    if (state.selectedEdge == null) return;
    state.edges.splice(state.selectedEdge, 1);
    state.selectedEdge = null;
    render();
  }

  // ── inspector ───────────────────────────────────────────
  function renderInspector() {
    inspectorEl.innerHTML = "";

    if (state.selectedEdge != null) {
      var edge = state.edges[state.selectedEdge];
      if (edge) {
        var p = document.createElement("p");
        p.className = "io-list";
        p.textContent = "Connection: " + edge.from + " → " + edge.to;
        inspectorEl.appendChild(p);
        inspectorEl.appendChild(deleteButton("Delete connection", deleteSelectedEdge));
      }
      return;
    }

    if (!state.selectedNode) {
      var hint = document.createElement("p");
      hint.className = "io-list";
      hint.textContent = "Select a node to edit its parameters.";
      inspectorEl.appendChild(hint);
      return;
    }

    var node = nodeById(state.selectedNode);
    if (!node) return;
    var meta = state.types[node.type] || { params: [], inputs: [], outputs: [] };

    var head = document.createElement("p");
    head.innerHTML = "<strong>" + esc(node.id) + "</strong> · " + esc(node.type);
    inspectorEl.appendChild(head);

    meta.params.forEach(function (spec) {
      inspectorEl.appendChild(paramField(node, spec));
    });

    var inTitle = document.createElement("h2");
    inTitle.textContent = "Inputs";
    inspectorEl.appendChild(inTitle);
    var inList = document.createElement("p");
    inList.className = "io-list";
    inList.innerHTML = (meta.inputs || []).map(function (i) {
      return "<span>" + esc(i.name) + "</span>";
    }).join("") || "—";
    inspectorEl.appendChild(inList);

    var outTitle = document.createElement("h2");
    outTitle.textContent = "Outputs";
    inspectorEl.appendChild(outTitle);
    var outList = document.createElement("p");
    outList.className = "io-list";
    outList.innerHTML = (meta.outputs || []).map(function (o) {
      return "<span>" + esc(o.name) + "</span>";
    }).join("") || "—";
    inspectorEl.appendChild(outList);

    inspectorEl.appendChild(deleteButton("Delete node", function () {
      deleteNode(node.id);
    }));
  }

  function deleteButton(label, handler) {
    var btn = document.createElement("button");
    btn.className = "danger";
    btn.textContent = label;
    btn.style.marginTop = "12px";
    btn.addEventListener("click", handler);
    return btn;
  }

  function paramField(node, spec) {
    var wrap = document.createElement("div");
    wrap.className = "inspector-field";
    var label = document.createElement("label");
    label.textContent = spec.name;
    wrap.appendChild(label);

    var value = node.params[spec.name];
    var input;

    if (spec.options) {
      input = document.createElement("select");
      spec.options.forEach(function (opt) {
        var o = document.createElement("option");
        o.value = opt;
        o.textContent = opt;
        if (opt === value) o.selected = true;
        input.appendChild(o);
      });
      input.addEventListener("change", function () {
        node.params[spec.name] = input.value;
      });
    } else if (spec.type === "bool") {
      input = document.createElement("input");
      input.type = "checkbox";
      input.checked = !!value;
      input.addEventListener("change", function () {
        node.params[spec.name] = input.checked;
      });
    } else if (spec.type === "int" || spec.type === "float") {
      input = document.createElement("input");
      input.type = "number";
      input.step = spec.type === "int" ? "1" : "any";
      input.value = value == null ? "" : value;
      input.addEventListener("change", function () {
        node.params[spec.name] = input.value === "" ? null : Number(input.value);
      });
    } else if (spec.type === "list" || spec.type === "dict") {
      input = document.createElement("textarea");
      input.value = value == null ? "" : JSON.stringify(value);
      input.addEventListener("change", function () {
        try {
          node.params[spec.name] = input.value.trim() === "" ? null : JSON.parse(input.value);
          setStatus("Updated " + spec.name + ".", "ok");
        } catch (err) {
          setStatus("Invalid JSON for " + spec.name + ".", "err");
        }
      });
    } else {
      input = document.createElement("input");
      input.type = "text";
      input.value = value == null ? "" : value;
      input.addEventListener("change", function () {
        node.params[spec.name] = input.value;
      });
    }

    wrap.appendChild(input);
    return wrap;
  }

  // ── validation & persistence ────────────────────────────
  function validate() {
    var errors = [];
    if (state.nodes.length === 0) {
      errors.push("Strategy has no nodes.");
    }
    state.edges.forEach(function (e) {
      if (!nodeById(e.from) || !nodeById(e.to)) {
        errors.push("Connection references a missing node: " + e.from + " → " + e.to);
      }
    });
    state.nodes.forEach(function (n) {
      if (!state.types[n.type]) {
        errors.push("Unknown node type: " + n.type);
      }
    });
    if (errors.length === 0 && hasCycle()) {
      errors.push("Graph contains a cycle.");
    }
    return errors;
  }

  function hasCycle() {
    var visiting = {};
    var visited = {};
    var result = false;
    function visit(id) {
      if (result) return;
      if (visiting[id]) { result = true; return; }
      if (visited[id]) return;
      visiting[id] = true;
      state.edges.forEach(function (e) {
        if (e.from === id) visit(e.to);
      });
      visiting[id] = false;
      visited[id] = true;
    }
    state.nodes.forEach(function (n) { visit(n.id); });
    return result;
  }

  async function save() {
    var errors = validate();
    if (errors.length) {
      setStatus("Validation failed: " + errors.join(" "), "err");
      return;
    }
    var payload = {
      name: document.getElementById("strategy-name").value || "Untitled Strategy",
      description: "Created with the visual strategy editor",
      nodes: state.nodes.map(function (n) {
        return {
          id: n.id,
          type: n.type,
          params: n.params,
          position: { x: n.x, y: n.y }
        };
      }),
      connections: state.edges.map(function (e) {
        return { from: e.from, to: e.to };
      })
    };

    try {
      var res = await fetch("/strategies", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify(payload)
      });
      var body = await res.json();
      if (!res.ok) {
        throw new Error(body && body.error ? body.error.message : res.statusText);
      }
      state.strategyId = body.data.id;
      document.getElementById("strategy-id").textContent = "Saved: " + state.strategyId;
      setStatus("Strategy saved.", "ok");
      refreshLoadList();
    } catch (err) {
      setStatus("Save failed: " + err.message, "err");
    }
  }

  async function refreshLoadList() {
    var select = document.getElementById("load-select");
    try {
      var res = await fetch("/strategies", { headers: headers() });
      var body = await res.json();
      var list = (body.data || []);
      select.innerHTML = '<option value="">Load strategy…</option>';
      list.forEach(function (s) {
        var opt = document.createElement("option");
        opt.value = s.id;
        opt.textContent = s.name + " (" + s.status + ")";
        select.appendChild(opt);
      });
    } catch (err) {
      setStatus("Failed to list strategies: " + err.message, "err");
    }
  }

  async function loadStrategy(id) {
    if (!id) return;
    try {
      var res = await fetch("/strategies/" + encodeURIComponent(id) + "/flowchart", { headers: headers() });
      var body = await res.json();
      if (!res.ok) throw new Error(body && body.error ? body.error.message : res.statusText);
      var data = body.data;
      state.nodes = (data.nodes || []).map(function (n) {
        return {
          id: n.id,
          type: n.type,
          params: n.params || {},
          x: n.position && typeof n.position.x === "number" ? n.position.x : 40,
          y: n.position && typeof n.position.y === "number" ? n.position.y : 40
        };
      });
      state.edges = (data.connections || []).map(function (c) {
        return { from: c.from, to: c.to };
      });
      state.seq = state.nodes.length;
      state.selectedNode = null;
      state.selectedEdge = null;
      state.pendingFrom = null;
      state.strategyId = id;
      document.getElementById("strategy-name").value = data.strategy_name || "Loaded Strategy";
      document.getElementById("strategy-id").textContent = "Loaded: " + id;
      render();
      setStatus("Loaded strategy.", "ok");
    } catch (err) {
      setStatus("Load failed: " + err.message, "err");
    }
  }

  // ── wiring ──────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", function () {
    canvas = document.getElementById("canvas");
    edgesSvg = document.getElementById("edges");
    paletteEl = document.getElementById("palette");
    inspectorEl = document.getElementById("inspector");
    statusEl = document.getElementById("status");

    document.getElementById("btn-save").addEventListener("click", save);
    document.getElementById("btn-validate").addEventListener("click", function () {
      var errors = validate();
      setStatus(
        errors.length ? "Invalid: " + errors.join(" ") : "Valid strategy graph.",
        errors.length ? "err" : "ok"
      );
    });
    document.getElementById("load-select").addEventListener("change", function (ev) {
      loadStrategy(ev.target.value);
    });

    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Delete" || ev.key === "Backspace") {
        var tag = (ev.target.tagName || "").toLowerCase();
        if (tag === "input" || tag === "textarea" || tag === "select") return;
        if (state.selectedNode) { deleteNode(state.selectedNode); ev.preventDefault(); }
        else if (state.selectedEdge != null) { deleteSelectedEdge(); ev.preventDefault(); }
      }
    });

    canvas.addEventListener("mousedown", function (ev) {
      if (ev.target === canvas) {
        state.selectedNode = null;
        state.selectedEdge = null;
        state.pendingFrom = null;
        render();
        renderInspector();
      }
    });

    loadCatalog();
    refreshLoadList();
  });
})();
