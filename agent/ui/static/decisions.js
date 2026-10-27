/* The decision for the chosen track: the ranked list, the key numbers, the equity audit, and the draft proposal.
   Every number here is computed from the city's heat data; none is written by the assistant. */
(function () {
  "use strict";
  const { h, $, fmt, signed, pct, getJson, state, bus } = HP;
  const params = { today: { focus: "hydration", limit: 10 }, budget: { radius_km: 1.5, cost: "" }, trees: { limit: 8 } };
  const TITLES = { today: "Dispatch list", budget: "Proposed cooling centers", trees: "Planting priorities" };
  const DRAFT = { today: "Draft dispatch brief", budget: "Draft council proposal", trees: "Draft planting brief" };
  const cache = {};

  const url = (t) => t === "today" ? `/api/today?focus=${params.today.focus}&limit=${params.today.limit}`
    : t === "budget" ? `/api/budget?radius_km=${params.budget.radius_km}${params.budget.cost !== "" ? `&cost_per_center=${params.budget.cost}` : ""}`
    : `/api/trees?limit=${params.trees.limit}`;

  const items = (r) => r.sites || r.centers || [];
  const chipFor = (s) => h("span", { class: "chipv", style: `background:${HP.offsetCss(s.offset_f, state.maxAbs)}` }, `${signed(s.offset_f)}°`);

  function row(s, t, r) {
    const extra = t === "budget" ? `${fmt(s.people_covered, 0)} people covered · ${pct(s.share_of_need)} of the need` : t === "trees" ? `${pct(s.share_of_priority)} of the priority · intervention undetermined` : "";
    return h("div", { class: "rank", tabindex: "0", role: "button", "aria-label": `${s.rank}. ${s.area}`, onclick: () => bus.emit("place", { ...s, geo_id: s.geo_id, lat: s.lat, lon: s.lon, offset_f: s.offset_f, tract: s, source: "list", fly: true }),
      onkeydown: (e) => { if (e.key === "Enter") e.currentTarget.click(); } },
      h("div", { class: "n" }, s.rank),
      h("div", {}, h("div", { class: "t" }, s.area), h("div", { class: "m" }, s.reason), extra ? h("div", { class: "m strong" }, extra) : null),
      chipFor(s));
  }

  // ---------------------------------------------------------------- controls
  function controls(t) {
    const box = $("#listControls");
    const select = (label, value, options, onchange) => h("label", { class: "ctl" }, h("span", {}, label), h("select", { onchange: (e) => onchange(e.target.value) }, options.map(([v, text]) => h("option", { value: v, selected: String(v) === String(value) }, text))));
    if (t === "today") {
      box.replaceChildren(h("div", { class: "seg" }, Object.entries(state.focus || {}).map(([k, label]) => h("button", { type: "button", "aria-pressed": String(params.today.focus === k), onclick: () => { params.today.focus = k; load(); } }, label))));
    } else if (t === "budget") {
      box.replaceChildren(
        h("div", { class: "ctl fixed" }, h("span", {}, "Centers funded"), h("b", {}, "3")),
        select("Walking radius", params.budget.radius_km, [[1, "1 km"], [1.5, "1.5 km"], [2, "2 km"], [3, "3 km"]], (v) => { params.budget.radius_km = Number(v); load(); }),
        h("label", { class: "ctl" }, h("span", {}, "Cost per center (optional)"), h("input", { type: "number", min: "0", step: "50000", placeholder: "USD", value: params.budget.cost, onchange: (e) => { params.budget.cost = e.target.value; load(); } })));
    } else {
      box.replaceChildren(select("Areas", params.trees.limit, [[5, "Top 5"], [8, "Top 8"], [12, "Top 12"]], (v) => { params.trees.limit = Number(v); load(); }));
    }
  }

  // ---------------------------------------------------------------- key numbers
  const tile = (label, value, sub, color) => h("div", { class: "kpi" }, h("div", { class: "k-label" }, label), h("div", { class: "k-value", style: color ? `color:${color}` : null }, value), h("div", { class: "k-sub", title: sub }, sub || " "));

  function kpis() {
    const t = state.track, r = state.decision && state.decision.track === t ? state.decision : null, T = state.tracts, S = state.scenarioHigh;
    const total = T.reduce((a, x) => a + (x.total_pop || 0), 0);
    let tiles = [];
    if (t === "today") {
      const over = S === null ? [] : T.filter((x) => S + x.offset_f >= 100);
      tiles = [
        tile("Scenario high", S === null ? "–" : `${fmt(S, 0)}°F`, S === null ? "Waiting for the forecast" : `${state.scenarioSource || "scenario"} (live NWS forecast)`),
        tile("Areas expected at 100°F+", S === null || !T.length ? "–" : String(over.length), S !== null && S < 95 ? "Forecast is mild: try the 102°F scenario" : T.length ? `of ${T.length} areas` : ""),
        tile("People in those areas", S === null ? "–" : fmt(over.reduce((a, x) => a + (x.total_pop || 0), 0), 0), total ? `of ${fmt(total, 0)} in the measured area` : ""),
        tile("First stop", r ? r.sites[0].area : "–", r ? r.sites[0].reason : "", "var(--cyan)")];
    } else if (t === "budget") {
      const d = r && r.heat_days;
      tiles = [
        tile("Centers proposed", r ? String(r.count) : "–", r ? `${r.radius_km} km walk each${r.total_cost_usd !== null ? ` · $${fmt(r.total_cost_usd, 0)} total` : " · cost not in the data"}` : ""),
        tile("People covered", r ? fmt(r.people_covered, 0) : "–", total ? `of ${fmt(total, 0)} in the measured area` : ""),
        tile("Heat-exposed people covered", r && r.heat_exposed_people ? pct(r.heat_exposed_covered / r.heat_exposed_people) : "–", r ? `${fmt(r.heat_exposed_covered, 0)} of ${fmt(r.heat_exposed_people, 0)} in areas ≥ +1°F` : ""),
        tile("Days at 100°F a year", d ? fmt(d.average_days_per_year, 0) : "–", d ? `peak ${d.peak_days} in ${d.peak_year} (station history)` : "", "var(--hot)")];
    } else {
      const top = r && r.sites[0], poverty = r && r.audit.rows.find((x) => x.measure === "Poverty rate");
      tiles = [
        tile("Top planting area", top ? top.area : "–", top ? top.reason : "", "var(--ok)"),
        tile("People in the top areas", r ? fmt(r.sites.reduce((a, s) => a + (s.people || 0), 0), 0) : "–", r ? `${r.sites.length} areas of ${T.length}` : ""),
        tile("Share of the priority", r ? pct(r.share_of_priority) : "–", "people × excess heat × poverty, across the measured area"),
        tile("Poverty in these areas", poverty ? pct(poverty.chosen) : "–", poverty ? `vs. ${pct(poverty.city)} for the city · ${poverty.verdict}` : "")];
    }
    $("#kpis").replaceChildren(...tiles);
  }

  // ---------------------------------------------------------------- equity audit (compact)
  function equity(r) {
    const body = $("#equityBody");
    if (!r) return body.replaceChildren(h("div", { class: "mute pad" }, "Waiting for the decision…"));
    const a = r.audit, fmtv = (row, v) => (v === null ? "n/a" : row.percent ? pct(v) : fmt(v, 0));
    const rows = a.rows.map((x) => {
      const top = Math.max(x.chosen || 0, x.city || 0, 0.0001) * 1.25, kind = x.verdict.split(" ")[0];
      return h("div", { class: "eqrow", title: `${x.measure}: ${fmtv(x, x.chosen)} in these areas, ${fmtv(x, x.city)} for the city (${x.verdict})` },
        h("div", { class: "eql" }, x.measure.replace("Households without a car", "No car in household")),
        h("div", { class: "eqbar" }, h("i", { class: "fill " + kind, style: `width:${((x.chosen || 0) / top) * 100}%` }), h("i", { class: "tick", style: `left:${((x.city || 0) / top) * 100}%` })),
        h("div", { class: "eqv" }, h("b", {}, fmtv(x, x.chosen)), h("span", {}, ` vs ${fmtv(x, x.city)}`)));
    });
    body.replaceChildren(h("div", { class: "equity compact" },
      h("div", { class: "eq-summary" }, a.summary),
      ...rows,
      h("div", { class: "eq-legend" }, h("i", { class: "fill above" }), "these areas", h("i", { class: "tick sample" }), "city average", h("span", { title: a.note }, "· race is never used")),
      h("div", { class: "eq-legend", style: "margin-top:2px" }, `Compared with all ${a.city_tracts} measured tracts, weighted by population.`)));
  }

  // ---------------------------------------------------------------- coverage built up by the three centers (Fund Cooling Centers)
  function coverage(r) {
    const body = $("#coverageBody"), curve = (r.curve || []).slice(0, 3);
    if (!curve.length) return body.replaceChildren(h("div", { class: "mute pad" }, "No coverage data."));
    const max = Math.max(...curve.map((c) => c.people_covered), 1), k = (n) => (n >= 1000 ? `${fmt(n / 1000, n >= 100000 ? 0 : 1)}k` : fmt(n, 0));
    const last = curve[curve.length - 1];
    const cols = curve.map((c) => h("div", { class: "ccol" + (c.count === curve.length ? " on" : ""), title: `${c.count === 1 ? "The first center" : `The first ${c.count} centers`}: ${fmt(c.people_covered, 0)} people (+${fmt(c.added, 0)} from this center)` },
      h("div", { class: "cval" }, k(c.people_covered)), h("div", { class: "cbar" }, h("i", { style: `height:${(c.people_covered / max) * 100}%` })),
      h("div", { class: "cadd" }, c.count === 1 ? "center 1" : "+" + k(c.added)), h("div", { class: "cn" }, c.count === 1 ? "1 center" : `${c.count} centers`)));
    body.replaceChildren(h("div", { class: "coverage" },
      h("div", { class: "cov-sub" }, h("b", {}, fmt(last.people_covered, 0)), ` people covered by the ${curve.length} centers, each within ${r.radius_km} km. Every center covers people the others do not.`),
      h("div", { class: "cols three" }, cols),
      h("div", { class: "cov-note" }, `Together they reach ${pct(r.share_of_need_covered)} of the heat-exposed need and ${fmt(r.heat_exposed_covered, 0)} of the ${fmt(r.heat_exposed_people, 0)} people in the hottest areas.`)));
  }

  // ---------------------------------------------------------------- list
  function render(t, r) {
    $("#listTitle").textContent = TITLES[t];
    $("#draftBtn").textContent = DRAFT[t];
    $("#listMethod").textContent = r.method.length > 110 ? r.method.slice(0, 108) + "…" : r.method;
    $("#listMethod").title = r.method;
    if (t === "budget") coverage(r);
    $("#listBody").replaceChildren(...[
      t === "trees" ? h("div", { class: "note-inline" }, "Intervention is undetermined: no canopy or pavement data is loaded, so this ranks where to start, not what to build.") : null,
      t === "budget" && r.heat_days ? h("div", { class: "note-inline ok" }, `Station history: the city reaches 100°F on ${fmt(r.heat_days.average_days_per_year, 0)} days a year on average (peak ${r.heat_days.peak_days} in ${r.heat_days.peak_year}).`) : null,
      t === "budget" ? h("div", { class: "note-inline" }, r.cost_note) : null,
      ...items(r).map((s) => row(s, t, r))].filter(Boolean));
  }

  let token = 0;
  async function load() {
    const t = state.track, mine = ++token;
    controls(t);
    $("#listBody").replaceChildren(h("div", { class: "mute pad" }, "Loading…"));
    try {
      await HP.loadTracts();
      const r = await getJson(url(t));
      if (mine !== token) return;
      r.track = t; state.decision = r; cache[t] = r;
      render(t, r); equity(r); kpis();
      bus.emit("decision", { track: t, result: r, params: params[t] });
    } catch (e) {
      if (mine !== token) return;
      $("#listBody").replaceChildren(h("div", { class: "pad" }, h("div", { class: "err-card" }, e.message)));
      equity(null);
    }
  }

  // ---------------------------------------------------------------- draft proposal
  async function draft() {
    const t = state.track, modal = $("#proposalModal"), body = $("#proposalBody");
    $("#proposalTitle").textContent = DRAFT[t];
    $("#proposalNote").textContent = "";
    body.replaceChildren(h("div", { class: "thinking" }, h("i"), h("i"), h("i"), h("span", { class: "secs" }, "Drafting from the figures…")));
    modal.hidden = false;
    const p = params[t];
    const payload = t === "today" ? { track: t, focus: p.focus, limit: p.limit } : t === "budget" ? { track: t, radius_km: p.radius_km, cost_per_center: p.cost === "" ? null : Number(p.cost) } : { track: t, limit: p.limit };
    try {
      const res = await fetch("/api/proposal", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || "Could not draft the proposal");
      body.replaceChildren(h("pre", { class: "proposal-text" }, data.text));
      $("#proposalNote").textContent = "Drafted by the assistant from the figures on this page only. Review before use.";
    } catch (e) {
      body.replaceChildren(h("div", { class: "err-card" }, e.message));
    }
  }

  function init() {
    $("#draftBtn").addEventListener("click", draft);
    $("#proposalClose").addEventListener("click", () => { $("#proposalModal").hidden = true; });
    $("#proposalModal").addEventListener("click", (e) => { if (e.target.id === "proposalModal") e.target.hidden = true; });
    $("#proposalCopy").addEventListener("click", async () => { try { await navigator.clipboard.writeText($("#proposalBody").innerText); $("#proposalCopy").textContent = "Copied"; setTimeout(() => ($("#proposalCopy").textContent = "Copy text"), 1500); } catch (_) { /* clipboard blocked */ } });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#proposalModal").hidden = true; });
    bus.on("track", () => { if (cache[state.track]) { state.decision = cache[state.track]; render(state.track, state.decision); equity(state.decision); controls(state.track); kpis(); bus.emit("decision", { track: state.track, result: state.decision, params: params[state.track] }); } else load(); });
    ["scenario", "data"].forEach((e) => bus.on(e, kpis));
    // The assistant answered with a decision: show the same one here.
    bus.on("decision-request", ({ track, args }) => {
      const p = params[track];
      if (track === "today") { if (args.focus && state.focus[args.focus]) p.focus = args.focus; if (args.top_n) p.limit = Math.max(1, Math.min(25, args.top_n)); }
      if (track === "budget") { if (args.radius_km) p.radius_km = args.radius_km; p.cost = args.cost_per_center_usd == null ? "" : args.cost_per_center_usd; }
      if (track === "trees" && args.top_n) p.limit = Math.max(1, Math.min(15, args.top_n));
      delete cache[track];
      if (state.track !== track) HP.setTrack(track); else load();
    });
    HP.loadTracts().then(() => bus.emit("data", { tracts: state.tracts })).catch(() => {});
  }
  init();
})();
