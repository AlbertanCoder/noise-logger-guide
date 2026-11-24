// 3D viewer + step panel. Since 24 Nov 2026 it handles like the drone guide's 3D view: the wheel zooms, one finger turns,
// two fingers zoom, the model stops dead when you let go, Reset view and Full screen (Round 2 of the 3D plan).
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const $ = (id) => document.getElementById(id);
const host = $("viewer"), caption = $("vcaption");
const LABELS = JSON.parse($("model-labels").textContent);
const LABEL_STEP = JSON.parse($("label-steps").textContent);
const STEPS = JSON.parse($("steps-data").textContent);
const PI = ["board", "gpio", "usb-c_power", "micro-hdmi_0", "micro-hdmi_1", "ethernet", "usb_stack_lower", "usb_stack_upper",
  "mipi", "poe", "fan_plug", "power_button", "pcie", "sdcard", "heatsink", "fan"];
const TO_CONFIRM = ["mic"]; // the mic's shape is drawn by eye, so it is slightly see-through
const CASE = ["case_base", "case_frame", "case_lid"];
const OVERVIEW_LABELS = ["case_lid", "mic", "shelf", "cable"];
const EXPLODED_LABELS = ["case_lid", "fan", "heatsink", "board", "case_base"];
const BOX_PARTS = [...CASE, ...PI];
// camera direction per view (after loading, model Z is screen-up)
const VIEWS = { overview: [0.25, 0.8, 1.0], top: [0.001, 1, 0.02], front: [0.1, 0.45, 1.0], under: [-0.6, -0.35, 0.8], mic: [0.6, 0.35, 1.0] };
// view, extra, and (optional) the parts the camera frames
const STEP_VIEW = { 0: ["overview"], 1: ["overview"], 2: ["overview"], 3: ["mic"], 4: ["mic"], 5: ["under", null, ["case_base", "board"]],
  6: ["front", "assemble"], 7: ["front", "power", ["case_base", "case_lid"]], 8: ["overview", "power"], 9: ["mic"], 10: ["mic"], 11: ["overview", "power"] };
const DEFAULT_CAPTION = caption.textContent;
// the hint line in the drone guide's words; a touch screen gets the touch words
if (window.matchMedia && matchMedia("(pointer: coarse)").matches) $("vhint").textContent = "Drag to rotate · pinch to zoom · two-finger drag to pan";

const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFShadowMap;
host.appendChild(renderer.domElement);
const scene = new THREE.Scene(); scene.background = new THREE.Color(0xeef1ee);
scene.add(new THREE.HemisphereLight(0xffffff, 0xbdb6a6, 1.5));
const sun = new THREE.DirectionalLight(0xffffff, 1.8); sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048); scene.add(sun, sun.target);
const fill = new THREE.DirectionalLight(0xffffff, 0.5); fill.position.set(-1, 0.6, -1); scene.add(fill);
const camera = new THREE.PerspectiveCamera(32, 1, 1, 5000);
const controls = new OrbitControls(camera, renderer.domElement);
// as on the drone guide: no glide after you let go; the wheel zooms; one finger turns, two fingers zoom and slide;
// the page scrolls when touched outside the model (touch-action:none on the model only)
controls.enableDamping = false;
controls.enablePan = true;
controls.zoomSpeed = 0.9;
controls.touches = { ONE: THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_PAN };
const FLOOR = Math.PI * 0.495, BELOW = Math.PI * 0.97;   // never under the floor, except in a view from below (step 5)
let userMoved = false;                                    // the camera is where you put it (until Reset view or a step)
controls.addEventListener("start", () => { userMoved = true; });
const root = new THREE.Group(); scene.add(root);
const groups = {}, home = new Map(), labelEls = {}, anchors = {};
let spin = false, exploded = false, xray = false, labelsOn = true, power = false, measure = false, focus = null, topView = false;
let fanPivot = null, measureGroup = null, fitSphere = null, stepIdx = 0, tween = null, partTween = null, gltfScene = null;
const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
const baseKey = (n) => (n || "").split("#")[0].split("__")[0];
let currentView = "overview", currentAimNodes = null;

