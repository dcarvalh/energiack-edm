// 3D maps. Geneva: real buildings (SITG), terrain (swissALTI3D), aerial photo (SWISSIMAGE).
// Rive-Claire (fictional commune of the challenge): schematic blocks from tools/make_rive_claire_map.py, measured values per site.
// Loaded on demand by index.html when the "3D map" tab opens. No external requests: three.js is vendored.
import * as THREE from "three";
import { OrbitControls } from "./vendor/OrbitControls.js?v=2";  // patched: wheel zoom, see file
import { computeBoundsTree, acceleratedRaycast } from "./vendor/three-mesh-bvh.module.js";

THREE.BufferGeometry.prototype.computeBoundsTree = computeBoundsTree;
THREE.Mesh.prototype.raycast = acceleratedRaycast;

const V = "13";
const GREY = 0xb9bfbb;
const RAMP = {
  idc:   [0x2e9e6e, 0x9cc95a, 0xf0b33c, 0xe0663a, 0xb8322a],
  solar: [0xfdf1c7, 0xf8d66d, 0xf1b52c, 0xd98b0b],
  elec:  [0xdbe6fb, 0x9fbcf2, 0x5b8be0, 0x2a56b8],
  water: [0xd3f0f4, 0x8fd5e2, 0x3cb3c9, 0x1a7f95],
};
const HEAT = { fossil: 0xe0663a, district: 0x2a9d8f, heatpump: 0x2e9e6e, wood: 0x8a9a3b, electric: 0x7b6fd0 };

// SITG publishes its value lists in French only: English labels for the values that cover ~99 % of buildings.
const EN = {
  "Hab plusieurs logements": "Apartment building", "Hab. - rez activités": "Housing, shops on ground floor",
  "Habitation - activités": "Housing and business", "Habitation un logement": "Single-family house", "Bureaux": "Offices",
  "Garage privé": "Private garage", "Autre bât. 20m2 et plus": "Other building (20 m² +)", "Atelier": "Workshop",
  "Commerce": "Shop", "Dépôt": "Storage", "Hab. deux logements": "Two-family house", "Hôtel": "Hotel",
  "Ecole primaire": "Primary school", "Garage": "Garage", "Autre bât. d'activités": "Other business building",
  "Restaurant": "Restaurant", "Résidence meublée": "Serviced apartments", "Université": "University",
  "Hôpital, Clinique": "Hospital, clinic", "Salle de sport": "Sports hall", "Usine": "Factory", "Autre école": "Other school",
  "Eglise": "Church", "EMS": "Nursing home", "Hangar": "Shed", "Ecole privée": "Private school", "Jardin d'enfants": "Kindergarten",
  "Collège": "Upper secondary school", "Centre de loisirs": "Leisure centre", "Administrations publiques": "Public administration",
  "Musée": "Museum", "Serre": "Greenhouse", "Foyer": "Hostel", "Bât. électricité SIG": "SIG electricity building",
  "Instal. tech. élec. SIG": "SIG electrical installation", "Salle de spectacle": "Performance hall",
  "Autre héberg. collectif": "Other group housing", "Autre bât. de loisirs": "Other leisure building",
  "Bureaux des OIG": "International organisation offices", "Autre équipement collectif": "Other public facility",
  "Mission permanente": "Permanent mission", "Théâtre": "Theatre", "Temple": "Protestant church", "Chapelle": "Chapel", "Poste": "Post office",
  "Gaz": "Gas", "Mazout": "Heating oil", "Chauffage à distance": "District heating", "PAC - Électricité consommée": "Heat pump (electricity used)",
  "PAC - Comptage de chaleur": "Heat pump (heat metered)", "CAD tarifé": "District heating (billed)", "Électricité directe": "Direct electric heating",
  "Électricité PAC (DD après le 5 août 2010)": "Heat pump electricity (after 2010)", "Électricité PAC (DD avant le 5 août 2010)": "Heat pump electricity (before 2010)",
  "Gaz - Sous-comptage de chaleur": "Gas (heat sub-metered)", "Bois - Sous-comptage de chaleur": "Wood (heat sub-metered)",
  "Mazout - Sous-comptage de chaleur": "Heating oil (heat sub-metered)", "Bois en pellets": "Wood pellets", "CAD réparti": "District heating (shared)",
  "Bois en bûches dur": "Hardwood logs", "Bois en bûches tendre": "Softwood logs", "Bois en bûches": "Wood logs", "Bois plaquettes dur": "Hardwood chips",
  "Autre": "Other", "HEL": "Heating oil (HEL)", "Bois a": "Wood (a)", "Bois b": "Wood (b)", "Biogaz": "Biogas", "Electricité": "Electricity",
  "A déterminer": "To be determined", "Géothermie": "Geothermal", "Solaire": "Solar",
  // Rive-Claire (typologies, installations, labels, building names, remarks)
  "Administration": "Administration", "École primaire": "Primary school", "École avec piscine": "School with pool", "Crèche (EVE)": "Nursery",
  "Maison de quartier": "Community centre", "Salle communale": "Community hall", "Bibliothèque": "Library", "Salle de spectacle": "Theatre",
  "Installation sportive": "Sports facility", "Piscine couverte": "Indoor pool", "Patinoire": "Ice rink", "Voirie et ateliers": "Works depot",
  "Caserne de pompiers": "Fire station", "Logements communaux": "Municipal housing", "Abri PC": "Civil-defence shelter", "Cimetière": "Cemetery",
  "Parking souterrain": "Underground car park",
  "Chaudière à gaz": "Gas boiler", "Chaudière à mazout": "Oil boiler", "Chaudière à granulés de bois": "Wood-pellet boiler",
  "Sous-station de chauffage à distance": "District-heating substation", "Pompe à chaleur sol-eau (sondes géothermiques)": "Ground-source heat pump (boreholes)",
  "Pompe à chaleur air-eau": "Air-source heat pump", "Installation photovoltaïque": "Solar PV", "Chauffage électrique direct": "Direct electric heating",
  "Capteurs solaires thermiques (eau chaude sanitaire)": "Solar thermal collectors (hot water)", "Groupe froid de la patinoire": "Ice-rink chiller",
  "Patrimoine recensé": "Listed heritage", "Minergie (rénovation)": "Minergie (renovation)", "Hôtel de ville": "Town hall",
  "Annexe administrative": "Administrative annex", "Bâtiment principal": "Main building", "Pavillon": "Pavilion",
  "Exploitation saisonnière : septembre à mars (saison 2022-23 écourtée par mesure de sobriété : glace arrêtée fin février 2023).":
    "Seasonal operation: September to March (2022-23 season cut short to save energy: ice stopped at the end of February 2023).",
  "Non chauffé : pas de surface de référence énergétique.": "Unheated: no energy reference area.",
};

