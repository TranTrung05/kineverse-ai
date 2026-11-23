"use strict";
/* KINEVERSE AI CORE – dashboard. Không phụ thuộc thư viện ngoài, chạy offline. */
const $ = (id) => document.getElementById(id);
const WS_URL = "ws://127.0.0.1:" + (new URLSearchParams(location.search).get("ws") || "8765");
const COLORS = { cy: "#00D9FF", bl: "#1677FF", or: "#FF8A00", ok: "#00E5A8", wa: "#FFC247", er: "#FF4D6D" };
const CONN = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[17,18],[18,19],[19,20],[0,17]];
const TIPS = new Set([4, 8, 12, 16, 20]);

const S = {
  source: "mouse", status: null, frame: null, img: null, effects: [], pulse: { c: COLORS.cy, t: 0 },
  mouse: null, lastRow: null,
  rows: new Map(), hist: [], connected: false,
};

/* ---------- WebSocket ---------- */
let ws;
function connect() {
  ws = new WebSocket(WS_URL);
  ws.onopen = () => { S.connected = true; setSys(); };
  ws.onclose = () => { S.connected = false; setSys(); setTimeout(connect, 1500); };
  ws.onerror = () => ws.close();
  ws.onmessage = (e) => { try { handle(JSON.parse(e.data)); } catch (err) { console.error(err); } };
}
const send = (o) => { if (ws && ws.readyState === 1) ws.send(JSON.stringify(o)); };
function setSys() {
  const el = $("h-sys");
  el.textContent = S.connected ? "CORE ONLINE" : "CORE OFFLINE";
  el.className = "pill " + (S.connected ? "ok" : "err");
}

function handle(m) {
  switch (m.type) {
    case "status": onStatus(m); break;
    case "frame": onFrame(m); break;
    case "decision": onDecision(m); break;
    case "command_sent": break;
    case "command_result": onResult(m); break;
    case "source_changed": onSourceChanged(m); break;
    case "info": toast(m.text); break;
    case "summary": renderSummary(m.groups); break;
    case "exported": toast("EXPORTED → " + m.path); $("t-info").textContent = m.path; break;
    case "task_done": if (m.task) $("t-info").textContent = `${m.task.name}: ${m.task.duration_s}s ${m.task.success ? "OK" : "FAIL"} (retry ${m.task.retries})`; break;
  }
}

/* ---------- Panels ---------- */
function onStatus(m) {
  S.status = m;
  S.source = m.active_source;
  const dev = m.devices;
  for (const k of ["camera", "glove", "mouse"]) {
    const d = dev[k], b = document.querySelector(`.src[data-src="${k}"]`);
    b.classList.toggle("active", k === m.active_source);
    b.classList.toggle("off", !d.connected);
    $("d-" + k).textContent = !d.connected ? "OFF" : d.simulated ? "SIM" : "READY";
    b.title = d.detail || "";
  }
  const u = m.unity;
  $("h-unity").textContent = u.connected ? "UNITY ✓" : "UNITY ✕";
  $("h-unity").className = "pill " + (u.connected ? "ok" : "err");
  $("u-state").textContent = u.connected ? "CONNECTED" : "DISCONNECTED";
  $("u-state").style.color = u.connected ? COLORS.ok : COLORS.er;
  $("u-ep").textContent = u.endpoint;
  $("u-cmd").textContent = u.last_command || "--";
  $("u-resp").textContent = u.last_response || "--";
  const p = m.perf;
  const f1 = (v, n = 1) => (v === null || v === undefined ? "--" : Number(v).toFixed(n));
  $("h-fps").textContent = f1(p.fps, 0);
  $("h-lat").textContent = f1(p.e2e_mean_ms, 0);
  $("p-fps").textContent = f1(p.fps);
  $("p-proc").textContent = f1(p.proc_ms) + " ms";
  $("p-e2e").textContent = `${f1(p.e2e_mean_ms)} / ${f1(p.e2e_p95_ms)} ms`;
  $("p-drop").textContent = p.dropped_frames;
  $("p-cmd").textContent = `${p.in_flight} / ${p.dropped_commands}`;
  $("p-cam").textContent = dev.camera.connected ? (dev.camera.detail || "OK") : "NO SIGNAL";
  $("demo-banner").hidden = !m.demo;
}