function resize() { const w = host.clientWidth, h = host.clientHeight; if (!w || !h) return; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); }
// a new size (a turned phone, Full screen) frames the view again, unless you have moved the camera yourself
new ResizeObserver(() => { resize(); if (!tween && !userMoved) aimAt(currentView, false, currentAimNodes); }).observe(host); resize();

Promise.all([new Promise((res, rej) => new GLTFLoader().load("models/noise-logger.glb", res, undefined, rej)),
  fetch("models/colors.json").then((r) => r.json()), fetch("models/numbers.json").then((r) => r.json())])
  .then(([gltf, colors, numbers]) => {
    const s = gltf.scene; gltfScene = s; s.rotation.x = -Math.PI / 2; root.add(s);
    s.traverse((o) => {
      if (!o.isMesh) return;
      const k = baseKey(o.name), metal = /pin|heatsink|neck|usb_stack|ethernet|hdmi|usb-c|soc|wifi/.test(o.name) && !/tongue|led/.test(o.name);
      o.material = new THREE.MeshStandardMaterial({ color: new THREE.Color(colors[o.name] || colors[o.name.split("#")[0]] || "#c9ced3"),
        roughness: metal ? 0.35 : 0.7, metalness: metal ? 0.55 : 0.05 });
      o.castShadow = true; o.receiveShadow = true;
      o.userData.key = k; o.userData.detail = o.name.split("#")[0];
      (groups[k] = groups[k] || []).push(o);
    });
    // fan blades spin around the hub (power preview)
    root.updateMatrixWorld(true);  // the -90° turn must be applied before any world <-> local conversion
    const hub = (groups.fan || []).find((o) => o.userData.detail === "fan__hub");
    if (hub) {
      const hc = new THREE.Box3().setFromObject(hub).getCenter(new THREE.Vector3());
      fanPivot = new THREE.Group(); s.add(fanPivot); fanPivot.position.copy(s.worldToLocal(hc.clone()));
      (groups.fan || []).filter((o) => o.userData.detail === "fan__blades").forEach((b) => fanPivot.attach(b));
      fanPivot.userData.key = "fan";
    }
    // remember where every movable piece sits (for the exploded view)
    s.traverse((o) => { if (o.isMesh && o.parent === s) home.set(o, o.position.clone()); });
    if (fanPivot) home.set(fanPivot, fanPivot.position.clone());
    // ground with a soft shadow
    const box = new THREE.Box3().setFromObject(root);
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(3000, 3000), new THREE.ShadowMaterial({ opacity: 0.18 }));
    ground.rotation.x = -Math.PI / 2; ground.position.y = box.min.y - 0.01; ground.receiveShadow = true; root.add(ground);
    const c = box.getCenter(new THREE.Vector3()), r = box.getSize(new THREE.Vector3()).length();
    sun.position.set(c.x + r * 0.4, c.y + r, c.z + r * 0.5); sun.target.position.copy(c);
    const sc = sun.shadow.camera; sc.left = sc.bottom = -r; sc.right = sc.top = r; sc.near = 1; sc.far = r * 4; sc.updateProjectionMatrix();
    fitSphere = box.getBoundingSphere(new THREE.Sphere());
    buildMeasurements(s, numbers);
    Object.keys(LABELS).forEach((k) => {
      if (!groups[k]) return;
      const b = document.createElement("button");
      b.className = "vlabel"; b.type = "button"; b.innerHTML = LABELS[k] + '<i class="dot"></i>';
      b.addEventListener("click", () => { // a label opens its step on the Build tab
        const st = $("step-" + LABEL_STEP[k]), tab = document.querySelector('[role="tab"][data-tab="build"]');
        if (st && tab) { tab.click(); st.classList.add("open"); setTimeout(() => st.scrollIntoView({ behavior: "smooth" }), 60); }
      });
      host.appendChild(b); labelEls[k] = b;
    });
    // where three labels' dots sit (in the part's own coordinates, so they follow the exploded view and Auto-spin)
    const meshOf = (detail) => Object.values(groups).flat().find((o) => o.userData.detail === detail);
    const base = meshOf("case_base"), brd = meshOf("board"), usb = meshOf("cable__usb");
    if (base) { base.geometry.computeBoundingBox(); const bb = base.geometry.boundingBox;   // on the front wall, right of the socket openings
      anchors.case_base = { mesh: base, at: new THREE.Vector3(bb.min.x + 0.8 * (bb.max.x - bb.min.x), bb.min.y, (bb.min.z + bb.max.z) / 2) }; }
    if (brd) { brd.geometry.computeBoundingBox(); const bb = brd.geometry.boundingBox;      // near the card end of the board, away from the heatsink's label
      anchors.board = { mesh: brd, at: new THREE.Vector3(bb.min.x + 0.12 * (bb.max.x - bb.min.x), (bb.min.y + bb.max.y) / 2, bb.max.z) }; }
    if (usb) { const pos = usb.geometry.attributes.position; let best = 0, miss = 1e9;      // a point on the mic's cable itself, where it reaches the shelf
      for (let i = 0; i < pos.count; i++) { const e = Math.abs(pos.getZ(i) - 150); if (e < miss) { miss = e; best = i; } }
      anchors.cable = { mesh: usb, at: new THREE.Vector3().fromBufferAttribute(pos, best) }; }
    if (new URLSearchParams(location.search).get("view") === "top") { // proof view: the bare board from above, like the official drawing
      topView = true; labelsOn = false;
      Object.keys(groups).forEach((k) => { if (!PI.includes(k) || k === "heatsink" || k === "fan") groups[k].forEach((o) => (o.visible = false)); });
      aimAt("top", false, ["board"]);
    } else {
      const q = new URLSearchParams(location.search), st = parseInt(q.get("step") || "0", 10);
      renderStep(STEPS.findIndex((x) => x.n === st) >= 0 ? STEPS.findIndex((x) => x.n === st) : 0, false);
      (q.get("mode") || "").split(",").forEach((m) => {  // e.g. ?mode=exploded,xray,power,measure (shareable views)
        if (m === "exploded") { setExploded(true, false); aimAt("overview", false, BOX_PARTS); }
        if (m === "xray") { xray = true; press("b-xray", true); }
        if (m === "power") { power = true; press("b-power", true); }
        if (m === "measure") { measure = true; setExploded(false, false); xray = true; press("b-xray", true); aimAt("top", false, ["board"]); press("b-measure", true); if (measureGroup) measureGroup.visible = true; }
        if (m === "nolabels") { labelsOn = false; press("b-labels", false); }
      });
      paint();
    }
    document.body.dataset.modelLoaded = "yes";
  })
  .catch((err) => host.insertAdjacentHTML("beforeend", "<p style='padding:12px'>The 3D model could not load: " + err.message + "</p>"));

