/* Map: Google Maps with a deck.gl heat surface of the measured readings and the model's prediction for each area,
   plus the current track's decision (dispatch stops, cooling centers with their walking radius, planting areas). */
(function () {
  "use strict";
  const { h, $, $$, fmt, signed, pct, nice, offsetRgb, getJson, state, bus, script } = HP;
  const DECK_SRC = "https://cdn.jsdelivr.net/npm/deck.gl@9.1.0/dist.min.js";
  const DARK_STYLE = [
    { elementType: "geometry", stylers: [{ color: "#0f1729" }] }, { elementType: "labels.text.fill", stylers: [{ color: "#8d9ab1" }] },
    { elementType: "labels.text.stroke", stylers: [{ color: "#0b1220" }] }, { featureType: "administrative", elementType: "geometry", stylers: [{ color: "#26324f" }] },
    { featureType: "poi", stylers: [{ visibility: "off" }] }, { featureType: "transit", stylers: [{ visibility: "off" }] },
    { featureType: "road", elementType: "geometry", stylers: [{ color: "#1e2a47" }] }, { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#33447a" }] },
    { featureType: "water", elementType: "geometry", stylers: [{ color: "#071226" }] },
  ];
  const TRACK_RGB = { today: [34, 211, 238], budget: [124, 92, 255], trees: [52, 211, 153] };
  const map = { gmap: null, overlay: null, traffic: null, m3d: null, base: "roadmap", show: { heat: true, tracts: true, traffic: false }, selected: null, area: null, sites: [], radiusKm: 0, started: false, fit: true };

  const isDark = () => (document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark")) === "dark";
  const message = (text, bad) => { const el = $("#mapMsg"); el.textContent = text || ""; el.hidden = !text; el.className = "overlay-msg" + (bad ? " err" : ""); };
  const center = () => {
    const pts = state.points.length ? state.points : state.tracts.map((t) => ({ lat: t.lat, lon: t.lon }));
    return pts.length ? { lat: pts.reduce((a, p) => a + p.lat, 0) / pts.length, lon: pts.reduce((a, p) => a + p.lon, 0) / pts.length } : { lat: 32.78, lon: -96.8 };
  };

  // ---------------------------------------------------------------- deck.gl layers
  function layers() {
    const { HeatmapLayer, ScatterplotLayer, TextLayer } = deck, maxAbs = state.maxAbs, rgb = TRACK_RGB[state.track] || TRACK_RGB.today, list = [];
    if (map.show.heat && state.points.length) {
      const lo = Math.min(...state.points.map((p) => p.offset_f));
      list.push(new HeatmapLayer({ id: "heat", data: state.points, getPosition: (d) => [d.lon, d.lat], getWeight: (d) => d.offset_f - lo + 0.05, aggregation: "MEAN", radiusPixels: 40, intensity: 1.2, threshold: 0.04,
        colorRange: [[56, 189, 248], [125, 211, 252], [226, 232, 240], [253, 164, 175], [244, 63, 94], [159, 18, 57]] }));
    }
    if (map.show.tracts) {
      list.push(new ScatterplotLayer({ id: "tracts", data: state.tracts, getPosition: (d) => [d.lon, d.lat], getRadius: (d) => 230 + Math.sqrt(d.total_pop || 0) * 5.5, radiusUnits: "meters",
        getFillColor: (d) => [...offsetRgb(d.offset_f, maxAbs), 170], getLineColor: [255, 255, 255, 110], getLineWidth: 1, lineWidthUnits: "pixels", stroked: true, pickable: true, autoHighlight: true, highlightColor: [34, 211, 238, 120],
        onClick: ({ object }) => object && bus.emit("place", { ...object, tract: object, source: "map" }) }));
    }
    if (map.radiusKm && map.sites.length) {
      list.push(new ScatterplotLayer({ id: "coverage", data: map.sites, getPosition: (d) => [d.lon, d.lat], getRadius: map.radiusKm * 1000, radiusUnits: "meters", stroked: true, filled: true, getFillColor: [...rgb, 34], getLineColor: [...rgb, 200], getLineWidth: 2, lineWidthUnits: "pixels" }));
    }
    if (map.area) list.push(new ScatterplotLayer({ id: "area", data: map.area, getPosition: (d) => [d.lon, d.lat], getRadius: (d) => 330 + Math.sqrt(d.total_pop || 0) * 5.5, radiusUnits: "meters", stroked: true, filled: false, getLineColor: [34, 211, 238, 255], getLineWidth: 3, lineWidthUnits: "pixels" }));
    if (map.sites.length) {
      list.push(new ScatterplotLayer({ id: "sites", data: map.sites, getPosition: (d) => [d.lon, d.lat], getRadius: 420, radiusUnits: "meters", stroked: true, filled: true, getFillColor: [11, 18, 32, 215], getLineColor: [...rgb, 255], getLineWidth: 3, lineWidthUnits: "pixels", pickable: true,
        onClick: ({ object }) => object && bus.emit("place", { ...object, tract: object, source: "list" }) }));
      list.push(new TextLayer({ id: "site-rank", data: map.sites, getPosition: (d) => [d.lon, d.lat], getText: (d) => String(d.rank), getSize: 15, getColor: [255, 255, 255, 255], fontFamily: "Inter, sans-serif", fontWeight: 700, outlineWidth: 2, outlineColor: [11, 18, 32, 255], billboard: true }));
    }
    if (map.selected) list.push(new ScatterplotLayer({ id: "selection", data: [map.selected], getPosition: (d) => [d.lon, d.lat], getRadius: 520, radiusUnits: "meters", stroked: true, filled: false, getLineColor: [255, 255, 255, 255], getLineWidth: 2, lineWidthUnits: "pixels" }));
    return list;
  }
  const refresh = () => map.overlay && map.overlay.setProps({ layers: layers() });

  // ---------------------------------------------------------------- base map types
  function applyBase(kind) {
    map.base = kind;
    $$("#baseSeg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.base === kind)));
    const threeD = kind === "3d";
    $("#map").hidden = threeD; $("#map3d").hidden = !threeD; $("#layerBar").hidden = threeD; $("#mapLegend").hidden = threeD;
    if (threeD) return open3d();
    if (!map.gmap) return;
    map.gmap.setMapTypeId(kind);
    map.gmap.setOptions({ styles: kind === "roadmap" && isDark() ? DARK_STYLE : null });
    map.gmap.setTilt(kind === "roadmap" ? 0 : 45);
  }

  async function open3d() {
    try {
      const { Map3DElement, Marker3DElement } = await google.maps.importLibrary("maps3d");
      const c = center();
      $("#map3d").replaceChildren();
      map.m3d = new Map3DElement({ center: { lat: c.lat, lng: c.lon, altitude: 0 }, range: 6500, tilt: 62, heading: 0, mode: "HYBRID" });
      $("#map3d").append(map.m3d);
      map.sites.slice(0, 8).forEach((s) => map.m3d.append(new Marker3DElement({ position: { lat: s.lat, lng: s.lon, altitude: 40 }, altitudeMode: "RELATIVE_TO_GROUND", extruded: true, label: String(s.rank) })));
      message("");
    } catch (e) {
      console.error(e);
      message("The 3D aerial view is not available for this project or browser. Showing aerial imagery instead.", true);
      applyBase("hybrid");
    }
  }

  function fly(lat, lon, zoomIn) {
    if (map.base === "3d" && map.m3d) { try { map.m3d.flyCameraTo({ endCamera: { center: { lat, lng: lon, altitude: 0 }, tilt: 62, range: 1400 }, durationMillis: 2500 }); } catch (_) { /* older runtime */ } return; }
    if (!map.gmap) return;
    map.gmap.panTo({ lat, lng: lon });
    if (zoomIn || map.gmap.getZoom() < 13) map.gmap.setZoom(zoomIn || 14);
  }

  function fitSites() {
    if (!map.gmap || !map.sites.length || !map.fit) return;
    map.fit = false;
    const b = new google.maps.LatLngBounds();
    map.sites.forEach((s) => b.extend({ lat: s.lat, lng: s.lon }));
    map.gmap.fitBounds(b, 90);
    google.maps.event.addListenerOnce(map.gmap, "idle", () => { if (map.gmap.getZoom() > 13) map.gmap.setZoom(13); });
  }

  // ---------------------------------------------------------------- place card (by area name)
  function placeCard(p) {
    const box = $("#placeCard"), t = p.tract || p, exp = state.track === "today" ? HP.expected(p.offset_f) : null;
    const row = (k, v) => h("div", { class: "row" }, h("span", { class: "mute" }, k), h("b", {}, v));
    const drivers = (p.drivers || []).slice(0, 3).map((d) => row(nice(d.feature), `${signed(d.effect_f)} °F`));
    const people = t.total_pop ?? t.people;
    box.replaceChildren(...[
      h("h3", {}, p.area || "Selected area", h("button", { type: "button", class: "x", "aria-label": "Close", onclick: () => { map.selected = null; map.area = null; box.hidden = true; refresh(); } }, "×")),
      p.zip ? h("div", { class: "mute", style: "font-size:12px" }, `ZIP ${p.zip}${p.city ? " · " + p.city : ""}`) : null,
      h("div", { class: "big", style: `color:${HP.offsetCss(p.offset_f, state.maxAbs)}` }, `${signed(p.offset_f)} °F`),
      h("div", { class: "mute", style: "font-size:12px;margin-bottom:8px" }, exp === null ? "predicted vs. the city average" : `predicted vs. average · about ${fmt(exp, 0)} °F expected on the scenario day`),
      people !== undefined && people !== null ? row("Population", fmt(people, 0)) : null,
      t.median_age !== undefined && t.median_age !== null ? row("Median age", fmt(t.median_age)) : null,
      t.poverty_rate !== undefined && t.poverty_rate !== null ? row("Poverty rate", pct(t.poverty_rate)) : null,
      t.no_vehicle_rate !== undefined && t.no_vehicle_rate !== null ? row("No car", pct(t.no_vehicle_rate)) : null,
      p.reason ? h("div", { class: "mute", style: "font-size:12px;margin-top:6px" }, p.reason) : null,
      drivers.length ? h("div", { style: "margin-top:8px" }, h("div", { class: "mute", style: "font-size:11px;text-transform:uppercase;letter-spacing:.04em" }, "What drove it"), drivers) : null,
      h("div", { class: "actions", style: "margin-top:12px" },
        h("button", { type: "button", class: "btn primary", onclick: () => HP.askChat(HP.areaQuestion(p)) }, "Ask the assistant"),
        h("button", { type: "button", class: "btn", onclick: () => { applyBase("hybrid"); fly(p.lat, p.lon, 18); } }, "Aerial view")),
    ].filter(Boolean));
    box.hidden = false;
  }

  function onPlace(p) { map.selected = { lat: p.lat, lon: p.lon }; map.area = null; placeCard(p); if (p.fly) fly(p.lat, p.lon); refresh(); }

  // The assistant answered about a named area: ring its tracts and show a summary.
  function onArea(r) {
    const ids = new Set(r.tract_ids || []);
    map.area = state.tracts.filter((t) => ids.has(t.geo_id));
    map.selected = null;
    placeCard({ area: r.area, offset_f: r.predicted_offset_f, drivers: r.drivers, people: r.people ?? r.total_population, median_age: r.median_age, poverty_rate: r.poverty_rate, no_vehicle_rate: r.no_vehicle_rate,
      lat: r.center.lat, lon: r.center.lon, zip: (r.zip_codes || [])[0] });
    fly(r.center.lat, r.center.lon, 13);
    refresh();
  }

  // ---------------------------------------------------------------- start
  function loadGoogle(key) {
    if (window.google && google.maps) return Promise.resolve();
    return new Promise((resolve, reject) => {
      window.__gmReady = resolve;
      window.gm_authFailure = () => message(`Google Maps rejected the API key for ${location.origin}. Check that the Maps JavaScript API is enabled and this address is an allowed referrer for the key.`, true);
      script(`https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&callback=__gmReady&v=weekly&loading=async`).catch(reject);
    });
  }

  async function start() {
    if (map.started) return;
    map.started = true;
    message("Loading the map…");
    try {
      const [cfg, pts] = await Promise.all([getJson("/api/map/config"), getJson("/api/map/points"), HP.loadTracts()]);
      state.points = pts.points;
      state.maxAbs = Math.max(Math.abs(pts.min_offset_f), Math.abs(pts.max_offset_f), 1);
      bus.emit("data", { points: state.points, tracts: state.tracts });
      if (!cfg.mapsKey) throw new Error("No Google Maps key is configured. Set GOOGLE_MAPS_API_KEY on the service.");
      await Promise.all([loadGoogle(cfg.mapsKey), script(DECK_SRC)]);
      const c = center();
      map.gmap = new google.maps.Map($("#map"), { center: { lat: c.lat, lng: c.lon }, zoom: 11, mapTypeControl: false, streetViewControl: true, fullscreenControl: false, rotateControl: true, gestureHandling: "greedy", styles: isDark() ? DARK_STYLE : null, backgroundColor: "#0b1220" });
      const bounds = new google.maps.LatLngBounds();
      state.points.forEach((p) => bounds.extend({ lat: p.lat, lng: p.lon }));
      map.gmap.fitBounds(bounds);
      map.traffic = new google.maps.TrafficLayer();
      map.overlay = new deck.GoogleMapsOverlay({ layers: layers(), getTooltip: ({ object, layer }) => {
        if (!object || !layer) return null;
        if (layer.id === "tracts" || layer.id === "sites") { const e = state.track === "today" ? HP.expected(object.offset_f) : null; return `${object.area}: ${signed(object.offset_f)} °F${e === null ? "" : ` · ~${fmt(e, 0)} °F expected`}`; }
        return null; } });
      map.overlay.setMap(map.gmap);
      message("");
      fitSites();
    } catch (e) { map.started = false; message(e.message, true); }
  }

  function init() {
    $$("[data-layer]").forEach((box) => box.addEventListener("change", () => {
      map.show[box.dataset.layer] = box.checked;
      if (box.dataset.layer === "traffic") { if (map.traffic) map.traffic.setMap(box.checked ? map.gmap : null); } else refresh();
    }));
    $$("#baseSeg button").forEach((b) => b.addEventListener("click", () => applyBase(b.dataset.base)));
    bus.on("place", onPlace);
    bus.on("area", onArea);
    bus.on("scenario", refresh);
    bus.on("track", () => {
      map.sites = []; map.radiusKm = 0; map.area = null; map.selected = null; map.fit = true; $("#placeCard").hidden = true;
      if (state.track !== "today" && map.show.traffic) { map.show.traffic = false; $("[data-layer=traffic]").checked = false; if (map.traffic) map.traffic.setMap(null); }
      refresh();
    });
    bus.on("decision", ({ track, result }) => {
      if (track !== state.track) return;
      map.sites = result.sites || result.centers || [];
      map.radiusKm = track === "budget" ? result.radius_km : 0;
      refresh(); fitSites();
      if (map.base === "3d") open3d();
    });
    bus.on("theme", () => { if (map.gmap && map.base === "roadmap") map.gmap.setOptions({ styles: isDark() ? DARK_STYLE : null }); });
    bus.on("layout", () => { if (map.gmap) google.maps.event.trigger(map.gmap, "resize"); });
    start();
  }
  init();
})();
