// 3D viewer + step panel. Since 24 Nov 2026 it handles like the drone guide's 3D view: the wheel zooms, one finger turns,
// two fingers zoom, the model stops dead when you let go, Reset view and Full screen (Round 2 of the 3D plan).
// Round 3: the model is built in Blender (scripts/build_model_blender.py) and carries its own materials, part names,
// accuracy tags and label points; the look is the drone guide's (cream studio, ACES tone 1.05, five lights, soft shadow).
// Round 4: the step's parts glow orange and the rest dim to 62%; labels stay hidden until the Labels button is pressed
// (the choice is remembered); pointing at a part with the mouse, or tapping it, names it;
// Play / Pause and a slider animate the current step, and you can turn and zoom while it plays.
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
const BOARD_PARTS = PI.filter((k) => !["sdcard", "heatsink", "fan"].includes(k));   // what moves when the bare board moves
const CASE = ["case_base", "case_frame", "case_lid"];
const OVERVIEW_LABELS = ["case_lid", "mic", "shelf", "cable"];
const EXPLODED_LABELS = ["case_lid", "fan", "heatsink", "board", "case_base"];
const BOX_PARTS = [...CASE, ...PI];
// how exact each part's drawing is, in the guide's own words (the model file tags every part)
const ACC = { official: "from the official drawing", simplified: "simplified", eye: "drawn by eye" };
// camera direction per view (after loading, model Z is screen-up)
const VIEWS = { overview: [0.25, 0.8, 1.0], top: [0.001, 1, 0.02], front: [0.1, 0.45, 1.0], under: [-0.6, -0.35, 0.8], mic: [0.6, 0.35, 1.0] };
// view, extra, and (optional) the parts the camera frames
const STEP_VIEW = { 0: ["overview"], 1: ["overview"], 2: ["overview"], 3: ["mic"], 4: ["mic"], 5: ["under", null, ["case_base", "board"]],
  6: ["front", null, BOX_PARTS], 7: ["front", "power", ["case_base", "case_lid"]], 8: ["overview", "power"], 9: ["mic"], 10: ["mic"],
  11: ["overview", "power", ["case_base", "case_lid"]] };   // steps 7 and 11: a close look at the box while it runs
const DEFAULT_CAPTION = caption.textContent;
const MODEL_V = "b77ff950";   // fingerprint of the model files, written by scripts/make_pictures.py: a changed model gets a new address, so no phone shows a saved old one
// the hint line in the drone guide's words; a touch screen gets the touch words
if (window.matchMedia && matchMedia("(pointer: coarse)").matches) $("vhint").textContent = "Drag to rotate · pinch to zoom · two-finger drag to pan";
// remembered choices (private browsing has no storage: then the choice lasts until the page closes)
const store = {
  get(k) { try { return window.localStorage.getItem("noise-logger-3d-" + k); } catch (e) { return null; } },
  set(k, v) { try { window.localStorage.setItem("noise-logger-3d-" + k, v); } catch (e) { /* not available */ } },
};

