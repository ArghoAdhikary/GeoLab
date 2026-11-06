/* GeoLab Mobile: the web UI. The analysis engine runs in worker.js (Python via Pyodide). */
"use strict";
const PYODIDE_VERSION = "0.27.7";
const CDN = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const store = {
  get(k, d) { try { const v = localStorage.getItem("geolab." + k); return v === null ? d : v; } catch { return d; } },
  set(k, v) { try { localStorage.setItem("geolab." + k, v); } catch { /* private mode */ } },
};

// ---------------------------------------------------------------- engine
const worker = new Worker("worker.js");
let seq = 0;
const pending = new Map();
worker.onmessage = (e) => {
  const m = e.data;
  if (m.progress) { $("#boot-msg").textContent = m.progress; return; }
  const p = pending.get(m.id);
  if (!p) return;
  pending.delete(m.id);
  m.ok ? p.resolve(JSON.parse(m.result)) : p.reject(new Error(m.error));
};
function call(fn, ...args) {
  return new Promise((resolve, reject) => {
    const id = ++seq;
    pending.set(id, { resolve, reject });
    worker.postMessage({ id, fn, args: args.map((a) => (typeof a === "object" ? JSON.stringify(a) : a)) });
  });
}
async function boot() {
  let base = CDN;
  try {
    const r = await fetch("pyodide/pyodide.js", { method: "HEAD" });
    if (r.ok) base = new URL("pyodide/", location.href).href;
  } catch { /* use the CDN */ }
  return new Promise((resolve, reject) => {
    const id = ++seq;
    pending.set(id, { resolve, reject });
    worker.postMessage({ id, fn: "__boot__", base });
  });
}

// ---------------------------------------------------------------- state
let INFO = null;
let S = null;          // project state from Python
let selected = null;   // analysis id
let tab = "analysis";
let field = null;      // FE result field shown

async function run(fn, args = [], msg) {
  const t = msg ? setTimeout(() => busy(msg), 120) : null;
  try {
    const s = await call(fn, ...args);
    if (s && s.analyses) setState(s);
    return s;
  } catch (err) {
    toast(err.message, true);
    throw err;
  } finally {
    if (t) clearTimeout(t);
    busy(null);
  }
}
function setState(s) {
  S = s;
  if (!S.analyses.some((a) => a.id === selected)) {
    const slope = S.analyses.find((a) => a.kind === "slope");
    selected = (slope || S.analyses[0] || {}).id;
  }
  autosave();
  showApp();
}
let saveTimer = null;
function autosave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    try { store.set("last", JSON.stringify(await call("to_json"))); } catch { /* ignore */ }
  }, 600);
}
const cur = () => (S ? S.analyses.find((a) => a.id === selected) : null);

// ---------------------------------------------------------------- UI helpers
function busy(msg) { $("#busy").hidden = !msg; if (msg) $("#busy-msg").textContent = msg; }
let toastTimer;
function toast(msg, err = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = err ? "err" : "";
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), err ? 5200 : 2600);
}
function sheet(title, html) {
  $("#sheet-title").textContent = title;
  $("#sheet-body").innerHTML = html;
  $("#sheet").hidden = false;
}
$("#sheet-close").onclick = () => ($("#sheet").hidden = true);
$("#sheet").onclick = (e) => { if (e.target.id === "sheet") $("#sheet").hidden = true; };
const fmt = (v, d = 3) => (v === null || v === undefined || !isFinite(v) ? "–" : Number(v).toFixed(d));
const fosClass = (f) => (f === null ? "" : f >= 1.5 ? "good" : f < 1.0 ? "bad" : "");

