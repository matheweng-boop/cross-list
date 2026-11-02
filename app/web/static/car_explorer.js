// Car explorer (Systems & applications; owner, 2 Nov 2026): the approved mockup's see-through car, built from simple
// shapes in code (no model file). The page (business/car_explorer.html) shows the area buttons and lists itself,
// checks for WebGL and loads this module only when the browser has it. three.js 0.160.0 (MIT, see
// /static/vendor/three/LICENSE) is served from this site; "three" resolves through the page's import map.
// Light on an iPad: pixel ratio at most 2, no shadows, drawing only while the car is on screen.
import * as THREE from "three";
import { OrbitControls } from "/static/vendor/three/OrbitControls.js";

const ui = window.carExplorer;
const canvas = document.getElementById("ce-canvas");
const stage = document.getElementById("ce-stage");
const tip = document.getElementById("ce-tip");
const back = document.getElementById("ce-back");
const hint = document.getElementById("ce-hint");

let renderer = null;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "low-power" });
} catch (e) {
  ui.no3d(); // WebGL was there for the page's check but not for the car: the buttons and lists still work
}
if (renderer) start(renderer);

function start(renderer) {
  const AREAS = Object.fromEntries(ui.areas.map((a) => [a.id, a]));
  const HINT = hint.textContent;
  const root = document.documentElement;
  const dark = root.dataset.theme === "dark" ||
    (root.dataset.theme !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 100);
  // home view; a tall, narrow stage (a phone) moves the camera back so the whole car stays in view
  const TARGET = new THREE.Vector3(0, 0.6, 0);
  const OFFSET = new THREE.Vector3(4.6, 2.0, 5.4);
  const homePos = () => TARGET.clone().add(OFFSET.clone().multiplyScalar(Math.min(2.2, Math.max(1, 1.25 / camera.aspect))));
  camera.position.copy(TARGET).add(OFFSET);
  const controls = new OrbitControls(camera, canvas);
  controls.target.copy(TARGET);
  controls.enableDamping = true;
  controls.minDistance = 1.5;
  controls.maxDistance = 20;
  controls.maxPolarAngle = Math.PI * 0.49;
  controls.autoRotate = true; // slowly, until someone touches the car
  controls.autoRotateSpeed = 0.86;
  let touched = false;
  controls.addEventListener("start", () => { touched = true; controls.autoRotate = false; });

  scene.add(new THREE.HemisphereLight(0xffffff, dark ? 0x223344 : 0xb8c4d6, 1.6));
  const sun = new THREE.DirectionalLight(0xffffff, 1.6);
  sun.position.set(5, 8, 6);
  scene.add(sun);
  const ground = new THREE.Mesh(new THREE.CircleGeometry(9, 64),
    new THREE.MeshStandardMaterial({ color: dark ? 0x262b35 : 0xe9ecf3 }));
  ground.rotation.x = -Math.PI / 2;
  scene.add(ground);

  const mat = (c, o = {}) => new THREE.MeshStandardMaterial({ color: c, roughness: 0.55, metalness: 0.1, ...o });
  const car = new THREE.Group();
  scene.add(car);
  // body shell: an extruded side profile, see-through so the inside shows
  const W = 1.85;
  const prof = new THREE.Shape();
  prof.moveTo(-2.3, 0.35); prof.lineTo(-2.3, 0.75); prof.quadraticCurveTo(-2.25, 0.95, -1.6, 1.0);
  prof.lineTo(-0.85, 1.05); prof.quadraticCurveTo(-0.5, 1.55, 0.1, 1.58); prof.lineTo(1.0, 1.56);
  prof.quadraticCurveTo(1.5, 1.5, 1.85, 1.1); prof.lineTo(2.25, 1.02); prof.quadraticCurveTo(2.35, 0.9, 2.33, 0.55);
  prof.lineTo(2.3, 0.35); prof.closePath();
  const bodyGeo = new THREE.ExtrudeGeometry(prof, { depth: W, bevelEnabled: true, bevelSize: 0.08, bevelThickness: 0.12,
    bevelSegments: 4, curveSegments: 24 });
  bodyGeo.translate(0, 0, -W / 2);
  car.add(new THREE.Mesh(bodyGeo, mat(dark ? 0x6f86a8 : 0x9fb3d1, { transparent: true, opacity: 0.28, depthWrite: false })));
  car.add(new THREE.LineSegments(new THREE.EdgesGeometry(bodyGeo, 25),
    new THREE.LineBasicMaterial({ color: dark ? 0x9aa3b2 : 0x5d6676 })));
  const floor = new THREE.Mesh(new THREE.BoxGeometry(4.3, 0.08, 1.75), mat(0x8a93a3));
  floor.position.y = 0.4;
  car.add(floor);
  const wheelGeo = new THREE.CylinderGeometry(0.36, 0.36, 0.26, 32).rotateX(Math.PI / 2);
  const hubGeo = new THREE.CylinderGeometry(0.16, 0.16, 0.27, 24).rotateX(Math.PI / 2);
  for (const [x, z] of [[-1.45, 0.9], [-1.45, -0.9], [1.5, 0.9], [1.5, -0.9]]) {
    const w = new THREE.Mesh(wheelGeo, mat(0x2a2f3a));
    w.position.set(x, 0.36, z);
    const hub = new THREE.Mesh(hubGeo, mat(0xc9cfdb, { metalness: 0.6 }));
    hub.position.copy(w.position);
    car.add(w, hub);
  }

  // the areas: the ids of data/business/car_areas.yaml
  const zones = [];
  const zone = (key, mesh, x, y, z) => {
    mesh.position.set(x, y, z);
    mesh.userData.zone = key;
    mesh.userData.color = mesh.material.color.getHex();
    mesh.userData.emissive = mesh.material.emissive.getHex();
    zones.push(mesh);
    car.add(mesh);
    return mesh;
  };
  const seat = (x, z, key) => {
    const m = () => mat(0x6b7a8f);
    zone(key, new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.12, 0.48), m()), x, 0.55, z);
    zone(key, new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.6, 0.48), m()), x + 0.25, 0.85, z).rotation.z = -0.15;
    zone(key, new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.16, 0.3), m()), x + 0.32, 1.22, z);
  };
  seat(-0.35, 0.42, "seat"); seat(-0.35, -0.42, "seat");
  seat(0.75, 0.42, "rear-seats"); seat(0.75, -0.42, "rear-seats");
  zone("dashboard", new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.28, 1.6), mat(0x4f5a6b)), -1.0, 0.95, 0);
  const wheel = zone("dashboard", new THREE.Mesh(new THREE.TorusGeometry(0.17, 0.03, 12, 32), mat(0x333a46)), -0.78, 1.05, 0.42);
  wheel.rotation.y = Math.PI / 2;
  wheel.rotation.x = 0.4;
  zone("roof", new THREE.Mesh(new THREE.ConeGeometry(0.1, 0.22, 16).scale(1.8, 1, 0.6), mat(0x3a4150)), 1.0, 1.75, 0);
  zone("front", new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.18, 0.4), mat(0x3d6fb6)), -2.45, 0.6, 0); // radar
  zone("front", new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.08, 0.14), mat(0x3d6fb6)), -0.82, 1.48, 0); // camera
  for (const z of [0.65, -0.65]) {
    zone("lights", new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.12, 0.32), mat(0xffe08a, { emissive: 0x332200 })), -2.42, 0.82, z);
    zone("lights", new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.12, 0.32), mat(0xf08a8a, { emissive: 0x220000 })), 2.45, 0.85, z);
  }
  zone("battery", new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.16, 1.5), mat(0x5aa37f)), 0, 0.27, 0);
  zone("motor", new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.2, 0.5, 24).rotateX(Math.PI / 2),
    mat(0xd08a3c, { metalness: 0.4 })), 1.5, 0.36, 0);
  zone("motor", new THREE.Mesh(new THREE.BoxGeometry(0.4, 0.18, 0.36), mat(0xd08a3c)), 1.95, 0.5, 0); // inverter
  zone("charge-port", new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.05, 20).rotateX(Math.PI / 2),
    mat(0x2f8a7a)), 1.85, 1.0, W / 2 + 0.13);
  zone("charge-port", new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.15, 0.35), mat(0x2f8a7a)), 2.0, 0.75, 0.45); // charger
  for (const s of [1, -1]) {
    zone("doors", new THREE.Mesh(new THREE.BoxGeometry(0.14, 0.1, 0.18), mat(0x4f5a6b)), -0.75, 1.12, s * (W / 2 + 0.2)); // mirror
    zone("doors", new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.04, 0.04), mat(0x4f5a6b)), 0.05, 0.98, s * (W / 2 + 0.13)); // handle
    zone("doors", new THREE.Mesh(new THREE.SphereGeometry(0.05, 16, 12), mat(0x7a3db8)), 0.4, 1.0, s * (W / 2 + 0.12)); // key anchor
  }

  // hover (mouse) and the selected area in one highlight colour
  const ray = new THREE.Raycaster();
  const ptr = new THREE.Vector2();
  let hover = null;
  let selected = null;
  const paint = () => {
    for (const m of zones) {
      const on = m.userData.zone === hover || m.userData.zone === selected;
      m.material.color.setHex(on ? 0x9b5de5 : m.userData.color);
      m.material.emissive.setHex(on ? 0x2a0f45 : m.userData.emissive);
    }
  };
  const pick = (e) => {
    const r = canvas.getBoundingClientRect();
    ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ptr, camera);
    const hit = ray.intersectObjects(zones, false)[0];
    return hit ? hit.object.userData.zone : null;
  };
  const hideTip = () => { tip.style.opacity = "0"; };
  canvas.addEventListener("pointermove", (e) => {
    if (e.pointerType !== "mouse") return; // a finger has no hover: a tap selects
    const k = pick(e);
    if (k !== hover) { hover = k; paint(); }
    canvas.style.cursor = k ? "pointer" : "grab";
    if (!k) { hideTip(); return; }
    const n = AREAS[k] ? AREAS[k].n : 0;
    tip.textContent = `${AREAS[k] ? AREAS[k].title : k} · ${n} car diagram${n === 1 ? "" : "s"} – click to fly in`;
    const r = stage.getBoundingClientRect();
    const x = Math.min(e.clientX - r.left + 12, r.width - tip.offsetWidth - 6);
    tip.style.transform = `translate(${Math.max(6, x)}px, ${e.clientY - r.top + 14}px)`;
    tip.style.opacity = "1";
  });
  canvas.addEventListener("pointerleave", () => { if (hover) { hover = null; paint(); } hideTip(); });
  let down = null;
  canvas.addEventListener("pointerdown", (e) => { down = [e.clientX, e.clientY]; });
  canvas.addEventListener("pointerup", (e) => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 6) return; // a drag turns the car
    const k = pick(e);
    if (k) { select(k); ui.show(k); }
  });

  // flying in and out
  let fly = null;
  const flyTo = (pos, tgt) => {
    fly = { p0: camera.position.clone(), t0: controls.target.clone(), p1: pos, t1: tgt, s: performance.now() };
  };
  const setHint = (id) => {
    if (!id) { hint.textContent = HINT; return; }
    const a = document.createElement("a");
    a.href = `#ce-area-${id}`;
    a.textContent = "list below ↓";
    hint.replaceChildren(`${AREAS[id] ? AREAS[id].title : id} · `, a);
  };
  function select(k) {
    const box = new THREE.Box3();
    for (const m of zones) if (m.userData.zone === k) box.expandByObject(m);
    if (box.isEmpty()) return;
    selected = k;
    paint();
    hideTip();
    controls.autoRotate = false;
    const c = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3()).length();
    const dir = camera.position.clone().sub(controls.target).normalize();
    if (dir.y < 0.25) { dir.y = 0.35; dir.normalize(); }
    flyTo(c.clone().add(dir.multiplyScalar(Math.max(1.6, size * 1.6))), c);
    back.hidden = false;
    setHint(k);
  }
  function home() {
    selected = null;
    paint();
    flyTo(homePos(), TARGET.clone());
    back.hidden = true;
    setHint("");
    controls.autoRotate = !touched;
  }
  back.addEventListener("click", () => { home(); ui.show(""); });
  ui.fly = (id) => (id ? select(id) : home()); // the area buttons below the car
  // for the browser tests: where an area is on the screen (page coordinates of its centre)
  ui.where = (id) => {
    const box = new THREE.Box3();
    for (const m of zones) if (m.userData.zone === id) box.expandByObject(m);
    const p = box.getCenter(new THREE.Vector3()).project(camera);
    const r = canvas.getBoundingClientRect();
    return [r.left + ((p.x + 1) / 2) * r.width, r.top + ((1 - p.y) / 2) * r.height];
  };

  // size, drawing loop (only while the car is on screen), lost context
  const resize = () => {
    const r = stage.getBoundingClientRect();
    if (!r.width || !r.height) return;
    renderer.setSize(r.width, r.height, false);
    camera.aspect = r.width / r.height;
    camera.updateProjectionMatrix();
    if (!touched && !selected && !fly) { // same direction, the home distance for this shape of stage
      const off = camera.position.clone().sub(controls.target).setLength(homePos().sub(TARGET).length());
      camera.position.copy(controls.target).add(off);
    }
  };
  if (window.ResizeObserver) new ResizeObserver(resize).observe(stage);
  else window.addEventListener("resize", resize);
  resize();
  let last = performance.now();
  const frame = (t) => {
    const dt = Math.min(0.1, Math.max(0, (t - last) / 1000));
    last = t;
    if (fly) {
      const k = Math.min(1, (t - fly.s) / 900);
      const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
      camera.position.lerpVectors(fly.p0, fly.p1, e);
      controls.target.lerpVectors(fly.t0, fly.t1, e);
      if (k >= 1) fly = null;
    }
    controls.update(dt);
    renderer.render(scene, camera);
    if (!stage.dataset.ready) stage.dataset.ready = "1"; // drawn at least once (the browser tests wait for it)
  };
  let running = false;
  const run = (on) => {
    if (on === running) return;
    running = on;
    last = performance.now();
    renderer.setAnimationLoop(on ? frame : null);
  };
  if (window.IntersectionObserver) new IntersectionObserver((es) => run(es[es.length - 1].isIntersecting)).observe(stage);
  else run(true);
  canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); run(false); ui.no3d(); });
  if (ui.selected) select(ui.selected); // opened with ?area=…
}
