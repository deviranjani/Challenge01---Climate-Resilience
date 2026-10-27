/* Heat days tracker: how many days a year the weather stations reach a threshold, and whether that is changing. */
(function () {
  "use strict";
  const { h, $, $$, fmt, getJson, state, bus } = HP;
  const body = $("#historyBody");
  let threshold = 100;

  function chart(series, avg) {
    const W = 520, H = 190, pad = { l: 8, r: 8, t: 20, b: 26 }, max = Math.max(...series.map((d) => d.days), 1);
    const bw = (W - pad.l - pad.r) / series.length, ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("class", "chart"); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", `Days per year at or above ${threshold} degrees`);
    const el = (n, a, t) => { const e = document.createElementNS(ns, n); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); if (t !== undefined) e.textContent = t; svg.append(e); return e; };
    const defs = el("defs", {}); defs.innerHTML = '<linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#7c5cff"/></linearGradient>';
    const base = H - pad.b, scale = (v) => ((base - pad.t) * v) / max;
    series.forEach((d, i) => {
      const x = pad.l + i * bw + bw * 0.16, w = bw * 0.68, bh = scale(d.days);
      const bar = el("rect", { class: "bar", x, y: base - bh, width: w, height: Math.max(bh, 1), rx: 5 });
      const t = document.createElementNS(ns, "title"); t.textContent = `${d.year}: ${d.days} days`; bar.append(t);
      el("text", { x: x + w / 2, y: base - bh - 5, "text-anchor": "middle", class: "val" }, d.days);
      el("text", { x: x + w / 2, y: H - 8, "text-anchor": "middle" }, d.year);
    });
    el("line", { class: "avg", x1: pad.l, x2: W - pad.r, y1: base - scale(avg), y2: base - scale(avg) });
    el("text", { x: W - pad.r, y: base - scale(avg) - 4, "text-anchor": "end" }, `avg ${fmt(avg, 0)}`);
    return svg;
  }

  function render(r) {
    const tagLabel = { rising: "Rising", falling: "Falling", no_clear_trend: "No clear trend", insufficient_data: "Too few years" }[r.direction] || r.direction;
    body.replaceChildren(h("div", { class: "chartwrap" }, chart(r.days_per_year, r.average_days)),
      h("div", { class: "trend" }, h("span", { class: `tag ${r.direction}` }, tagLabel), r.trend));
  }

  async function load(t) {
    threshold = t;
    $$("#thrSeg button").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.thr) === t)));
    body.replaceChildren(h("div", { class: "mute pad" }, "Loading history…"));
    try {
      const r = await getJson(`/api/history?threshold=${t}`);
      if (t === 100) { state.history = r; bus.emit("history", r); }
      render(r);
    } catch (e) { body.replaceChildren(h("div", { class: "pad" }, h("div", { class: "err-card" }, e.message))); }
  }

  $$("#thrSeg button").forEach((b) => b.addEventListener("click", () => load(Number(b.dataset.thr))));
  bus.on("threshold", (t) => { if (!loaded) return; const near = [95, 100, 105].reduce((a, b) => (Math.abs(b - t) < Math.abs(a - t) ? b : a)); load(near); });
  let loaded = false;
  bus.on("track", (id) => { if (id === "budget" && !loaded) { loaded = true; load(100); } });
})();