// ---------------------------------------------------------------- theme
function applyTheme(mode) {
  store.set("theme", mode);
  if (mode === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = mode;
  document.querySelectorAll("#theme-seg button").forEach((b) => b.classList.toggle("on", b.dataset.theme === mode));
  requestAnimationFrame(draw);
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => requestAnimationFrame(draw));
document.querySelectorAll("#theme-seg button").forEach((b) => (b.onclick = () => applyTheme(b.dataset.theme)));
const isDark = () => getComputedStyle(document.documentElement).getPropertyValue("--canvas").trim().toLowerCase() !== "#ffffff";

// ---------------------------------------------------------------- start page
const LAYER_COLORS = ["#d9c49c", "#a9c98f", "#c99f7f", "#9fb7d6", "#d6a3b8", "#b5b5b5"];
let layers = [{ name: "Clay", c: 10, phi: 25, gamma: 18, thickness: 5 }, { name: "Sand", c: 0, phi: 34, gamma: 20, thickness: 0 }];
function renderLayers() {
  $("#q-layers").innerHTML = layers.map((l, i) => `
    <div class="layer" data-i="${i}">
      <div class="lh"><i style="background:${LAYER_COLORS[i % 6]}"></i><input data-k="name" value="${esc(l.name)}">
        ${layers.length > 1 ? `<button data-del="${i}" aria-label="Remove layer">×</button>` : ""}</div>
      <div class="grid3">
        <label>c' (kPa)<input data-k="c" type="number" inputmode="decimal" value="${l.c}"></label>
        <label>φ' (°)<input data-k="phi" type="number" inputmode="decimal" value="${l.phi}"></label>
        <label>γ (kN/m³)<input data-k="gamma" type="number" inputmode="decimal" value="${l.gamma}"></label>
      </div>
      ${i < layers.length - 1 ? `<label style="margin-top:6px">Thickness (m)<input data-k="thickness" type="number" inputmode="decimal" value="${l.thickness}"></label>`
        : `<p class="muted" style="margin:6px 0 0">Goes down to the bottom of the model.</p>`}
    </div>`).join("");
  $("#q-layers").querySelectorAll("input").forEach((inp) => (inp.oninput = () => {
    const i = +inp.closest(".layer").dataset.i;
    layers[i][inp.dataset.k] = inp.dataset.k === "name" ? inp.value : parseFloat(inp.value);
  }));
  $("#q-layers").querySelectorAll("[data-del]").forEach((b) => (b.onclick = () => { layers.splice(+b.dataset.del, 1); renderLayers(); }));
}
$("#q-add").onclick = () => {
  if (layers.length >= 6) return toast("Up to six layers.");
  layers[layers.length - 1].thickness = layers[layers.length - 1].thickness || 4;
  layers.push({ name: `Soil ${layers.length + 1}`, c: 5, phi: 30, gamma: 19, thickness: 0 });
  renderLayers();
};
$("#q-build").onclick = async () => {
  const v = (id) => parseFloat($(id).value);
  const params = { height: v("#q-height"), ratio: v("#q-ratio"), crest: v("#q-crest"), toe: v("#q-toe"),
    base: v("#q-base"), surcharge: v("#q-surcharge") || 0, layers,
    water: $("#q-water-on").checked ? v("#q-water") : null };
  store.set("quick", JSON.stringify(params));
  await run("quick_slope", [params], "Building...");
  await solveSelected();
};
function showStart() {
  $("#start").hidden = false;
  $("#app").hidden = true;
  $("#title").textContent = "GeoLab";
  $("#subtitle").textContent = "Start";
  $("#start-resume").hidden = !S;
}
$("#btn-home").onclick = showStart;
$("#start-resume").onclick = () => showApp();
$("#start-open").onclick = () => $("#file").click();

// ---------------------------------------------------------------- menu
$("#btn-menu").onclick = (e) => { e.stopPropagation(); $("#menu").hidden = !$("#menu").hidden; };
document.addEventListener("click", (e) => { if (!$("#menu").contains(e.target)) $("#menu").hidden = true; });
$("#menu").addEventListener("click", async (e) => {
  const act = e.target.dataset.act;
  if (!act) return;
  $("#menu").hidden = true;
  if (act === "open") $("#file").click();
  if (act === "save") saveProject();
  if (act === "report") showReport();
  if (act === "rename" && S) {
    const t = prompt("Project name", S.title);
    if (t !== null) run("set_title", [t]);
  }
  if (act === "about") sheet("About", `<p><b>GeoLab Mobile ${esc(INFO.version)}</b></p>
    <p class="muted">The same analysis engine as GeoLab for Windows and Mac: limit equilibrium slope stability
    (Ordinary, Bishop, Janbu, Spencer, Morgenstern-Price and more), seepage, stress and the other
    finite element analyses. Projects (.slab) open on the desktop app and back.</p>
    <p class="muted">Everything runs on this phone; nothing is sent anywhere.</p>
    <p class="muted">https://github.com/ArghoAdhikary/GeoLab</p>`);
});
$("#file").onchange = async () => {
  const f = $("#file").files[0];
  $("#file").value = "";
  if (!f) return;
  const buf = new Uint8Array(await f.arrayBuffer());
  let bin = "";
  for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
  await run("open_file", [f.name, btoa(bin)], "Opening...");
  fit();
};
async function saveProject() {
  if (!S) return;
  const r = await call("save_file");
  const cap = window.Capacitor;
  const plugins = cap && cap.Plugins;
  if (plugins && plugins.Filesystem && plugins.Share) {
    try {
      const w = await plugins.Filesystem.writeFile({ path: r.name, data: r.b64, directory: "CACHE" });
      await plugins.Share.share({ title: r.name, files: [w.uri], dialogTitle: "Save or send the project" });
      return;
    } catch (err) {
      if (!/cancel/i.test(String(err && err.message))) toast("Could not share: " + err.message, true);
      return;
    }
  }
  const bytes = Uint8Array.from(atob(r.b64), (c) => c.charCodeAt(0));
  const file = new File([bytes], r.name, { type: "application/octet-stream" });
  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    try { await navigator.share({ files: [file], title: r.name }); return; } catch { /* fall back */ }
  }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(file);
  a.download = r.name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}