// ---------- what Play shows in each step (times in seconds, moves in mm: [right, back, up]) ----------
// 'on' moves whole parts; 'plug' moves a plug and bends its cable with it; 'power' switches the lights and the fan;
// 'explode' opens the case. Every step ends in the position the model rests in.
const UP = (z) => [0, 0, z];
const ASSEMBLE = [
  { on: ["heatsink"], k: [[0, UP(46)], [1.4, UP(30)], [2.6, UP(30)], [4.0, UP(0)]] },          // pressed onto the chip, then down with the Pi
  { on: ["case_base__feet"], k: [[0, UP(-12)], [1.4, UP(-12)], [2.4, UP(0)]] },                // feet under the base
  { on: BOARD_PARTS, k: [[0, UP(30)], [2.6, UP(30)], [4.0, UP(0)]] },                          // the Pi into the base
  { on: ["case_frame", "fan"], k: [[0, UP(56)], [4.2, UP(56)], [5.8, UP(16)], [6.6, UP(16)], [7.8, UP(0)]] },   // frame: fan cable in, then clipped on
  { on: ["case_lid"], k: [[0, UP(84)], [8.0, UP(84)], [9.2, UP(0)]] },
  { on: ["sdcard"], k: [[0, [-26, 0, 0]], [9.4, [-26, 0, 0]], [10.6, [0, 0, 0]]] },            // the card goes in last
];
const faster = (tracks, f) => tracks.map((t) => ({ ...t, k: t.k.map(([time, v]) => [time * f, v]) }));
const STEP_PLAY = {
  1: { dur: 9.6, note: "The five parts coming together", hideCables: false, tracks: [...faster(ASSEMBLE, 0.6),
    { plug: "power", k: [[0, [0, -18, 0]], [6.6, [0, -18, 0]], [7.4, [0, 0, 0]]] },
    { plug: "mic", k: [[0, UP(60)], [7.2, UP(60)], [8.4, UP(0)]] },
    { plug: "pi", k: [[0, [20, 0, 0]], [8.4, [20, 0, 0]], [9.2, [0, 0, 0]]] }] },
  2: { dur: 2.6, note: "The case opens so you can check each part", explode: [[0, 0], [0.3, 0], [2.3, 1]], tracks: [] },
  3: { dur: 3.0, note: "The mic goes on the shelf", tracks: [{ plug: "mic", k: [[0, UP(60)], [0.3, UP(60)], [2.4, UP(0)]] }] },
  6: { dur: 11.0, note: "Heatsink, feet, Pi, frame, lid, then the card", hideCables: true, tracks: ASSEMBLE },
  7: { dur: 4.6, note: "The power plug goes in, then it starts", power: [[0, false], [2.6, true]],
    tracks: [{ plug: "power", k: [[0, [0, -18, 0]], [0.4, [0, -18, 0]], [2.0, [0, 0, 0]]] }] },
  9: { dur: 5.0, note: "The mic goes on the shelf, then its cable into the Pi", tracks: [
    { plug: "mic", k: [[0, UP(60)], [0.3, UP(60)], [2.2, UP(0)]] },
    { plug: "pi", k: [[0, [20, 0, 0]], [2.6, [20, 0, 0]], [4.2, [0, 0, 0]]] }] },
  11: { dur: 5.0, note: "It switches off and starts again by itself", power: [[0, true], [1.2, false], [3.4, true]], tracks: [] },
};
// a plug, the parts that move with it, the cable it bends and how far along the cable the bend reaches (mm)
const PLUGS = { pi: { on: ["cable__plug"], cable: "cable__usb", end: "cable__plug", reach: 70 },
  mic: { on: ["mic", "cable__micplug"], cable: "cable__usb", end: "cable__micplug", reach: 120 },
  power: { on: ["cable__powerplug"], cable: "cable__power", end: "cable__powerplug", reach: 60 } };

const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
host.appendChild(renderer.domElement);
// the drone guide's studio (its docs/js/viewer3d.js): cream backdrop, key / fill / rim / back / sky lights
const CREAM = 0xf7f2e8, EMBER = new THREE.Color(0xc2571b), SLATE = new THREE.Color(0x4a535c);
const scene = new THREE.Scene(); scene.background = new THREE.Color(CREAM);
const sun = new THREE.DirectionalLight(0xffffff, 2.1); sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048);
sun.shadow.radius = 3; sun.shadow.bias = -0.0006; scene.add(sun, sun.target);
const fill = new THREE.DirectionalLight(0xdfece6, 0.75); fill.position.set(-0.5, 0.3, 0.25); scene.add(fill);
const rim = new THREE.DirectionalLight(0xffe9d8, 1.3); rim.position.set(-0.2, 0.35, -0.55); scene.add(rim);
const back = new THREE.DirectionalLight(0xffffff, 0.8); back.position.set(0.1, 0.15, -0.7); scene.add(back);   // edges on black parts
scene.add(new THREE.HemisphereLight(0xffffff, 0xd8d2c4, 1.15));
// something for the metal parts to mirror (sockets, pins, the mic): a plain room with three soft light panels
{
  const room = new THREE.Scene();
  const panel = (w, h, x, y, z, power) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color: new THREE.Color().setScalar(power), side: THREE.DoubleSide }));
    m.position.set(x, y, z); m.lookAt(0, 0, 0); room.add(m);
  };
  room.add(new THREE.Mesh(new THREE.BoxGeometry(20, 20, 20), new THREE.MeshBasicMaterial({ color: 0x8f8a7e, side: THREE.BackSide })));
  panel(9, 9, 0, 9.5, 0, 5); panel(6, 8, 9, 3, 5, 4); panel(8, 5, -8, 4, -6, 2.5);
  const pm = new THREE.PMREMGenerator(renderer);
  scene.environment = pm.fromScene(room, 0.04).texture; scene.environmentIntensity = 0.45; pm.dispose();
}
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
const groups = {}, home = new Map(), labelEls = {}, anchors = {}, cables = {};
const offsets = new Map();                                // part -> how far the animation has moved it right now (model mm)
let spin = false, exploded = false, xray = false, labelsOn = store.get("labels") === "1", power = false, measure = false, focus = null, topView = false;
let fanPivot = null, measureGroup = null, fitSphere = null, stepIdx = 0, tween = null, gltfScene = null;
let explodeAmt = 0, explodeTween = null, litNow = null, openShown = false;
let still = false;                                        // proof pictures (?mode=still): the fan stands where it is, so the same model gives the same picture
let playWhenReady = false;                                // 'Watch it in 3D' was pressed before the model was here: play when it is
const anim = { def: null, t: 0, playing: false, moves: [], bends: [], last: 0 };   // the current step's Play
const ease = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);
const baseKey = (n) => (n || "").split("#")[0].split("__")[0];
let currentView = "overview", currentAimNodes = null;