function onFrame(m) {
  S.frame = m;
  if (m.jpeg) { const im = new Image(); im.onload = () => { S.img = im; }; im.src = "data:image/jpeg;base64," + m.jpeg; }
  else S.img = null;
  $("g-now").textContent = m.gesture === "UNKNOWN" ? "UNKNOWN" : m.gesture.replace("_", " ");
  $("g-conf").textContent = (m.confidence * 100).toFixed(0) + "%";
  $("g-bar").style.width = m.confidence * 100 + "%";
  $("v-hand").textContent = m.landmarks ? `${(m.hand || "hand").toUpperCase()} HAND · TRACKING` : "NO HAND";
}

const CONTINUOUS = new Set(["MOVE", "ROTATE", "SCALE"]);
function onDecision(m) {
  const e = m.event, cont = CONTINUOUS.has(e.action);
  $("g-evt").textContent = m.accepted ? "ACCEPTED" : "REJECTED · " + m.reason;
  $("g-evt").style.color = m.accepted ? COLORS.ok : COLORS.wa;
  if (cont && !m.accepted && m.reason === "throttled") return;           // không làm ngập log
  let row;
  const last = S.lastRow;
  if (cont && m.accepted && last && last.act === e.action && last.el.isConnected && last.el === $("log").firstChild) {
    row = last.el; last.n++;                                              // gộp chuỗi MOVE liên tiếp thành 1 dòng
    row.children[2].textContent = `${e.action} ×${last.n}`;
    row.children[3].textContent = (e.confidence * 100).toFixed(0);
  } else {
    row = addLog(e, m.accepted ? "wait" : "rej", m.accepted ? "…" : m.reason);
    S.lastRow = cont && m.accepted ? { el: row, act: e.action, n: 1 } : null;
  }
  if (m.accepted) { S.rows.set(e.event_id, row); applyAction(e); }
}

function onResult(m) {
  const row = S.rows.get(m.event_id);
  const good = m.status === "ACK";
  if (row) {
    row.className = good ? "ok" : "bad";
    row.lastChild.textContent = good ? `✓ ${m.e2e_ms}ms` : m.status;
    S.rows.delete(m.event_id);
  }
  $("g-cmd").textContent = m.command + (good ? " ✓" : " ✕");
  pulse(good ? COLORS.ok : COLORS.er);
  if (!good) toast("COMMAND " + (m.status === "FAILED" ? "FAILED" : m.status) + " · " + m.command);
}

function onSourceChanged(m) {
  if (!m.ok) { toast("SWITCH REFUSED · " + m.reason); return; }
  if (m.from !== m.to) {
    S.effects.push({ k: "banner", t0: performance.now(), text: `${m.from.toUpperCase()} → ${m.to.toUpperCase()}` });
    toast(m.by === "failover" ? "FAILOVER · " + m.to.toUpperCase() : "SOURCE · " + m.to.toUpperCase());
  }
}

function addLog(e, cls, result) {
  const d = document.createElement("div");
  d.className = cls;
  const t = new Date(e.timestamp * 1000).toTimeString().slice(0, 8);
  for (const v of [t, e.source.slice(0, 3).toUpperCase() + (e.simulated ? "*" : ""), e.action, (e.confidence * 100).toFixed(0), result]) {
    const s = document.createElement("span"); s.textContent = v; d.appendChild(s);
  }
  const log = $("log");
  log.prepend(d);
  while (log.children.length > 150) log.lastChild.remove();
  return d;
}

function renderSummary(groups) {
  const tb = $("sumtbl").tBodies[0];
  tb.textContent = "";
  for (const [k, g] of Object.entries(groups)) {
    const tr = tb.insertRow();
    if (g.simulated) tr.className = "sim";
    const L = g.latency_e2e_ms;
    const cells = [k, g.commands_sent, g.success_rate === null ? "--" : (g.success_rate * 100).toFixed(0) + "%",
      L.mean ?? "--", L.p95 ?? "--", g.misreads_marked, g.retries, g.tracking_lost, `${g.task_success}/${g.tasks}`];
    for (const c of cells) tr.insertCell().textContent = c;
  }
}