async function showReport() {
  const a = cur();
  if (!a || !a.solved) return toast("Solve the analysis first.");
  const r = await call("report", a.id);
  sheet("Report: " + a.name, `<pre>${esc(r.text)}</pre>`);
}

// ---------------------------------------------------------------- app view
function showApp() {
  $("#start").hidden = true;
  $("#app").hidden = false;
  $("#title").textContent = S.title;
  const a = cur();
  $("#subtitle").textContent = a ? a.name : "";
  renderPanel();
  resize();
}
document.querySelectorAll("#tabs button").forEach((b) => (b.onclick = () => {
  tab = b.dataset.tab;
  document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("on", x === b));
  renderPanel();
}));

async function solveSelected() {
  const a = cur();
  if (!a) return;
  await run("solve_one", [a.id], `Solving ${a.name}...`);
  const b = cur();
  if (b && b.kind === "slope" && b.draw && b.draw.fos !== null && b.draw.fos !== undefined) toast(`Factor of safety ${fmt(b.draw.fos)}`);
}

function renderPanel() {
  const P = $("#panel");
  const a = cur();
  if (tab === "analysis") {
    const list = S.analyses.map((x) => {
      const f = x.kind === "slope" && x.draw ? x.draw.fos : null;
      return `<div class="card ana ${x.id === selected ? "sel" : ""}" data-id="${x.id}">
        <div class="t"><b>${esc(x.name)}</b><small>${esc(x.kind_label)}</small></div>
        ${x.solved ? (x.kind === "slope" ? `<span class="badge ${fosClass(f)}">F = ${fmt(f)}</span>` : `<span class="badge">Solved</span>`) : ""}
      </div>`;
    }).join("");
    let opts = "";
    if (a && a.kind === "slope") {
      const methods = Object.entries(INFO.methods).map(([k, v]) => `<option value="${k}" ${k === a.method ? "selected" : ""}>${esc(v)}</option>`).join("");
      const pwp = Object.entries(INFO.pwp).map(([k, v]) => `<option value="${k}" ${k === a.pwp ? "selected" : ""}>${esc(v)}</option>`).join("");
      opts = `<div class="card">
        <h2>${esc(a.name)}</h2>
        <label>Method<select data-set="method">${methods}</select></label>
        <div class="grid2" style="margin-top:8px">
          <label>Pore water<select data-set="pwp">${pwp}</select></label>
          <label>Seismic kh<input data-set="kh" type="number" inputmode="decimal" step="0.01" value="${a.kh}"></label>
        </div>
        ${a.pwp === "ru" ? `<label style="margin-top:8px">Ru<input data-set="ru" type="number" inputmode="decimal" step="0.05" value="${a.ru}"></label>` : ""}
        ${S.piezo.length ? `<h3>Water table</h3><div class="stepper">
          <button class="ghost small" data-water="-1">▼ 1 m</button><button class="ghost small" data-water="-0.25">▼ 0.25</button>
          <button class="ghost small" data-water="0.25">▲ 0.25</button><button class="ghost small" data-water="1">▲ 1 m</button></div>` : ""}
        <h3>Crest load</h3>
        <div class="stepper"><input id="surch" type="number" inputmode="decimal" value="${S.surcharges.length ? S.surcharges[0][2] : 0}">
          <button class="ghost small" id="surch-set">Set (${esc(S.u.pressure)})</button></div>
      </div>`;
    } else if (a) {
      opts = `<div class="card"><h2>${esc(a.name)}</h2><p class="muted">${esc(a.kind_label)}. Change its settings in GeoLab
        on the desktop; here you can solve it and look at the results.</p></div>`;
    }
    P.innerHTML = `${list}${opts}
      <button class="primary" id="solve">Solve ${a ? esc(a.name) : ""}</button>
      ${S.analyses.length > 1 ? `<button class="ghost" style="width:100%" id="solve-all">Solve all analyses</button>` : ""}`;
    P.querySelectorAll(".ana").forEach((el) => (el.onclick = () => { selected = +el.dataset.id; field = null; showApp(); }));
    P.querySelectorAll("[data-set]").forEach((el) => (el.onchange = () => run("set_analysis", [a.id, el.dataset.set, el.value])));
    P.querySelectorAll("[data-water]").forEach((el) => (el.onclick = () => run("move_water", [parseFloat(el.dataset.water)])));
    const ss = $("#surch-set");
    if (ss) ss.onclick = () => run("set_surcharge", [parseFloat($("#surch").value) || 0]);
    $("#solve").onclick = solveSelected;
    const sa = $("#solve-all");
    if (sa) sa.onclick = async () => {
      const s = await run("solve_everything", [], "Solving all analyses...");
      if (s.errors && s.errors.length) toast(s.errors.join("\n"), true);
    };
  } else if (tab === "materials") {
    P.innerHTML = S.materials.map((m) => `<div class="card mat" data-id="${m.id}">
      <i style="background:${esc(m.color)}"></i>
      <div><div class="name">${esc(m.name)} <small>${esc(m.model_label)}${m.used ? "" : " · not used"}</small></div>
        <div class="grid3">
          <label>c' (${esc(S.u.pressure)})<input data-f="cohesion" type="number" inputmode="decimal" value="${m.cohesion}"></label>
          <label>φ' (°)<input data-f="phi" type="number" inputmode="decimal" value="${m.phi}"></label>
          <label>γ (${esc(S.u.unit_weight)})<input data-f="unit_weight" type="number" inputmode="decimal" value="${m.unit_weight}"></label>
        </div></div></div>`).join("") +
      `<p class="muted">Changes clear the results; solve again on the Analysis tab.</p>`;
    P.querySelectorAll(".mat input").forEach((inp) => (inp.onchange = () =>
      run("set_material", [inp.closest(".mat").dataset.id, inp.dataset.f, inp.value])));
  } else {
    if (!a || !a.solved) {
      P.innerHTML = `<div class="card"><p class="muted">No results yet.</p><button class="primary" id="solve">Solve ${a ? esc(a.name) : ""}</button></div>`;
      $("#solve").onclick = solveSelected;
      return;
    }
    const d = a.draw || {};
    let html = "";
    if (a.kind === "slope") {
      if (d.message) html += `<div class="card"><p>${esc(d.message)}</p></div>`;
      else {
        const methodName = INFO.methods[a.method];
        html += `<div class="card"><h2>Factor of safety</h2>
          <div style="font-size:38px;font-weight:800" class="${fosClass(d.fos)}">${fmt(d.fos)}</div>
          <p class="muted">${esc(methodName)} · ${d.n_valid} of ${d.n_total} trial surfaces valid
          ${d.centre ? `<br>Centre (${fmt(d.centre[0], 2)}, ${fmt(d.centre[1], 2)}), radius ${fmt(d.centre[2], 2)} ${esc(S.u.length)}` : ""}</p></div>
          <div class="card"><h2>All methods (same surface)</h2><table>${Object.entries(d.methods).map(([k, v]) =>
            `<tr class="${k === methodName ? "cur" : ""}"><td>${esc(k)}</td><td>${fmt(v)}</td></tr>`).join("")}</table></div>`;
        if (d.probability) {
          const p = d.probability;
          html += `<div class="card"><h2>Probabilistic</h2><table>
            <tr><td>Mean F</td><td>${fmt(p.mean)}</td></tr><tr><td>Std. deviation</td><td>${fmt(p.sd)}</td></tr>
            ${p.pf !== undefined ? `<tr><td>Probability of failure</td><td>${fmt(100 * p.pf, 1)} %</td></tr>` : ""}
            ${p.beta !== undefined ? `<tr><td>Reliability index</td><td>${fmt(p.beta, 2)}</td></tr>` : ""}</table></div>`;
        }
      }
    } else if (d.fields) {
      const keys = Object.keys(d.fields);
      if (!field || !d.fields[field]) field = keys[0] || null;
      html += `<div class="card"><h2>Show</h2><select id="field">${keys.map((k) =>
        `<option value="${k}" ${k === field ? "selected" : ""}>${esc(d.fields[k].label)}</option>`).join("")}</select></div>`;
    } else if (d.message) html += `<div class="card"><p class="muted">${esc(d.message)}</p></div>`;
    html += `<button class="ghost" style="width:100%" id="rep">Full report</button>`;
    P.innerHTML = html;
    const fs = $("#field");
    if (fs) fs.onchange = () => { field = fs.value; draw(); };
    $("#rep").onclick = showReport;
  }
}

