/* Parts cards, totals, build steps and remembered checkmarks. Data lives in the JSON blocks in index.html. */
(function () {
  "use strict";
  var STORE = "noise-logger-guide-v1";
  var buy = JSON.parse(document.getElementById("buy-data").textContent);
  var steps = JSON.parse(document.getElementById("steps-data").textContent);

  function load() { try { return JSON.parse(localStorage.getItem(STORE)) || {}; } catch (e) { return {}; } }
  function save(st) { try { localStorage.setItem(STORE, JSON.stringify(st)); } catch (e) { /* private mode: ticks just aren't remembered */ } }
  var state = load();
  state.own = state.own || {}; state.done = state.done || {};

  function money(v) { return "$" + v.toFixed(2); }
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }

  // ---------- parts cards (UI fixes 1 and 10) ----------
  var cards = document.getElementById("cards");
  buy.lines.forEach(function (p) {
    var c = el("article", "part");
    c.appendChild(el("h3", null, p.item));
    c.appendChild(el("div", "soft small", "Model #: <b>" + p.model + "</b>"));
    c.appendChild(el("div", "price", money(p.price)));
    c.appendChild(el("div", null, '<a href="' + p.url + '" target="_blank" rel="noopener">Buy at ' + p.shop + ' ↗</a>'));
    c.appendChild(el("div", "small", p.stock + ' · checked ' + buy.checkedOn + ' <span class="badge' + (p.status === "VERIFIED" ? "" : " unv") + '">' + p.status + "</span>"));
    c.appendChild(el("div", "small soft", p.why));
    var lab = el("label", "own");
    var box = document.createElement("input"); box.type = "checkbox"; box.checked = !!state.own[p.id];
    box.addEventListener("change", function () { state.own[p.id] = box.checked; save(state); totals(); });
    lab.appendChild(box); lab.appendChild(document.createTextNode("I already own one"));
    c.appendChild(lab);
    cards.appendChild(c);
  });

  function totals() {
    var all = 0, need = 0;
    buy.lines.forEach(function (p) { all += p.price; if (!state.own[p.id]) need += p.price; });
    var gAll = Math.round(all * (1 + buy.gst) * 100) / 100, gNeed = Math.round(need * (1 + buy.gst) * 100) / 100;
    document.getElementById("totals").innerHTML =
      '<div class="tile"><b>' + money(gAll) + '</b>all parts, with GST</div>' +
      '<div class="tile"><b>' + money(gNeed) + '</b>still to buy, with GST</div>' +
      '<div class="tile"><b>$500</b>hard budget cap</div>';
    document.getElementById("chip-cost").textContent = money(gAll) + " with GST";
    document.getElementById("tc-cost").textContent = money(gAll) + " with GST, before PiShop shipping";
    document.body.dataset.total = gAll.toFixed(2);
  }
  totals();

  // ---------- build steps (UI fixes 7 and 8) ----------
  var wrap = document.getElementById("steps");
  steps.forEach(function (s) {
    var art = el("article", "step"); art.id = "step-" + s.n;
    var head = el("header");
    head.appendChild(el("div", "num", String(s.n)));
    var hb = el("div");
    hb.appendChild(el("h3", null, s.title));
    hb.appendChild(el("div", "small", "⏱ " + s.time + ' · <span class="badge ' + (s.tested ? "tested" : "untested") + '">' + (s.tested ? "Tested" : "Not tested yet") + "</span>"));
    head.appendChild(hb); art.appendChild(head);
    var body = el("div", "body");
    var ol = el("ol"); s.actions.forEach(function (a) { ol.appendChild(el("li", null, a)); }); body.appendChild(ol);
    if (s.warn) body.appendChild(el("div", "warn", "⚠ " + s.warn));
    body.appendChild(el("div", "check", "<b>✓ Check it worked:</b> " + s.check));
    if (s.proof) body.appendChild(el("div", "small soft", "Proof: " + s.proof));
    if (s.focus && s.focus.length) {
      var b = el("button", "btn", "Show in 3D"); b.type = "button";
      b.addEventListener("click", function () {
        window.dispatchEvent(new CustomEvent("guide-focus", { detail: { nodes: s.focus, title: "Step " + s.n + ": " + s.title } }));
        document.getElementById("model").scrollIntoView({ behavior: "smooth" });
      });
      body.appendChild(b);
    }
    var lab = el("label", "done"); var box = document.createElement("input"); box.type = "checkbox"; box.checked = !!state.done[s.n];
    box.addEventListener("change", function () { state.done[s.n] = box.checked; save(state); progress(); });
    lab.appendChild(box); lab.appendChild(document.createTextNode("This step is done")); body.appendChild(lab);
    art.appendChild(body); wrap.appendChild(art);
  });

  function progress() {
    var n = steps.filter(function (s) { return state.done[s.n]; }).length;
    document.getElementById("progress-text").textContent = n + " of " + steps.length + " steps done";
    document.getElementById("progress-bar").style.width = (100 * n / steps.length) + "%";
  }
  progress();

  // ---------- print file sizes straight from the generator's report ----------
  fetch("models/numbers.json").then(function (r) { return r.json(); }).then(function (num) {
    Object.keys(num.parts).forEach(function (k) {
      var c = document.getElementById("sz-" + k);
      if (c) c.textContent = num.parts[k].size_mm.map(function (v) { return v.toFixed(1); }).join(" × ");
    });
  }).catch(function () { /* sizes stay blank if the file can't load */ });
})();
