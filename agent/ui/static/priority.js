/* Response tracker: tracts ranked by predicted heat blended with who is least able to cope. */
(function () {
  "use strict";
  const { h, $, fmt, signed, pct, getJson, state, bus } = HP;
  const body = $("#priorityBody");

  function render(r) {
    const sites = r.sites, top = Math.max(...sites.map((s) => s.priority_score), 0.01);
    const rows = sites.map((s, i) => {
      const color = HP.offsetCss(s.predicted_offset_f, state.maxAbs);
      return h("div", { class: "rank", tabindex: "0", role: "button", onclick: () => bus.emit("place", { lat: s.latitude, lon: s.longitude, geo_id: s.geo_id, offset_f: s.predicted_offset_f, drivers: s.top_drivers, tract: s, source: "priority", fly: true }),
        onkeydown: (e) => { if (e.key === "Enter") e.currentTarget.click(); } },
        h("div", { class: "n" }, i + 1),
        h("div", {}, h("div", { class: "t" }, `Tract ${String(s.geo_id).slice(-6)}`), h("div", { class: "m" }, `${pct(s.no_vehicle_rate)} no car · median age ${fmt(s.median_age, 0)} · ${fmt(s.total_pop, 0)} people`),
          h("div", { class: "bar" }, h("i", { style: `width:${Math.max(4, (s.priority_score / top) * 100)}%` }))),
        h("span", { class: "chipv", style: `background:${color};color:#0b1220` }, `${signed(s.predicted_offset_f)}°`));
    });
    body.replaceChildren(h("div", { class: "mute", style: "padding:10px 12px 4px;font-size:11.5px" }, r.method), ...rows);
  }

  async function init() {
    try {
      const r = await getJson("/api/priority?limit=10");
      state.priority = r.sites;
      render(r);
      bus.emit("priority", r.sites);
    } catch (e) { body.replaceChildren(h("div", { class: "pad" }, h("div", { class: "err-card" }, e.message))); }
  }
  bus.on("data", () => { if (state.priority) { /* colours depend on the offset scale */ } });
  init();
})();
