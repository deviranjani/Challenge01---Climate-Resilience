/* Heat Planner single-page UI. No build step, no dependencies. Model text is always set as textContent. */
(function () {
  "use strict";
  const $ = (s, el = document) => el.querySelector(s);
  const state = { history: [], running: false };

  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    return el;
  }
  const fmt = (n, d = 1) => (n === null || n === undefined ? "n/a" : Number(n).toLocaleString(undefined, { maximumFractionDigits: d }));
  const signed = (n) => (n > 0 ? "+" : "") + fmt(n, 2);
  const pct = (n) => (n === null || n === undefined ? "n/a" : fmt(n * 100, 0) + "%");
  const nice = (s) => String(s).replace(/_/g, " ");

  // ---------------------------------------------------------------- cards
  function problemCard(r) {
    return h("div", { class: "card " + (r.status === "error" ? "err" : "notice") }, h("h3", {}, r.status === "error" ? "That did not work" : "Outside the measured area"), h("div", {}, r.message || r.status));
  }

  function offsetCard(r) {
    const hot = r.predicted_offset_f > 0;
    const max = Math.max(...(r.drivers || []).map((d) => Math.abs(d.effect_f)), 0.01);
    const rows = (r.drivers || []).map((d) => {
      const w = (Math.abs(d.effect_f) / max) * 50;
      const style = d.effect_f >= 0 ? `left:50%;width:${w}%;background:var(--hot)` : `left:${50 - w}%;width:${w}%;background:var(--cool)`;
      return h("div", { class: "drv" }, h("span", {}, nice(d.feature)), h("span", { class: "track" }, h("span", { class: "fill", style })), h("span", { class: "num" }, signed(d.effect_f)));
    });
    const t = r.nearest_tract || {};
    return h("div", { class: "card" },
      h("h3", {}, `Predicted heat at ${fmt(r.latitude, 4)}, ${fmt(r.longitude, 4)}`),
      h("div", { class: "kpis" },
        h("div", { class: "kpi" }, h("div", { class: "v " + (hot ? "hot" : "cool") }, signed(r.predicted_offset_f) + " °F"), h("div", { class: "l" }, "vs. the city average that afternoon")),
        h("div", { class: "kpi" }, h("div", { class: "v" }, pct(t.no_vehicle_rate)), h("div", { class: "l" }, "households without a car")),
        h("div", { class: "kpi" }, h("div", { class: "v" }, fmt(t.median_age)), h("div", { class: "l" }, "median age"))),
      h("h3", { style: "margin-top:14px" }, "What drove it (°F)"), rows);
  }

  function sitesCard(r) {
    const head = h("tr", {}, ["#", "Tract", "Offset °F", "No car", "Median age", "Population", "Score"].map((t, i) => h("th", { class: i > 1 ? "n" : "" }, t)));
    const body = (r.sites || []).map((s, i) => h("tr", {},
      h("td", {}, i + 1), h("td", {}, s.geo_id), h("td", { class: "n" }, signed(s.predicted_offset_f)), h("td", { class: "n" }, pct(s.no_vehicle_rate)),
      h("td", { class: "n" }, fmt(s.median_age)), h("td", { class: "n" }, fmt(s.total_pop, 0)), h("td", { class: "n" }, fmt(s.priority_score, 2))));
    return h("div", { class: "card" }, h("h3", {}, "Where to send relief first"), h("div", { class: "mute", style: "font-size:13px;margin-bottom:8px" }, r.method),
      h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, head), h("tbody", {}, body))));
  }

  function frequencyCard(r) {
    const data = r.days_per_year || [];
    const card = h("div", { class: "card" }, h("h3", {}, `Days at or above ${fmt(r.threshold_f, 0)} °F, by year`));
    if (!data.length) { card.append(h("div", { class: "mute" }, r.trend)); return card; }
    const W = 640, H = 200, pad = 28, max = Math.max(...data.map((d) => d.days), 1), bw = (W - pad * 2) / data.length;
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("class", "chart"); svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Days per year at or above the threshold");
    const add = (name, attrs, text) => { const e = document.createElementNS(ns, name); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (text !== undefined) e.textContent = text; svg.append(e); return e; };
    data.forEach((d, i) => {
      const bh = ((H - pad * 2) * d.days) / max, x = pad + i * bw + bw * 0.15, w = bw * 0.7;
      const bar = add("rect", { class: "bar", x, y: H - pad - bh, width: w, height: bh, rx: 3 });
      bar.append(Object.assign(document.createElementNS(ns, "title"), { textContent: `${d.year}: ${d.days} days` }));
      add("text", { x: x + w / 2, y: H - pad - bh - 4, "text-anchor": "middle" }, d.days);
      add("text", { x: x + w / 2, y: H - 8, "text-anchor": "middle" }, d.year);
    });
    card.append(svg, h("div", { class: "mute", style: "font-size:13px" }, r.trend));
    return card;
  }

  function communityCard(r) {
    const k = (v, l) => h("div", { class: "kpi" }, h("div", { class: "v" }, v), h("div", { class: "l" }, l));
    return h("div", { class: "card" }, h("h3", {}, `Who lives within ${r.radius_km} km`),
      h("div", { class: "kpis" }, k(fmt(r.total_population, 0), `people in ${r.tracts_in_radius} tracts`), k(fmt(r.median_age), "median age"), k(pct(r.poverty_rate), "poverty rate"), k(pct(r.no_vehicle_rate), "households without a car")),
      h("div", { class: "mute", style: "font-size:13px;margin-top:8px" }, r.note));
  }

  const RENDER = { predict_heat_offset: offsetCard, rank_response_sites: sitesCard, heat_frequency: frequencyCard, community_profile: communityCard };

  function cardFor(c) {
    const r = c.result || {};
    if (r.status !== "ok") return problemCard(r);
    const draw = RENDER[c.tool];
    return draw ? draw(r) : null;
  }

  function stepsEl(steps) {
    if (!steps || !steps.length) return null;
    const items = steps.map((s) => h("li", { class: s.error ? "bad" : "" }, h("code", {}, `${s.tool}(${Object.entries(s.args || {}).map(([k, v]) => `${k}=${v}`).join(", ")})`), " ", h("span", {}, s.error ? "failed: " + s.error : (s.ms ?? "?") + " ms")));
    return h("details", { class: "steps" }, h("summary", {}, `How I got this · ${steps.length} step${steps.length === 1 ? "" : "s"}`), h("ol", {}, items));
  }

  // ---------------------------------------------------------------- chat
  function suggest(list, label) {
    $("#suggLabel").textContent = label;
    const box = $("#suggest");
    box.replaceChildren(...list.map((q) => h("button", { type: "button", class: "chip", onclick: () => ask(q) }, q)));
  }

  function setRunning(on) {
    state.running = on;
    $("#go").disabled = on; $("#q").readOnly = on;
    document.querySelectorAll("#suggest .chip").forEach((c) => (c.disabled = on));
  }

  async function ask(question) {
    question = (question || "").trim();
    if (!question || state.running) return;
    $("#q").value = "";
    const out = $("#out");
    out.append(h("div", { class: "you" }, question));
    const wait = h("div", { class: "card loading" }, "Thinking…");
    out.append(wait);
    wait.scrollIntoView({ block: "nearest" });
    setRunning(true);
    try {
      const res = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, history: state.history.slice(-12) }) });
      let data = null;
      try { data = await res.json(); } catch (_) { /* non-JSON error body */ }
      if (!res.ok) throw new Error((data && (data.error || data.detail)) || `Request failed (${res.status})`);
      const reply = h("div", { class: "reply" }, h("div", { class: "msg" }, data.message), (data.cards || []).map(cardFor), stepsEl(data.steps));
      wait.replaceWith(reply);
      state.history.push({ role: "user", text: question }, { role: "assistant", text: data.message });
      suggest(data.followups && data.followups.length ? data.followups : state.starters, data.followups && data.followups.length ? "Follow-up questions" : "Suggested questions");
      reply.scrollIntoView({ block: "nearest" });
    } catch (e) {
      wait.replaceWith(h("div", { class: "card err" }, h("h3", {}, "Something went wrong"), h("div", {}, e.message)));
    } finally {
      setRunning(false);
      $("#q").focus();
    }
  }

  function newChat() {
    if (state.running) return;
    state.history = [];
    $("#out").replaceChildren();
    suggest(state.starters, "Suggested questions");
  }

  // ---------------------------------------------------------------- theme
  function applyTheme(choice) {
    if (choice === "light" || choice === "dark") document.documentElement.dataset.theme = choice; else delete document.documentElement.dataset.theme;
    document.querySelectorAll("[data-theme-choice]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themeChoice === choice)));
    try { localStorage.setItem("heat-theme", choice); } catch (_) { /* private mode */ }
  }

  async function init() {
    document.querySelectorAll("[data-theme-choice]").forEach((b) => b.addEventListener("click", () => applyTheme(b.dataset.themeChoice)));
    let saved = "auto";
    try { saved = localStorage.getItem("heat-theme") || "auto"; } catch (_) { /* ignore */ }
    applyTheme(saved);
    $("#askForm").addEventListener("submit", (e) => { e.preventDefault(); ask($("#q").value); });
    $("#newchat").addEventListener("click", newChat);
    try { state.starters = (await (await fetch("/api/starters")).json()).suggestions; } catch (_) { state.starters = []; }
    suggest(state.starters, "Suggested questions");
  }
  init();
})();