// ---------------------------------------------------------------- drawing
const cv = $("#cv");
const g = cv.getContext("2d");
let view = null; // {s, ox, oy}: screen = (ox + s*x, oy - s*y)
let W = 0, H = 0;
function resize() {
  const r = cv.getBoundingClientRect();
  if (!r.width) return;
  const dpr = window.devicePixelRatio || 1;
  W = r.width; H = r.height;
  cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (!view || view.auto) fit();
  else draw();
}
window.addEventListener("resize", resize);
function fit() {
  if (!S || !W) return;
  let [x0, y0, x1, y1] = S.bounds;
  const pad = 26;
  const top = 58, bottom = 34;
  const s = Math.min((W - 2 * pad) / Math.max(x1 - x0, 1e-6), (H - top - bottom) / Math.max(y1 - y0, 1e-6));
  view = { s, ox: (W - s * (x1 + x0)) / 2, oy: top + (H - top - bottom + s * (y1 + y0)) / 2, auto: true };
  draw();
}
$("#btn-fit").onclick = fit;
const X = (x) => view.ox + view.s * x;
const Y = (y) => view.oy - view.s * y;
function path(pts, close) {
  g.beginPath();
  pts.forEach((p, i) => (i ? g.lineTo(X(p[0]), Y(p[1])) : g.moveTo(X(p[0]), Y(p[1]))));
  if (close) g.closePath();
}
function ramp(t) {
  // blue -> cyan -> green -> yellow -> red
  const stops = [[49, 54, 149], [69, 117, 180], [116, 173, 209], [171, 217, 233], [254, 224, 144], [253, 174, 97], [244, 109, 67], [215, 48, 39]];
  t = Math.min(Math.max(t, 0), 1) * (stops.length - 1);
  const i = Math.min(Math.floor(t), stops.length - 2), f = t - i;
  const c = stops[i].map((v, k) => Math.round(v + f * (stops[i + 1][k] - v)));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
function draw() {
  if (!S || !view || !W) return;
  const dark = isDark();
  const css = getComputedStyle(document.documentElement);
  g.fillStyle = css.getPropertyValue("--canvas");
  g.fillRect(0, 0, W, H);
  const ink = dark ? "#c8d0da" : "#2b3440";
  const a = cur();
  const d = a && a.draw;
  if (a && a.kind !== "slope" && d && d.fields && (!field || !d.fields[field])) field = Object.keys(d.fields)[0] || null;
  const showField = a && a.kind !== "slope" && d && d.fields && field && d.fields[field];
  const legend = [];
  // regions
  for (const r of S.regions) {
    path(r.pts, true);
    g.fillStyle = r.color;
    g.globalAlpha = showField ? 0.25 : dark ? 0.85 : 1;
    g.fill();
    g.globalAlpha = 1;
  }
  if (showField) {
    const f = d.fields[field].v;
    let lo = Infinity, hi = -Infinity;
    for (const v of f) if (isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
    for (const t of d.tris) {
      const v = (f[t[0]] + f[t[1]] + f[t[2]]) / 3;
      g.beginPath();
      t.forEach((n, i) => (i ? g.lineTo(X(d.nodes[n][0]), Y(d.nodes[n][1])) : g.moveTo(X(d.nodes[n][0]), Y(d.nodes[n][1]))));
      g.closePath();
      g.fillStyle = ramp((v - lo) / (hi - lo || 1));
      g.fill();
      g.strokeStyle = g.fillStyle;
      g.lineWidth = 0.6;
      g.stroke();
    }
    if (d.phreatic && d.phreatic.length > 1) {
      g.strokeStyle = "#1565c0"; g.lineWidth = 2; g.setLineDash([]);
      path(d.phreatic); g.stroke();
    }
    $("#legend").innerHTML = `<span>${esc(d.fields[field].label)}: ${fmt(lo, 3)}<span class="ramp" style="background:linear-gradient(90deg,${ramp(0)},${ramp(0.5)},${ramp(1)})"></span>${fmt(hi, 3)}</span>`;
  }
  g.strokeStyle = ink; g.lineWidth = 1;
  for (const r of S.regions) { path(r.pts, true); g.stroke(); }
  // water table
  const showPiezo = S.piezo.length > 1 && (!a || a.kind !== "slope" || a.pwp === "piezometric");
  if (showPiezo && !showField) {
    g.strokeStyle = "#1e6fd9"; g.lineWidth = 2; g.setLineDash([7, 4]);
    path(S.piezo); g.stroke(); g.setLineDash([]);
    const p = S.piezo[Math.floor(S.piezo.length / 2)];
    const x = X(p[0]) + 14, y = Y(p[1]) - 3;
    g.fillStyle = "#1e6fd9";
    g.beginPath(); g.moveTo(x - 6, y - 9); g.lineTo(x + 6, y - 9); g.lineTo(x, y); g.closePath(); g.fill();
    legend.push(`<span><i style="background:#1e6fd9"></i>Water table</span>`);
  }
  // surcharges
  for (const [x1, x2, q] of S.surcharges) {
    const n = Math.max(2, Math.round((X(x2) - X(x1)) / 14));
    g.strokeStyle = "#c2410c"; g.fillStyle = "#c2410c"; g.lineWidth = 1.4;
    const yTop = Math.min(...S.regions.flatMap((r) => r.pts.filter((pt) => pt[0] >= x1 - 1e-6 && pt[0] <= x2 + 1e-6).map((pt) => Y(pt[1]))), Y(S.bounds[3]));
    for (let i = 0; i <= n; i++) {
      const sx = X(x1) + (i / n) * (X(x2) - X(x1));
      g.beginPath(); g.moveTo(sx, yTop - 20); g.lineTo(sx, yTop - 3); g.stroke();
      g.beginPath(); g.moveTo(sx - 3, yTop - 7); g.lineTo(sx + 3, yTop - 7); g.lineTo(sx, yTop - 1); g.closePath(); g.fill();
    }
    g.beginPath(); g.moveTo(X(x1), yTop - 20); g.lineTo(X(x2), yTop - 20); g.stroke();
    g.font = "11px system-ui"; g.fillText(`${q} ${S.u.pressure}`, X(x1), yTop - 24);
  }
  // slope results
  $("#fos").hidden = true;
  if (a && a.kind === "slope" && d && d.slip) {
    if (d.trials) {
      const fs = d.trials.map((t) => t.fos).filter((v) => v !== null);
      const lo = Math.min(d.fos, ...fs), hi = Math.max(...fs, d.fos + 1e-6);
      for (let i = d.trials.length - 1; i >= 0; i--) {
        const t = d.trials[i];
        g.strokeStyle = ramp(0.3 + 0.7 * (t.fos - lo) / (hi - lo));
        g.globalAlpha = 0.45; g.lineWidth = 1;
        path(t.pts); g.stroke();
      }
      g.globalAlpha = 1;
    }
    path(d.mass, true);
    g.fillStyle = "rgba(255,210,77,0.45)"; g.fill();
    g.strokeStyle = dark ? "#e8d27a" : "#5a4a10"; g.lineWidth = 0.7;
    for (const [x, yb, yt] of d.slices) { g.beginPath(); g.moveTo(X(x), Y(yb)); g.lineTo(X(x), Y(yt)); g.stroke(); }
    g.strokeStyle = "#d01818"; g.lineWidth = 2.6;
    path(d.slip); g.stroke();
    if (d.centre) {
      const cx = X(d.centre[0]), cy = Y(d.centre[1]);
      if (cx > -20 && cx < W + 20 && cy > -20 && cy < H + 20) {
        g.setLineDash([3, 4]); g.lineWidth = 1;
        g.beginPath(); g.moveTo(cx, cy); g.lineTo(X(d.slip[0][0]), Y(d.slip[0][1]));
        g.moveTo(cx, cy); g.lineTo(X(d.slip[d.slip.length - 1][0]), Y(d.slip[d.slip.length - 1][1])); g.stroke();
        g.setLineDash([]); g.fillStyle = "#d01818"; g.beginPath(); g.arc(cx, cy, 3.5, 0, 7); g.fill();
      }
    }
    $("#fos").hidden = false;
    $("#fos").innerHTML = `<small>Factor of safety</small><span class="v ${fosClass(d.fos)}">${fmt(d.fos)}</span>`;
  } else if (a && a.kind === "slope" && d && d.message) {
    $("#fos").hidden = false;
    $("#fos").innerHTML = `<small>${esc(d.message.slice(0, 80))}</small>`;
  }
  // axes ticks
  g.fillStyle = dark ? "#8b97a7" : "#6b7685"; g.font = "10px system-ui"; g.strokeStyle = g.fillStyle; g.lineWidth = 1;
  const [x0, y0, x1] = S.bounds;
  const step = niceStep((x1 - x0) / 6);
  for (let x = Math.ceil(x0 / step) * step; x <= x1 + 1e-9; x += step) {
    g.beginPath(); g.moveTo(X(x), Y(y0)); g.lineTo(X(x), Y(y0) + 4); g.stroke();
    g.fillText(String(+x.toFixed(2)), X(x) - 6, Y(y0) + 15);
  }
  if (!showField) {
    const used = new Set(S.regions.map((r) => r.mid));
    $("#legend").innerHTML = S.materials.filter((m) => used.has(m.id))
      .map((m) => `<span><i style="background:${esc(m.color)}"></i>${esc(m.name)}</span>`).join("") + legend.join("");
  }
}
function niceStep(raw) {
  const p = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  const n = raw / p;
  return (n < 1.5 ? 1 : n < 3.5 ? 2 : n < 7.5 ? 5 : 10) * p;
}

// pan and pinch zoom
const pointers = new Map();
let gesture = null;
cv.addEventListener("pointerdown", (e) => { cv.setPointerCapture(e.pointerId); pointers.set(e.pointerId, [e.offsetX, e.offsetY]); startGesture(); });
cv.addEventListener("pointermove", (e) => {
  if (!pointers.has(e.pointerId) || !gesture || !view) return;
  pointers.set(e.pointerId, [e.offsetX, e.offsetY]);
  const pts = [...pointers.values()];
  const c = centroid(pts), dist = spread(pts);
  const k = gesture.dist > 0 && dist > 0 ? dist / gesture.dist : 1;
  view.s = gesture.s * k;
  view.ox = c[0] - (gesture.c[0] - gesture.ox) * k;
  view.oy = c[1] - (gesture.c[1] - gesture.oy) * k;
  view.auto = false;
  draw();
});
const endPointer = (e) => { pointers.delete(e.pointerId); startGesture(); };
cv.addEventListener("pointerup", endPointer);
cv.addEventListener("pointercancel", endPointer);
cv.addEventListener("dblclick", fit);
cv.addEventListener("wheel", (e) => {
  e.preventDefault();
  if (!view) return;
  const k = Math.exp(-e.deltaY * 0.0015);
  view.ox = e.offsetX - (e.offsetX - view.ox) * k;
  view.oy = e.offsetY - (e.offsetY - view.oy) * k;
  view.s *= k; view.auto = false; draw();
}, { passive: false });
function startGesture() {
  const pts = [...pointers.values()];
  gesture = pts.length && view ? { c: centroid(pts), dist: spread(pts), s: view.s, ox: view.ox, oy: view.oy } : null;
}
const centroid = (pts) => [pts.reduce((a, p) => a + p[0], 0) / pts.length, pts.reduce((a, p) => a + p[1], 0) / pts.length];
const spread = (pts) => (pts.length < 2 ? 0 : Math.hypot(pts[0][0] - pts[1][0], pts[0][1] - pts[1][1]));
new ResizeObserver(() => resize()).observe($("#view"));

// Android back button: close the open sheet or menu, then go back to the start page, then leave
(function nativeBack() {
  const plugins = window.Capacitor && window.Capacitor.Plugins;
  if (!plugins || !plugins.App) return;
  plugins.App.addListener("backButton", () => {
    if (!$("#sheet").hidden) $("#sheet").hidden = true;
    else if (!$("#menu").hidden) $("#menu").hidden = true;
    else if (!$("#app").hidden) showStart();
    else plugins.App.exitApp();
  });
})();

// ---------------------------------------------------------------- start up
(async function start() {
  applyTheme(store.get("theme", "auto"));
  try {
    const q = JSON.parse(store.get("quick", "null"));
    if (q) {
      for (const k of ["height", "ratio", "crest", "toe", "base", "surcharge"]) if (q[k] !== undefined && q[k] !== null) $("#q-" + k).value = q[k];
      if (q.water !== null && q.water !== undefined) { $("#q-water-on").checked = true; $("#q-water").value = q.water; }
      if (Array.isArray(q.layers) && q.layers.length) layers = q.layers;
    }
  } catch { /* defaults */ }
  renderLayers();
  try {
    INFO = await boot();
  } catch (err) {
    $("#boot-msg").textContent = "Could not start the engine: " + err.message;
    return;
  }
  $("#examples").innerHTML = INFO.examples.map((n) => `<button data-ex="${esc(n)}">${esc(n)}</button>`).join("");
  $("#examples").querySelectorAll("button").forEach((b) => (b.onclick = async () => {
    await run("open_example", [b.dataset.ex], "Opening...");
    fit();
  }));
  $("#foot").textContent = `GeoLab ${INFO.version} · runs fully on this device`;
  $("#boot").hidden = true;
  const last = store.get("last", null);
  if (last) {
    try { await run("from_json", [JSON.parse(last)]); } catch { /* start fresh */ }
  }
  showStart();
})();