// ---------- camera ----------
// how far a part rises in the exploded view (mm)
const lift = (k) => (k === "case_lid" ? 78 : k === "case_frame" || k === "fan" ? 52 : PI.includes(k) ? 22 : 0) + (k === "heatsink" ? 12 : 0);
/** the 8 corners of every shown part's box, where the parts will be once they stop moving (model 'up' is the screen's y) */
function cornersOf(nodes) {
  const pts = [], one = new THREE.Box3();
  (nodes && nodes.length ? nodes : Object.keys(groups)).forEach((k) => (groups[k] || []).forEach((o) => {
    if (!o.visible) return;
    const mover = home.has(o) ? o : o.parent, moved = home.has(mover) ? mover.position.z - home.get(mover).z : 0;
    const rise = (exploded ? lift(k) : 0) - moved;
    one.setFromObject(o); if (one.isEmpty()) return; one.min.y += rise; one.max.y += rise;
    for (let i = 0; i < 8; i++) pts.push(new THREE.Vector3(i & 1 ? one.max.x : one.min.x, i & 2 ? one.max.y : one.min.y, i & 4 ? one.max.z : one.min.z));
  }));
  return pts;
}
// the camera fit is the drone guide's (docs/js/viewer3d.js, collectCorners + fitCamera): framed tight, not by a loose ball
const probe = new THREE.PerspectiveCamera();
/** how far back the camera must sit, looking along dir at centre, for the farthest corner to reach 'fill' of the frame */
function fitDistance(points, centre, dir, fill = 0.88) {
  probe.fov = camera.fov; probe.aspect = camera.aspect; probe.near = camera.near; probe.far = camera.far; probe.updateProjectionMatrix();
  let dist = 0; points.forEach((p) => { dist = Math.max(dist, p.distanceTo(centre)); }); dist = Math.max(dist, 30) * 2.4;
  const q = new THREE.Vector3();
  for (let i = 0; i < 16; i++) {
    probe.position.copy(centre).addScaledVector(dir, dist); probe.lookAt(centre); probe.updateMatrixWorld(true);
    let worst = 0; points.forEach((p) => { q.copy(p).project(probe); worst = Math.max(worst, Math.abs(q.x), Math.abs(q.y)); });
    if (worst <= 0.001 || Math.abs(worst - fill) < 0.006) break;
    dist *= worst / fill;
  }
  return dist;
}
/** zoom limits as on the drone guide: 0.25x to 3.2x the fitted distance; the camera stays above the floor except from below */
function setLimits(dist, below) { controls.minDistance = dist * 0.25; controls.maxDistance = dist * 3.2; controls.maxPolarAngle = below ? BELOW : FLOOR; }
function aimAt(view, animate = true, nodes = null) {
  if (!fitSphere) return;
  currentView = view; currentAimNodes = nodes; userMoved = false;
  const pts = cornersOf(nodes), box = new THREE.Box3().setFromPoints(pts);
  const centre = pts.length ? box.getCenter(new THREE.Vector3()) : fitSphere.center.clone();
  const dir = new THREE.Vector3(...(VIEWS[view] || VIEWS.overview)).normalize();
  const dist = pts.length ? fitDistance(pts, centre, dir) : fitSphere.radius * 3;
  const toPos = centre.clone().addScaledVector(dir, dist), toTarget = centre.clone(), below = dir.y < 0;
  if (!animate) { tween = null; setLimits(dist, below); camera.position.copy(toPos); controls.target.copy(toTarget); controls.update(); return; }
  // while the camera glides to the new view the limits are wide open, so it never jumps; they close when it arrives
  controls.minDistance = 0; controls.maxDistance = Infinity; controls.maxPolarAngle = BELOW;
  const fromPos = camera.position.clone(), fromTarget = controls.target.clone(), t0 = performance.now();
  tween = (now) => {
    const e = ease(Math.min(1, (now - t0) / 900));
    camera.position.lerpVectors(fromPos, toPos, e); controls.target.lerpVectors(fromTarget, toTarget, e);
    if (e >= 1) { tween = null; setLimits(dist, below); }
  };
}
/** Reset view: the camera only (parts, modes and labels stay), back to the current step's own view */
let stepAim = { view: "overview", nodes: null };
function resetView() { aimAt(stepAim.view, true, stepAim.nodes); }

