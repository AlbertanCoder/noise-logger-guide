// 3D viewer + step panel. The page scrolls normally until "Move the model" is pressed (UI fix 2).
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const $ = (id) => document.getElementById(id);
const host = $("viewer"), caption = $("vcaption");
const LABELS = JSON.parse($("model-labels").textContent);
const LABEL_STEP = JSON.parse($("label-steps").textContent);
const STEPS = JSON.parse($("steps-data").textContent);
const PI = ["board", "gpio", "usb-c_power", "micro-hdmi_0", "micro-hdmi_1", "ethernet", "usb_stack_lower", "usb_stack_upper",
  "mipi", "poe", "fan_plug", "power_button", "pcie", "sdcard", "cooler", "fan"];
const TO_CONFIRM = ["mic"]; // the mic's shape and size are still to confirm with a tape (step 3)
const CASE = ["case_base", "case_lid"];
const OVERVIEW_LABELS = ["case_base", "case_lid", "mic_cradle", "mic"];
const EXPLODED_LABELS = ["case_lid", "cooler", "board", "case_base", "sdcard"];
const BOX_PARTS = ["case_base", "case_lid", ...PI];
// camera direction per view (after loading, model Z is screen-up)
const VIEWS = { overview: [0.25, 0.8, 1.0], top: [0.001, 1, 0.02], front: [0.1, 0.45, 1.0], under: [-0.6, -0.35, 0.8], mic: [0.6, 0.35, 1.0] };
const STEP_VIEW = { 0: ["overview"], 1: ["overview"], 2: ["overview"], 3: ["top", "measure"], 4: ["overview"], 5: ["under"],
  6: ["front", "assemble"], 7: ["front", "power"], 8: ["overview", "power"], 9: ["mic"], 10: ["mic"], 11: ["overview", "power"] };
const DEFAULT_CAPTION = caption.textContent;

const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
host.appendChild(renderer.domElement);
const scene = new THREE.Scene(); scene.background = new THREE.Color(0xeef1ee);
scene.add(new THREE.HemisphereLight(0xffffff, 0xbdb6a6, 1.5));
const sun = new THREE.DirectionalLight(0xffffff, 1.8); sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048); scene.add(sun, sun.target);
const fill = new THREE.DirectionalLight(0xffffff, 0.5); fill.position.set(-1, 0.6, -1); scene.add(fill);
const camera = new THREE.PerspectiveCamera(32, 1, 1, 5000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
// Not grabbed: one finger scrolls the page (touch-action pan-y), two fingers pinch-zoom the model, the mouse drags to turn it,
// and the mouse wheel scrolls the page (Ctrl + wheel zooms). 'Move the model' adds one-finger turning.
let grabbed = false;
function setTouches() { controls.touches = { ONE: grabbed ? THREE.TOUCH.ROTATE : null, TWO: THREE.TOUCH.DOLLY_PAN }; }
setTouches();
host.addEventListener("wheel", (e) => { if (!grabbed && !e.ctrlKey) e.stopPropagation(); }, { capture: true });
const root = new THREE.Group(); scene.add(root);
const groups = {}, home = new Map(), labelEls = {};
let spin = false, exploded = false, xray = false, labelsOn = true, power = false, measure = false, focus = null, topView = false;
let fanPivot = null, measureGroup = null, fitSphere = null, stepIdx = 0, tween = null, partTween = null, gltfScene = null;
const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
const baseKey = (n) => (n || "").split("#")[0].split("__")[0];
let currentView = "overview", currentAimNodes = null;

function resize() { const w = host.clientWidth, h = host.clientHeight; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); }
new ResizeObserver(() => { resize(); if (!tween) aimAt(currentView, false, currentAimNodes); }).observe(host); resize();

