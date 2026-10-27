/* Live map: Google Maps with a deck.gl heat surface of the measured readings, the model's forecast for each census
   tract, live traffic, satellite and aerial imagery, and Google's photorealistic 3D view. */
(function () {
  "use strict";
  const { h, $, $$, fmt, signed, pct, nice, offsetRgb, getJson, state, bus, script } = HP;
  const DECK_SRC = "https://cdn.jsdelivr.net/npm/deck.gl@9.1.0/dist.min.js";
  const DARK_STYLE = [
    { elementType: "geometry", stylers: [{ color: "#0f1729" }] },
    { elementType: "labels.text.fill", stylers: [{ color: "#8d9ab1" }] },
    { elementType: "labels.text.stroke", stylers: [{ color: "#0b1220" }] },
    { featureType: "administrative", elementType: "geometry", stylers: [{ color: "#26324f" }] },
    { featureType: "poi", stylers: [{ visibility: "off" }] },
    { featureType: "transit", stylers: [{ visibility: "off" }] },
    { featureType: "road", elementType: "geometry", stylers: [{ color: "#1e2a47" }] },
    { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#33447a" }] },
    { featureType: "water", elementType: "geometry", stylers: [{ color: "#071226" }] },
  ];
  const map = { gmap: null, overlay: null, traffic: null, m3d: null, base: "roadmap", show: { heat: true, dots: false, tracts: true, traffic: false }, selected: null, community: null, started: false, ready: false };

  const isDark = () => (document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark")) === "dark";
  const message = (text, bad) => { const el = $("#mapMsg"); el.textContent = text || ""; el.hidden = !text; el.className = "overlay-msg" + (bad ? " err" : ""); };

  // ---------------------------------------------------------------- deck.gl layers
  function layers() {
    const { HeatmapLayer, ScatterplotLayer } = deck;
    const list = [], maxAbs = state.maxAbs;
    if (map.show.heat && state.points.length) {
      const lo = Math.min(...state.points.map((p) => p.offset_f));
      list.push(new HeatmapLayer({ id: "heat", data: state.points, getPosition: (d) => [d.lon, d.lat], getWeight: (d) => d.offset_f - lo + 0.05, aggregation: "MEAN", radiusPixels: 40, intensity: 1.2, threshold: 0.04,
        colorRange: [[56, 189, 248], [125, 211, 252], [226, 232, 240], [253, 164, 175], [244, 63, 94], [159, 18, 57]] }));
    }
    if (map.show.dots) list.push(new ScatterplotLayer({ id: "dots", data: state.points, getPosition: (d) => [d.lon, d.lat], getRadius: 32, radiusUnits: "meters", getFillColor: (d) => [...offsetRgb(d.offset_f, maxAbs), 215], pickable: true }));
    if (map.show.tracts) {
      list.push(new ScatterplotLayer({ id: "tracts", data: state.tracts, getPosition: (d) => [d.lon, d.lat], getRadius: (d) => 230 + Math.sqrt(d.total_pop || 0) * 5.5, radiusUnits: "meters",
        getFillColor: (d) => [...offsetRgb(d.offset_f, maxAbs), 185], getLineColor: [255, 255, 255, 120], getLineWidth: 1, lineWidthUnits: "pixels", stroked: true, pickable: true, autoHighlight: true, highlightColor: [34, 211, 238, 120],
        onClick: ({ object }) => object && bus.emit("place", { lat: object.lat, lon: object.lon, geo_id: object.geo_id, offset_f: object.offset_f, drivers: object.drivers, tract: object, source: "map" }) }));
    }
    if (map.community) list.push(new ScatterplotLayer({ id: "community", data: [map.community], getPosition: (d) => [d.lon, d.lat], getRadius: (d) => d.radius_km * 1000, radiusUnits: "meters", stroked: true, filled: true, getFillColor: [124, 92, 255, 38], getLineColor: [124, 92, 255, 230], getLineWidth: 2, lineWidthUnits: "pixels" }));
    if (map.selected) list.push(new ScatterplotLayer({ id: "selection", data: [map.selected], getPosition: (d) => [d.lon, d.lat], getRadius: 260, radiusUnits: "meters", stroked: true, filled: false, getLineColor: [34, 211, 238, 255], getLineWidth: 3, lineWidthUnits: "pixels" }));
    return list;
  }
  const refresh = () => map.overlay && map.overlay.setProps({ layers: layers() });

  // ---------------------------------------------------------------- base map types
  function applyBase(kind) {
    map.base = kind;
    $$("#baseSeg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.base === kind)));
    const threeD = kind === "3d";
    $("#map").hidden = threeD; $("#map3d").hidden = !threeD;
    $("#layerBar").hidden = threeD; $("#mapLegend").hidden = threeD;
    if (threeD) return open3d();
    if (!map.gmap) return;
    map.gmap.setMapTypeId(kind);
    map.gmap.setOptions({ styles: kind === "roadmap" && isDark() ? DARK_STYLE : null });
    // Aerial (45 degree) imagery exists only where Google has it and at high zoom; ask for it and let Maps decide.
    map.gmap.setTilt(kind === "roadmap" ? 0 : 45);
  }

  async function open3d() {
    const box = $("#map3d");
    try {
      if (!map.m3d) {
        const { Map3DElement, Marker3DElement } = await google.maps.importLibrary("maps3d");
        const c = center();
        map.m3d = new Map3DElement({ center: { lat: c.lat, lng: c.lon, altitude: 0 }, range: 6500, tilt: 62, heading: 0, mode: "HYBRID" });
        box.replaceChildren(map.m3d);
        (state.priority || []).slice(0, 8).forEach((s, i) => {
          const m = new Marker3DElement({ position: { lat: s.latitude, lng: s.longitude, altitude: 40 }, altitudeMode: "RELATIVE_TO_GROUND", extruded: true, label: String(i + 1) });
          map.m3d.append(m);
        });
      }
      message("");
    } catch (e) {
      console.error(e);
      message("The 3D aerial view is not available for this project or browser. Showing aerial imagery instead.", true);
      applyBase("hybrid");
    }
  }

  const center = () => {
    const pts = state.points.length ? state.points : state.tracts.map((t) => ({ lat: t.lat, lon: t.lon }));
    if (!pts.length) return { lat: 32.78, lon: -96.8 };
    return { lat: pts.reduce((a, p) => a + p.lat, 0) / pts.length, lon: pts.reduce((a, p) => a + p.lon, 0) / pts.length };
  };

  function fly(lat, lon, zoomIn) {
    if (map.base === "3d" && map.m3d) {
      try { map.m3d.flyCameraTo({ endCamera: { center: { lat, lng: lon, altitude: 0 }, tilt: 62, range: 1400 }, durationMillis: 2500 }); } catch (_) { /* older runtime */ }
      return;
    }
    if (!map.gmap) return;
    map.gmap.panTo({ lat, lng: lon });
    if (zoomIn || map.gmap.getZoom() < 13) map.gmap.setZoom(zoomIn || 14);
  }

  // ---------------------------------------------------------------- place card
  function placeCard(p) {
    const box = $("#placeCard");
    const t = p.tract || {}, exp = HP.expected(p.offset_f);
    const row = (k, v) => h("div", { class: "row" }, h("span", { class: "mute" }, k), h("b", {}, v));
    const drivers = (p.drivers || []).slice(0, 3).map((d) => row(nice(d.feature), `${signed(d.effect_f || d.attribution)} °F`));
    const title = p.geo_id ? `Tract ${p.geo_id}` : `${fmt(p.lat, 4)}, ${fmt(p.lon, 4)}`;
    box.replaceChildren(...[
      h("h3", {}, title, h("button", { type: "button", class: "x", "aria-label": "Close", onclick: () => { map.selected = null; box.hidden = true; refresh(); } }, "×")),
      h("div", { class: "big", style: `color:${HP.offsetCss(p.offset_f, state.maxAbs)}` }, `${signed(p.offset_f)} °F`),
      h("div", { class: "mute", style: "font-size:12px;margin-bottom:8px" }, exp === null ? "predicted vs. the city average" : `predicted vs. average · about ${fmt(exp, 0)} °F expected on the scenario day`),
      t.total_pop !== undefined ? row("Population", fmt(t.total_pop, 0)) : null,
      t.median_age !== undefined && t.median_age !== null ? row("Median age", fmt(t.median_age)) : null,
      t.poverty_rate !== undefined && t.poverty_rate !== null ? row("Poverty rate", pct(t.poverty_rate)) : null,
      t.no_vehicle_rate !== undefined && t.no_vehicle_rate !== null ? row("No car", pct(t.no_vehicle_rate)) : null,
      drivers.length ? h("div", { style: "margin-top:8px" }, h("div", { class: "mute", style: "font-size:11px;text-transform:uppercase;letter-spacing:.04em" }, "What drove it"), drivers) : null,
      h("div", { class: "actions", style: "margin-top:12px" },
        h("button", { type: "button", class: "btn primary", onclick: () => HP.askChat(HP.placeQuestion(p.lat, p.lon)) }, "Ask the assistant"),
        h("button", { type: "button", class: "btn", onclick: () => { applyBase("hybrid"); fly(p.lat, p.lon, 18); } }, "Aerial view"))
    ].filter(Boolean));
    box.hidden = false;
  }

  function onPlace(p) {
    map.selected = { lat: p.lat, lon: p.lon };
    placeCard(p);
    if (p.fly) fly(p.lat, p.lon);
    refresh();
  }

  // ---------------------------------------------------------------- start
  function loadGoogle(key) {
    if (window.google && google.maps) return Promise.resolve();
    return new Promise((resolve, reject) => {
      window.__gmReady = resolve;
      // Google reports a rejected key after the script has loaded, so show it directly.
      window.gm_authFailure = () => message(`Google Maps rejected the API key for ${location.origin}. Check that the Maps JavaScript API is enabled and this address is an allowed referrer for the key.`, true);
      script(`https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&callback=__gmReady&v=weekly&loading=async`).catch(reject);
    });
  }

  async function start() {
    if (map.started) return;
    map.started = true;
    message("Loading the map…");
    try {
      const [cfg, pts, trs] = await Promise.all([getJson("/api/map/config"), getJson("/api/map/points"), getJson("/api/map/tracts")]);
      state.points = pts.points; state.tracts = trs.tracts;
      state.maxAbs = Math.max(Math.abs(pts.min_offset_f), Math.abs(pts.max_offset_f), 1);
      bus.emit("data", { points: state.points, tracts: state.tracts });
      $("#statusLine").textContent = `${fmt(state.points.length, 0)} measured readings · ${fmt(state.tracts.length, 0)} census tracts inside the measured area · measured average ${fmt(pts.avg_temp_f)} °F`;
      if (!cfg.mapsKey) throw new Error("No Google Maps key is configured. Set GOOGLE_MAPS_API_KEY on the service.");
      await Promise.all([loadGoogle(cfg.mapsKey), script(DECK_SRC)]);
      const c = center();
      map.gmap = new google.maps.Map($("#map"), { center: { lat: c.lat, lng: c.lon }, zoom: 11, mapTypeControl: false, streetViewControl: true, fullscreenControl: false, rotateControl: true, gestureHandling: "greedy", styles: isDark() ? DARK_STYLE : null, backgroundColor: "#0b1220" });
      const bounds = new google.maps.LatLngBounds();
      state.points.forEach((p) => bounds.extend({ lat: p.lat, lng: p.lon }));
      map.gmap.fitBounds(bounds);
      map.traffic = new google.maps.TrafficLayer();
      map.overlay = new deck.GoogleMapsOverlay({
        layers: layers(),
        getTooltip: ({ object, layer }) => {
          if (!object || !layer) return null;
          if (layer.id === "tracts") { const e = HP.expected(object.offset_f); return `Tract ${object.geo_id}: ${signed(object.offset_f)} °F${e === null ? "" : ` · ~${fmt(e, 0)} °F expected`}`; }
          if (layer.id === "dots") return `${fmt(object.temp_f)} °F measured (${signed(object.offset_f)} vs. average)`;
          return null;
        },
      });
      map.overlay.setMap(map.gmap);
      map.ready = true;
      message("");
      if (map.base !== "roadmap") applyBase(map.base);
    } catch (e) {
      map.started = false;
      message(e.message, true);
    }
  }

  function init() {
    $$("[data-layer]").forEach((box) => box.addEventListener("change", () => {
      map.show[box.dataset.layer] = box.checked;
      if (box.dataset.layer === "traffic") { if (map.traffic) map.traffic.setMap(box.checked ? map.gmap : null); } else refresh();
    }));
    $$("#baseSeg button").forEach((b) => b.addEventListener("click", () => applyBase(b.dataset.base)));
    bus.on("place", onPlace);
    bus.on("scenario", () => { refresh(); if (map.selected) { /* place card text uses the scenario; re-render on next select */ } });
    bus.on("community", (c) => { map.community = c; refresh(); fly(c.lat, c.lon, 13); });
    bus.on("theme", () => { if (map.gmap && map.base === "roadmap") map.gmap.setOptions({ styles: isDark() ? DARK_STYLE : null }); });
    bus.on("layout", () => { if (map.gmap) google.maps.event.trigger(map.gmap, "resize"); });
    bus.on("sites", () => { /* priority list feeds the 3D markers when opened */ });
    start();
  }
  init();
})();
