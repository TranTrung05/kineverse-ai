"use strict";
/* KINEVERSE · 3D TEST SCENE – vật thể 3D MOCK để thử điều khiển (KHÔNG phải Unity, không có vật lý).
   Bộ dựng hình 3D tối giản trên canvas 2D (không thư viện ngoài, chạy offline).
   Lệnh nhận vào là đúng các lệnh gửi Unity: SELECT / GRAB / MOVE / RELEASE / ROTATE / SCALE / SWITCH_MODE / CANCEL / ... */
const Scene3D = (() => {
  const TAU = Math.PI * 2, PHI = (1 + Math.sqrt(5)) / 2;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const MODES = ["MOVE", "ROTATE", "SCALE"];

  /* ---------- hình học ---------- */
  const norm3 = (v) => { const l = Math.hypot(...v) || 1; return v.map((x) => x / l); };
  const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
  const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

  function hull(verts, edge) {          // các tam giác có 3 cạnh = edge (dùng cho đa diện đều)
    const f = [], d = (i, j) => Math.hypot(...sub(verts[i], verts[j]));
    for (let i = 0; i < verts.length; i++) for (let j = i + 1; j < verts.length; j++) for (let k = j + 1; k < verts.length; k++)
      if (Math.abs(d(i, j) - edge) < 1e-3 && Math.abs(d(j, k) - edge) < 1e-3 && Math.abs(d(i, k) - edge) < 1e-3) f.push([i, j, k]);
    return f;
  }
  function stellate(g, h) {              // dựng chóp trên mỗi mặt -> hình sao gai
    const v = g.v.slice(), f = [];
    for (const face of g.f) {
      const pts = face.map((i) => g.v[i]);
      const c = [0, 1, 2].map((a) => pts.reduce((s, p) => s + p[a], 0) / pts.length);
      const n = norm3(cross(sub(pts[1], pts[0]), sub(pts[2], pts[0])));
      const s = dot(n, c) < 0 ? -1 : 1;
      v.push([c[0] + n[0] * h * s, c[1] + n[1] * h * s, c[2] + n[2] * h * s]);
      const a = v.length - 1;
      for (let i = 0; i < face.length; i++) f.push([face[i], face[(i + 1) % face.length], a]);
    }
    return { v, f, star: true };
  }
  const ring = (n, r, y) => Array.from({ length: n }, (_, i) => [r * Math.cos(TAU * i / n), y, r * Math.sin(TAU * i / n)]);

  const SHAPES = {
    cube: () => { const v = [[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]].map((p) => p.map((x) => x * 0.75));
      return { v, f: [[0,3,2,1],[4,5,6,7],[0,1,5,4],[2,3,7,6],[1,2,6,5],[0,4,7,3]], star: true }; },
    pyramid: () => ({ v: [[-0.9,0.7,-0.9],[0.9,0.7,-0.9],[0.9,0.7,0.9],[-0.9,0.7,0.9],[0,-1,0]],
      f: [[0,1,2,3],[0,1,4],[1,2,4],[2,3,4],[3,0,4]], star: true }),
    octahedron: () => { const v = [[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]].map((p) => p.map((x) => x * 1.1));
      return { v, f: hull(v, 1.1 * Math.SQRT2), star: true }; },
    icosahedron: () => { const v = []; for (const a of [-1, 1]) for (const b of [-PHI, PHI]) v.push([0, a, b], [a, b, 0], [b, 0, a]);
      const n = v.map(norm3); return { v: n, f: hull(n, 2 / Math.hypot(1, PHI)), star: true }; },
    sphere: () => { const v = [[0, -1, 0]], f = [], R = 7, L = 12;
      for (let r = 1; r < R; r++) { const t = Math.PI * r / R; for (let l = 0; l < L; l++) { const a = TAU * l / L; v.push([Math.sin(t) * Math.cos(a), -Math.cos(t), Math.sin(t) * Math.sin(a)]); } }
      v.push([0, 1, 0]); const top = v.length - 1;
      for (let l = 0; l < L; l++) f.push([0, 1 + (l + 1) % L, 1 + l]);
      for (let r = 0; r < R - 2; r++) for (let l = 0; l < L; l++) { const a = 1 + r * L + l, b = 1 + r * L + (l + 1) % L; f.push([a, b, b + L, a + L]); }
      for (let l = 0; l < L; l++) f.push([top, 1 + (R - 2) * L + l, 1 + (R - 2) * L + (l + 1) % L]);
      return { v: v.map((p) => p.map((x) => x * 0.95)), f, star: true }; },
    cylinder: () => { const n = 14, v = [...ring(n, 0.7, -0.95), ...ring(n, 0.7, 0.95)], f = [Array.from({ length: n }, (_, i) => i), Array.from({ length: n }, (_, i) => n + i)];
      for (let i = 0; i < n; i++) f.push([i, (i + 1) % n, n + (i + 1) % n, n + i]); return { v, f, star: true }; },
    cone: () => { const n = 16, v = [...ring(n, 0.9, 0.8), [0, -1.1, 0]], f = [Array.from({ length: n }, (_, i) => i)];
      for (let i = 0; i < n; i++) f.push([i, (i + 1) % n, n]); return { v, f, star: true }; },
    torus: () => { const U = 18, V = 8, v = [], f = [];
      for (let i = 0; i < U; i++) for (let j = 0; j < V; j++) { const a = TAU * i / U, b = TAU * j / V, r = 0.72 + 0.3 * Math.cos(b);
        v.push([r * Math.cos(a), 0.3 * Math.sin(b), r * Math.sin(a)]); }
      for (let i = 0; i < U; i++) for (let j = 0; j < V; j++) f.push([i * V + j, ((i + 1) % U) * V + j, ((i + 1) % U) * V + (j + 1) % V, i * V + (j + 1) % V]);
      return { v, f, star: false }; },
    star: () => { const ico = SHAPES.icosahedron(); const s = stellate({ v: ico.v.map((p) => p.map((x) => x * 0.62)), f: ico.f }, 0.55); return s; },
    gem: () => { const n = 8, v = [...ring(n, 0.55, -0.55), ...ring(n, 1.0, -0.1), [0, 1.05, 0]], f = [Array.from({ length: n }, (_, i) => i)];
      for (let i = 0; i < n; i++) f.push([i, (i + 1) % n, n + (i + 1) % n, n + i]);
      for (let i = 0; i < n; i++) f.push([n + i, n + (i + 1) % n, 2 * n]); return { v, f, star: true }; },
  };
  const KINDS = Object.keys(SHAPES);
  const HUES = { cube: 190, pyramid: 28, octahedron: 160, icosahedron: 265, sphere: 215, cylinder: 48, cone: 340, torus: 175, star: 8, gem: 295 };
  const geo = {};
  for (const k of KINDS) {
    const g = SHAPES[k]();
    g.n = g.f.map((face) => {            // pháp tuyến hướng ra ngoài (hình sao-đối-với-gốc) hoặc không định hướng (torus)
      const p = face.map((i) => g.v[i]);
      let n = norm3(cross(sub(p[1], p[0]), sub(p[2], p[0])));
      const c = [0, 1, 2].map((a) => p.reduce((s, q) => s + q[a], 0) / p.length);
      if (g.star && dot(n, c) < 0) n = n.map((x) => -x);
      return n;
    });
    geo[k] = g;
  }

  /* ---------- trạng thái ---------- */
  const st = {
    W: 960, H: 600, objs: [], nextId: 1, sel: null, grab: null, hover: null, mode: 0, layout: "SHOWCASE",
    zones: [], effects: [], pointer: null, ptrKind: "none", spin: false, labels: true,
    stats: {}, t0: null, banner: null, onToast: () => {}, onChange: () => {},
  };
  const rnd = (() => { let s = 12345; return () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296; })();
  const nowMs = () => performance.now();

  function resetStats() { st.stats = { moves: 0, grabs: 0, miss: 0, cancelGrab: 0, drops: 0, placed: 0 }; st.t0 = null; }
  function makeObj(kind, x, y, size = 1, extra = {}) {
    const o = { id: st.nextId++, kind, name: kind.toUpperCase(), x, y, tx: x, ty: y, size, tsize: size, hue: HUES[kind],
      rx: 0.5 + rnd() * 0.6, ry: rnd() * TAU, rz: 0, trx: 0, tgy: 0, vy: 0, placed: false, zone: null, flash: 0, ...extra };
    o.trx = o.rx; o.tgy = o.ry; st.objs.push(o); return o;
  }
  const base = () => Math.min(st.W, st.H) * 0.085;        // bán kính cơ sở (px)

  const LAYOUTS = {
    SHOWCASE() { KINDS.forEach((k, i) => makeObj(k, st.W * (0.12 + 0.19 * (i % 5)), st.H * (i < 5 ? 0.3 : 0.7))); },
    SCATTER() { KINDS.forEach((k) => makeObj(k, st.W * (0.1 + 0.8 * rnd()), st.H * (0.12 + 0.76 * rnd()), 0.7 + rnd() * 0.8)); },
    OVERLAP() {  // vật chồng sát nhau: thử độ chính xác chọn/nắm
      ["cube", "sphere", "torus", "gem", "star", "cone"].forEach((k, i) => makeObj(k, st.W * 0.5 + (i - 2.5) * base() * 0.85, st.H * 0.5 + ((i % 2) - 0.5) * base() * 0.7, 1.15));
    },
    SIZES() {    // lớn/nhỏ lẫn lộn: thử độ ổn định khi nắm vật nhỏ
      const s = [0.45, 0.6, 0.8, 1.0, 1.3, 1.7, 2.0];
      s.forEach((z, i) => makeObj(KINDS[(i * 3) % KINDS.length], st.W * (0.1 + 0.8 * i / (s.length - 1)), st.H * (0.35 + 0.3 * (i % 2)), z));
    },
    TARGETS() {  // kéo mỗi vật vào đúng vòng tròn nét đứt cùng màu; có đo thời gian
      const ks = ["cube", "pyramid", "sphere", "torus", "gem"];
      ks.forEach((k, i) => {
        const o = makeObj(k, st.W * (0.12 + 0.19 * i), st.H * 0.8, 0.9);
        const zx = st.W * (0.14 + 0.18 * ((i * 2) % 5)), zy = st.H * (0.32 + 0.06 * (i % 2));
        o.zone = { x: zx, y: zy, r: base() * 1.25 };
      });
    },
  };

  function load(name) {
    st.layout = name; st.objs = []; st.nextId = 1; st.sel = st.grab = st.hover = null; resetStats();
    LAYOUTS[name](); st.objs.forEach((o, i) => { o.name = `${o.kind.toUpperCase()}-${i + 1}`; });
    st.onChange();
  }

  /* ---------- chiếu & chọn ---------- */
  const rad = (o) => base() * o.size * 1.05;
  function toPx(pos, source) {         // pos chuẩn hóa 0..1 -> px cảnh. Camera: vùng với tay 12%..88% -> toàn cảnh
    let u = pos.x, v = pos.y;
    if (source === "camera") { u = clamp((u - 0.12) / 0.76, 0, 1); v = clamp((v - 0.1) / 0.78, 0, 1); }
    return { x: u * st.W, y: v * st.H };
  }
  function pick(p, slack = 1.0) {
    let best = null, bd = 1e9;
    for (const o of st.objs) {
      const d = Math.hypot(p.x - o.x, p.y - o.y) / (rad(o) * 1.15 * slack + 14);
      if (d < 1 && (d < bd - 0.02 || (Math.abs(d - bd) <= 0.02 && best && o.id === st.grab))) { best = o; bd = d; }
    }
    return best;
  }
  const byId = (id) => st.objs.find((o) => o.id === id) || null;
  const effect = (k, x, y, c) => st.effects.push({ k, x, y, c, t0: nowMs() });
  const toast = (t) => st.onToast(t);

  /* ---------- áp dụng lệnh ---------- */
  function apply(e) {
    const a = e.action, p = e.payload || {}, pos = p.position ? toPx(Array.isArray(p.position) ? { x: p.position[0], y: p.position[1] } : p.position, e.source) : null;
    const sel = byId(st.sel), g = byId(st.grab), tgt = g || sel;
    const step = base() * 1.6;
    switch (a) {
      case "SELECT": {
        const o = pos ? pick(pos, 1.3) : null;
        st.sel = o ? o.id : null; if (pos) effect("ring", pos.x, pos.y, o ? "#00D9FF" : "#FFC247");
        toast(o ? "TARGET · " + o.name : "NO TARGET"); break; }
      case "GRAB": {
        if (g) break;
        const o = (pos && pick(pos, 1.7)) || sel;
        if (!o) { st.stats.miss++; toast("GRAB MISS"); if (pos) effect("ring", pos.x, pos.y, "#FF4D6D"); break; }
        st.grab = st.sel = o.id; st.stats.grabs++; o.start = { x: o.x, y: o.y };
        o.off = pos ? { x: o.x - pos.x, y: o.y - pos.y } : { x: 0, y: 0 };
        if (st.t0 === null) st.t0 = nowMs();
        effect("ring", o.x, o.y, "#FF8A00"); toast("GRAB · " + o.name); break; }
      case "MOVE": {
        if (!g) break;
        st.stats.moves++;
        const dx = p.dx || 0, dy = p.dy || 0;
        if (st.mode === 0) {
          if (pos && g.off) { g.tx = clamp(pos.x + g.off.x, 0, st.W); g.ty = clamp(pos.y + g.off.y, 0, st.H); }
          else { g.tx = clamp(g.tx + dx * 1.2, 0, st.W); g.ty = clamp(g.ty + dy * 1.2, 0, st.H); }
        } else if (st.mode === 1) { g.tgy += dx * 0.014; g.trx += dy * 0.014; }
        else { g.tsize = clamp(g.tsize * Math.exp(-dy * 0.006), 0.3, 2.6); }
        break; }
      case "ROTATE": if (tgt) { tgt.tgy += (p.dx || 5) * 0.012; tgt.trx += (p.dy || 0) * 0.012; } break;
      case "SCALE": if (tgt) tgt.tsize = clamp(tgt.tsize + (p.delta || 0) * 1.2, 0.3, 2.6); break;
      case "RELEASE": {
        if (!g) break;
        st.grab = null; st.stats.drops++;
        if (g.zone && !g.placed && Math.hypot(g.tx - g.zone.x, g.ty - g.zone.y) < g.zone.r) {
          g.placed = true; g.tx = g.zone.x; g.ty = g.zone.y; g.flash = 1; st.stats.placed++;
          effect("ring", g.zone.x, g.zone.y, "#00E5A8");
          const total = st.objs.filter((o) => o.zone).length;
          toast(st.stats.placed === total ? `ALL PLACED · ${((nowMs() - st.t0) / 1000).toFixed(1)}s` : `PLACED ${st.stats.placed}/${total}`);
        } else toast("RELEASED");
        break; }
      case "CANCEL":
        if (g) { g.tx = g.start.x; g.ty = g.start.y; st.stats.cancelGrab++; toast("CANCEL WHILE GRABBING"); }
        st.grab = null; st.sel = null; break;
      case "CONFIRM": if (sel) { sel.flash = 1; toast("CONFIRMED · " + sel.name); } break;
      case "SWITCH_MODE": st.mode = (st.mode + 1) % MODES.length; st.banner = { t0: nowMs(), text: "MODE · " + MODES[st.mode] }; break;
      case "MOVE_LEFT": if (tgt) tgt.tx = clamp(tgt.tx - step, 0, st.W); break;
      case "MOVE_RIGHT": if (tgt) tgt.tx = clamp(tgt.tx + step, 0, st.W); break;
      case "MOVE_UP": if (tgt) tgt.ty = clamp(tgt.ty - step, 0, st.H); break;
      case "MOVE_DOWN": if (tgt) tgt.ty = clamp(tgt.ty + step, 0, st.H); break;
      case "RESET": load(st.layout); st.mode = 0; toast("SCENE RESET"); break;
    }
    st.onChange();
  }

  /* ---------- dựng hình ---------- */
  const LIGHT = norm3([-0.4, -0.7, -0.6]);
  function drawObject(cx, o) {
    const g = geo[o.kind], r = rad(o), D = 5;
    const sa = Math.sin(o.ry), ca = Math.cos(o.ry), sb = Math.sin(o.rx), cb = Math.cos(o.rx), sc = Math.sin(o.rz), cc = Math.cos(o.rz);
    const rot = (p) => { let [x, y, z] = p;
      let x1 = x * ca + z * sa, z1 = -x * sa + z * ca; x = x1; z = z1;
      let y1 = y * cb - z * sb, z2 = y * sb + z * cb; y = y1; z = z2;
      let x2 = x * cc - y * sc, y2 = x * sc + y * cc; return [x2, y2, z]; };
    const V = g.v.map(rot);
    const P = V.map(([x, y, z]) => { const k = D / (D + z * 0.6); return [o.x + x * r * k, o.y + y * r * k, z]; });
    const sel = st.sel === o.id, gr = st.grab === o.id, hov = st.hover === o.id;
    const col = gr ? "#FF8A00" : sel ? "#00D9FF" : null;
    const faces = [];
    g.f.forEach((face, i) => {
      const n = rot(g.n[i]);
      if (g.star && n[2] > 0.02) return;                      // loại mặt quay lưng (hình lồi/sao)
      const z = face.reduce((s, k) => s + V[k][2], 0) / face.length;
      faces.push({ face, n, z });
    });
    faces.sort((a, b) => b.z - a.z);
    // bóng đổ
    cx.fillStyle = "rgba(0,0,0,.28)"; cx.beginPath(); cx.ellipse(o.x, o.y + r * 1.15, r * 0.9, r * 0.22, 0, 0, TAU); cx.fill();
    const h = o.hue, flash = o.flash;
    for (const { face, n } of faces) {
      const lit = Math.abs(dot(n, LIGHT));
      cx.fillStyle = `hsla(${h},75%,${22 + 42 * lit + 18 * flash}%,0.86)`;
      cx.strokeStyle = col || `hsla(${h},100%,${62 + 20 * flash}%,.95)`;
      cx.lineWidth = sel || gr ? 1.8 : 1.1; cx.lineJoin = "round";
      cx.beginPath(); face.forEach((k, j) => (j ? cx.lineTo(P[k][0], P[k][1]) : cx.moveTo(P[k][0], P[k][1]))); cx.closePath(); cx.fill(); cx.stroke();
    }
    if (sel || gr || hov) {                                    // vòng chọn
      const t = nowMs() / 400;
      cx.strokeStyle = gr ? "#FF8A00" : sel ? "#00D9FF" : "rgba(0,217,255,.45)"; cx.lineWidth = gr ? 2.5 : 1.5;
      cx.setLineDash(gr ? [] : [6, 5]); cx.lineDashOffset = -t * 6;
      cx.beginPath(); cx.arc(o.x, o.y, r * 1.35 + (gr ? 3 * Math.sin(t * 2) : 0), 0, TAU); cx.stroke(); cx.setLineDash([]);
    }
    if (st.labels) {
      cx.font = "11px Consolas, monospace"; cx.textAlign = "center"; cx.fillStyle = gr ? "#FF8A00" : sel ? "#00D9FF" : "rgba(191,233,245,.65)";
      cx.fillText(o.name + (o.placed ? " ✓" : ""), o.x, o.y + r * 1.55 + 10); cx.textAlign = "start";
    }
  }

  function drawFloor(cx, now) {
    const W = st.W, H = st.H;
    cx.fillStyle = "#030911"; cx.fillRect(0, 0, W, H);
    const gr = cx.createLinearGradient(0, 0, 0, H); gr.addColorStop(0, "rgba(0,217,255,0)"); gr.addColorStop(1, "rgba(0,120,200,.13)");
    cx.fillStyle = gr; cx.fillRect(0, 0, W, H);
    cx.strokeStyle = "rgba(0,217,255,.09)"; cx.lineWidth = 1;
    for (let x = 0; x <= W; x += 48) { cx.beginPath(); cx.moveTo(x, 0); cx.lineTo(x, H); cx.stroke(); }
    for (let y = 0; y <= H; y += 48) { cx.beginPath(); cx.moveTo(0, y); cx.lineTo(W, y); cx.stroke(); }
    for (const o of st.objs) if (o.zone) {                      // vùng thả
      const z = o.zone; cx.strokeStyle = o.placed ? "#00E5A8" : `hsl(${o.hue},90%,60%)`; cx.lineWidth = 2; cx.setLineDash([8, 6]);
      cx.lineDashOffset = -now / 60; cx.beginPath(); cx.arc(z.x, z.y, z.r, 0, TAU); cx.stroke(); cx.setLineDash([]);
      cx.fillStyle = o.placed ? "rgba(0,229,168,.12)" : "rgba(255,255,255,.03)"; cx.fill();
      cx.font = "11px Consolas, monospace"; cx.textAlign = "center"; cx.fillStyle = cx.strokeStyle; cx.fillText("DROP · " + o.kind.toUpperCase(), z.x, z.y - z.r - 6); cx.textAlign = "start";
    }
  }

  function drawPip(cx, frame, active) {                          // khung camera thu nhỏ: nhìn bàn tay ngay trong cảnh
    if (!frame || !frame.landmarks) return;
    const w = 176, h = 132, x0 = st.W - w - 12, y0 = 12;
    cx.fillStyle = "rgba(3,9,17,.78)"; cx.fillRect(x0, y0, w, h); cx.strokeStyle = "rgba(0,217,255,.5)"; cx.lineWidth = 1; cx.strokeRect(x0, y0, w, h);
    const lm = frame.landmarks, X = (p) => x0 + p[0] * w, Y = (p) => y0 + p[1] * h;
    cx.strokeStyle = "#00D9FF"; cx.lineWidth = 1.5;
    for (const [a, b] of CONN) { cx.beginPath(); cx.moveTo(X(lm[a]), Y(lm[a])); cx.lineTo(X(lm[b]), Y(lm[b])); cx.stroke(); }
    const pinch = frame.gesture === "PINCH";
    cx.fillStyle = pinch ? "#FF8A00" : "#fff";
    for (const i of [4, 8]) { cx.beginPath(); cx.arc(X(lm[i]), Y(lm[i]), pinch ? 4.5 : 3, 0, TAU); cx.fill(); }
    cx.font = "11px Consolas, monospace"; cx.fillStyle = pinch ? "#FF8A00" : "#00D9FF";
    cx.fillText(`${frame.gesture} ${(frame.confidence * 100).toFixed(0)}%`, x0 + 6, y0 + 14);
  }
  const CONN = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[17,18],[18,19],[19,20],[0,17]];

  function frame(cx, now, ctx) {                                 // ctx: {source, frame}
    const W = st.W, H = st.H;
    for (const o of st.objs) {                                   // làm mượt chuyển động
      const k = st.grab === o.id ? 0.35 : 0.2;
      o.x += (o.tx - o.x) * k; o.y += (o.ty - o.y) * k; o.size += (o.tsize - o.size) * 0.25;
      o.rx += (o.trx - o.rx) * 0.3; o.ry += (o.tgy - o.ry) * 0.3;
      if (st.spin && st.grab !== o.id) { o.tgy += 0.008; o.ry += 0.008; }
      else if (!st.sel && st.grab !== o.id) { o.tgy += 0.0025; o.ry += 0.0025; }
      o.flash *= 0.94;
    }
    // con trỏ: camera = điểm chụm/đầu ngón trỏ; chuột = vị trí chuột
    let ptr = null;
    if (ctx.source === "camera" && ctx.frame && ctx.frame.pointer) ptr = toPx({ x: ctx.frame.pointer[0], y: ctx.frame.pointer[1] }, "camera");
    else if (ctx.mouse) ptr = ctx.mouse;
    st.pointer = ptr; st.hover = ptr && !st.grab ? (pick(ptr, 1.0) || { id: null }).id : null;
    drawFloor(cx, now);
    [...st.objs].sort((a, b) => (st.grab === a.id) - (st.grab === b.id) || a.y - b.y).forEach((o) => drawObject(cx, o));
    if (ptr) {
      const gr = !!st.grab, pinch = ctx.frame && ctx.frame.gesture === "PINCH" && ctx.source === "camera";
      cx.strokeStyle = gr || pinch ? "#FF8A00" : "#00D9FF"; cx.lineWidth = 2; cx.beginPath(); cx.arc(ptr.x, ptr.y, gr ? 11 : 16, 0, TAU); cx.stroke();
      if (gr || pinch) { cx.fillStyle = "rgba(255,138,0,.35)"; cx.fill(); }
      cx.beginPath(); cx.moveTo(ptr.x - 24, ptr.y); cx.lineTo(ptr.x - 8, ptr.y); cx.moveTo(ptr.x + 8, ptr.y); cx.lineTo(ptr.x + 24, ptr.y);
      cx.moveTo(ptr.x, ptr.y - 24); cx.lineTo(ptr.x, ptr.y - 8); cx.moveTo(ptr.x, ptr.y + 8); cx.lineTo(ptr.x, ptr.y + 24); cx.stroke();
    }
    st.effects = st.effects.filter((e) => now - e.t0 < 900);
    for (const e of st.effects) { const t = (now - e.t0) / 900; cx.strokeStyle = e.c; cx.globalAlpha = 1 - t; cx.lineWidth = 3;
      cx.beginPath(); cx.arc(e.x, e.y, 14 + 70 * t, 0, TAU); cx.stroke(); cx.globalAlpha = 1; }
    // HUD
    cx.font = "13px Consolas, monospace"; cx.fillStyle = "#00D9FF";
    cx.fillText(`MODE ${MODES[st.mode]}  ·  ${st.layout}  ·  SRC ${ctx.source.toUpperCase()}`, 14, 22);
    const g = byId(st.grab), s = byId(st.sel);
    cx.fillStyle = g ? "#FF8A00" : "#5C8aa0"; cx.fillText(g ? "GRABBED " + g.name : s ? "SELECTED " + s.name : "NO SELECTION", 14, 42);
    if (st.t0 !== null && st.objs.some((o) => o.zone)) { cx.fillStyle = "#00E5A8"; cx.fillText(`PLACED ${st.stats.placed}/${st.objs.filter((o) => o.zone).length}  ${((now - st.t0) / 1000).toFixed(1)}s`, 14, 62); }
    if (ctx.source === "camera") drawPip(cx, ctx.frame, true);
    if (st.banner && now - st.banner.t0 < 1100) { const a = 1 - (now - st.banner.t0) / 1100;
      cx.fillStyle = `rgba(5,11,20,${0.8 * a})`; cx.fillRect(0, H / 2 - 34, W, 68); cx.fillStyle = `rgba(0,217,255,${a})`;
      cx.font = "bold 28px Consolas, monospace"; cx.textAlign = "center"; cx.fillText(st.banner.text, W / 2, H / 2 + 10); cx.textAlign = "start"; }
  }

  load("SHOWCASE");
  return {
    st, MODES, KINDS, LAYOUTS: Object.keys(LAYOUTS), apply, frame, load, pick, toPx,
    modeName: () => MODES[st.mode],
    add(kind) { kind = kind || KINDS[Math.floor(rnd() * KINDS.length)]; const o = makeObj(kind, st.W * (0.15 + 0.7 * rnd()), st.H * (0.2 + 0.6 * rnd()), 0.8 + rnd() * 0.5); o.name = `${kind.toUpperCase()}-${o.id}`; st.onChange(); return o; },
    removeSelected() { const o = byId(st.sel); if (!o) return; st.objs = st.objs.filter((x) => x !== o); st.sel = st.grab = null; st.onChange(); },
    selectId(id) { st.sel = id; st.onChange(); },
    toggleSpin() { st.spin = !st.spin; return st.spin; },
    toggleLabels() { st.labels = !st.labels; return st.labels; },
    byId,
  };
})();