function resize() { const w = host.clientWidth, h = host.clientHeight; if (!w || !h) return; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); }
// a new size (a turned phone, Full screen) frames the view again, unless you have moved the camera yourself
new ResizeObserver(() => { resize(); if (!tween && !userMoved) aimAt(currentView, false, currentAimNodes); }).observe(host); resize();

Promise.all([new Promise((res, rej) => new GLTFLoader().load("models/noise-logger.glb?v=" + MODEL_V, res, undefined, rej)),
  fetch("models/colors.json?v=" + MODEL_V).then((r) => r.json()), fetch("models/numbers.json?v=" + MODEL_V).then((r) => r.json())])
  .then(([gltf, colors, numbers]) => {
    const s = gltf.scene; gltfScene = s; s.rotation.x = -Math.PI / 2; root.add(s);
    s.traverse((o) => {
      if (!o.isMesh) return;
      const k = baseKey(o.name);
      // every part gets its own copy of the material the model file gave it; colors.json can still override a colour
      o.material = o.material.clone();
      const own = colors[o.name]; if (own && !o.material.map) o.material.color.set(own);
      o.userData.base = { color: o.material.color.clone(), emissive: o.material.emissive.clone(), glow: o.material.emissiveIntensity,
        opacity: o.material.opacity, clear: o.material.transparent };
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
      fanPivot.userData.key = "fan"; fanPivot.userData.detail = "fan__pivot";
    }
    // remember where every movable piece sits (for the exploded view and the step animations)
    s.traverse((o) => { if (o.isMesh && o.parent === s) home.set(o, o.position.clone()); });
    if (fanPivot) home.set(fanPivot, fanPivot.position.clone());
    // ground with a soft shadow
    const box = new THREE.Box3().setFromObject(root);
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(3000, 3000), new THREE.ShadowMaterial({ color: 0x2b3a33, opacity: 0.16 }));
    ground.rotation.x = -Math.PI / 2; ground.position.y = box.min.y - 0.01; ground.receiveShadow = true; root.add(ground);
    const c = box.getCenter(new THREE.Vector3()), r = box.getSize(new THREE.Vector3()).length();
    sun.position.copy(c).add(new THREE.Vector3(0.35, 0.55, 0.32).multiplyScalar(r * 1.6)); sun.target.position.copy(c);
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
    // where each label's dot sits: the model file carries a point per label and the part it rides on,
    // so the dots follow the exploded view, Auto-spin and the step animations
    const meshOf = (detail) => Object.values(groups).flat().find((o) => o.userData.detail === detail);
    s.children.filter((o) => o.userData.kind === "label").forEach((o) => {
      const ride = meshOf(o.userData.ride);
      if (ride) anchors[o.userData.key] = { mesh: ride, at: ride.worldToLocal(o.getWorldPosition(new THREE.Vector3())) };
    });
    // cables that bend when a plug moves: remember the cable's shape and how strongly each point follows each plug
    Object.entries(PLUGS).forEach(([name, p]) => {
      const mesh = meshOf(p.cable), plug = meshOf(p.end); if (!mesh || !plug) return;
      const pos = mesh.geometry.attributes.position, at = new THREE.Box3().setFromBufferAttribute(plug.geometry.attributes.position).getCenter(new THREE.Vector3());
      const cb = cables[p.cable] = cables[p.cable] || { mesh, pos, rest: pos.array.slice(), pull: {}, was: "" };
      const w = cb.pull[name] = new Float32Array(pos.count), v3 = new THREE.Vector3();
      for (let i = 0; i < pos.count; i++) { const t = Math.max(0, Math.min(1, 1 - (v3.fromBufferAttribute(pos, i).distanceTo(at) - 12) / p.reach)); w[i] = t * t * (3 - 2 * t); }
      mesh.frustumCulled = false;
    });
    press("b-labels", labelsOn);
    if (new URLSearchParams(location.search).get("view") === "top") { // proof view: the bare board from above, like the official drawing
      topView = true; labelsOn = false;
      Object.keys(groups).forEach((k) => { if (!PI.includes(k) || k === "heatsink" || k === "fan") groups[k].forEach((o) => (o.visible = false)); });
      aimAt("top", false, PI.filter((k) => k !== "heatsink" && k !== "fan"));   // the board with its sockets (they stick out past its edge)
    } else {
      const q = new URLSearchParams(location.search), asked = q.get("step") === null ? -1 : STEPS.findIndex((x) => x.n === parseInt(q.get("step"), 10));
      const cam = (q.get("cam") || "").split(",").map(Number);    // proof pictures: ?cam=x,y,z looks at the whole model from that side
      if (cam.length === 3 && cam.every(isFinite)) VIEWS.overview = cam;
      // the step in the address, or else the one already chosen while the model was on its way (audit of 24 Nov 2026,
      // finding 2: on a slow connection Next, Back and 'Watch it in 3D' pressed before the model was here were thrown away)
      const playNow = playWhenReady;
      renderStep(asked >= 0 ? asked : stepIdx, false);
      (q.get("mode") || "").split(",").forEach((m) => {  // e.g. ?mode=exploded,xray,power,measure (shareable views)
        if (m === "exploded") { setExploded(true, false); aimAt("overview", false, BOX_PARTS); }
        if (m === "xray") { xray = true; press("b-xray", true); }
        if (m === "power") { power = true; press("b-power", true); }
        if (m === "measure") { measure = true; setExploded(false, false); xray = true; press("b-xray", true); aimAt("top", false, ["board"]); press("b-measure", true); if (measureGroup) measureGroup.visible = true; }
        if (m === "still") still = true;
        if (m === "nolabels") { labelsOn = false; press("b-labels", false); }   // for this visit only: the remembered choice stays
      });
      if (q.get("frame")) aimAt("overview", false, q.get("frame").split(","));   // proof pictures: ?frame=mic fills the picture with those parts
      const at = parseFloat(q.get("at"));                                         // proof pictures: ?at=0.5 stops the step's animation half way
      if (anim.def && isFinite(at)) seek(at * anim.def.dur); else if (playNow) play();
      paint();
    }
    if (!topView) place();
    if ($("vload")) $("vload").remove();                   // the 'Loading' words
    document.body.dataset.modelLoaded = "yes";
  })
  .catch((err) => { if ($("vload")) $("vload").remove(); host.insertAdjacentHTML("beforeend", "<p style='padding:12px'>The 3D model could not load: " + err.message + "</p>"); });