// ---------- modes ----------
function setExploded(on, animate = true) {
  exploded = on;
  (groups.cable || []).forEach((o) => { o.visible = !on; }); // cables would hang in the air beside the opened case
  // the glTF scene is turned -90° about X, so model Z (up) is the scene's local Z
  const target = (o) => { const p = home.get(o).clone(); if (on) p.z += lift(o.userData.key); return p; };
  if (!animate) { home.forEach((h, o) => o.position.copy(target(o))); partTween = null; }
  else {
    const from = new Map(), t0 = performance.now(); home.forEach((h, o) => from.set(o, o.position.clone()));
    partTween = (now) => {
      const e = ease(Math.min(1, (now - t0) / 1200));
      home.forEach((h, o) => o.position.lerpVectors(from.get(o), target(o), e));
      if (e >= 1) partTween = null;
    };
  }
  press("b-exploded", on); press("b-assembled", !on);
}
function paint() {
  Object.entries(groups).forEach(([k, list]) => list.forEach((o) => {
    const on = !focus || focus.includes(k), m = o.material, xr = xray && CASE.includes(k);
    const seeThrough = xr || !on || TO_CONFIRM.includes(k);
    // three.js only rebuilds a material when told to: without needsUpdate a part first drawn solid stays solid
    // (final audit FA-03: 'See inside', 'Show measurements' and the step highlighting did nothing after a normal load)
    if (m.transparent !== seeThrough) { m.transparent = seeThrough; m.needsUpdate = true; }
    m.opacity = xr ? 0.14 : !on ? 0.16 : TO_CONFIRM.includes(k) ? 0.85 : 1;
    m.depthWrite = !(xr || !on);
    m.emissive = new THREE.Color(on && focus ? 0x1b5e4f : 0x000000); m.emissiveIntensity = on && focus ? 0.28 : 0;
    if (power && /led/.test(o.userData.detail)) { m.emissive = m.color.clone(); m.emissiveIntensity = 2.5; }
  }));
}
function press(id, on) { const b = $(id); if (b) b.setAttribute("aria-pressed", on ? "true" : "false"); }
$("b-assembled").onclick = () => { setExploded(false); focus = null; paint(); caption.textContent = DEFAULT_CAPTION; aimAt("overview"); };
// the measuring lines belong to the closed box seen from above: Exploded or See inside switches them off
function setMeasure(on) { measure = on; press("b-measure", on); if (measureGroup) measureGroup.visible = on; xray = on; press("b-xray", on); paint(); }
$("b-exploded").onclick = () => { if (measure) setMeasure(false); setExploded(true); aimAt("overview", true, BOX_PARTS); };
$("b-xray").onclick = () => { if (measure) { setMeasure(false); return; } xray = !xray; press("b-xray", xray); paint(); };
$("b-labels").onclick = () => { labelsOn = !labelsOn; press("b-labels", labelsOn); };
$("b-measure").onclick = () => { setMeasure(!measure); if (measure) { setExploded(false, false); aimAt("top", true, ["board"]); } };
$("b-power").onclick = () => { power = !power; press("b-power", power); paint(); };
$("b-spin").onclick = () => { spin = !spin; press("b-spin", spin); };
$("b-reset").onclick = resetView;
// Full screen as on the drone guide: the real full screen where the browser has one for a page element; otherwise
// (iPhone Safari), or when it fails, the 3D view fills the screen as an overlay with a Close button. Esc closes both.
const vwrap = $("vwrap");
function isFull() { return document.fullscreenElement === vwrap || vwrap.classList.contains("v-overlay"); }
function setFullLabel() { $("b-full").textContent = isFull() ? "Close full screen" : "Full screen"; press("b-full", isFull()); }
function closeOverlay() { vwrap.classList.remove("v-overlay"); document.documentElement.classList.remove("v-locked"); setFullLabel(); }
function openOverlay() { vwrap.classList.add("v-overlay"); document.documentElement.classList.add("v-locked"); setFullLabel(); }
$("b-full").onclick = () => {
  if (vwrap.classList.contains("v-overlay")) { closeOverlay(); return; }
  if (document.fullscreenElement) { document.exitFullscreen(); return; }
  if (typeof vwrap.requestFullscreen === "function") vwrap.requestFullscreen().catch(openOverlay); else openOverlay();
};
document.addEventListener("fullscreenchange", setFullLabel);
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && vwrap.classList.contains("v-overlay")) closeOverlay(); });

