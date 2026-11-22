/* Option 6 preview: the drone guide's layout (Home · Build · 3D · Buy · Print) with the noise logger's content.
   Parts, steps and 3D labels are read from index.html. */
(function () {
  "use strict";
  var STORE = "noise-logger-guide-v1"; // same storage as the live guide: ticks carry over
  function load() { try { return JSON.parse(localStorage.getItem(STORE)) || {}; } catch (e) { return {}; } }
  function save(st) { try { localStorage.setItem(STORE, JSON.stringify(st)); } catch (e) { /* private mode */ } }
  var state = load(); state.own = state.own || {}; state.done = state.done || {}; state.open = state.open || null; state.printed = state.printed || {};
  function el(tag, cls, html) { var e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  function money(v) { return "$" + v.toFixed(2); }

  function boot() {
    start(JSON.parse(document.getElementById("buy-data").textContent), JSON.parse(document.getElementById("steps-data").textContent));
    var m = document.createElement("script"); m.type = "module"; m.src = "js/viewer.js"; document.body.appendChild(m);
  }
  boot();

  function start(buy, steps) {
    // ---------- tabs (side bar and bottom bar stay in step) ----------
    function show(tab) {
      document.querySelectorAll('[role="tab"]').forEach(function (b) { b.setAttribute("aria-selected", b.dataset.tab === tab ? "true" : "false"); });
      document.querySelectorAll('[role="tabpanel"]').forEach(function (p) { p.hidden = p.id !== "p-" + tab; });
      try { history.replaceState(null, "", "#" + tab); } catch (e) { /* file:// */ }
      window.scrollTo(0, 0);
    }
    document.querySelectorAll('[role="tab"]').forEach(function (b) { b.addEventListener("click", function () { show(b.dataset.tab); }); });
    document.querySelectorAll("[data-go]").forEach(function (b) { b.addEventListener("click", function () { show(b.dataset.go); }); });

    // ---------- Buy ----------
    var NAMES = {}; buy.lines.forEach(function (p) { NAMES[p.id] = p.item; });
    function bill() {
      var all = 0, got = 0; buy.lines.forEach(function (p) { all += p.price; if (state.own[p.id]) got += p.price; });
      var g = 1 + buy.gst;
      document.getElementById("bill").innerHTML =
        '<div class="tile"><b>' + money(all * g) + '</b>all parts, with GST (PiShop and Solen shipping are extra)</div><div class="tile"><b>' + money(got * g) +
        '</b>bought so far</div><div class="tile"><b>' + money((all - got) * g) + "</b>still to buy</div>";
      document.getElementById("t-cost").textContent = money(all * g);
      dashboard();
    }
    var cards = document.getElementById("cards");
    buy.lines.forEach(function (p) {
      var c = el("article", "part");
      c.appendChild(el("b", null, p.item));
      c.appendChild(el("span", "small soft", "Model #: <b>" + p.model + "</b>"));
      c.appendChild(el("span", "price", money(p.price)));
      c.appendChild(el("a", null, "Buy at " + p.shop + " ↗")); c.lastChild.href = p.url; c.lastChild.target = "_blank"; c.lastChild.rel = "noopener";
      c.appendChild(el("span", "small", p.stock + " · checked " + buy.checkedOn + ' <span class="badge">' + p.status + "</span>"));
      c.appendChild(el("span", "small soft", p.why));
      var lab = el("label", "own"), box = document.createElement("input"); box.type = "checkbox"; box.checked = !!state.own[p.id];
      box.addEventListener("change", function () { state.own[p.id] = box.checked; save(state); bill(); });
      lab.appendChild(box); lab.appendChild(document.createTextNode("I've bought this")); c.appendChild(lab);
      cards.appendChild(c);
    });
    bill();

    // ---------- Build: step cards in the drone guide's format ----------
    var wrap = document.getElementById("steps");
    function need(s) {
      var list = !s.parts || !s.parts.length ? [] : s.parts[0] === "all" ? ["All the parts from the Buy list"] : s.parts.map(function (id) { return NAMES[id] || id; });
      list = list.concat(s.tools || []);
      return list.length ? list.join(" · ") : "Nothing new: just the laptop.";
    }
    steps.forEach(function (s) {
      var art = el("article", "step"); art.id = "step-" + s.n;
      var head = el("header");
      head.innerHTML = '<div class="num" id="num-' + s.n + '">' + s.n + '</div><div class="t"><b>' + s.title + "</b><span>⏱ " + s.time +
        ' · <span class="badge ' + (s.tested ? "" : "untested") + '">' + (s.tested ? "Tested" : "Not tested yet") + '</span></span></div><span class="chev">⌄</span>';
      head.addEventListener("click", function () { art.classList.toggle("open"); state.open = art.classList.contains("open") ? s.n : null; save(state); });
      art.appendChild(head);
      var body = el("div", "body");
      var still = el("div", "still", '<img src="images/steps/step-' + s.n + '.jpg" alt="3D view for step ' + s.n + '" loading="lazy"><span class="play">▶</span>');
      var watch = el("button", "watch", "Watch it in 3D"); watch.type = "button";
      function go3d() {
        show("model");
        var tries = 0, t = setInterval(function () {
          if (document.body.dataset.modelLoaded === "yes" || ++tries > 50) {
            clearInterval(t);
            window.dispatchEvent(new CustomEvent("guide-focus", { detail: { nodes: s.focus || [], title: "Step " + s.n + ": " + s.title } }));
          }
        }, 100);
      }
      still.addEventListener("click", go3d); watch.addEventListener("click", go3d);
      body.appendChild(still); body.appendChild(watch);
      body.appendChild(el("details", null, "<summary>You will need</summary><div>" + need(s) + "</div>"));
      body.appendChild(el("details", null, "<summary>Show the written steps</summary><div><ol>" +
        s.actions.map(function (a) { return "<li>" + a + "</li>"; }).join("") + "</ol></div>"));
      if (s.warn) body.appendChild(el("div", "note safety", "<b>⚠ Safety:</b> " + s.warn));
      body.appendChild(el("details", null, "<summary>✓ Before you go on</summary><div>" + s.check + (s.proof ? '<p class="small soft">Proof: ' + s.proof + "</p>" : "") + "</div>"));
      var lab = el("label", "done"), box = document.createElement("input"); box.type = "checkbox"; box.checked = !!state.done[s.n];
      box.addEventListener("change", function () { state.done[s.n] = box.checked; save(state); progress(); dashboard(); if (box.checked) openNext(); });
      lab.appendChild(box); lab.appendChild(document.createTextNode("This step is done")); body.appendChild(lab);
      art.appendChild(body); wrap.appendChild(art);
    });
    function nextStep() { for (var i = 0; i < steps.length; i++) if (!state.done[steps[i].n] && steps[i].n !== 0) return steps[i]; return null; }
    function openNext() { var n = nextStep(); document.querySelectorAll(".step").forEach(function (a) { a.classList.toggle("open", !!n && a.id === "step-" + n.n); }); }
    function progress() {
      var done = steps.filter(function (s) { return state.done[s.n]; }).length;
      document.getElementById("progress-text").textContent = done + " of " + steps.length + " steps done";
      document.getElementById("progress-bar").style.width = (100 * done / steps.length) + "%";
      steps.forEach(function (s) { var n = document.getElementById("num-" + s.n); n.textContent = state.done[s.n] ? "✓" : s.n; n.classList.toggle("ok", !!state.done[s.n]); });
      var nx = nextStep();
      document.getElementById("next-title").textContent = nx ? "Next: Step " + nx.n + " · " + nx.title : "All steps done — well done!";
      document.getElementById("next-go").textContent = nx ? "Go to Step " + nx.n : "See the build";
    }
    document.getElementById("next-go").addEventListener("click", function () {
      var nx = nextStep(); show("build"); openNext();
      if (nx) setTimeout(function () { document.getElementById("step-" + nx.n).scrollIntoView({ behavior: "smooth" }); }, 50);
    });
    var lo = document.getElementById("leftoff"); lo.value = state.leftoff || "";
    lo.addEventListener("input", function () { state.leftoff = lo.value; save(state); });
    progress(); openNext();

    // ---------- Home dashboard (Option 4's progress cards) ----------
    function dashboard() {
      var g = 1 + buy.gst, left = 0;
      var bought = buy.lines.filter(function (p) { if (!state.own[p.id]) left += p.price; return state.own[p.id]; }).length;
      var done = steps.filter(function (s) { return state.done[s.n]; }).length;
      var set = function (id, t) { var e = document.getElementById(id); if (e) e.textContent = t; };
      set("dc-buy", bought + " / " + buy.lines.length); set("dc-buy2", left > 0 ? money(left * g) + " still to buy" : "all bought");
      set("dc-mic", state.done[3] ? "Passed" : "Not yet"); set("dc-build", done + " / " + steps.length);
      var nx = nextStep(); set("dc-build2", nx ? "next: step " + nx.n : "all done");
      var ready = !!state.done[11]; set("dc-use", ready ? "Ready" : "Use it"); set("dc-use2", ready ? "open the phone page" : "after step 11");
      [["dc-buy", bought === buy.lines.length], ["dc-mic", !!state.done[3]], ["dc-build", done === steps.length], ["dc-use", ready]].forEach(function (x) {
        var e = document.getElementById(x[0]); if (e) e.parentNode.classList.toggle("ok", x[1]);
      });
      // overall: buying 20%, building 80%
      var pct = Math.round(20 * bought / buy.lines.length + 80 * done / steps.length);
      var ring = document.getElementById("ring"); if (ring) ring.style.setProperty("--p", pct);
      set("ring-pct", pct + "%");
      set("ring-text", pct === 0 ? "Nothing ticked yet: start with Buy." : pct >= 100 ? "Built and running. Well done!" :
        (nx ? "Next: Step " + nx.n + " · " + nx.title : "Keep going"));
    }
    dashboard();

    var first = (location.hash || "#home").slice(1);
    show(["home", "build", "model", "buy"].indexOf(first) >= 0 ? first : "home");
  }
})();