// ---------- camera ----------
// how far a part rises in the exploded view (mm)
const lift = (k) => (k === "case_lid" ? 78 : k === "case_frame" || k === "fan" ? 52 : PI.includes(k) ? 22 : 0) + (k === "heatsink" ? 12 : 0);
/** the 8 corners of every shown part's box, where the parts will be once they stop moving (model 'up' is the screen's y).
    In a step that has an animation the box also covers everywhere the part travels, so nothing flies out of the picture. */
function cornersOf(nodes) {
  const pts = [], one = new THREE.Box3(), reach = new Map();
  anim.moves.forEach((m) => m.objs.forEach((o) => {
    const b = reach.get(o) || new THREE.Box3(new THREE.Vector3(), new THREE.Vector3());
    m.k.forEach(([, v]) => b.expandByPoint(new THREE.Vector3(v[0], v[2], -v[1])));   // model [right, back, up] is the screen's x, -z, y
    reach.set(o, b);
  }));
  (nodes && nodes.length ? nodes : Object.keys(groups)).forEach((k) => (groups[k] || []).forEach((o) => {
    if (k === "cable" ? exploded : !o.visible) return;      // cables are hidden only while the case is open
    const mover = home.has(o) ? o : o.parent, off = offsets.get(mover);
    const rise = ((exploded ? 1 : 0) - explodeAmt) * lift(k);
    one.setFromObject(o); if (one.isEmpty()) return;
    if (off) { one.min.x -= off.x; one.max.x -= off.x; one.min.y -= off.z; one.max.y -= off.z; one.min.z += off.y; one.max.z += off.y; }   // back to its resting place
    one.min.y += rise; one.max.y += rise;
    const far = reach.get(mover); if (far) { one.min.add(far.min); one.max.add(far.max); }
    for (let i = 0; i < 8; i++) pts.push(new THREE.Vector3(i & 1 ? one.max.x : one.min.x, i & 2 ? one.max.y : one.min.y, i & 4 ? one.max.z : one.min.z));
  }));
  // the measuring lines run outside the board and the case: while they are shown they belong in the picture too
  // (audit of 24 Nov 2026, finding 1: the tight frame had pushed three of the five numbers out of it)
  if (measure && measureGroup) measureGroup.children.forEach((line) => {
    const p = line.geometry.attributes.position;
    for (let i = 0; i < 2; i++) pts.push(line.localToWorld(new THREE.Vector3().fromBufferAttribute(p, i)));
  });
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
  const dist = pts.length ? fitDistance(pts, centre, dir, measure ? 0.8 : 0.88) : fitSphere.radius * 3;   // measuring: room for the number tags at the ends of the lines
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
/** Reset view: the camera only (parts, modes, labels and the animation stay), back to the current step's own view */
let stepAim = { view: "overview", nodes: null };
function resetView() { aimAt(stepAim.view, true, stepAim.nodes); }

// ---------- where every part is: its place, plus the exploded lift, plus the step animation ----------
/** a value part way through a list of [time, value] keys: numbers and [x, y, z] glide, true / false switch at their time */
function keyAt(k, t) {
  if (t <= k[0][0]) return k[0][1];
  for (let i = 0; i < k.length - 1; i++) {
    const a = k[i], b = k[i + 1]; if (t >= b[0]) continue;
    if (typeof a[1] === "boolean") return a[1];
    const e = ease((t - a[0]) / (b[0] - a[0]));
    return typeof a[1] === "number" ? a[1] + (b[1] - a[1]) * e : a[1].map((n, j) => n + (b[1][j] - n) * e);
  }
  return k[k.length - 1][1];
}
const picks = (sel, o) => (sel.includes("__") ? (o.userData.detail || "").startsWith(sel) : o.userData.key === sel);
const animMoving = () => !!anim.def && anim.t < anim.def.dur - 0.001;
const powerNow = () => (animMoving() && anim.def.power ? keyAt(anim.def.power, anim.t) : power);
/** ties the step's tracks to the parts they move and the cables they bend; the animation waits at its end */
function bindPlay(def) {
  anim.def = def || null; anim.moves = []; anim.bends = []; anim.playing = false; anim.t = def ? def.dur : 0;
  (def ? def.tracks : []).forEach((t) => {
    const names = t.plug ? PLUGS[t.plug].on : t.on;
    anim.moves.push({ k: t.k, objs: [...home.keys()].filter((o) => names.some((n) => picks(n, o))) });
    if (t.plug && cables[PLUGS[t.plug].cable]) anim.bends.push({ k: t.k, cable: cables[PLUGS[t.plug].cable], end: t.plug });
  });
}
function place() {
  const t = anim.t, moving = animMoving();
  if (moving && anim.def.explode) { explodeAmt = keyAt(anim.def.explode, t); exploded = explodeAmt > 0.5; }
  if (exploded !== openShown) { openShown = exploded; press("b-exploded", exploded); press("b-assembled", !exploded); }
  offsets.clear();
  if (moving) anim.moves.forEach((m) => { const mv = keyAt(m.k, t); m.objs.forEach((o) => { let a = offsets.get(o); if (!a) offsets.set(o, a = new THREE.Vector3()); a.x += mv[0]; a.y += mv[1]; a.z += mv[2]; }); });
  home.forEach((h, o) => { const a = offsets.get(o); o.position.set(h.x + (a ? a.x : 0), h.y + (a ? a.y : 0), h.z + explodeAmt * lift(o.userData.key) + (a ? a.z : 0)); });
  // cables: bent toward a plug that is on its way; hidden while the case is open (they would hang in the air)
  Object.values(cables).forEach((cb) => {
    const pulls = moving ? anim.bends.filter((b) => b.cable === cb).map((b) => [cb.pull[b.end], keyAt(b.k, t)]) : [];
    const sig = pulls.map((p) => p[1].map((n) => n.toFixed(2)).join()).join("|"); if (sig === cb.was) return; cb.was = sig;
    const arr = cb.pos.array; arr.set(cb.rest);
    pulls.forEach(([w, mv]) => { for (let i = 0; i < w.length; i++) if (w[i] > 0) { arr[3 * i] += mv[0] * w[i]; arr[3 * i + 1] += mv[1] * w[i]; arr[3 * i + 2] += mv[2] * w[i]; } });
    cb.pos.needsUpdate = true;
  });
  const noCables = explodeAmt > 0.01 || (moving && !!anim.def.hideCables);
  (groups.cable || []).forEach((o) => { o.visible = !noCables; });
  const lit = powerNow(); if (lit !== litNow) { litNow = lit; paint(); }
}

// ---------- Play per step ----------
const playBtn = $("b-play"), seekBar = $("v-seek"), playNote = $("v-playnote");
function showPlay() {
  const d = anim.def;
  playBtn.disabled = seekBar.disabled = !d;
  playBtn.textContent = anim.playing ? "⏸ Pause" : "▶ Play"; press("b-play", anim.playing);
  playNote.textContent = d ? d.note : "Nothing moves in this step";
  if (!anim.playing || !d) seekBar.value = d ? Math.round(1000 * anim.t / d.dur) : 1000;
}
function endPlay() { if (anim.def) { anim.t = anim.def.dur; anim.playing = false; showPlay(); } }
function seek(t) {
  if (!anim.def) return;
  anim.playing = false; anim.t = Math.max(0, Math.min(anim.def.dur, t));
  // a step that opens the case (step 2): the slider decides how far open it is, at its very end too
  // (audit of 24 Nov 2026, finding 9: a jump from the start to the end left the case shut, though playing ends with it open)
  if (anim.def.explode) { explodeTween = null; explodeAmt = keyAt(anim.def.explode, anim.t); exploded = explodeAmt > 0.5; }
  else if (animMoving() && exploded) setExploded(false, false);
  place(); showPlay();
}
function play() {
  if (!anim.def) return;
  if (!animMoving()) anim.t = 0;                         // at the end: start again from the beginning
  if (!anim.def.explode && exploded) setExploded(false, false);
  anim.playing = true; anim.last = performance.now(); showPlay();
}
playBtn.onclick = () => { if (anim.playing) { anim.playing = false; showPlay(); } else play(); };
seekBar.addEventListener("input", () => { if (anim.def) seek(anim.def.dur * seekBar.value / 1000); });

// ---------- modes ----------
function setExploded(on, animate = true) {
  exploded = on;
  const from = explodeAmt, to = on ? 1 : 0, t0 = performance.now();
  if (!animate) { explodeAmt = to; explodeTween = null; }
  else explodeTween = (now) => { const e = ease(Math.min(1, (now - t0) / 1200)); explodeAmt = from + (to - from) * e; if (e >= 1) explodeTween = null; };
  press("b-exploded", on); press("b-assembled", !on); openShown = on;
}
const hsl = {};
function paint() {
  const lit = powerNow();
  Object.entries(groups).forEach(([k, list]) => list.forEach((o) => {
    const m = o.material, b = o.userData.base, xr = xray && CASE.includes(k), glow = !!focus && focus.includes(k), dim = !!focus && !glow;
    const seeThrough = xr || dim || b.clear;
    // three.js only rebuilds a material when told to: without needsUpdate a part first drawn solid stays solid
    // (final audit FA-03: 'See inside', 'Show measurements' and the step highlighting did nothing after a normal load)
    if (m.transparent !== seeThrough) { m.transparent = seeThrough; m.needsUpdate = true; }
    m.opacity = xr ? 0.14 : dim ? 0.62 * b.opacity : b.opacity;
    m.depthWrite = !(xr || dim);
    m.color.copy(b.color); m.emissive.copy(b.emissive); m.emissiveIntensity = b.glow;
    if (dim && !xr) { m.color.lerp(SLATE, 0.55); m.emissive.setScalar(0); }        // the other parts: darker slate, mostly solid (as on the drone guide)
    else if (glow && !xr) {                                                        // this step's parts: orange glow, tinted toward orange
      b.color.getHSL(hsl); const pale = hsl.l > 0.75;                              // near-white parts need more tint and less light
      if (m.map) { m.color.lerp(EMBER, 0.35); m.emissive.copy(EMBER); m.emissiveIntensity = 0.16; }   // a part with a picture on it (the wood) keeps its grain
      else { m.color.lerp(EMBER, pale ? 0.9 : 0.65); if (pale) m.color.multiplyScalar(0.5); m.emissive.copy(EMBER); m.emissiveIntensity = pale ? 0.1 : 0.75; }
    }
    if (lit && /led/.test(o.userData.detail)) { m.emissive.copy(b.color); m.emissiveIntensity = 2.5; }
  }));
}
function press(id, on) { const b = $(id); if (b) b.setAttribute("aria-pressed", on ? "true" : "false"); }
$("b-assembled").onclick = () => { endPlay(); setExploded(false); focus = null; paint(); caption.textContent = DEFAULT_CAPTION; aimAt("overview"); };
// the measuring lines belong to the closed box seen from above: Exploded or See inside switches them off
function setMeasure(on) { measure = on; press("b-measure", on); if (measureGroup) measureGroup.visible = on; xray = on; press("b-xray", on); paint(); }
$("b-exploded").onclick = () => { endPlay(); if (measure) setMeasure(false); setExploded(true); aimAt("overview", true, BOX_PARTS); };
$("b-xray").onclick = () => { if (measure) { setMeasure(false); return; } xray = !xray; press("b-xray", xray); paint(); };
$("b-labels").onclick = () => { labelsOn = !labelsOn; press("b-labels", labelsOn); store.set("labels", labelsOn ? "1" : "0"); };   // remembered for next time
$("b-measure").onclick = () => { setMeasure(!measure); if (measure) { endPlay(); setExploded(false, false); aimAt("top", true, ["board"]); } };
$("b-power").onclick = () => { power = !power; press("b-power", power); paint(); };
$("b-spin").onclick = () => { spin = !spin; press("b-spin", spin); };
$("b-reset").onclick = resetView;
// Full screen as on the drone guide: the real full screen where the browser has one for a page element; otherwise
// (iPhone Safari), or when it fails, the 3D view fills the screen as an overlay with a Close button. Esc closes both.
const vwrap = $("vwrap");
function isFull() { return document.fullscreenElement === vwrap || vwrap.classList.contains("v-overlay"); }
function setFullLabel() {
  $("b-full").textContent = isFull() ? "Close full screen" : "Full screen"; press("b-full", isFull());
  // Full screen on a phone: the view buttons fold shut under their "Views" heading, so the model gets the screen; a tap opens them.
  // Everywhere else they are simply there (audit of 24 Nov 2026, finding 6).
  $("views").open = !(isFull() && window.matchMedia("(max-width: 899px)").matches);
}
function closeOverlay() { vwrap.classList.remove("v-overlay"); document.documentElement.classList.remove("v-locked"); setFullLabel(); }
function openOverlay() { vwrap.classList.add("v-overlay"); document.documentElement.classList.add("v-locked"); setFullLabel(); }
function leaveFull() { if (vwrap.classList.contains("v-overlay")) closeOverlay(); else if (document.fullscreenElement) document.exitFullscreen(); }
$("b-full").onclick = () => {
  if (vwrap.classList.contains("v-overlay") || document.fullscreenElement) { leaveFull(); return; }
  if (typeof vwrap.requestFullscreen === "function") vwrap.requestFullscreen().catch(openOverlay); else openOverlay();
};
$("b-fullclose").onclick = leaveFull;                     // the Close button at the top of the full-screen view (a phone has no Esc key)
document.addEventListener("fullscreenchange", setFullLabel);
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && vwrap.classList.contains("v-overlay")) closeOverlay(); });

