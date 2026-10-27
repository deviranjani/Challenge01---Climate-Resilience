/* Trackers: five headline numbers that update as the scenario, data and conversation change. */
(function () {
  "use strict";
  const { h, $, fmt, signed, pct, state, bus } = HP;
  const set = (id, value, sub, color) => { const k = $(id); const v = $(".k-value", k); v.textContent = value; v.style.color = color || ""; $(".k-sub", k).textContent = sub || " "; };
  let sparkHost = null;

  function spark(series) {
    const old = $("svg.spark", $("#kpi-days")); if (old) old.remove();
    if (!series || series.length < 2) return;
    const W = 70, H = 26, max = Math.max(...series.map((d) => d.days), 1), ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg"); svg.setAttribute("class", "spark"); svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    const pts = series.map((d, i) => `${(i / (series.length - 1)) * W},${H - 2 - (d.days / max) * (H - 4)}`).join(" ");
    const line = document.createElementNS(ns, "polyline"); line.setAttribute("points", pts); line.setAttribute("fill", "none"); line.setAttribute("stroke", "#22d3ee"); line.setAttribute("stroke-width", "2"); line.setAttribute("stroke-linejoin", "round");
    svg.append(line); $("#kpi-days").append(svg);
  }

  function update() {
    const S = state.scenarioHigh, T = state.tracts;
    set("#kpi-forecast", S === null ? "–" : `${fmt(S, 0)}°F`, S === null ? "" : "scenario high for the city");
    if (S !== null && T.length) {
      const peak = T.reduce((a, b) => (b.offset_f > a.offset_f ? b : a), T[0]);
      set("#kpi-peak", `${fmt(S + peak.offset_f, 0)}°F`, `tract ${String(peak.geo_id).slice(-6)} · ${signed(peak.offset_f)}° vs. average`, "var(--hot)");
    }
    if (T.length) {
      const hot = T.filter((t) => t.offset_f >= 1), total = T.reduce((a, t) => a + (t.total_pop || 0), 0), pop = hot.reduce((a, t) => a + (t.total_pop || 0), 0);
      set("#kpi-people", fmt(pop, 0), `${total ? fmt((pop / total) * 100, 0) : 0}% of ${fmt(total, 0)} people · ${hot.length} tracts ≥ +1°F`);
    }
    const top = state.priority && state.priority[0];
    if (top) set("#kpi-top", String(top.geo_id).slice(-6), `${signed(top.predicted_offset_f)}° · ${pct(top.no_vehicle_rate)} no car · score ${fmt(top.priority_score, 2)}`);
    const hist = state.history;
    if (hist) {
      const full = hist.partial_last_year ? hist.days_per_year.slice(0, -1) : hist.days_per_year, last = full[full.length - 1];
      const dir = { rising: "rising", falling: "falling", no_clear_trend: "no clear trend", insufficient_data: "too few years" }[hist.direction];
      set("#kpi-days", String(last.days), `${last.year} · ${dir} · peak ${hist.peak_days} in ${hist.peak_year}`);
      spark(hist.days_per_year);
    }
  }
  ["scenario", "data", "priority", "history", "forecast"].forEach((e) => bus.on(e, update));
})();