function toast(text) {
  const d = document.createElement("div");
  d.className = "toast"; d.innerHTML = "<b>JARVIS</b> · ";
  d.appendChild(document.createTextNode(text));
  $("toasts").appendChild(d);
  setTimeout(() => d.remove(), 2700);
}
const pulse = (c) => { S.pulse = { c, t: performance.now() }; };
/* ---------- Hiệu ứng theo lệnh ---------- */
function applyAction(e) {
  const p = e.payload || {}, pos = p.position || {};
  const at = { x: pos.x ?? 0.5, y: pos.y ?? 0.5 };
  const hist = $("g-hist");
  if (!CONTINUOUS.has(e.action) || !hist.firstChild || hist.firstChild.textContent !== e.action) {
    const s = document.createElement("span"); s.textContent = e.action; hist.prepend(s);
    while (hist.children.length > 8) hist.lastChild.remove();
  }
  $("g-cmd").textContent = e.action;
  Scene3D.apply(e);                                    // vật thể 3D mock phản ứng đúng như Unity sẽ làm
  const now = performance.now();
  switch (e.action) {
    case "GRAB": S.effects.push({ k: "ring", t0: now, ...at, c: COLORS.or }); break;
    case "SELECT": S.effects.push({ k: "ring", t0: now, ...at, c: COLORS.cy }); break;
    case "ACTIVATE": toast("SYSTEM ACTIVE"); pulse(COLORS.cy); break;
    case "CONFIRM": pulse(COLORS.ok); break;
    case "CANCEL": pulse(COLORS.wa); break;
    case "SWITCH_MODE": S.effects.push({ k: "banner", t0: now, text: "MODE · " + Scene3D.modeName() }); break;
    case "MOVE_LEFT": case "MOVE_RIGHT": case "MOVE_UP": case "MOVE_DOWN":
      S.effects.push({ k: "sweep", t0: now, dir: e.action.slice(5).toLowerCase() }); break;
  }
}

/* ---------- Vẽ khung nhìn chính ---------- */
const cv = $("cv"), cx = cv.getContext("2d");
function drawMain(now) {
  const W = cv.width, H = cv.height, f = S.frame;
  cx.clearRect(0, 0, W, H);
  cx.fillStyle = "#030911"; cx.fillRect(0, 0, W, H);
  if (S.img) { cx.globalAlpha = 0.7; cx.drawImage(S.img, 0, 0, W, H); cx.globalAlpha = 1; }
  cx.strokeStyle = "rgba(0,217,255,.08)"; cx.lineWidth = 1;
  for (let x = 0; x <= W; x += 40) { cx.beginPath(); cx.moveTo(x, 0); cx.lineTo(x, H); cx.stroke(); }
  for (let y = 0; y <= H; y += 40) { cx.beginPath(); cx.moveTo(0, y); cx.lineTo(W, y); cx.stroke(); }
  const sy = (now / 12) % (H + 80) - 40;                                    // đường quét holographic
  const g = cx.createLinearGradient(0, sy - 30, 0, sy + 30);
  g.addColorStop(0, "rgba(0,217,255,0)"); g.addColorStop(0.5, "rgba(0,217,255,.12)"); g.addColorStop(1, "rgba(0,217,255,0)");
  cx.fillStyle = g; cx.fillRect(0, sy - 30, W, 60);

  let palm = null;
  const lm = f && f.landmarks;
  if (lm) {
    cx.strokeStyle = COLORS.cy; cx.lineWidth = 2; cx.shadowColor = COLORS.cy; cx.shadowBlur = 8;
    for (const [a, b] of CONN) { cx.beginPath(); cx.moveTo(lm[a][0] * W, lm[a][1] * H); cx.lineTo(lm[b][0] * W, lm[b][1] * H); cx.stroke(); }
    cx.shadowBlur = 0;
    lm.forEach((p, i) => { cx.fillStyle = TIPS.has(i) ? COLORS.or : "#fff"; cx.beginPath(); cx.arc(p[0] * W, p[1] * H, TIPS.has(i) ? 5 : 3, 0, 7); cx.fill(); });
    palm = lm[9];
    const px = palm[0] * W, py = palm[1] * H, r = 26 + 4 * Math.sin(now / 250);
    cx.strokeStyle = COLORS.or; cx.lineWidth = 1.5;
    cx.beginPath(); cx.arc(px, py, r, 0, 7); cx.stroke();
    cx.beginPath(); cx.arc(px, py, r + 12, now / 400, now / 400 + 2.2); cx.stroke();
    cx.fillStyle = COLORS.or; cx.font = "11px Consolas, monospace";
    cx.fillText(`X ${palm[0].toFixed(2)}  Y ${palm[1].toFixed(2)}`, px + r + 8, py - 4);
  }
  // Radar góc phải trên
  const rx = W - 70, ry = 70;
  cx.strokeStyle = "rgba(0,217,255,.5)"; cx.lineWidth = 1;
  for (const r of [18, 36, 54]) { cx.beginPath(); cx.arc(rx, ry, r, 0, 7); cx.stroke(); }
  cx.beginPath(); cx.moveTo(rx - 54, ry); cx.lineTo(rx + 54, ry); cx.moveTo(rx, ry - 54); cx.lineTo(rx, ry + 54); cx.stroke();
  const ang = now / 700;
  const rg = cx.createConicGradient ? cx.createConicGradient(ang, rx, ry) : null;
  if (rg) { rg.addColorStop(0, "rgba(0,217,255,.35)"); rg.addColorStop(0.18, "rgba(0,217,255,0)"); rg.addColorStop(1, "rgba(0,217,255,0)"); cx.fillStyle = rg; cx.beginPath(); cx.arc(rx, ry, 54, 0, 7); cx.fill(); }
  if (palm) { cx.fillStyle = COLORS.or; cx.beginPath(); cx.arc(rx + (palm[0] - 0.5) * 100, ry + (palm[1] - 0.5) * 100, 3, 0, 7); cx.fill(); }
  // Khung góc + nhãn
  cx.strokeStyle = COLORS.cy; cx.lineWidth = 2;
  for (const [x, y, sx, sy2] of [[8, 8, 1, 1], [W - 8, 8, -1, 1], [8, H - 8, 1, -1], [W - 8, H - 8, -1, -1]]) {
    cx.beginPath(); cx.moveTo(x, y + 24 * sy2); cx.lineTo(x, y); cx.lineTo(x + 24 * sx, y); cx.stroke();
  }
  cx.font = "13px Consolas, monospace"; cx.fillStyle = COLORS.cy;
  cx.fillText(`SRC ${S.source.toUpperCase()}`, 20, 28);
  if (f) { cx.fillText(`${f.gesture} ${(f.confidence * 100).toFixed(0)}%  ·  ${f.state}`, 20, H - 20); }
  if (S.source !== "camera") {
    cx.fillStyle = "rgba(255,193,71,.9)";
    cx.fillText(S.source === "mouse" ? "MOUSE PAD: click=SELECT · giữ=GRAB · kéo=MOVE · Ctrl+kéo=ROTATE · lăn=SCALE · dbl=CONFIRM · phải=CANCEL"
      : "GLOVE ACTIVE · xem EVENT LOG", 20, 48);
  }
  if (f && f.demo) { cx.save(); cx.translate(W / 2, H / 2); cx.rotate(-0.25); cx.font = "bold 46px Consolas, monospace"; cx.fillStyle = "rgba(255,194,71,.16)"; cx.textAlign = "center"; cx.fillText("DEMO MODE", 0, 0); cx.restore(); }
  drawEffects(now, W, H);
}