// ---------- point at a part with the mouse, or tap it: its name and how exact its drawing is ----------
// a tapped name stays for 5 seconds; a pointed-at name stays while the mouse is on the part; a drag is never a tap
const tag = document.createElement("div"); tag.className = "vtag"; host.appendChild(tag);
const ray = new THREE.Raycaster(), fingers = new Set();
let downAt = null, tagTimer = 0, tagFor = null, tagPointed = false, pointAt = null;
function showTag(o, x, y, pointed = false) {
  if (!o) {
    if (pointed && !tagPointed) return;                   // the mouse over nothing leaves a tapped name up for its 5 seconds
    clearTimeout(tagTimer); tag.style.display = "none"; tagFor = null; return;
  }
  clearTimeout(tagTimer);
  if (o !== tagFor) {
    tag.replaceChildren();
    const b = document.createElement("b"); b.textContent = o.userData.part || LABELS[o.userData.key] || o.userData.key; tag.appendChild(b);
    if (ACC[o.userData.acc]) { const sp = document.createElement("span"); sp.textContent = ACC[o.userData.acc]; tag.appendChild(sp); }
  }
  tagFor = o; tagPointed = pointed;
  tag.style.display = "block";
  tag.style.left = Math.max(4, Math.min(host.clientWidth - tag.offsetWidth - 4, x + 12)) + "px";
  tag.style.top = Math.max(4, Math.min(host.clientHeight - tag.offsetHeight - 4, y + 12)) + "px";
  if (!pointed) tagTimer = setTimeout(() => { tag.style.display = "none"; tagFor = null; }, 5000);
}
function pick(cx, cy, pointed = false) {
  if (!gltfScene) return;
  const r = renderer.domElement.getBoundingClientRect();
  ray.setFromCamera(new THREE.Vector2(((cx - r.left) / r.width) * 2 - 1, -((cy - r.top) / r.height) * 2 + 1), camera);
  // a part you can see through (See inside) is not in the way: the tap goes to what is behind it
  const hit = ray.intersectObject(gltfScene, true).find((h) => h.object.isMesh && h.object.visible && h.object.material.opacity > 0.2);
  showTag(hit ? hit.object : null, cx - r.left, cy - r.top, pointed);
}
const cnv = renderer.domElement;
function tapDown(id, x, y) { fingers.add(id); downAt = fingers.size === 1 ? [x, y] : null; }    // a second finger is a pinch, not a tap
function tapUp(id, x, y) { const d = downAt; downAt = null; fingers.delete(id); if (d && Math.hypot(x - d[0], y - d[1]) < 6) pick(x, y); }   // moved 6 px or more: a drag
cnv.addEventListener("pointerdown", (e) => tapDown(e.pointerId, e.clientX, e.clientY));
cnv.addEventListener("pointerup", (e) => tapUp(e.pointerId, e.clientX, e.clientY));
cnv.addEventListener("pointercancel", (e) => { fingers.delete(e.pointerId); downAt = null; });
// the mouse resting on a part names it (looked up once per drawn frame); while a button is held it is a drag, so no name
cnv.addEventListener("pointermove", (e) => { if (e.pointerType !== "mouse") return; pointAt = e.buttons ? null : [e.clientX, e.clientY]; if (e.buttons && tagPointed) showTag(null); });
cnv.addEventListener("pointerleave", () => { pointAt = null; if (tagPointed) showTag(null); });

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
  stepIdx = Math.max(0, Math.min(STEPS.length - 1, i)); playWhenReady = false;
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
  bindPlay(STEP_PLAY[s.n]); showPlay(); showTag(null);        // the step's animation waits at its end: the finished step
  focus = s.focus && s.focus.length ? [...new Set(s.focus.map(baseKey))] : null;
  setExploded(!!(focus && focus.some((k) => PI.includes(k)) && view !== "front"), animate);
  power = extra === "power"; press("b-power", power);
  measure = extra === "measure"; press("b-measure", measure); if (measureGroup) measureGroup.visible = measure;
  // a close look at the box while it runs (steps 7 and 11): the case is drawn see-through, so the lights and the fan show.
  // (Audit of 24 Nov 2026, finding 4: with the case shut, Play in step 11 changed nothing you could see.)
  const seeIn = extra === "power" && !!frame, seeInWords = "the case is drawn see-through so you can watch the lights and the fan";
  xray = measure || view === "under" || seeIn; press("b-xray", xray);
  caption.textContent = focus ? "Step " + s.n + ": " + s.title + " — the glowing parts are the ones this step uses." + (seeIn ? " Here " + seeInWords + "." : "")
    : seeIn ? "Step " + s.n + ": " + s.title + " — " + seeInWords + "." : DEFAULT_CAPTION;
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
// "Watch it in 3D" on a Build step opens that step here and plays it
window.addEventListener("guide-focus", (e) => { const j = STEPS.findIndex((s) => "Step " + s.n + ": " + s.title === e.detail.title); renderStep(j >= 0 ? j : 0); if (groups.board) play(); else playWhenReady = true; });
document.body.dataset.viewerReady = "yes";              // js/app2.js waits for this before it sends 'Watch it in 3D' here

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
  // nothing is worked out or drawn while the 3D view is not on screen (Home, Build or Buy is open): that spares a phone's battery
  // (audit of 24 Nov 2026, finding 5: the whole scene was drawn every frame behind the other tabs)
  if (!host.clientWidth || !host.clientHeight) return;
  if (tween) tween(now);
  if (explodeTween) explodeTween(now);
  if (anim.playing) {   // the parts keep moving while you turn and zoom: the camera is yours
    anim.t = Math.min(anim.def.dur, anim.t + Math.min(0.1, (now - anim.last) / 1000)); anim.last = now;
    seekBar.value = Math.round(1000 * anim.t / anim.def.dur);
    if (!animMoving()) { anim.playing = false; showPlay(); }
  }
  if (home.size && !topView) place();
  if (pointAt) { pick(pointAt[0], pointAt[1], true); pointAt = null; }
  if (spin) root.rotation.y += 0.004;
  if (powerNow() && fanPivot && !still) fanPivot.rotation.z += 0.35;
  controls.update();
  renderer.render(scene, camera);
  placeLabels();
});

