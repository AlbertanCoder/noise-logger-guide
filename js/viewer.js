// 3D viewer. The page scrolls normally until "Move the model" is pressed (UI fix 2).
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const host = document.getElementById("viewer");
const caption = document.getElementById("vcaption");
const LABELS = JSON.parse(document.getElementById("model-labels").textContent);
const LABEL_STEP = JSON.parse(document.getElementById("label-steps").textContent);
const PI_PARTS = ["board", "gpio", "usb-c_power", "micro-hdmi_0", "micro-hdmi_1", "ethernet", "usb_stack_lower", "usb_stack_upper", "cooler", "fan", "sdcard"];
const TO_CONFIRM = ["ethernet", "usb_stack_lower", "usb_stack_upper", "gpio", "mic"]; // sizes not from the drawing -> see-through
const DEFAULT_CAPTION = caption.textContent;
const COLORS = { case_base: 0xe9e2d0, case_lid: 0xe9e2d0, mic_cradle: 0xe9e2d0, board: 0x2f7d4f, gpio: 0x202225, cooler: 0xb8bcc2, fan: 0x2a2d31,
  sdcard: 0x3b82c4, ethernet: 0xc9ced3, usb_stack_lower: 0x2f6fd6, usb_stack_upper: 0x30343a, mic: 0x1d1f22 };
const DEFAULT_PORT = 0xc9ced3;
const OVERVIEW_LABELS = ["case_base", "case_lid", "mic_cradle", "mic"]; // assembled view: few labels, no clutter (UI fix 6)

const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
host.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xeef1ee);
scene.add(new THREE.HemisphereLight(0xffffff, 0xc8c2b4, 1.6));
const sun = new THREE.DirectionalLight(0xffffff, 1.4); sun.position.set(1, 2, 1.5); scene.add(sun);
const camera = new THREE.PerspectiveCamera(35, 1, 1, 5000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enabled = false;            // not grabbed: wheel and swipes scroll the page
const root = new THREE.Group(); scene.add(root);
const nodes = {}, home = {}, labelEls = {};
let spin = false, exploded = false, focus = null, topView = false;

let fitSphere = null;
const VIEW_DIR = new THREE.Vector3(0.2, 0.75, 0.95).normalize();
function fitCamera() {  // whole model in view on any screen shape (narrow phones need more distance)
  if (!fitSphere) return;
  const vfov = THREE.MathUtils.degToRad(camera.fov);
  const hfov = 2 * Math.atan(Math.tan(vfov / 2) * camera.aspect);
  const dist = fitSphere.radius / Math.sin(Math.min(vfov, hfov) / 2) * 1.05;
  controls.target.copy(fitSphere.center);
  camera.position.copy(fitSphere.center).addScaledVector(VIEW_DIR, dist);
  controls.update();
}
function resize() {
  const w = host.clientWidth, h = host.clientHeight;
  renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); fitCamera();
}
new ResizeObserver(resize).observe(host); resize();

new GLTFLoader().load("models/noise-logger.glb", (gltf) => {
  const model = gltf.scene;
  model.rotation.x = -Math.PI / 2;   // the parts were made Z-up (like a printer); three.js is Y-up
  root.add(model);
  model.traverse((o) => {
    if (o.isMesh) {
      o.material = o.material.clone();
      const key = keyOf(o);
      o.material.vertexColors = false;
      o.material.color = new THREE.Color(COLORS[key] !== undefined ? COLORS[key] : DEFAULT_PORT);
      o.material.roughness = 0.75; o.material.metalness = 0.05;
      if (TO_CONFIRM.includes(key)) { o.material.transparent = true; o.material.opacity = 0.55; }
    }
  });
  model.traverse((o) => { const k = o.name; if (k && !nodes[k] && (LABELS[k] || PI_PARTS.includes(k) || k.startsWith("case") || k.startsWith("mic"))) { nodes[k] = o; home[k] = o.position.clone(); } });
  fitSphere = new THREE.Box3().setFromObject(root).getBoundingSphere(new THREE.Sphere());
  fitCamera();
  if (new URLSearchParams(location.search).get("view") === "top") {  // proof view: board from above, like the official drawing
    topView = true;
    ["case_lid", "case_base", "mic", "mic_cradle", "cooler", "fan"].forEach((k) => { if (nodes[k]) nodes[k].visible = false; });
    const b = new THREE.Box3().setFromObject(nodes.board), c = b.getCenter(new THREE.Vector3());
    controls.target.copy(c); camera.position.set(c.x, c.y + 260, c.z + 0.01); camera.fov = 20; camera.updateProjectionMatrix(); controls.update();
    fitSphere = null; document.querySelectorAll(".vlabel").forEach((e) => e.remove()); Object.keys(labelEls).forEach((k) => delete labelEls[k]);
  }
  Object.keys(LABELS).forEach((k) => {
    if (!nodes[k] || topView) return;
    const b = document.createElement("button");
    b.className = "vlabel"; b.type = "button"; b.textContent = LABELS[k];
    b.addEventListener("click", () => { const s = document.getElementById("step-" + LABEL_STEP[k]); if (s) s.scrollIntoView({ behavior: "smooth" }); });
    host.appendChild(b); labelEls[k] = b;
  });
  document.body.dataset.modelLoaded = "yes";
}, undefined, (err) => { host.insertAdjacentHTML("beforeend", "<p style='padding:12px'>The 3D model could not load: " + err.message + "</p>"); });

