/* The three tracks: the selector, and the problem card that tells judges exactly what is being solved and from what data. */
(function () {
  "use strict";
  const { h, $, getJson, state, bus } = HP;

  const ICON = {
    today: '<path d="M12 3v3M12 18v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M3 12h3M18 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/><circle cx="12" cy="12" r="4"/>',
    budget: '<path d="M3 21h18M5 21V9l7-5 7 5v12M9 21v-6h6v6"/>',
    trees: '<path d="M12 22v-6M7 16h10l-3-4h2l-4-5-4 5h2z"/>',
  };
  const svg = (name) => { const s = document.createElementNS("http://www.w3.org/2000/svg", "svg"); s.setAttribute("viewBox", "0 0 24 24"); s.setAttribute("fill", "none"); s.setAttribute("stroke", "currentColor"); s.setAttribute("stroke-width", "2"); s.setAttribute("stroke-linecap", "round"); s.setAttribute("stroke-linejoin", "round"); s.innerHTML = ICON[name]; return s; };

  function renderNav() {
    $("#trackNav").replaceChildren(...Object.values(state.tracks).map((t) => h("button", { type: "button", role: "tab", class: "track-btn", "data-track": t.id, "aria-selected": String(t.id === state.track), onclick: () => setTrack(t.id) },
      h("span", { class: "ticon" }, svg(t.id)), h("span", { class: "ttext" }, h("b", {}, t.title), h("small", {}, t.subtitle)))));
  }

  function renderProblem() {
    const t = state.tracks[state.track];
    if (!t) return;
    const list = (items) => h("ul", {}, items.map((x) => h("li", {}, x)));
    $("#problemCard").replaceChildren(
      h("div", { class: "p-main" },
        h("div", { class: "p-kicker" }, `${t.title} · ${t.who}`),
        h("h2", {}, t.question),
        h("div", { class: "p-grid" },
          h("div", {}, h("h3", {}, "The problem"), h("p", {}, t.problem)),
          h("div", {}, h("h3", {}, "What we do"), h("p", {}, t.solution)),
          h("div", {}, h("h3", {}, "What you get"), h("p", {}, t.output)))),
      h("div", { class: "p-side" },
        h("div", {}, h("h3", {}, "Data used"), h("div", { class: "fchips" }, t.data.map((x) => h("span", { class: "tchip" }, x)))),
        h("div", {}, h("h3", {}, "Live data"), h("p", { class: "mute" }, t.live_api || "None for this track: every figure comes from the city's heat and Census data.")),
        h("div", {}, h("h3", {}, "What this cannot do"), list(t.cannot_do))));
    $("#trackLine").textContent = `${t.title} · ${t.subtitle}`;
    $("#foot").textContent = `Offsets describe one afternoon's spatial pattern (NOAA Heat Watch), not a forecast, and are less certain away from the roads that were measured. Areas outside that area are not shown. The assistant can make mistakes: check key figures against the panels.`;
  }

  function setTrack(id) {
    if (!state.tracks[id]) return;
    state.track = id;
    document.body.dataset.track = id;
    try { localStorage.setItem("heat-track", id); } catch (_) { /* private mode */ }
    if (location.hash !== "#" + id) history.replaceState(null, "", "#" + id);
    renderNav(); renderProblem();
    bus.emit("track", id);
    requestAnimationFrame(() => bus.emit("layout"));
  }
  HP.setTrack = setTrack;

  async function init() {
    const data = await getJson("/api/tracks");
    state.tracks = Object.fromEntries(data.tracks.map((t) => [t.id, t]));
    state.focus = data.focus;
    // The scripts after this one register their listeners as they load. Announce the track only once all of them have run,
    // or a fast response can fire the event before anyone is listening and the page never loads its data.
    if (document.readyState === "loading") await new Promise((resolve) => document.addEventListener("DOMContentLoaded", resolve, { once: true }));
    let start = location.hash.replace("#", "");
    if (!state.tracks[start]) { try { start = localStorage.getItem("heat-track"); } catch (_) { start = null; } }
    bus.emit("tracks-ready", state.tracks);
    setTrack(state.tracks[start] ? start : "today");
  }
  init().catch((e) => { $("#problemCard").textContent = `Could not load the tracks: ${e.message}`; });
})();