// read-only numbers for the page check (checks/selftest.html): camera, zoom limits, the floor angle, the animation, the highlight
window.__view = () => {
  const one = (name) => Object.values(groups).flat().find((o) => o.userData.detail === name), lid = one("case_lid"), mic = one("mic"), shelf = one("shelf");
  return { dist: camera.position.distanceTo(controls.target), min: controls.minDistance, max: controls.maxDistance,
    polar: controls.getPolarAngle(), maxPolar: controls.maxPolarAngle, moved: userMoved, damping: controls.enableDamping, tweening: !!tween,
    playT: anim.t, playDur: anim.def ? anim.def.dur : 0, playing: anim.playing, lidUp: lid ? lid.position.z - home.get(lid).z : null,
    lit: !!powerNow(), fanTurn: fanPivot ? fanPivot.rotation.z : 0, seeInside: xray,
    micGlow: mic ? mic.material.emissive.getHexString() : "", micGlowPower: mic ? mic.material.emissiveIntensity : 0, shelfOpacity: shelf ? shelf.material.opacity : null,
    tag: tag.style.display === "block" ? tag.textContent : "", labels: labelsOn, tone: renderer.toneMapping === THREE.ACESFilmicToneMapping ? renderer.toneMappingExposure : 0 };
};
// for the page check only: a press and a release at a spot (through the same code as a real finger), 'drag' px apart
window.__tap = (x, y, drag = 0) => { tapDown(-7, x, y); tapUp(-7, x + drag, y); };
window.__point = (x, y) => pick(x, y, true);          // the mouse resting at a spot
// for the page check only: where a part is on the screen, so the test can tap it
window.__spot = (name) => {
  const o = Object.values(groups).flat().find((m) => m.userData.detail === name); if (!o) return null;
  const c = new THREE.Box3().setFromObject(o).getCenter(new THREE.Vector3()), r = renderer.domElement.getBoundingClientRect(), p = project(c, r.width, r.height);
  return { x: r.left + p.x, y: r.top + p.y };
};