function drawEffects(now, W, H) {
  S.effects = S.effects.filter((e) => now - e.t0 < 1200);
  for (const e of S.effects) {
    const t = (now - e.t0) / 1200, a = 1 - t;
    if (e.k === "ring") {
      cx.strokeStyle = e.c; cx.globalAlpha = a; cx.lineWidth = 3;
      cx.beginPath(); cx.arc(e.x * W, e.y * H, 20 + 70 * t, 0, 7); cx.stroke();
      cx.beginPath(); cx.arc(e.x * W, e.y * H, 10 + 40 * t, 0, 7); cx.stroke(); cx.globalAlpha = 1;
    } else if (e.k === "sweep") {
      const horiz = e.dir === "left" || e.dir === "right", fwd = e.dir === "right" || e.dir === "down";
      const pos = (fwd ? t : 1 - t) * (horiz ? W : H);
      const gr = horiz ? cx.createLinearGradient(pos - 60, 0, pos + 60, 0) : cx.createLinearGradient(0, pos - 60, 0, pos + 60);
      gr.addColorStop(0, "rgba(0,217,255,0)"); gr.addColorStop(0.5, `rgba(0,217,255,${0.5 * a})`); gr.addColorStop(1, "rgba(0,217,255,0)");
      cx.fillStyle = gr; horiz ? cx.fillRect(pos - 60, 0, 120, H) : cx.fillRect(0, pos - 60, W, 120);
      cx.fillStyle = `rgba(255,138,0,${a})`; cx.font = "bold 30px Consolas, monospace"; cx.textAlign = "center";
      cx.fillText({ left: "◀◀", right: "▶▶", up: "▲▲", down: "▼▼" }[e.dir], W / 2, H / 2); cx.textAlign = "start";
    } else if (e.k === "banner") {
      cx.fillStyle = `rgba(5,11,20,${0.8 * a})`; cx.fillRect(0, H / 2 - 36, W, 72);
      cx.strokeStyle = `rgba(0,217,255,${a})`; cx.lineWidth = 2; cx.strokeRect(0, H / 2 - 36, W, 72);
      cx.fillStyle = `rgba(0,217,255,${Math.min(1, a * 1.5)})`; cx.font = "bold 28px Consolas, monospace"; cx.textAlign = "center";
      cx.fillText(e.text, W / 2, H / 2 + 10); cx.textAlign = "start";
    }
  }
}