// ---------- measurements drawn on the model (official numbers) ----------
function buildMeasurements(s, num) {
  measureGroup = new THREE.Group(); measureGroup.visible = false; s.add(measureGroup);
  const [bx, by] = num.board_corner_in_bought_case_mm, z = num.board_top_z_mm + 0.4; // just above the board
  const ow = num.bought_case_mm[0];
  const mat = new THREE.LineBasicMaterial({ color: 0xc2571b });
  [{ a: [bx, by - 9, z], b: [bx + 85, by - 9, z], text: "85 mm (official)" },
   { a: [bx - 9, by, z], b: [bx - 9, by + 56, z], text: "56 mm" },
   { a: [bx + 3.5, by + 3.5, z], b: [bx + 61.5, by + 3.5, z], text: "holes 58 mm" },
   { a: [bx + 61.5, by + 3.5, z], b: [bx + 61.5, by + 52.5, z], text: "holes 49 mm" },
   { a: [0, -16, 0], b: [ow, -16, 0], text: ow.toFixed(1) + " mm case (official)" }].forEach((L) => {
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...L.a), new THREE.Vector3(...L.b)]), mat);
    const el = document.createElement("span"); el.className = "mlabel"; el.textContent = L.text; host.appendChild(el);
    line.userData.el = el; measureGroup.add(line);
  });
}