const bucket = (v, cuts) => { let i = 0; while (i < cuts.length && v >= cuts[i]) i++; return i; };
// Each layer: cls(b) -> class index (or -1 = no data), ramp/labels per class, val(b) -> text for the tooltip
function layers(t, nf) {
  const yr = t("m_yr");
  const heatKeys = ["fossil", "district", "heatpump", "wood", "electric"];
  return {
    idc: { cls: b => b.idc ? bucket(b.idc.mj_m2, [350, 450, 600, 800]) : -1, ramp: RAMP.idc,
           labels: ["< 350", "350–450", "450–600", "600–800", "≥ 800"], unit: "MJ/m²·" + yr,
           val: b => b.idc ? `${nf(b.idc.mj_m2)} MJ/m²` : null },
    heat: { cls: b => b.heat ? heatKeys.indexOf(b.heat) : -1, ramp: heatKeys.map(k => HEAT[k]),
            labels: heatKeys.map(k => t("m_heat_" + k)), val: b => b.heat ? t("m_heat_" + b.heat) : null },
    solar: { cls: b => b.pv ? bucket(b.pv.kwh, [20000, 35000, 50000]) : -1, ramp: RAMP.solar,
             labels: ["< 20", "20–35", "35–50", "≥ 50"], unit: "MWh/" + yr, val: b => b.pv ? `${nf(b.pv.kwh / 1000)} MWh/${yr}` : null },
    elec: { cls: b => b.sim ? bucket(b.sim.elec_kwh, [35000, 60000, 95000]) : -1, ramp: RAMP.elec, sim: true,
            labels: ["< 35", "35–60", "60–95", "≥ 95"], unit: "MWh/" + yr, val: b => b.sim ? `${nf(b.sim.elec_kwh / 1000)} MWh/${yr}` : null },
    water: { cls: b => b.sim ? bucket(b.sim.water_m3, [400, 900, 1800]) : -1, ramp: RAMP.water, sim: true,
             labels: ["< 400", "400–900", "900–1 800", "≥ 1 800"], unit: "m³/" + yr, val: b => b.sim ? `${nf(b.sim.water_m3)} m³/${yr}` : null },
  };
}
// Rive-Claire: measured values per site (meta.year), same layer keys so the UI code is shared
function layersRC(t, nf) {
  const yr = t("m_yr"), heatKeys = ["fossil", "district", "heatpump", "wood", "electric"], mwh = v => `${nf(v / 1000)} MWh/${yr}`;
  return {
    // approximate heat index, same unit and classes as the Geneva IDC layer so the two maps read the same way
    idc: { cls: b => b.rc.mj_m2 == null ? -1 : bucket(b.rc.mj_m2, [350, 450, 600, 800]), ramp: RAMP.idc,
           labels: ["< 350", "350–450", "450–600", "600–800", "≥ 800"], unit: "MJ/m²·" + yr, val: b => b.rc.mj_m2 == null ? null : `${nf(b.rc.mj_m2)} MJ/m²` },
    heat: { cls: b => b.rc.heat ? heatKeys.indexOf(b.rc.heat) : -1, ramp: heatKeys.map(k => HEAT[k]),
            labels: heatKeys.map(k => t("m_heat_" + k)), val: b => b.rc.heat ? t("m_heat_" + b.rc.heat) : null },
    solar: { cls: b => b.rc.pv_kwh ? bucket(b.rc.pv_kwh, [50000, 100000, 150000]) : -1, ramp: RAMP.solar,
             labels: ["< 50", "50–100", "100–150", "≥ 150"], unit: "MWh/" + yr, val: b => b.rc.pv_kwh ? mwh(b.rc.pv_kwh) : null },
    elec: { cls: b => b.rc.elec_kwh ? bucket(b.rc.elec_kwh, [25000, 75000, 150000]) : -1, ramp: RAMP.elec,
            labels: ["< 25", "25–75", "75–150", "≥ 150"], unit: "MWh/" + yr, val: b => b.rc.elec_kwh ? mwh(b.rc.elec_kwh) : null },
    water: { cls: b => b.rc.water_m3 ? bucket(b.rc.water_m3, [500, 1500, 4000]) : -1, ramp: RAMP.water,
             labels: ["< 500", "500–1 500", "1 500–4 000", "≥ 4 000"], unit: "m³/" + yr, val: b => b.rc.water_m3 ? `${nf(b.rc.water_m3)} m³/${yr}` : null },
  };
}
const LAYER_KEYS = ["idc", "heat", "solar", "elec", "water"];
const hex = c => "#" + c.toString(16).padStart(6, "0");
const norm = s => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

