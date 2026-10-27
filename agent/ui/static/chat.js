/* The assistant: a conversation in the left panel. Replies are cards; the workspace on the right follows the
   conversation (it fetches the same decision, highlights the area, and switches track when the question belongs to another). */
(function () {
  "use strict";
  const { h, $, fmt, signed, pct, nice, getJson, state, bus } = HP;
  const chat = { history: [], running: false, areas: [] };

  // ---------------------------------------------------------------- result cards (compact, for the sidebar)
  const miniCard = (title, ...body) => h("div", { class: "mini" }, h("h3", {}, title), body);
  const problem = (r) => h("div", { class: r.status === "error" ? "err-card" : "note-card" }, r.message || r.status, r.suggestions && r.suggestions.length ? h("div", { class: "chips", style: "margin-top:8px" }, r.suggestions.map((s) => h("button", { type: "button", class: "chip", onclick: () => send(`How hot is ${s}?`) }, s))) : null);
  const auditLine = (r) => (r.audit ? h("div", { class: "mute", style: "font-size:12px;margin-top:8px" }, h("b", {}, "Who it reaches: "), r.audit.summary) : null);

  function areaCard(r) {
    const max = Math.max(...(r.drivers || []).map((d) => Math.abs(d.effect_f)), 0.01);
    const rows = (r.drivers || []).map((d) => {
      const w = (Math.abs(d.effect_f) / max) * 50;
      const style = d.effect_f >= 0 ? `left:50%;width:${w}%;background:var(--hot)` : `left:${50 - w}%;width:${w}%;background:var(--cool)`;
      return h("div", { class: "drv" }, h("span", {}, nice(d.feature)), h("span", { class: "track" }, h("span", { class: "fill", style })), h("span", { class: "num" }, signed(d.effect_f)));
    });
    return miniCard(r.area,
      h("div", { class: "kv" },
        h("div", {}, h("div", { class: "v " + (r.predicted_offset_f > 0 ? "hotc" : "coolc") }, signed(r.predicted_offset_f) + " °F"), h("div", { class: "l" }, "vs. city average")),
        h("div", {}, h("div", { class: "v" }, fmt(r.people, 0)), h("div", { class: "l" }, "people")),
        h("div", {}, h("div", { class: "v" }, pct(r.no_vehicle_rate)), h("div", { class: "l" }, "no car"))),
      h("div", { style: "margin-top:10px" }, rows),
      h("div", { class: "mute", style: "font-size:11px;margin-top:6px" }, `${r.tracts} census tracts`),
      h("div", { class: "actions", style: "margin-top:8px" }, h("button", { type: "button", class: "btn", onclick: () => bus.emit("area", r) }, "Show on map")));
  }

  function tableCard(title, head, rows, note) {
    return miniCard(title, h("table", {}, h("thead", {}, h("tr", {}, head.map((t, i) => h("th", { class: i > 1 ? "n" : "" }, t)))), h("tbody", {}, rows)), note ? h("div", { class: "mute", style: "font-size:11px;margin-top:6px" }, note) : null);
  }
  const placeOf = (s) => ({ ...s, tract: s, source: "chat", fly: true });
  const clickRow = (s, ...cells) => h("tr", { class: "click", onclick: () => bus.emit("place", placeOf(s)) }, cells);

  function sitesCard(r) {
    return tableCard(`${r.focus_label}: where first`, ["#", "Area", "°F", "No car", "People"],
      r.sites.map((s) => clickRow(s, h("td", {}, s.rank), h("td", {}, s.area), h("td", { class: "n" }, signed(s.offset_f)), h("td", { class: "n" }, pct(s.no_vehicle_rate)), h("td", { class: "n" }, fmt(s.people, 0)))), "Click a row to fly to it.");
  }
  function centersCard(r) {
    const d = r.heat_days;
    return miniCard("Proposed cooling centers",
      h("table", {}, h("thead", {}, h("tr", {}, ["#", "Area", "People", "Need"].map((t, i) => h("th", { class: i > 1 ? "n" : "" }, t)))), h("tbody", {}, r.centers.map((c) => clickRow(c, h("td", {}, c.rank), h("td", {}, c.area), h("td", { class: "n" }, fmt(c.people_covered, 0)), h("td", { class: "n" }, pct(c.share_of_need)))))),
      h("div", { class: "mute", style: "font-size:12px;margin-top:6px" }, `${fmt(r.people_covered, 0)} people within ${r.radius_km} km.${d ? ` Dallas reaches 100°F on ${fmt(d.average_days_per_year, 0)} days a year (peak ${d.peak_days} in ${d.peak_year}).` : ""} Cost and land use are not in the data.`), auditLine(r));
  }
  function plantingCard(r) {
    return miniCard("Where planting should start",
      h("table", {}, h("thead", {}, h("tr", {}, ["#", "Area", "°F", "People"].map((t, i) => h("th", { class: i > 1 ? "n" : "" }, t)))), h("tbody", {}, r.sites.map((s) => clickRow(s, h("td", {}, s.rank), h("td", {}, s.area), h("td", { class: "n" }, signed(s.offset_f)), h("td", { class: "n" }, fmt(s.people, 0)))))),
      h("div", { class: "mute", style: "font-size:12px;margin-top:6px" }, "Intervention undetermined: no canopy or pavement data is loaded."), auditLine(r));
  }
  function frequencyCard(r) {
    const data = r.days_per_year || [];
    if (!data.length) return miniCard(`Days at or above ${fmt(r.threshold_f, 0)} °F`, h("div", { class: "mute" }, r.trend));
    const max = Math.max(...data.map((d) => d.days), 1);
    const bars = data.map((d) => h("div", { style: "flex:1;text-align:center;font-size:10px;color:var(--mute)" }, h("div", { style: `height:${Math.max(3, (d.days / max) * 54)}px;background:var(--brand);border-radius:4px 4px 0 0;margin:0 2px` }), fmt(d.days, 0), h("div", {}, String(d.year).slice(2))));
    return miniCard(`Days at or above ${fmt(r.threshold_f, 0)} °F`, h("div", { style: "display:flex;align-items:flex-end;gap:2px;height:86px" }, bars), h("div", { class: "mute", style: "font-size:12px;margin-top:6px" }, r.trend));
  }
  function communityCard(r) {
    const k = (v, l, c) => h("div", {}, h("div", { class: "v" }, v), h("div", { class: "l" }, l + (c === undefined ? "" : ` · city ${c}`)));
    return miniCard(`Who lives in ${r.area}`, h("div", { class: "kv" }, k(fmt(r.total_population, 0), "people"), k(fmt(r.median_age), "median age", fmt(r.city.median_age)), k(pct(r.poverty_rate), "poverty", pct(r.city.poverty_rate)), k(pct(r.no_vehicle_rate), "no car", pct(r.city.no_vehicle_rate))),
      h("div", { class: "actions", style: "margin-top:8px" }, h("button", { type: "button", class: "btn", onclick: () => bus.emit("area", r) }, "Show on map")));
  }

  const RENDER = { predict_heat_offset: areaCard, rank_response_sites: sitesCard, recommend_cooling_centers: centersCard, rank_planting_sites: plantingCard, heat_frequency: frequencyCard, community_profile: communityCard };
  const TRACK_OF = { rank_response_sites: "today", recommend_cooling_centers: "budget", rank_planting_sites: "trees" };

  function followCards(cards) {
    for (const c of cards || []) {
      const r = c.result || {};
      if (r.status !== "ok") continue;
      if (TRACK_OF[c.tool]) bus.emit("decision-request", { track: TRACK_OF[c.tool], args: c.args || {} });
      else if (c.tool === "predict_heat_offset" || c.tool === "community_profile") bus.emit("area", r);
      else if (c.tool === "heat_frequency") bus.emit("threshold", r.threshold_f);
    }
  }

  const cardFor = (c) => { const r = c.result || {}; if (r.status !== "ok") return problem(r); const draw = RENDER[c.tool]; return draw ? draw(r) : null; };

  // ---------------------------------------------------------------- suggestions per track
  function starters() {
    const a = chat.areas.map((x) => x.name), one = a[0] || "Oak Cliff", two = a[1] || "South Dallas";
    return {
      today: ["Where should hydration trucks go first?", "Which areas need wellness checks for older residents?", `How hot is ${one} and who lives there?`],
      budget: ["Where should the three cooling centers go?", "How often does Dallas reach 100°F, and is it getting worse?", `Who would a center in ${two} serve?`],
      trees: ["Where should tree planting start?", "Does the planting plan reach high-poverty areas?", `What is driving the heat in ${one}?`],
    }[state.track] || [];
  }
  function suggest(list) {
    $("#suggest").replaceChildren(...list.slice(0, 4).map((q) => h("button", { type: "button", class: "chip", disabled: chat.running, onclick: () => send(q) }, q)));
  }
  function welcome() {
    const t = state.tracks[state.track];
    if (!t || $("#out").children.length) return;
    $("#out").replaceChildren(h("div", { class: "welcome", id: "welcome" }, h("div", { class: "hello" }, `${t.title}: ${t.subtitle}`), h("p", {}, t.question), h("p", { class: "mute" }, "Ask about areas by name, like Oak Cliff or 75215. Speak or type, and the workspace follows.")));
    suggest(starters());
  }

  function setRunning(on) {
    chat.running = on;
    $("#go").disabled = on;
    document.querySelectorAll("#suggest .chip").forEach((c) => (c.disabled = on));
  }

  async function send(question, via) {
    question = (question || "").trim();
    if (!question || chat.running) return;
    const out = $("#out"), w = $("#welcome"); if (w) w.remove();
    $("#q").value = ""; autosize();
    out.append(h("div", { class: "you" }, via === "voice" ? h("span", { class: "via" }, "voice") : null, question));
    const secs = h("span", { class: "secs" }, "");
    const wait = h("div", { class: "thinking", "aria-label": "Thinking" }, h("i"), h("i"), h("i"), secs);
    const started = Date.now();
    const tick = setInterval(() => { const n = Math.floor((Date.now() - started) / 1000); secs.textContent = n >= 3 ? `${n}s` : ""; }, 1000);
    out.append(wait); out.scrollTop = out.scrollHeight;
    setRunning(true);
    try {
      const res = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, track: state.track, history: chat.history.slice(-12) }) });
      let data = null;
      try { data = await res.json(); } catch (_) { /* non-JSON error body */ }
      if (!res.ok) throw new Error((data && (data.error || data.detail)) || `Request failed (${res.status})`);
      wait.replaceWith(h("div", { class: "reply" }, h("div", { class: "msg" }, data.message), (data.cards || []).map(cardFor)));
      chat.history.push({ role: "user", text: question }, { role: "assistant", text: data.message });
      suggest(data.followups && data.followups.length ? data.followups : starters());
      followCards(data.cards);
    } catch (e) {
      wait.replaceWith(h("div", { class: "err-card" }, e.message));
    } finally {
      clearInterval(tick); setRunning(false); out.scrollTop = out.scrollHeight; $("#q").focus();
    }
  }

  function newChat() { if (chat.running) return; chat.history = []; $("#out").replaceChildren(); welcome(); }
  function autosize() { const q = $("#q"); q.style.height = "auto"; q.style.height = Math.min(q.scrollHeight, 120) + "px"; }

  // ---------------------------------------------------------------- voice
  function wireVoice() {
    const mic = $("#mic"), note = $("#voiceNote");
    if (!HP.voice.supported) { mic.disabled = true; mic.title = "Voice input needs a browser with microphone and AudioWorklet support"; return; }
    const bars = h("span", { class: "bars" }, h("i"), h("i"), h("i"), h("i"), h("i"));
    const say = (text, cls) => { note.className = "voice-note" + (cls ? " " + cls : ""); note.replaceChildren(...(cls === "live" ? [bars] : []), text); note.hidden = !text; };
    const cb = {
      onState(s) { mic.setAttribute("aria-pressed", String(s === "listening" || s === "connecting")); mic.classList.toggle("busy", s === "processing");
        say(s === "connecting" ? "Connecting…" : s === "listening" ? "Listening… say an area and a question" : s === "processing" ? "Transcribing…" : "", s === "listening" ? "live" : ""); },
      onInterim(text) { $("#q").value = text; autosize(); },
      onLevel(l) { [...bars.children].forEach((b, i) => (b.style.height = 3 + Math.round(l * (6 + ((i * 7) % 9))) + "px")); },
      onFinal(text) { if (text) send(text, "voice"); else say("I did not catch that. Try again.", "err"); },
      onError(message) { say(message, "err"); },
    };
    mic.addEventListener("click", () => { if (chat.running) return; if (HP.voice.active) HP.voice.stop(); else HP.voice.start(cb); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && HP.voice.active) { HP.voice.cancel(); say(""); $("#q").value = ""; } });
  }

  async function init() {
    $("#askForm").addEventListener("submit", (e) => { e.preventDefault(); send($("#q").value); });
    $("#q").addEventListener("input", autosize);
    $("#q").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send($("#q").value); } });
    $("#newchat").addEventListener("click", newChat);
    $("#themeBtn").addEventListener("click", () => {
      const dark = (document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark")) === "dark";
      const next = dark ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("heat-theme", next); } catch (_) { /* private mode */ }
      bus.emit("theme", next);
    });
    wireVoice();
    HP.askChat = (q) => send(q);
    bus.on("track", () => { if (!chat.history.length) { $("#out").replaceChildren(); } welcome(); if (chat.history.length) suggest(starters()); });
    try { chat.areas = (await getJson("/api/areas")).areas; } catch (_) { chat.areas = []; }
    if (state.track) { welcome(); }
  }
  init();
})();