/* ---------- Arc reactor ---------- */
const ac = $("arc"), ax = ac.getContext("2d");
function drawArc(now) {
  const W = ac.width, c = W / 2;
  ax.clearRect(0, 0, W, W);
  const age = (now - S.pulse.t) / 900, base = Scene3D.st.grab ? COLORS.or : COLORS.cy;
  const col = age < 1 ? S.pulse.c : base, boost = age < 1 ? 1 - age : 0;
  const gr = ax.createRadialGradient(c, c, 5, c, c, 100);
  gr.addColorStop(0, col + "cc"); gr.addColorStop(0.45, col + "33"); gr.addColorStop(1, "rgba(0,0,0,0)");
  ax.fillStyle = gr; ax.fillRect(0, 0, W, W);
  ax.strokeStyle = col; ax.lineWidth = 2; ax.shadowColor = col; ax.shadowBlur = 10 + 14 * boost;
  [[28, 0], [56, 1], [84, -1]].forEach(([r, d], i) => {
    ax.beginPath(); ax.arc(c, c, r, 0, 7); ax.globalAlpha = 0.5; ax.stroke(); ax.globalAlpha = 1;
    for (let k = 0; k < 6; k++) { const a0 = now / (900 + i * 400) * (d || 1) + k * Math.PI / 3; ax.beginPath(); ax.arc(c, c, r, a0, a0 + 0.55); ax.lineWidth = 4; ax.stroke(); }
    ax.lineWidth = 2;
  });
  ax.beginPath(); ax.arc(c, c, 14 + 2 * Math.sin(now / 200) + 6 * boost, 0, 7); ax.fillStyle = "#fff"; ax.fill(); ax.shadowBlur = 0;
}

/* ---------- Cảnh 3D mock ---------- */
const sc = $("sc"), sx = sc.getContext("2d");
Scene3D.st.W = sc.width; Scene3D.st.H = sc.height;
Scene3D.st.onToast = (t) => toast(t);
function updateSceneUi() {
  const st = Scene3D.st, k = st.stats, total = st.objs.filter((o) => o.zone).length;
  $("s-modename").textContent = Scene3D.modeName();
  document.querySelectorAll(".lay").forEach((b) => b.classList.toggle("on", b.dataset.lay === st.layout));
  $("s-spin").classList.toggle("on", st.spin); $("s-lbl").classList.toggle("on", st.labels);
  const el = $("s-stats"); el.textContent = "";
  const add = (label, v, bad) => { const sp = document.createElement("span"); sp.textContent = label + " "; const b = document.createElement("b"); b.textContent = v; if (bad) b.className = "bad"; sp.appendChild(b); el.appendChild(sp); };
  add("OBJECTS", st.objs.length); add("GRABS", k.grabs); add("GRAB-MISS", k.miss, k.miss > 0); add("CANCEL-GRAB", k.cancelGrab, k.cancelGrab > 0);
  add("MOVES", k.moves); add("DROPS", k.drops); if (total) add("PLACED", `${k.placed}/${total}`);
}
Scene3D.st.onChange = updateSceneUi;
document.querySelectorAll(".lay").forEach((b) => b.addEventListener("click", () => { Scene3D.load(b.dataset.lay); toast("LAYOUT · " + b.dataset.lay); }));
$("s-add").onclick = () => Scene3D.add();
$("s-del").onclick = () => Scene3D.removeSelected();
$("s-spin").onclick = () => Scene3D.toggleSpin();
$("s-lbl").onclick = () => Scene3D.toggleLabels();
$("s-mode").onclick = () => sendMouse("SWITCH_MODE");
updateSceneUi();

function loop(now) { drawMain(now); drawArc(now); Scene3D.frame(sx, now, { source: S.source, frame: S.frame, mouse: S.mouse }); requestAnimationFrame(loop); }