export async function initMap(root, api, cfg = { key: "ge", dir: "map/" }) {
  const { t, nf, esc } = api, RC = cfg.key === "rc", DIR = cfg.dir;
  const tr = s => (api.lang() === "en" && EN[s]) || s;
  root.innerHTML = `
    <div class="m3-stage"><div class="m3-loading"><div class="m3-spin"></div><span>${esc(t("m_loading"))}</span></div></div>
    <div class="m3-labels"></div>
    <div class="m3-ui">
      <div class="m3-card">
        <div class="seg m3-maps"><button data-map="rc"></button><button data-map="ge"></button></div>
        <div class="m3-title"></div><div class="m3-sub"></div>
        <div class="m3-search"><input type="search" autocomplete="off"><div class="m3-results hide"></div></div>
        <div class="chips m3-layers"></div>
        <div class="m3-legend"></div>
      </div>
    </div>
    <div class="m3-panel hide"></div>
    <div class="m3-tools"><div class="m3-grp m3-g-mode"><button class="m3-btn" data-tool="pan"><svg viewBox="0 0 24 24"><path d="M12 3v18M3 12h18M12 3 9.5 5.5M12 3l2.5 2.5M12 21l-2.5-2.5M12 21l2.5-2.5M3 12l2.5-2.5M3 12l2.5 2.5M21 12l-2.5-2.5M21 12l-2.5 2.5"/></svg></button><button class="m3-btn" data-tool="orbit"><svg viewBox="0 0 24 24"><ellipse cx="12" cy="12" rx="10" ry="4.5"/><path d="M12 4v16"/><circle cx="12" cy="12" r="1.6"/></svg></button></div><div class="m3-grp"><button class="m3-btn" data-tool="in"><svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></svg></button><button class="m3-btn" data-tool="out"><svg viewBox="0 0 24 24"><path d="M5 12h14"/></svg></button></div><div class="m3-grp m3-g-rot"><button class="m3-btn" data-tool="rl"><svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 1 0 2.4-5.7"/><path d="M4 4v5h5"/></svg></button><button class="m3-btn" data-tool="rr"><svg viewBox="0 0 24 24"><path d="M20 12a8 8 0 1 1-2.4-5.7"/><path d="M20 4v5h-5"/></svg></button></div><div class="m3-grp"><button class="m3-btn" data-tool="top"><b>2D</b></button><button class="m3-btn m3-north" data-tool="north"><svg viewBox="0 0 24 24"><path d="M12 3l4 9h-8z" fill="#e0663a"/><path d="M12 21l-4-9h8z" fill="currentColor" opacity=".45"/></svg></button></div><div class="m3-grp"><button class="m3-btn" data-tool="full"><svg viewBox="0 0 24 24"><path class="fs-in" d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/><path class="fs-out" d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/></svg></button><button class="m3-btn" data-tool="home"><svg viewBox="0 0 24 24"><path d="M3 11.5 12 4l9 7.5M5.5 10v10h13V10"/></svg></button></div></div>
    <div class="m3-foot"><span class="m3-hint"></span></div>
    <div class="m3-attr"></div>`;
  const stage = root.querySelector(".m3-stage");
  const loading = (k) => { const s = stage.querySelector(".m3-loading span"); if (s) s.textContent = t(k); };
  const data = await fetch(DIR + "buildings.json?v=" + V).then(r => r.json());
  loading("m_loading_scene");
  const M = data.meta, B = data.buildings, [W, H] = M.size, { nx, ny, scale, step } = M.terrain, NT = M.tiles || 1;
  if (RC && api.heatIndex) for (const b of B) {            // heat index from the app's own figures (one calculation for table, site page and map)
    const x = api.heatIndex(b.site, b.rc.year);
    b.rc.mj_m2 = x && x.hi != null ? Math.round(x.hi) : null; b.rc.hi_est = !!(x && x.hiEst);
  }
  const [terr, imgs] = await Promise.all([
    fetch(DIR + "terrain.bin?v=" + V).then(r => r.arrayBuffer()).then(b => new Int16Array(b)),
    Promise.all(Array.from({ length: NT * NT }, (_, k) => new Promise((res, rej) => {
      const i = k % NT, j = Math.floor(k / NT), im = new Image();
      im.onload = () => res({ i, j, im }); im.onerror = rej; im.src = `${DIR}aerial_${i}_${j}.jpg?v=${V}`;
    }))),
  ]);
  await new Promise(r => setTimeout(r, 30));   // let the "building the scene" text paint
  const T0 = performance.now();

  // ---------------------------------------------------------------- scene
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(40, 1, 10, 40000);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.screenSpacePanning = false;
  controls.mouseButtons = { LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.ROTATE };
  controls.touches = { ONE: THREE.TOUCH.PAN, TWO: THREE.TOUCH.DOLLY_ROTATE };
  controls.enableDamping = true; controls.dampingFactor = 0.12; controls.zoomSpeed = 1.2;
  controls.maxPolarAngle = 1.3; controls.minDistance = 60; controls.maxDistance = Math.max(W, H) * 1.6;
  const HOME = RC   // Rive-Claire: shift left so the north-west quarter is not under the card
    ? { pos: new THREE.Vector3(-W * 0.3, Math.max(W, H) * 0.62, H * 0.92), target: new THREE.Vector3(-W * 0.13, 0, -H * 0.02) }
    : { pos: new THREE.Vector3(-W * 0.18, Math.max(W, H) * 0.42, H * 0.72), target: new THREE.Vector3(0, 0, -H * 0.04) };

  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8f8c, 2.3));
  const sun = new THREE.DirectionalLight(0xfff4e6, 2.2); sun.position.set(-0.6, 1, 0.45).multiplyScalar(1000); scene.add(sun);

  // terrain: one mesh per aerial tile; grid from swissALTI3D
  const hAt = (r, c) => terr[r * nx + c] * scale;
  const groundMat = [];
  const segX = (nx - 1) / NT, segY = (ny - 1) / NT;
  for (const { i, j, im } of imgs) {
    const g = new THREE.PlaneGeometry(W / NT, H / NT, segX, segY); g.rotateX(-Math.PI / 2);
    g.translate(-W / 2 + (i + 0.5) * W / NT, 0, -H / 2 + (j + 0.5) * H / NT);
    const p = g.attributes.position;
    for (let r = 0; r <= segY; r++) for (let c = 0; c <= segX; c++) p.setY(r * (segX + 1) + c, hAt(j * segY + r, i * segX + c));
    g.computeVertexNormals();
    const tex = new THREE.Texture(im); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = renderer.capabilities.getMaxAnisotropy(); tex.needsUpdate = true;
    const m = new THREE.MeshLambertMaterial({ map: tex }); groundMat.push(m);
    scene.add(new THREE.Mesh(g, m));
  }
  // plinth: a clean base under the map edge, like a physical model
  const base = -25, sk = [];
  const edge = (pts) => { for (let k = 0; k < pts.length - 1; k++) { const [a, b] = [pts[k], pts[k + 1]]; sk.push(a[0], a[1], a[2], b[0], base, b[2], b[0], b[1], b[2], a[0], a[1], a[2], a[0], base, a[2], b[0], base, b[2]); } };
  const X = c => -W / 2 + c * step, Z = r => -H / 2 + r * step;
  edge(Array.from({ length: nx }, (_, c) => [X(c), hAt(0, c), Z(0)]));
  edge(Array.from({ length: nx }, (_, c) => [X(nx - 1 - c), hAt(ny - 1, nx - 1 - c), Z(ny - 1)]));
  edge(Array.from({ length: ny }, (_, r) => [X(0), hAt(ny - 1 - r, 0), Z(ny - 1 - r)]));
  edge(Array.from({ length: ny }, (_, r) => [X(nx - 1), hAt(r, nx - 1), Z(r)]));
  const skg = new THREE.BufferGeometry(); skg.setAttribute("position", new THREE.Float32BufferAttribute(sk, 3)); skg.computeVertexNormals();
  const plinthMat = new THREE.MeshLambertMaterial({ color: 0xd9ddd9, side: THREE.DoubleSide });
  scene.add(new THREE.Mesh(skg, plinthMat));

  // buildings: one merged mesh, vertex colours, triangle -> building for picking (BVH-accelerated)
  const P = [], tri2b = [], ranges = [], centers = [];
  const toV = (x, y, z) => [x - W / 2, z, -(y - H / 2)];
  const area = r => { let s = 0; for (let i = 0, n = r.length; i < n; i++) { const a = r[i], b = r[(i + 1) % n]; s += a[0] * b[1] - b[0] * a[1]; } return s / 2; };
  B.forEach((b, bi) => {
    const start = P.length / 3, z0 = b.z - 1.5, z1 = b.z + b.h;
    const polys = [];
    for (const r0 of b.rings) {
      const last = r0[r0.length - 1], closed = r0.length > 3 && r0[0][0] === last[0] && r0[0][1] === last[1];
      const r = closed ? r0.slice(0, -1) : r0;
      if (r.length < 3) continue;
      if (area(r) < 0 || !polys.length) polys.push({ outer: r, holes: [] }); else polys[polys.length - 1].holes.push(r);
    }
    let cx = 0, cy = 0, n = 0;
    for (const p of polys) {
      const v2 = r => r.map(([x, y]) => new THREE.Vector2(x, y));
      const outer = v2(p.outer), holes = p.holes.map(v2), all = outer.concat(...holes);
      for (const f of THREE.ShapeUtils.triangulateShape(outer, holes)) for (const k of [f[0], f[2], f[1]]) P.push(...toV(all[k].x, all[k].y, z1));
      for (const ring of [p.outer, ...p.holes]) for (let i = 0; i < ring.length; i++) {
        const a = ring[i], c = ring[(i + 1) % ring.length];
        const A0 = toV(a[0], a[1], z0), A1 = toV(a[0], a[1], z1), C0 = toV(c[0], c[1], z0), C1 = toV(c[0], c[1], z1);
        P.push(...A0, ...C0, ...C1, ...A0, ...C1, ...A1);
      }
      for (const [x, y] of p.outer) { cx += x; cy += y; n++; }
    }
    const end = P.length / 3;
    for (let k = start; k < end; k += 3) tri2b.push(bi);
    ranges.push([start, end]);
    centers.push(new THREE.Vector3(...toV(cx / (n || 1), cy / (n || 1), b.z + b.h / 2)));
  });
  const bg = new THREE.BufferGeometry();
  bg.setAttribute("position", new THREE.Float32BufferAttribute(P, 3));
  const colors = new Float32Array(P.length);
  bg.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  bg.computeVertexNormals();
  bg.computeBoundsTree();
  const bMat = new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide });
  const bMesh = new THREE.Mesh(bg, bMat);
  scene.add(bMesh);
  // trees (Rive-Claire scenery, generated): one instanced mesh, not pickable
  let treeMesh = null;
  if (M.trees && M.trees.length) {
    const n = M.trees.length / 3, tg = new THREE.IcosahedronGeometry(1, 1), mtx = new THREE.Matrix4(), q = new THREE.Quaternion(), sc = new THREE.Vector3(), ps = new THREE.Vector3();
    treeMesh = new THREE.InstancedMesh(tg, new THREE.MeshLambertMaterial({ color: 0x7fa36a }), n);
    for (let i = 0; i < n; i++) {
      const [x, y, r] = [M.trees[3 * i], M.trees[3 * i + 1], M.trees[3 * i + 2]];
      treeMesh.setMatrixAt(i, mtx.compose(ps.set(...toV(x, y, r * 1.3)), q, sc.set(r, r * 1.35, r)));
    }
    scene.add(treeMesh);
  }
  const buildMs = Math.round(performance.now() - T0);
  stage.innerHTML = ""; stage.appendChild(renderer.domElement);

  // ---------------------------------------------------------------- colouring + class filter
  let LAYER = "idc", SEL = -1, HOV = -1, ONLY = null;   // ONLY = isolated class index, or "nd" for no data
  const col = new THREE.Color(), white = new THREE.Color(0xffffff), ghost = new THREE.Color();
  const L = () => (RC ? layersRC : layers)(t, nf)[LAYER];
  function paint(bi, lay = L()) {
    const c = lay.cls(B[bi]);
    const hidden = ONLY !== null && (ONLY === "nd" ? c !== -1 : c !== ONLY);
    if (hidden) col.copy(ghost); else col.setHex(c < 0 ? GREY : lay.ramp[c]);
    if (bi === SEL) col.lerp(white, 0.6); else if (bi === HOV) col.lerp(white, 0.35);
    const [s, e] = ranges[bi];
    for (let k = s; k < e; k++) { colors[3 * k] = col.r; colors[3 * k + 1] = col.g; colors[3 * k + 2] = col.b; }
  }
  function paintAll() { const lay = L(); for (let i = 0; i < B.length; i++) paint(i, lay); flush(); }
  function flush() { bg.attributes.color.needsUpdate = true; request(); }

  // ---------------------------------------------------------------- UI
  function legendHtml() {
    const lay = L(), counts = new Array(lay.labels.length).fill(0); let nd = 0;
    for (const b of B) { const c = lay.cls(b); if (c < 0) nd++; else counts[c]++; }
    const item = (key, colour, label, n) => `<button class="m3-key ${ONLY === key ? "on" : ""} ${ONLY !== null && ONLY !== key ? "off" : ""}" data-cls="${key}"><i style="background:${hex(colour)}"></i><span>${esc(label)}</span><em>${nf(n)}</em></button>`;
    return `<div class="m3-unit">${esc(t((RC ? "m_lg_rc_" : "m_lg_") + LAYER))}${lay.unit ? ` · ${esc(lay.unit)}` : ""}${lay.sim ? ` <span class="pill p-warn">${esc(t("m_sim"))}</span>` : ""}</div>`
      + `<div class="m3-keys">${lay.labels.map((l, i) => item(i, lay.ramp[i], l, counts[i])).join("")}${item("nd", GREY, t("m_nodata"), nd)}</div>`
      + `<div class="m3-fhint">${esc(ONLY === null ? t("m_filter_hint") : t("m_filter_clear"))}</div>`;
  }
  function ui() {
    for (const b of root.querySelectorAll("[data-map]")) { b.textContent = t("m_map_" + b.dataset.map); b.classList.toggle("on", b.dataset.map === cfg.key); }
    root.querySelector(".m3-title").textContent = t(RC ? "m_map_title_rc" : "m_map_title");
    root.querySelector(".m3-sub").textContent = RC ? t("m_sub_rc", { n: nf(B.length), s: nf(new Set(B.map(b => b.site)).size), y: M.year }) : t("m_sub", { n: nf(B.length) });
    root.querySelector(".m3-search input").placeholder = t(RC ? "m_search_rc" : "m_search");
    root.querySelector(".m3-layers").innerHTML = LAYER_KEYS.map(k => `<button class="chip ${k === LAYER ? "on" : ""}" data-ml="${k}">${esc(t(RC && k === "idc" ? "m_l_hi" : "m_l_" + k))}</button>`).join("");
    root.querySelector(".m3-legend").innerHTML = legendHtml();
    root.querySelector(".m3-hint").textContent = matchMedia("(pointer:coarse)").matches ? t("m_hint_touch") : t("m_hint");
    const tips = { pan: "m_t_pan", orbit: "m_t_orbit", in: "m_t_in", out: "m_t_out", rl: "m_t_rl", rr: "m_t_rr", top: isTop() ? "m_t_tilt" : "m_t_top", north: "m_north", full: isFull() ? "m_t_fullx" : "m_t_full", home: "m_reset" };
    for (const [k, v] of Object.entries(tips)) { const el = root.querySelector(`[data-tool="${k}"]`); el.title = t(v); el.setAttribute("aria-label", t(v)); }
    root.querySelector(".m3-attr").textContent = RC ? t("m_attr_rc", { k: nf(M.scale || 1, 1) }) : t("m_attr");
    if (SEL >= 0) panel(SEL);
  }
  function row(label, value, sim) { return value == null || value === "" ? "" : `<div class="m3-row"><span>${esc(label)}</span><b>${value}${sim ? ` <span class="pill p-warn">${esc(t("m_sim"))}</span>` : ""}</b></div>`; }
  function panelRC(b) {
    const r = b.rc, yr = t("m_yr"), hc = r.heat ? hex(HEAT[r.heat]) : null, mwh = v => v ? nf(v / 1000) + " MWh" : null;
    const nb = d => d.replace("-", "\u2011");   // non-breaking hyphen: keep 2024-07 on one line
    const note = k => `<div class="mut" style="font-size:12px;margin:-2px 0 4px">${esc(t(k))}</div>`;
    const inst = b.inst.map(x => row(tr(x.t), [x.kw ? nf(x.kw) + (/photovolta/.test(x.t) ? " kWp" : " kW") : "", x.from ? (x.to ? `${nb(x.from)} → ${nb(x.to)}` : t("m_p_since", { d: nb(x.from) })) : ""].filter(Boolean).join(" · "))).join("");
    return `<div class="row" style="flex-wrap:nowrap;align-items:flex-start"><div style="min-width:0;flex:1"><div class="tsub">${esc(tr(b.use))} · ${esc(b.q)}</div><h2 style="margin:2px 0 0">${esc(b.name)}</h2>${b.bname ? `<div class="mut">${esc(tr(b.bname))}</div>` : ""}</div><button class="x m3-close" aria-label="close">×</button></div>
      <div class="m3-acts"><a class="btn" href="#fiche/${esc(b.id)}">${esc(t("fs_title"))}</a><a class="btn alt" href="#site/${esc(b.site)}">${esc(t("m_open_site"))}</a></div>
      <div class="m3-sec">${row(t("m_p_year"), b.year)}${row(t("m_p_reno"), b.reno)}${row(t("m_p_levels"), b.levels ? nf(b.levels) + (b.under ? " · " + esc(t("m_p_under")) : "") : null)}${row(t("m_p_sre"), b.sre ? nf(b.sre) + " m²" : esc(t("m_na")))}${row(t("m_p_label"), b.label ? esc(tr(b.label)) : null)}${row(t("m_p_homes"), b.homes)}${row(t("m_p_open"), b.open)}
        ${b.note ? note(tr(b.note)) : ""}</div>
      <div class="m3-sec"><div class="m3-h">${esc(t("m_l_heat"))}</div>
        ${r.heat ? `<span class="pill" style="background:${hc}22;color:${hc}">${esc(t("m_heat_" + r.heat))}</span>` : `<span class="mut">${esc(t("m_nodata"))}</span>`}
        ${inst}</div>
      <div class="m3-sec"><div class="m3-h">${esc(t("m_p_measured", { y: r.year }))}${b.nb > 1 ? ` · ${esc(t("m_p_site", { n: b.nb }))}` : ""}</div>
        ${row(t("m_p_hi"), r.mj_m2 == null ? esc(t("m_na")) : `<span class="pill ${r.mj_m2 >= 800 ? "p-fossil" : r.mj_m2 >= 450 ? "p-warn" : "p-ren"}">${nf(r.mj_m2)} MJ/m²</span> ≈ ${nf(r.mj_m2 / 3.6)} kWh/m²`)}${r.mj_m2 == null ? "" : note(r.hi_est ? "m_n_hi_est" : "m_n_hi")}
        ${row(t("m_l_int"), r.kwh_m2 == null ? esc(t("m_na")) : nf(r.kwh_m2) + " kWh/m²")}
        ${row(t("m_p_heatkwh"), mwh(r.heat_kwh))}${r.deliveries ? note("m_n_deliv") : ""}
        ${row(t("m_l_elec"), mwh(r.elec_kwh))}${b.homes ? note("m_n_common") : ""}
        ${row(t("m_p_pvprod"), mwh(r.pv_kwh))}${row(t("m_l_water"), r.water_m3 ? nf(r.water_m3) + " m³" : null)}</div>
      <div class="m3-src">${esc(b.site)} · ${esc(t("m_src_rc"))}</div>`;
  }
  function panel(bi) {
    const b = B[bi], el = root.querySelector(".m3-panel"), yr = t("m_yr");
    if (RC) { el.innerHTML = panelRC(b); el.classList.remove("hide"); el.querySelector(".m3-close").onclick = () => select(-1); return; }
    const idcClass = b.idc ? (b.idc.mj_m2 >= 800 ? "p-fossil" : b.idc.mj_m2 >= 450 ? "p-warn" : "p-ren") : "";
    const hc = b.heat ? hex(HEAT[b.heat]) : null;
    el.innerHTML = `<div class="row"><div style="min-width:0"><div class="tsub">${esc(tr(b.use) || "")}</div><h2 style="margin:2px 0 0">${esc(b.addr || "EGID " + (b.egid || "–"))}</h2></div><div class="spacer"></div><button class="x m3-close" aria-label="close">×</button></div>
      <div class="m3-sec">${row(t("m_p_year"), b.year)}${row(t("m_p_levels"), b.levels)}${row(t("m_p_height"), nf(b.h, 1) + " m")}${row(t("m_p_sre"), b.sre ? nf(b.sre) + " m²" : null)}</div>
      <div class="m3-sec"><div class="m3-h">${esc(t("m_l_heat"))}</div>
        ${b.heat ? `<span class="pill" style="background:${hc}22;color:${hc}">${esc(t("m_heat_" + b.heat))}</span>` : `<span class="mut">${esc(t("m_nodata"))}</span>`}
        ${b.idc ? row(t("m_p_idc", { y: b.idc.year }), `<span class="pill ${idcClass}">${nf(b.idc.mj_m2)} MJ/m²</span> ≈ ${nf(b.idc.kwh_m2)} kWh/m²`) + row(t("m_p_carriers"), esc((b.idc.carriers || []).map(tr).join(" · "))) + row(t("m_p_heatkwh"), b.idc.kwh ? nf(b.idc.kwh / 1000) + " MWh" : null) : ""}
        ${(b.boilers || []).map(x => row(t("m_p_boiler"), `${esc(tr(x.fuel))}${x.year ? " · " + x.year : ""}${x.kw ? " · " + nf(x.kw) + " kW" : ""}`)).join("")}
      </div>
      <div class="m3-sec"><div class="m3-h">${esc(t("m_l_solar"))}</div>${b.pv ? row(t("m_p_pv"), nf(b.pv.kwh / 1000) + " MWh/" + yr) + row(t("m_p_kwp"), nf(b.pv.kwp, 1) + " kWp · " + nf(b.pv.m2) + " m²") : `<span class="mut">${esc(t("m_nodata"))}</span>`}</div>
      ${b.sim ? `<div class="m3-sec">${row(t("m_l_elec"), nf(b.sim.elec_kwh / 1000) + " MWh/" + yr, true)}${row(t("m_l_water"), nf(b.sim.water_m3) + " m³/" + yr, true)}</div>` : ""}
      <div class="m3-src">EGID ${esc(b.egid || "–")} · ${esc(t("m_src"))}</div>`;
    el.classList.remove("hide");
    el.querySelector(".m3-close").onclick = () => select(-1);
  }
  function select(bi, fly) {
    const prev = SEL; SEL = bi;
    if (prev >= 0) paint(prev);
    if (bi >= 0) { paint(bi); panel(bi); if (fly) flyTo(centers[bi]); } else root.querySelector(".m3-panel").classList.add("hide");
    flush(); placeLabels();
  }

  // search by address
  const input = root.querySelector(".m3-search input"), results = root.querySelector(".m3-results");
  const index = B.map((b, i) => [norm(b.addr), i]).filter(([a]) => a);
  input.addEventListener("input", () => {
    const q = norm(input.value.trim());
    if (q.length < 3) { results.classList.add("hide"); return; }
    const hits = index.filter(([a]) => a.includes(q)).slice(0, 7);
    results.innerHTML = hits.length ? hits.map(([, i]) => `<button data-bi="${i}"><b>${esc(B[i].addr)}</b><span>${esc(tr(B[i].use) || "")}</span></button>`).join("") : `<div class="mut">${esc(t("m_noresult"))}</div>`;
    results.classList.remove("hide");
  });
  input.addEventListener("keydown", e => { if (e.key === "Enter") { const f = results.querySelector("[data-bi]"); if (f) f.click(); } if (e.key === "Escape") results.classList.add("hide"); });

  root.addEventListener("click", e => {
    const l = e.target.closest("[data-ml]"); if (l) { LAYER = l.dataset.ml; ONLY = null; ui(); paintAll(); return; }
    const k = e.target.closest("[data-cls]");
    if (k) { const v = k.dataset.cls === "nd" ? "nd" : +k.dataset.cls; ONLY = ONLY === v ? null : v; root.querySelector(".m3-legend").innerHTML = legendHtml(); paintAll(); return; }
    const r = e.target.closest("[data-bi]"); if (r) { results.classList.add("hide"); input.value = B[+r.dataset.bi].addr; select(+r.dataset.bi, true); return; }
    const mp = e.target.closest("[data-map]"); if (mp) { if (mp.dataset.map !== cfg.key) api.switchMap(mp.dataset.map); return; }
    const tb = e.target.closest("[data-tool]"); if (!tb) return;
    const tool = tb.dataset.tool;
    if (tool === "pan" || tool === "orbit") setMode(tool);
    else if (tool === "in" || tool === "out") orbitTo({ scale: tool === "in" ? 0.6 : 1.65 });
    else if (tool === "rl" || tool === "rr") orbitTo({ dTheta: (tool === "rl" ? 1 : -1) * Math.PI / 4 });
    else if (tool === "top") orbitTo(isTop() ? { phi: 0.95 } : { phi: 0.0001 });
    else if (tool === "north") orbitTo({ theta: 0 });
    else if (tool === "full") toggleFull();
    else if (tool === "home") { ONLY = null; ui(); paintAll(); animate(HOME.pos.clone(), HOME.target.clone()); }
  });

  // ---------------------------------------------------------------- view tools: drag mode, orbit moves, full screen
  function setMode(m) {
    const pan = m === "pan";
    controls.mouseButtons = { LEFT: pan ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: pan ? THREE.MOUSE.ROTATE : THREE.MOUSE.PAN };
    controls.touches = { ONE: pan ? THREE.TOUCH.PAN : THREE.TOUCH.ROTATE, TWO: THREE.TOUCH.DOLLY_ROTATE };
    root.querySelector('[data-tool="pan"]').classList.toggle("on", pan);
    root.querySelector('[data-tool="orbit"]').classList.toggle("on", !pan);
  }
  const sph = () => new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
  const isTop = () => sph().phi < 0.2;
  function orbitTo({ dTheta = 0, theta, phi, scale = 1 }, ms = 650) {
    const s0 = sph();
    let th1 = theta === undefined ? s0.theta + dTheta : theta;
    while (th1 - s0.theta > Math.PI) th1 -= 2 * Math.PI;
    while (th1 - s0.theta < -Math.PI) th1 += 2 * Math.PI;
    const r1 = THREE.MathUtils.clamp(s0.radius * scale, controls.minDistance, controls.maxDistance), ph1 = phi === undefined ? s0.phi : phi;
    const s = new THREE.Spherical(), v = new THREE.Vector3();
    anim = { t0: performance.now(), ms, fn: k => {
      s.set(s0.radius + (r1 - s0.radius) * k, s0.phi + (ph1 - s0.phi) * k, s0.theta + (th1 - s0.theta) * k);
      camera.position.copy(controls.target).add(v.setFromSpherical(s));
    } };
    request();
  }
  const isFull = () => !!document.fullscreenElement || root.classList.contains("m3-full");
  function toggleFull() {
    if (document.fullscreenElement) document.exitFullscreen();
    else if (root.classList.contains("m3-full")) root.classList.remove("m3-full");
    else if (root.requestFullscreen) root.requestFullscreen()
      .then(() => setTimeout(() => { if (!document.fullscreenElement) root.classList.add("m3-full"); onFull(); }, 200))
      .catch(() => { root.classList.add("m3-full"); onFull(); });
    else { root.classList.add("m3-full"); onFull(); }   // iPhone Safari: no element full screen, fill the window instead
    setTimeout(onFull, 50);
  }
  function onFull() {
    root.classList.toggle("is-full", isFull());
    (document.fullscreenElement || document.body).appendChild(document.getElementById("tip"));   // keep tooltips visible
    ui();
  }
  const onEsc = e => { if (e.key === "Escape" && root.classList.contains("m3-full")) { root.classList.remove("m3-full"); onFull(); } };
  document.addEventListener("fullscreenchange", onFull);
  document.addEventListener("keydown", onEsc);

  // ---------------------------------------------------------------- camera moves
  let anim = null;
  function animate(toPos, toTarget, ms = 750) {
    anim = { t0: performance.now(), ms, p0: camera.position.clone(), q0: controls.target.clone(), p1: toPos, q1: toTarget }; request();
  }
  function flyTo(c) {
    const dir = camera.position.clone().sub(controls.target).normalize(), dist = Math.min(camera.position.distanceTo(controls.target), 420);
    const tgt = new THREE.Vector3(c.x, Math.max(0, c.y - 10), c.z);
    animate(tgt.clone().add(dir.multiplyScalar(Math.max(dist, 220))), tgt);
  }
  function clampTarget() {   // keep the view over the map
    const t0 = controls.target, cx = THREE.MathUtils.clamp(t0.x, -W / 2, W / 2), cz = THREE.MathUtils.clamp(t0.z, -H / 2, H / 2);
    if (cx !== t0.x || cz !== t0.z) { const d = new THREE.Vector3(cx - t0.x, 0, cz - t0.z); t0.add(d); camera.position.add(d); }
  }

  // ---------------------------------------------------------------- picking
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  ray.firstHitOnly = true;
  let lastPickMs = 0;
  function pick(ev) {
    const r = renderer.domElement.getBoundingClientRect(), t1 = performance.now();
    ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hit = ray.intersectObject(bMesh, false)[0];
    lastPickMs = performance.now() - t1;
    return hit ? tri2b[hit.faceIndex] : -1;
  }
  let down = null;
  renderer.domElement.tabIndex = 0;
  controls.listenToKeyEvents(renderer.domElement); controls.keyPanSpeed = 40;
  renderer.domElement.addEventListener("pointerdown", e => { down = [e.clientX, e.clientY]; results.classList.add("hide"); renderer.domElement.focus({ preventScroll: true }); });
  renderer.domElement.addEventListener("pointerup", e => {
    if (down && Math.hypot(e.clientX - down[0], e.clientY - down[1]) < 6 && e.button === 0) select(pick(e));
    down = null;
  });
  let hovT = 0;
  renderer.domElement.addEventListener("pointermove", e => {
    if (e.pointerType !== "mouse" || e.buttons) return;
    const now = performance.now(); if (now - hovT < 30) return; hovT = now;
    const bi = pick(e);
    if (bi !== HOV) { const p = HOV; HOV = bi; if (p >= 0) paint(p); if (bi >= 0) paint(bi); flush(); }
    renderer.domElement.style.cursor = bi >= 0 ? "pointer" : "";
    if (bi >= 0) { const b = B[bi], v = L().val(b); api.showTip(e, `<b>${esc(b.addr || "EGID " + b.egid)}</b><br>${esc(tr(b.use) || "")}${v ? `<br>${esc(v)}` : ""}`); } else api.hideTip();
  });
  renderer.domElement.addEventListener("pointerleave", () => { api.hideTip(); if (HOV >= 0) { const p = HOV; HOV = -1; paint(p); flush(); } });

  // ---------------------------------------------------------------- place labels
  const labWrap = root.querySelector(".m3-labels");
  const labs = (M.labels || []).map(l => { const d = document.createElement("div"); d.className = "m3-place"; d.textContent = l.name; labWrap.appendChild(d); return { d, v: new THREE.Vector3(...toV(l.x, l.y, l.z + 30)) }; });
  const pv = new THREE.Vector3();
  function placeLabels() {
    const w = stage.clientWidth, h = stage.clientHeight, dist = camera.position.distanceTo(controls.target);
    const pnl = root.querySelector(".m3-panel"), cut = pnl.classList.contains("hide") || w < 720 ? w : w - pnl.offsetWidth - 70;
    for (const l of labs) {
      pv.copy(l.v).project(camera);
      const vis = pv.z < 1 && Math.abs(pv.x) < 1.05 && Math.abs(pv.y) < 1.05 && dist > 500 && ((pv.x + 1) / 2) * w < cut;
      l.d.style.opacity = vis ? 1 : 0;
      if (vis) l.d.style.transform = `translate(${((pv.x + 1) / 2) * w}px, ${((1 - pv.y) / 2) * h}px) translate(-50%, -100%)`;
    }
  }

  // ---------------------------------------------------------------- render on demand
  const northSvg = root.querySelector(".m3-north svg"), topBtn = root.querySelector('[data-tool="top"]');
  let lastTop = null;
  let pending = false;
  function request() { if (!pending) { pending = true; requestAnimationFrame(frame); } }
  function frame() {
    pending = false;
    if (anim) {
      const k = Math.min(1, (performance.now() - anim.t0) / anim.ms), e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
      if (anim.fn) anim.fn(e); else { camera.position.lerpVectors(anim.p0, anim.p1, e); controls.target.lerpVectors(anim.q0, anim.q1, e); }
      if (k >= 1) anim = null;
    }
    const moving = controls.update();
    clampTarget();
    const az = Math.atan2(camera.position.x - controls.target.x, camera.position.z - controls.target.z);
    northSvg.style.transform = `rotate(${az}rad)`;
    const top = isTop(); if (top !== lastTop) { lastTop = top; topBtn.innerHTML = `<b>${top ? "3D" : "2D"}</b>`; topBtn.classList.toggle("on", top); topBtn.title = t(top ? "m_t_tilt" : "m_t_top"); }
    renderer.render(scene, camera);
    placeLabels();
    if (moving || anim) request();
  }
  controls.addEventListener("change", request);
  function theme() {
    const dark = api.dark(), bgc = dark ? 0x0e1311 : 0xeef1ee;
    scene.background = new THREE.Color(bgc);
    scene.fog = new THREE.Fog(bgc, Math.max(W, H) * 1.1, Math.max(W, H) * 3);
    for (const m of groundMat) m.color.setScalar(dark ? 0.6 : 1);
    plinthMat.color.setHex(dark ? 0x26302c : 0xd9ddd9);
    if (treeMesh) treeMesh.material.color.setHex(dark ? 0x4a6440 : 0x7fa36a);
    ghost.setHex(dark ? 0x3a4440 : 0xe4e7e4);
    paintAll();
  }
  const ro = new ResizeObserver(() => {
    const w = stage.clientWidth, h = stage.clientHeight; if (!w || !h) return;
    renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); request();
  });
  ro.observe(stage);
  camera.position.copy(HOME.pos); controls.target.copy(HOME.target); controls.update();
  theme(); setMode("pan"); ui();
  window.__m3 = { buildMs, lastPick: () => lastPickMs, n: B.length, cam: () => { const s = sph(); return [Math.round(s.radius), +s.phi.toFixed(3), +s.theta.toFixed(3), Math.round(controls.target.x), Math.round(controls.target.z)]; } };   // read by the headless check
  function destroy() {   // before switching map: free the GL context and the page-level listeners
    document.removeEventListener("fullscreenchange", onFull); document.removeEventListener("keydown", onEsc);
    ro.disconnect(); controls.dispose(); api.hideTip();
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    root.classList.remove("m3-full", "is-full"); document.body.appendChild(document.getElementById("tip"));
    scene.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) { if (o.material.map) o.material.map.dispose(); o.material.dispose(); } });
    renderer.dispose(); renderer.forceContextLoss(); root.innerHTML = "";
  }
  return { relabel: () => ui(), theme, destroy, count: B.length };
}
