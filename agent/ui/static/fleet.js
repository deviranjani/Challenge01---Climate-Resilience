/* Fleet plan (Respond Today): split the fleet you have across the ranked areas. Interactive: drag the slider and the plan updates. */
(function () {
  "use strict";
  const { h, $, fmt, signed, getJson, state, bus } = HP;
  const body = $("#fleetBody");
  const fleet = { units: 12, focus: "hydration", token: 0, timer: 0, built: false, loaded: false };
  let nEl, nameEl, summaryEl, listEl, sliderEl;

  function build() {
    nEl = h("b", {}, String(fleet.units)); nameEl = h("span", {}, "trucks"); summaryEl = h("div", { class: "fleet-summary" }); listEl = h("div", { class: "fleet-list" });
    sliderEl = h("input", { type: "range", min: "1", max: "30", step: "1", value: String(fleet.units), "aria-label": "Units available",
      oninput: (e) => { fleet.units = Number(e.target.value); nEl.textContent = fleet.units; }, onchange: () => load() });
    body.replaceChildren(h("div", { class: "fleet-controls" }, h("div", { class: "fleet-n" }, nEl, " ", nameEl, h("small", {}, " available")), sliderEl), summaryEl, listEl);
    fleet.built = true;
  }

  function render(r) {
    $("#fleetUnit").textContent = r.units_name;
    nameEl.textContent = fleet.units === 1 ? r.unit : r.units_name;
    summaryEl.replaceChildren(h("b", {}, fmt(r.people_reached, 0)), " people reached · about ", h("b", {}, fmt(r.people_per_unit, 0)), ` per ${r.unit} · ${r.areas_served} area${r.areas_served === 1 ? "" : "s"}`);
    const max = Math.max(...r.plan.map((p) => p.units), 1);
    listEl.replaceChildren(...r.plan.map((p) => h("div", { class: "frow", tabindex: "0", role: "button", onclick: () => bus.emit("place", { ...p, tract: p, source: "fleet", fly: true }), onkeydown: (e) => { if (e.key === "Enter") e.currentTarget.click(); } },
      h("div", { class: "n" }, p.rank),
      h("div", { class: "fmid" }, h("div", { class: "t" }, p.area), h("div", { class: "bar" }, h("i", { style: `width:${(p.units / max) * 100}%` })),
        h("div", { class: "m" }, `${fmt(p.people, 0)} people · about ${fmt(p.people_per_unit, 0)} per ${r.unit}`)),
      h("div", { class: "fcount" }, "×" + p.units))));
  }

  async function load() {
    if (!fleet.built) build();
    const mine = ++fleet.token;
    try {
      const r = await getJson(`/api/fleet?focus=${fleet.focus}&units=${fleet.units}`);
      if (mine === fleet.token) render(r);
    } catch (e) { if (mine === fleet.token) { if (!fleet.built) build(); listEl.replaceChildren(h("div", { class: "err-card" }, e.message)); } }
  }

  bus.on("decision", ({ track, params }) => {
    if (track !== "today") return;
    const changed = params && params.focus && params.focus !== fleet.focus;
    if (params && params.focus) fleet.focus = params.focus;
    if (!fleet.loaded || changed) { fleet.loaded = true; load(); }
  });
})();