Promise.all([new Promise((res, rej) => new GLTFLoader().load("models/noise-logger.glb", res, undefined, rej)),
  fetch("models/colors.json").then((r) => r.json()), fetch("models/numbers.json").then((r) => r.json())])
  .then(([gltf, colors, numbers]) => {
    const s = gltf.scene; gltfScene = s; s.rotation.x = -Math.PI / 2; root.add(s);
    s.traverse((o) => {
      if (!o.isMesh) return;
      const k = baseKey(o.name), metal = /pin|cooler|fin|usb_stack|ethernet|hdmi|usb-c|soc|wifi/.test(o.name) && !/tongue|led/.test(o.name);
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
      b.addEventListener("click", () => { const st = $("step-" + LABEL_STEP[k]); if (st) st.scrollIntoView({ behavior: "smooth" }); });
      host.appendChild(b); labelEls[k] = b;
    });
    if (new URLSearchParams(location.search).get("view") === "top") { // proof view: the bare board from above, like the official drawing
      topView = true; labelsOn = false;
      Object.keys(groups).forEach((k) => { if (!PI.includes(k) || k === "cooler" || k === "fan") groups[k].forEach((o) => (o.visible = false)); });
      aimAt("top", false, ["board"]);
    } else {
      const q = new URLSearchParams(location.search), st = parseInt(q.get("step") || "0", 10);
      renderStep(STEPS.findIndex((x) => x.n === st) >= 0 ? STEPS.findIndex((x) => x.n === st) : 0, false);
      (q.get("mode") || "").split(",").forEach((m) => {  // e.g. ?mode=exploded,xray,power,measure (shareable views)
        if (m === "exploded") { setExploded(true, false); aimAt("overview", false, BOX_PARTS); }
        if (m === "xray") { xray = true; press("b-xray", true); }
        if (m === "power") { power = true; press("b-power", true); }
        if (m === "measure") { measure = true; press("b-measure", true); if (measureGroup) measureGroup.visible = true; }
        if (m === "nolabels") { labelsOn = false; press("b-labels", false); }
      });
      paint();
    }
    document.body.dataset.modelLoaded = "yes";
  })
  .catch((err) => host.insertAdjacentHTML("beforeend", "<p style='padding:12px'>The 3D model could not load: " + err.message + "</p>"));

// ---------- camera ----------
function aimAt(view, animate = true, nodes = null) {
  if (!fitSphere) return;
  currentView = view; currentAimNodes = nodes;
  let sphere = fitSphere;
  if (nodes && nodes.length) {
    const b = new THREE.Box3(); nodes.forEach((k) => (groups[k] || []).forEach((o) => b.expandByObject(o)));
    if (!b.isEmpty()) sphere = b.getBoundingSphere(new THREE.Sphere());
  }
  const vfov = THREE.MathUtils.degToRad(camera.fov), hfov = 2 * Math.atan(Math.tan(vfov / 2) * camera.aspect);
  const dist = Math.max(sphere.radius, 30) / Math.sin(Math.min(vfov, hfov) / 2) * 1.08;
  const dir = new THREE.Vector3(...(VIEWS[view] || VIEWS.overview)).normalize();
  const toPos = sphere.center.clone().addScaledVector(dir, dist), toTarget = sphere.center.clone();
  if (!animate) { camera.position.copy(toPos); controls.target.copy(toTarget); controls.update(); return; }
  const fromPos = camera.position.clone(), fromTarget = controls.target.clone(), t0 = performance.now();
  tween = (now) => {
    const e = ease(Math.min(1, (now - t0) / 900));
    camera.position.lerpVectors(fromPos, toPos, e); controls.target.lerpVectors(fromTarget, toTarget, e);
    if (e >= 1) tween = null;
  };
}