/* ---------- Điều khiển ---------- */
document.querySelectorAll(".src").forEach((b) => b.addEventListener("click", () => send({ type: "set_source", source: b.dataset.src })));
$("b-reconnect").onclick = () => { send({ type: "unity_reconnect" }); toast("RECONNECTING UNITY…"); };
$("b-cal").onclick = () => send({ type: "glove_calibrate" });
$("b-ts").onclick = () => { send({ type: "task_start", name: $("t-name").value }); $("t-info").textContent = "task đang chạy…"; };
$("b-tok").onclick = () => send({ type: "task_end", success: true });
$("b-tfail").onclick = () => send({ type: "task_end", success: false });
$("b-retry").onclick = () => send({ type: "mark_retry" });
$("b-mis").onclick = () => send({ type: "mark_misread" });
$("b-export").onclick = () => send({ type: "export" });

const sendMouse = (action, payload = {}) => send({ type: "mouse", action, payload });
const normOf = (cvs) => (e) => { const r = cvs.getBoundingClientRect(); return { x: +((e.clientX - r.left) / r.width).toFixed(4), y: +((e.clientY - r.top) / r.height).toFixed(4) }; };
let md = null, lastMove = 0;
function bindPad(cvs) {
  const norm = normOf(cvs);
  const posPayload = (e, extra = {}) => ({ position: { ...norm(e), z: 0 }, ...extra });
  cvs.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    const down = posPayload(e);
    md = { x0: e.clientX, y0: e.clientY, lx: e.clientX, ly: e.clientY, moved: false, grab: false, down, cvs };
    md.timer = setTimeout(() => { if (md && !md.moved && !md.grab) { md.grab = true; sendMouse("GRAB", down); } }, 250);
  });
  cvs.addEventListener("mousemove", (e) => {
    if (cvs === sc) { const r = sc.getBoundingClientRect(); S.mouse = { x: (e.clientX - r.left) / r.width * sc.width, y: (e.clientY - r.top) / r.height * sc.height }; }
    if (!md || md.cvs !== cvs) return;
    if (Math.hypot(e.clientX - md.x0, e.clientY - md.y0) > 6) {
      if (!md.moved && !md.grab && !e.ctrlKey) { md.grab = true; clearTimeout(md.timer); sendMouse("GRAB", md.down); }  // kéo ngay: tự GRAB tại điểm nhấn
      md.moved = true;
    }
    const now = performance.now();
    if (md.moved && now - lastMove > 40) {
      const dx = e.clientX - md.lx, dy = e.clientY - md.ly; md.lx = e.clientX; md.ly = e.clientY; lastMove = now;
      if (e.ctrlKey) sendMouse("ROTATE", posPayload(e, { dx, dy }));
      else if (md.grab) sendMouse("MOVE", posPayload(e, { dx, dy }));
    }
  });
  cvs.addEventListener("mouseleave", () => { if (cvs === sc) S.mouse = null; });
  cvs.addEventListener("dblclick", (e) => sendMouse("CONFIRM", posPayload(e)));
  cvs.addEventListener("contextmenu", (e) => { e.preventDefault(); sendMouse("CANCEL", posPayload(e)); });
  cvs.addEventListener("wheel", (e) => { e.preventDefault(); sendMouse("SCALE", posPayload(e, { delta: e.deltaY < 0 ? 0.08 : -0.08 })); }, { passive: false });
  return posPayload;
}
bindPad(cv); const scPos = bindPad(sc);
window.addEventListener("mouseup", (e) => {
  if (!md) return;
  clearTimeout(md.timer);
  const pp = { position: { ...normOf(md.cvs)(e), z: 0 } };
  if (md.grab) sendMouse("RELEASE", pp); else if (!md.moved) sendMouse("SELECT", pp);
  md = null;
});
window.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT") return;
  const k = e.key;
  if (k === "1") send({ type: "set_source", source: "camera" });
  else if (k === "2") send({ type: "set_source", source: "glove" });
  else if (k === "3") send({ type: "set_source", source: "mouse" });
  else if (k === "r" || k === "R") sendMouse("RESET");
  else if (k === "m" || k === "M") sendMouse("SWITCH_MODE");
  else if (k === "Escape") sendMouse("CANCEL");
});

setInterval(() => { $("h-clock").textContent = new Date().toTimeString().slice(0, 8); }, 1000);
setSys(); connect(); requestAnimationFrame(loop);
