/* The assistant: a conversation in the left panel. Replies are cards; the workspace on the right follows the
   conversation through the event bus (places, ranked sites, thresholds, community radius). */
(function () {
  "use strict";
  const { h, $, fmt, signed, pct, nice, getJson, placeQuestion, state, bus } = HP;
  const chat = { history: [], running: false, starters: [] };
  const MODEL_NAMES = { "gemini-4-argon": "Gemini 4 Argon" };

  // ---------------------------------------------------------------- result cards (compact, for the sidebar)
  const miniCard = (title, ...body) => h("div", { class: "mini" }, h("h3", {}, title), body);

  function problem(r) {
    return h("div", { class: r.status === "error" ? "err-card" : "note-card" }, r.message || r.status);
  }

  function offsetCard(r) {
    const max = Math.max(...(r.drivers || []).map((d) => Math.abs(d.effect_f)), 0.01);
    const rows = (r.drivers || []).map((d) => {
      const w = (Math.abs(d.effect_f) / max) * 50;
      const style = d.effect_f >= 0 ? `left:50%;width:${w}%;background:var(--hot)` : `left:${50 - w}%;width:${w}%;background:var(--cool)`;
      return h("div", { class: "drv" }, h("span", {}, nice(d.feature)), h("span", { class: "track" }, h("span", { class: "fill", style })), h("span", { class: "num" }, signed(d.effect_f)));
    });
    const t = r.nearest_tract || {}, exp = HP.expected(r.predicted_offset_f);
    return miniCard(`Predicted heat at ${fmt(r.latitude, 4)}, ${fmt(r.longitude, 4)}`,
      h("div", { class: "kv" },
        h("div", {}, h("div", { class: "v " + (r.predicted_offset_f > 0 ? "hotc" : "coolc") }, signed(r.predicted_offset_f) + " °F"), h("div", { class: "l" }, "vs. city average")),
        exp === null ? null : h("div", {}, h("div", { class: "v" }, fmt(exp, 0) + " °F"), h("div", { class: "l" }, "expected on the scenario day")),
        h("div", {}, h("div", { class: "v" }, pct(t.no_vehicle_rate)), h("div", { class: "l" }, "no car"))),
      h("div", { style: "margin-top:10px" }, rows),
      h("div", { class: "actions", style: "margin-top:10px" }, h("button", { type: "button", class: "btn", onclick: () => bus.emit("place", { lat: r.latitude, lon: r.longitude, offset_f: r.predicted_offset_f, drivers: r.drivers, tract: t, source: "chat", fly: true }) }, "Show on map")));
  }

  function sitesCard(r) {
    const head = h("tr", {}, ["#", "Tract", "°F", "No car", "Score"].map((t, i) => h("th", { class: i > 1 ? "n" : "" }, t)));
    const body = (r.sites || []).map((s, i) => h("tr", { class: "click", onclick: () => bus.emit("place", { lat: s.latitude, lon: s.longitude, geo_id: s.geo_id, offset_f: s.predicted_offset_f, drivers: s.top_drivers, tract: s, source: "chat", fly: true }) },
      h("td", {}, i + 1), h("td", {}, String(s.geo_id).slice(-6)), h("td", { class: "n" }, signed(s.predicted_offset_f)), h("td", { class: "n" }, pct(s.no_vehicle_rate)), h("td", { class: "n" }, fmt(s.priority_score, 2))));
    return miniCard("Where to send relief first", h("table", {}, h("thead", {}, head), h("tbody", {}, body)), h("div", { class: "l mute", style: "font-size:11px;margin-top:6px" }, "Click a row to fly to it on the map."));
  }

  function frequencyCard(r) {
    const data = r.days_per_year || [];
    if (!data.length) return miniCard(`Days at or above ${fmt(r.threshold_f, 0)} °F`, h("div", { class: "mute" }, r.trend));
    const max = Math.max(...data.map((d) => d.days), 1);
    const bars = data.map((d) => h("div", { style: "flex:1;text-align:center;font-size:10px;color:var(--mute)" }, h("div", { style: `height:${Math.max(3, (d.days / max) * 54)}px;background:var(--brand);border-radius:4px 4px 0 0;margin:0 2px` }), fmt(d.days, 0), h("div", {}, String(d.year).slice(2))));
    return miniCard(`Days at or above ${fmt(r.threshold_f, 0)} °F`, h("div", { style: "display:flex;align-items:flex-end;gap:2px;height:86px" }, bars), h("div", { class: "mute", style: "font-size:12px;margin-top:6px" }, r.trend));
  }

  function communityCard(r) {
    const k = (v, l) => h("div", {}, h("div", { class: "v" }, v), h("div", { class: "l" }, l));
    return miniCard(`Who lives within ${r.radius_km} km`, h("div", { class: "kv" }, k(fmt(r.total_population, 0), "people"), k(fmt(r.median_age), "median age"), k(pct(r.poverty_rate), "poverty"), k(pct(r.no_vehicle_rate), "no car")));
  }

  const RENDER = { predict_heat_offset: offsetCard, rank_response_sites: sitesCard, heat_frequency: frequencyCard, community_profile: communityCard };

  // The workspace follows what the assistant just answered.
  function followCards(cards) {
    for (const c of cards || []) {
      const r = c.result || {};
      if (r.status !== "ok") continue;
      if (c.tool === "predict_heat_offset") bus.emit("place", { lat: r.latitude, lon: r.longitude, offset_f: r.predicted_offset_f, drivers: r.drivers, tract: r.nearest_tract, source: "chat", fly: true });
      else if (c.tool === "rank_response_sites") { bus.emit("sites", r.sites); if (r.sites && r.sites[0]) { const s = r.sites[0]; bus.emit("place", { lat: s.latitude, lon: s.longitude, geo_id: s.geo_id, offset_f: s.predicted_offset_f, drivers: s.top_drivers, tract: s, source: "chat", fly: true }); } }
      else if (c.tool === "heat_frequency") bus.emit("threshold", r.threshold_f);
      else if (c.tool === "community_profile" && c.args) bus.emit("community", { lat: c.args.latitude, lon: c.args.longitude, radius_km: r.radius_km });
    }
  }

  function cardFor(c) {
    const r = c.result || {};
    if (r.status !== "ok") return problem(r);
    const draw = RENDER[c.tool];
    return draw ? draw(r) : null;
  }

  function stepsEl(steps) {
    if (!steps || !steps.length) return null;
    const items = steps.map((s) => h("li", { class: s.error ? "bad" : "" }, h("code", {}, `${s.tool}(${Object.entries(s.args || {}).map(([k, v]) => `${k}=${v}`).join(", ")})`), " ", s.error ? "failed: " + s.error : `${s.ms ?? "?"} ms`));
    return h("details", { class: "steps" }, h("summary", {}, `How I got this · ${steps.length} step${steps.length === 1 ? "" : "s"}`), h("ol", {}, items));
  }

  // ---------------------------------------------------------------- conversation
  function suggest(list) {
    const box = $("#suggest");
    box.replaceChildren(...list.slice(0, 4).map((q) => h("button", { type: "button", class: "chip", disabled: chat.running, onclick: () => send(q) }, q)));
  }

  function setRunning(on) {
    chat.running = on;
    $("#go").disabled = on;
    document.querySelectorAll("#suggest .chip").forEach((c) => (c.disabled = on));
  }

  async function send(question, via) {
    question = (question || "").trim();
    if (!question || chat.running) return;
    const out = $("#out");
    const welcome = $("#welcome"); if (welcome) welcome.remove();
    $("#q").value = ""; autosize();
    out.append(h("div", { class: "you" }, via === "voice" ? h("span", { class: "via" }, "voice") : null, question));
    const secs = h("span", { class: "secs" }, "");
    const wait = h("div", { class: "thinking", "aria-label": "Thinking" }, h("i"), h("i"), h("i"), secs);
    const started = Date.now();
    const tick = setInterval(() => { const n = Math.floor((Date.now() - started) / 1000); secs.textContent = n >= 3 ? `${n}s` : ""; }, 1000);
    out.append(wait); out.scrollTop = out.scrollHeight;
    setRunning(true);
    try {
      const res = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, history: chat.history.slice(-12) }) });
      let data = null;
      try { data = await res.json(); } catch (_) { /* non-JSON error body */ }
      if (!res.ok) throw new Error((data && (data.error || data.detail)) || `Request failed (${res.status})`);
      const reply = h("div", { class: "reply" }, h("div", { class: "msg" }, data.message), (data.cards || []).map(cardFor), stepsEl(data.steps));
      wait.replaceWith(reply);
      chat.history.push({ role: "user", text: question }, { role: "assistant", text: data.message });
      suggest(data.followups && data.followups.length ? data.followups : chat.starters);
      followCards(data.cards);
    } catch (e) {
      wait.replaceWith(h("div", { class: "err-card" }, e.message));
    } finally {
      clearInterval(tick);
      setRunning(false);
      out.scrollTop = out.scrollHeight;
      $("#q").focus();
    }
  }

  function newChat() {
    if (chat.running) return;
    chat.history = [];
    $("#out").replaceChildren(h("div", { class: "welcome", id: "welcome" }, h("div", { class: "hello" }, "Ask about heat in Dallas"), h("p", {}, "Where it is hottest, why, how often it happens and who lives there. Speak or type, and the workspace follows the conversation.")));
    suggest(chat.starters);
  }

  function autosize() { const q = $("#q"); q.style.height = "auto"; q.style.height = Math.min(q.scrollHeight, 120) + "px"; }

  // ---------------------------------------------------------------- voice
  function wireVoice() {
    const mic = $("#mic"), note = $("#voiceNote"), badge = $("#voiceBadge");
    if (!HP.voice.supported) { mic.disabled = true; mic.title = "Voice input needs a browser with microphone and AudioWorklet support"; badge.classList.add("off"); badge.title = "Voice input is not supported in this browser"; return; }
    const bars = h("span", { class: "bars" }, h("i"), h("i"), h("i"), h("i"), h("i"));
    const say = (text, cls) => { note.className = "voice-note" + (cls ? " " + cls : ""); note.replaceChildren(...(cls === "live" ? [bars] : []), text); note.hidden = !text; };
    const cb = {
      onState(s) {
        mic.setAttribute("aria-pressed", String(s === "listening" || s === "connecting"));
        mic.classList.toggle("busy", s === "processing");
        if (s === "connecting") say("Connecting to Gemini Live…");
        else if (s === "listening") say("Listening… speak your question", "live");
        else if (s === "processing") say("Transcribing…");
        else say("");
      },
      onInterim(text) { $("#q").value = text; autosize(); },
      onLevel(l) { [...bars.children].forEach((b, i) => (b.style.height = 3 + Math.round(l * (6 + ((i * 7) % 9))) + "px")); },
      onFinal(text) { if (text) send(text, "voice"); else say("I did not catch that. Try again.", "err"); },
      onError(message) { say(message, "err"); },
    };
    mic.addEventListener("click", () => {
      if (chat.running) return;
      if (HP.voice.active) HP.voice.stop(); else HP.voice.start(cb);
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && HP.voice.active) { HP.voice.cancel(); say(""); $("#q").value = ""; } });
  }

  // ---------------------------------------------------------------- start
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
    try {
      const [starters, health] = await Promise.all([getJson("/api/starters"), getJson("/api/health")]);
      chat.starters = starters.suggestions; suggest(chat.starters);
      $("#modelBadge").textContent = MODEL_NAMES[health.llm_model] || health.llm_model;
      $("#cityLine").textContent = `${health.city} · heat response`;
      $("#pageTitle").textContent = `${health.city} heat command center`;
      $("#voiceBadge").title = `Speech to text: ${health.live_model}`;
    } catch (_) { suggest([]); }
  }
  init();
})();