// ---------- modes ----------
function setExploded(on, animate = true) {
  exploded = on;
  const target = (o) => {
    const p = home.get(o).clone(), k = o.userData.key; if (!on) return p;
    // the glTF scene is turned -90° about X, so model Z (up) is the scene's local Z
    if (k === "case_lid") p.z += 45; else if (PI.includes(k)) p.z += 22;
    if (k === "cooler" || k === "fan") p.z += 14;
    return p;
  };
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
    m.transparent = xr || !on || TO_CONFIRM.includes(k);
    m.opacity = xr ? 0.14 : !on ? 0.16 : TO_CONFIRM.includes(k) ? 0.85 : 1;
    m.depthWrite = !(xr || !on);
    m.emissive = new THREE.Color(on && focus ? 0x1b5e4f : 0x000000); m.emissiveIntensity = on && focus ? 0.28 : 0;
    if (power && /led/.test(o.userData.detail)) { m.emissive = m.color.clone(); m.emissiveIntensity = 2.5; }
  }));
}
function press(id, on) { const b = $(id); if (b) b.setAttribute("aria-pressed", on ? "true" : "false"); }
$("b-assembled").onclick = () => { setExploded(false); focus = null; paint(); caption.textContent = DEFAULT_CAPTION; aimAt("overview"); };
$("b-exploded").onclick = () => { setExploded(true); aimAt("overview", true, BOX_PARTS); };
$("b-xray").onclick = () => { xray = !xray; press("b-xray", xray); paint(); };
$("b-labels").onclick = () => { labelsOn = !labelsOn; press("b-labels", labelsOn); };
$("b-measure").onclick = () => {
  measure = !measure; press("b-measure", measure); if (measureGroup) measureGroup.visible = measure;
  if (measure) { xray = true; press("b-xray", true); paint(); aimAt("top", true, ["board"]); }
};
$("b-power").onclick = () => { power = !power; press("b-power", power); paint(); };
$("b-spin").onclick = () => { spin = !spin; press("b-spin", spin); };
$("b-grab").onclick = () => {
  grabbed = !grabbed; setTouches(); host.classList.toggle("grabbed", grabbed); press("b-grab", grabbed);
  $("b-grab").textContent = grabbed ? "Done moving (scroll the page again)" : "Move the model";
};

// ---------- measurements drawn on the model (official numbers) ----------
function buildMeasurements(s, num) {
  measureGroup = new THREE.Group(); measureGroup.visible = false; s.add(measureGroup);
  const [bx, by] = num.board_corner_in_case_mm, z = 2 + 4 + 1.6 + 0.4; // board top: floor 2 + standoff 4 + board 1.6
  const ow = num.outer_mm[0];
  const mat = new THREE.LineBasicMaterial({ color: 0xc2571b });
  [{ a: [bx, by - 9, z], b: [bx + 85, by - 9, z], text: "85 mm (official)" },
   { a: [bx - 9, by, z], b: [bx - 9, by + 56, z], text: "56 mm" },
   { a: [bx + 3.5, by + 3.5, z], b: [bx + 61.5, by + 3.5, z], text: "holes 58 mm" },
   { a: [bx + 61.5, by + 3.5, z], b: [bx + 61.5, by + 52.5, z], text: "holes 49 mm" },
   { a: [0, -16, 0], b: [ow, -16, 0], text: ow.toFixed(1) + " mm case" }].forEach((L) => {
    const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(...L.a), new THREE.Vector3(...L.b)]), mat);
    const el = document.createElement("span"); el.className = "mlabel"; el.textContent = L.text; host.appendChild(el);
    line.userData.el = el; measureGroup.add(line);
  });
}