// ---------- step panel ----------
function renderStep(i, animate = true) {
  stepIdx = Math.max(0, Math.min(STEPS.length - 1, i));
  const s = STEPS[stepIdx], [view, extra, frame] = STEP_VIEW[s.n] || ["overview"];
  $("sp-count").textContent = s.n === 0 ? "Optional" : "Step " + s.n + " of " + (STEPS.length - 1);
  $("sp-title").textContent = s.n + ". " + s.title;
  $("sp-text").innerHTML = s.actions.slice(0, 3).map((a) => "• " + a).join("<br>") + (s.actions.length > 3 ? "<br>… (all of it is on the Build tab)" : "");
  $("sp-check").innerHTML = "<b>✓ Check:</b> " + s.check;
  $("sp-badge").className = "badge " + (s.tested ? "tested" : "untested"); $("sp-badge").textContent = s.tested ? "Tested" : "Not tested yet";
  $("sp-back").disabled = stepIdx === 0; $("sp-next").disabled = stepIdx === STEPS.length - 1;
  $("m-back").disabled = stepIdx === 0; $("m-next").disabled = stepIdx === STEPS.length - 1;
  $("m-count").textContent = (s.n === 0 ? "" : "Step " + s.n + " of " + (STEPS.length - 1) + ": ") + s.title;
  if (!groups.board) return;
  focus = s.focus && s.focus.length ? [...new Set(s.focus.map(baseKey))] : null;
  if (extra === "assemble") { setExploded(true, false); setTimeout(() => setExploded(false), 400); }
  else setExploded(!!(focus && focus.some((k) => PI.includes(k)) && view !== "front"), animate);
  power = extra === "power"; press("b-power", power);
  measure = extra === "measure"; press("b-measure", measure); if (measureGroup) measureGroup.visible = measure;
  xray = measure || view === "under"; press("b-xray", xray);
  paint();
  caption.textContent = focus ? "Step " + s.n + ": " + s.title + " — the highlighted parts are the ones this step uses." : DEFAULT_CAPTION;
  const aim = frame ? frame : view === "mic" ? (s.n === 9 ? ["mic", "shelf", "cable", "case_base"] : ["mic"]) : extra === "measure" ? ["board"] : focus && view !== "overview" ? focus.filter((k) => k !== "mic") : null;
  if (extra === "measure") focus = ["board"];
  paint();
  stepAim = { view, nodes: aim && aim.length ? aim : null };
  aimAt(view, animate, stepAim.nodes);
}
$("sp-back").onclick = () => renderStep(stepIdx - 1);
$("sp-next").onclick = () => renderStep(stepIdx + 1);
$("m-back").onclick = () => renderStep(stepIdx - 1);
$("m-next").onclick = () => renderStep(stepIdx + 1);
window.addEventListener("guide-focus", (e) => { const j = STEPS.findIndex((s) => "Step " + s.n + ": " + s.title === e.detail.title); renderStep(j >= 0 ? j : 0); });

