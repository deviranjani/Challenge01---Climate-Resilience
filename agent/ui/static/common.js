/* Shared helpers, state and a tiny event bus. Model and data text is always set as textContent. */
window.HP = (function () {
  "use strict";
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
  const fmt = (n, d = 1) => (n === null || n === undefined || Number.isNaN(n) ? "n/a" : Number(n).toLocaleString(undefined, { maximumFractionDigits: d }));
  const signed = (n) => (n === null || n === undefined ? "n/a" : (n > 0 ? "+" : "") + fmt(n, 2));
  const pct = (n) => (n === null || n === undefined ? "n/a" : fmt(n * 100, 0) + "%");
  const nice = (s) => String(s).replace(/_/g, " ");
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];

  // Diverging scale for an offset in degrees F: sky blue (cooler), pale, rose-red (hotter).
  const COOL = [56, 189, 248], MID = [226, 232, 240], HOT = [244, 63, 94];
  function offsetRgb(offset, maxAbs) {
    const t = Math.max(-1, Math.min(1, (offset || 0) / (maxAbs || 1)));
    const [a, b] = t < 0 ? [MID, COOL] : [MID, HOT];
    const k = Math.abs(t);
    return a.map((v, i) => Math.round(v + (b[i] - v) * k));
  }
  const offsetCss = (offset, maxAbs) => `rgb(${offsetRgb(offset, maxAbs).join(",")})`;

  async function getJson(path) {
    const res = await fetch(path);
    let data = null;
    try { data = await res.json(); } catch (_) { /* non-JSON error body */ }
    if (!res.ok) throw new Error((data && (data.error || data.detail)) || `Request failed (${res.status})`);
    return data;
  }

  // People ask about areas by name. A neighbourhood name if Google gave one, otherwise the ZIP code.
  const areaName = (p) => (p && (p.neighbourhood || (p.zip ? `ZIP ${p.zip}` : null))) || (p && p.area) || "this area";
  const areaQuestion = (p) => `How much hotter than average is ${areaName(p)}, and why?`;

  // ---- state and events -------------------------------------------------------------------------------
  const state = { track: "today", tracks: {}, tracts: [], points: [], maxAbs: 3, forecast: null, scenarioHigh: null, scenarioSource: "", history: null, decision: null, selected: null };
  const listeners = {};
  const bus = {
    on(name, fn) { (listeners[name] = listeners[name] || []).push(fn); },
    emit(name, payload) { (listeners[name] || []).forEach((fn) => { try { fn(payload); } catch (e) { console.error(name, e); } }); },
  };
  // Expected temperature at a place = scenario (forecast) high + the model's offset for that place.
  const expected = (offset) => (state.scenarioHigh === null || offset === null || offset === undefined ? null : state.scenarioHigh + offset);

  // One shared load of the per-area predictions, so the map, trackers and forecast all use the same numbers.
  let tractsPromise = null;
  function loadTracts() {
    if (!tractsPromise) tractsPromise = getJson("/api/map/tracts").then((d) => { state.tracts = d.tracts; return d.tracts; }).catch((e) => { tractsPromise = null; throw e; });
    return tractsPromise;
  }

  function script(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src; s.async = true; s.onload = resolve; s.onerror = () => reject(new Error(`Could not load ${src}`));
      document.head.append(s);
    });
  }

  function setText(el, text) { el.textContent = text; }

  return { h, $, $$, fmt, signed, pct, nice, offsetRgb, offsetCss, getJson, areaName, areaQuestion, state, bus, loadTracts, expected, script, setText, views: {}, askChat: () => {} };
})();