// ---------- step panel ----------
function renderStep(i, animate = true) {
  stepIdx = Math.max(0, Math.min(STEPS.length - 1, i));
  const s = STEPS[stepIdx], [view, extra] = STEP_VIEW[s.n] || ["overview"];
  $("sp-count").textContent = "Step " + (stepIdx + 1) + " of " + STEPS.length;
  $("sp-title").textContent = s.n + ". " + s.title;
  $("sp-text").innerHTML = s.actions.slice(0, 3).map((a) => "• " + a).join("<br>") + (s.actions.length > 3 ? "<br>… (full step below)" : "");
  $("sp-check").innerHTML = "<b>✓ Check:</b> " + s.check;
  $("sp-badge").className = "badge " + (s.tested ? "tested" : "untested"); $("sp-badge").textContent = s.tested ? "Tested" : "Not tested yet";
  $("sp-back").disabled = stepIdx === 0; $("sp-next").disabled = stepIdx === STEPS.length - 1;
  $("m-back").disabled = stepIdx === 0; $("m-next").disabled = stepIdx === STEPS.length - 1;
  $("m-count").textContent = "Step " + (stepIdx + 1) + " of " + STEPS.length + ": " + s.title;
  document.querySelectorAll(".sp-list button").forEach((b, j) => b.setAttribute("aria-current", j === stepIdx ? "step" : "false"));
  if (!groups.board) return;
  focus = s.focus && s.focus.length ? [...new Set(s.focus.map(baseKey))] : null;
  if (extra === "assemble") { setExploded(true, false); setTimeout(() => setExploded(false), 400); }
  else setExploded(!!(focus && focus.some((k) => PI.includes(k)) && view !== "front"), animate);
  power = extra === "power"; press("b-power", power);
  measure = extra === "measure"; press("b-measure", measure); if (measureGroup) measureGroup.visible = measure;
  xray = measure || view === "under"; press("b-xray", xray);
  paint();
  caption.textContent = focus ? "Step " + s.n + ": " + s.title + " — the highlighted parts are the ones this step uses." : DEFAULT_CAPTION;
  const aim = view === "mic" ? ["mic", "mic_cradle"] : extra === "measure" ? ["board"] : focus && view !== "overview" ? focus.filter((k) => k !== "mic") : null;
  if (extra === "measure") focus = ["board"];
  paint();
  aimAt(view, animate, aim && aim.length ? aim : null);
}
$("sp-back").onclick = () => renderStep(stepIdx - 1);
$("sp-next").onclick = () => renderStep(stepIdx + 1);
$("m-back").onclick = () => renderStep(stepIdx - 1);
$("m-next").onclick = () => renderStep(stepIdx + 1);
const list = document.querySelector(".sp-list");
STEPS.forEach((s, j) => { const b = document.createElement("button"); b.type = "button"; b.innerHTML = "<b>" + s.n + "</b> " + s.title; b.onclick = () => renderStep(j); list.appendChild(b); });
window.addEventListener("guide-focus", (e) => { const j = STEPS.findIndex((s) => "Step " + s.n + ": " + s.title === e.detail.title); renderStep(j >= 0 ? j : 0); });

// ---------- labels (leader dot, never overlapping, always inside the frame) ----------
const v = new THREE.Vector3();
function project(p, w, h) { v.copy(p).project(camera); return { x: (v.x * 0.5 + 0.5) * w, y: (-v.y * 0.5 + 0.5) * h, ok: v.z < 1 }; }
function placeLabels() {
  const w = host.clientWidth, h = host.clientHeight, shown = [];
  Object.keys(labelEls).forEach((k) => {
    const b = labelEls[k], box = new THREE.Box3(); (groups[k] || []).forEach((o) => { if (o.visible) box.expandByObject(o); });
    const wanted = labelsOn && !topView && !box.isEmpty() && (focus ? focus.includes(k) : (exploded ? EXPLODED_LABELS.includes(k) : OVERVIEW_LABELS.includes(k)));
    if (!wanted) { b.style.display = "none"; return; }
    const c = box.getCenter(new THREE.Vector3()); c.y = box.max.y;
    const p = project(c, w, h);
    if (!p.ok || p.x < 0 || p.x > w || p.y < 0 || p.y > h) { b.style.display = "none"; return; }
    b.style.display = ""; shown.push({ b, x: p.x, y: p.y - 10 });
  });
  shown.sort((a, c) => a.y - c.y);
  for (let i = 0; i < shown.length; i++) for (let j = 0; j < i; j++) {
    const a = shown[j], c = shown[i];
    if (Math.abs(a.x - c.x) < 130 && c.y - a.y < 30) c.y = a.y + 30;
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