// ---------- labels (leader dot, never overlapping, always inside the frame) ----------
const v = new THREE.Vector3();
function project(p, w, h) { v.copy(p).project(camera); return { x: (v.x * 0.5 + 0.5) * w, y: (-v.y * 0.5 + 0.5) * h, ok: v.z < 1 }; }
function placeLabels() {
  const w = host.clientWidth, h = host.clientHeight, shown = [];
  Object.keys(labelEls).forEach((k) => {
    const b = labelEls[k], box = new THREE.Box3(); (groups[k] || []).forEach((o) => { if (o.visible) box.expandByObject(o); });
    const wanted = labelsOn && !topView && !measure && !box.isEmpty() && (focus ? focus.includes(k) : (exploded ? EXPLODED_LABELS.includes(k) : OVERVIEW_LABELS.includes(k)));
    if (!wanted) { b.style.display = "none"; return; }
    const a = anchors[k], c = a && a.mesh.visible ? a.mesh.localToWorld(a.at.clone()) : box.getCenter(new THREE.Vector3());
    if (!a) c.y = box.max.y;
    const p = project(c, w, h);
    if (!p.ok || p.x < 0 || p.x > w || p.y < 0 || p.y > h) { b.style.display = "none"; return; }
    b.style.display = ""; shown.push({ b, x: p.x, y: p.y - 10 });
  });
  shown.sort((a, c) => a.y - c.y);
  for (let i = 0; i < shown.length; i++) for (let j = 0; j < i; j++) {
    const a = shown[j], c = shown[i];
    if (Math.abs(a.x - c.x) < (a.b.offsetWidth + c.b.offsetWidth) / 2 + 6 && c.y - a.y < 34) c.y = a.y + 34;
  }
  shown.forEach(({ b, x, y }) => { const half = b.offsetWidth / 2 + 4; b.style.left = Math.max(half, Math.min(w - half, x)) + "px"; b.style.top = Math.max(b.offsetHeight + 4, Math.min(y, h - 4)) + "px"; });
  if (measureGroup) measureGroup.children.forEach((line) => {
    const el = line.userData.el; if (!measure) { el.style.display = "none"; return; }
    const pos = line.geometry.attributes.position;
    const mid = new THREE.Vector3().fromBufferAttribute(pos, 0).add(new THREE.Vector3().fromBufferAttribute(pos, 1)).multiplyScalar(0.5);
    line.localToWorld(mid); const p = project(mid, w, h);
    el.style.display = p.ok ? "" : "none"; el.style.left = p.x + "px"; el.style.top = p.y + "px";
  });
}

renderer.setAnimationLoop((now) => {
  if (tween) tween(now);
  if (partTween) partTween(now);
  if (spin) root.rotation.y += 0.004;
  if (power && fanPivot) fanPivot.rotation.z += 0.35;
  controls.update();
  renderer.render(scene, camera);
  placeLabels();
});

// read-only numbers for the page check (checks/selftest.html): camera distance, zoom limits, the floor angle
window.__view = () => ({ dist: camera.position.distanceTo(controls.target), min: controls.minDistance, max: controls.maxDistance,
  polar: controls.getPolarAngle(), maxPolar: controls.maxPolarAngle, moved: userMoved, damping: controls.enableDamping, tweening: !!tween });