function keyOf(o) { let p = o; while (p) { if (LABELS[p.name] || PI_PARTS.includes(p.name) || (p.name || "").startsWith("case") || (p.name || "").startsWith("mic")) return p.name; p = p.parent; } return ""; }

function setExploded(on) {
  exploded = on;
  Object.keys(nodes).forEach((k) => {
    const n = nodes[k], h = home[k]; if (!h) return;
    n.position.copy(h);
    if (!on) return;
    // model space is Z-up: lift the Pi out of the case, and the lid higher still
    if (k === "case_lid") n.position.z += 45;
    else if (PI_PARTS.includes(k)) n.position.z += 22;
    if (k === "cooler" || k === "fan") n.position.z += 14;
  });
  press("b-exploded", on); press("b-assembled", !on);
}

function setFocus(list, title) {
  focus = list && list.length ? list : null;
  Object.values(nodes).forEach((n) => n.traverse((o) => {
    if (!o.isMesh) return;
    const k = keyOf(o), on = !focus || focus.includes(k);
    o.material.emissive = new THREE.Color(on && focus ? 0x1b5e4f : 0x000000);
    o.material.emissiveIntensity = on && focus ? 0.35 : 0;
    o.material.transparent = !on || TO_CONFIRM.includes(k);
    o.material.opacity = on ? (TO_CONFIRM.includes(k) ? 0.55 : 1) : 0.15;
  }));
  caption.textContent = focus ? title + " — the highlighted parts are the ones this step uses." : DEFAULT_CAPTION;
}

function press(id, on) { document.getElementById(id).setAttribute("aria-pressed", on ? "true" : "false"); }
document.getElementById("b-assembled").onclick = () => { setExploded(false); setFocus(null); };
document.getElementById("b-exploded").onclick = () => setExploded(true);
document.getElementById("b-spin").onclick = () => { spin = !spin; press("b-spin", spin); };
document.getElementById("b-grab").onclick = () => {
  controls.enabled = !controls.enabled;
  host.classList.toggle("grabbed", controls.enabled);
  press("b-grab", controls.enabled);
  document.getElementById("b-grab").textContent = controls.enabled ? "Done moving (scroll the page again)" : "Move the model";
};
window.addEventListener("guide-focus", (e) => { setExploded(e.detail.nodes.some((k) => PI_PARTS.includes(k))); setFocus(e.detail.nodes, e.detail.title); });

const v = new THREE.Vector3();
function placeLabels() {
  const w = host.clientWidth, h = host.clientHeight;
  const shown = [];
  Object.keys(labelEls).forEach((k) => {
    const n = nodes[k], b = labelEls[k];
    const box = new THREE.Box3().setFromObject(n); box.getCenter(v); v.y = box.max.y;
    v.project(camera);
    const x = (v.x * 0.5 + 0.5) * w, y = (-v.y * 0.5 + 0.5) * h;
    const wanted = focus ? focus.includes(k) : (exploded || OVERVIEW_LABELS.includes(k));
    const visible = wanted && v.z < 1 && x > 0 && x < w && y > 14 && y < h;
    b.style.display = visible ? "" : "none";
    if (visible) shown.push({ b, x, y });
  });
  // nudge overlapping labels apart so none hides another
  shown.sort((a, c) => a.y - c.y);
  for (let i = 0; i < shown.length; i++) {
    for (let j = 0; j < i; j++) {
      const a = shown[j], c = shown[i];
      if (Math.abs(a.x - c.x) < 120 && c.y - a.y < 30) c.y = a.y + 30;
    }
  }
  shown.forEach(({ b, x, y }) => {  // keep every label fully inside the viewer
    const half = b.offsetWidth / 2 + 4;
    b.style.left = Math.max(half, Math.min(w - half, x)) + "px";
    b.style.top = Math.max(b.offsetHeight + 4, Math.min(y, h - 4)) + "px";
  });
}
renderer.setAnimationLoop(() => {
  if (spin) root.rotation.y += 0.005;
  controls.update();
  renderer.render(scene, camera);
  placeLabels();
});
