/* Forecast and scenario pane: the National Weather Service forecast sets the city's expected high; the model's
   per-tract offsets turn it into an expected temperature for every part of the city. */
(function () {
  "use strict";
  const { h, $, fmt, pct, getJson, state, bus } = HP;
  const body = $("#forecastBody");
  const TIERS = [[105, "Extreme", "var(--hot)"], [100, "High", "#fb7185"], [95, "Elevated", "var(--warn)"], [0, "Low", "var(--ok)"]];
  const tier = (t) => TIERS.find(([min]) => t >= min);
  let selectedDate = null, slider = null, statsBox = null, bigNum = null, bigTag = null;

  const dayName = (d) => new Date(d.date + "T12:00:00").toLocaleDateString(undefined, { weekday: "short" });

  function setScenario(high, source) {
    state.scenarioHigh = high;
    if (slider) slider.value = high;
    if (bigNum) bigNum.textContent = `${fmt(high, 0)}°F`;
    if (bigTag) bigTag.textContent = source;
    updateStats();
    bus.emit("scenario", { high, source });
  }

  function updateStats() {
    if (!statsBox) return;
    const T = state.tracts, S = state.scenarioHigh;
    if (!T.length || S === null) { statsBox.replaceChildren(h("div", { class: "mute" }, "Waiting for tract predictions…")); return; }
    const exp = T.map((t) => ({ ...t, temp: S + t.offset_f })).sort((a, b) => b.temp - a.temp);
    const peak = exp[0], low = exp[exp.length - 1];
    const over = (x) => exp.filter((t) => t.temp >= x);
    const pop = (list) => list.reduce((a, t) => a + (t.total_pop || 0), 0);
    const [, label, color] = tier(peak.temp);
    const total = pop(exp);
    statsBox.replaceChildren(
      h("div", { class: "stats" },
        h("div", { class: "stat" }, h("b", {}, `${fmt(peak.temp, 0)}°F`), h("span", {}, `hottest tract · ${String(peak.geo_id).slice(-6)}`)),
        h("div", { class: "stat" }, h("b", {}, `${fmt(low.temp, 0)}°F`), h("span", {}, "coolest tract")),
        h("div", { class: "stat" }, h("b", {}, `${over(100).length} tracts`), h("span", {}, `at or above 100°F · ${fmt(pop(over(100)), 0)} people`)),
        h("div", { class: "stat" }, h("b", {}, `${over(105).length} tracts`), h("span", {}, `at or above 105°F · ${fmt(pop(over(105)), 0)} people`))),
      h("div", { style: "margin-top:10px;font-size:12.5px" }, h("span", { class: "tag", style: `background:${color}` }, `${label} heat`), "planning tier for the hottest tract"),
      h("div", { class: "hbar", title: "Share of people in tracts at or above 100°F" }, h("i", { style: `width:${total ? (pop(over(100)) / total) * 100 : 0}%` })));
  }

  function render(fc) {
    const days = fc.days;
    const hottest = days.reduce((a, b) => (b.high_f > a.high_f ? b : a), days[0]);
    selectedDate = hottest.date;
    const cards = days.map((d) => h("button", { type: "button", class: "day", "aria-pressed": String(d.date === selectedDate), "data-date": d.date,
      onclick: () => { selectedDate = d.date; document.querySelectorAll(".day").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.date === selectedDate))); setScenario(d.high_f, `${dayName(d)} forecast`); } },
      h("div", { class: "dn" }, d === days[0] ? "Today" : dayName(d)), h("div", { class: "dh" }, `${d.high_f}°`), h("div", { class: "dl" }, d.low_f === null ? "" : `low ${d.low_f}°`), h("div", { class: "ds" }, d.summary || "")));
    bigNum = h("b", {}, "–"); bigTag = h("span", { class: "mute" }, "");
    slider = h("input", { type: "range", min: "70", max: "118", step: "1", "aria-label": "Scenario high temperature", oninput: (e) => setScenario(Number(e.target.value), "custom scenario") });
    statsBox = h("div", {});
    const preset = (label, v) => h("button", { type: "button", class: "btn", onclick: () => { selectedDate = null; document.querySelectorAll(".day").forEach((x) => x.setAttribute("aria-pressed", "false")); setScenario(v, label); } }, label);
    body.replaceChildren(
      h("div", { class: "days" }, cards),
      h("div", { class: "scen" },
        h("h3", {}, "Scenario high"),
        h("div", { class: "sv" }, bigNum, bigTag),
        slider,
        h("div", { class: "actions" }, preset("102°F day", 102), preset("108°F heat wave", 108)),
        h("div", { style: "margin-top:10px" }, statsBox)),
      h("div", { class: "mute", style: "font-size:11.5px;padding:0 14px 14px" }, `Source: ${fc.source}${fc.updated ? `, updated ${new Date(fc.updated).toLocaleString()}` : ""}. Expected temperature = scenario high + each tract's predicted offset.`));
    setScenario(hottest.high_f, `${dayName(hottest)} forecast`);
    const pill = $("#fcPill"); pill.textContent = `NWS forecast · ${fc.place || "Dallas"}`; pill.className = "pill ok";
  }

  async function init() {
    bus.on("data", updateStats);
    try {
      const fc = await getJson("/api/forecast");
      state.forecast = fc;
      render(fc);
      bus.emit("forecast", fc);
    } catch (e) {
      body.replaceChildren(h("div", { class: "pad" }, h("div", { class: "err-card" }, e.message), h("div", { class: "mute", style: "margin-top:10px" }, "You can still explore scenarios by choosing a high temperature."),
        h("div", { class: "actions", style: "margin-top:10px" }, h("button", { type: "button", class: "btn primary", onclick: () => { state.scenarioHigh = 102; bus.emit("scenario", { high: 102 }); } }, "Use a 102°F scenario"))));
      const pill = $("#fcPill"); pill.textContent = "Forecast unavailable"; pill.className = "pill bad";
    }
  }
  init();
})();
