/* Speech to text through the Gemini Live API.
   The microphone is captured as 16 kHz 16-bit mono PCM and streamed to /api/live; the server holds the Live session,
   so no credentials reach the browser. The transcript comes back as it forms and is final when speech stops. */
HP.voice = (function () {
  "use strict";
  const WORKLET = `class Pcm16 extends AudioWorkletProcessor{constructor(){super();this.r=sampleRate/16000;this.ph=0;this.sum=0;this.cnt=0;this.out=[];this.e=0;this.n=0}
process(inputs){const ch=inputs[0]&&inputs[0][0];if(!ch)return true;
for(let i=0;i<ch.length;i++){const s=ch[i];this.e+=s*s;this.n++;this.sum+=s;this.cnt++;this.ph+=1;if(this.ph>=this.r){this.out.push(this.sum/this.cnt);this.ph-=this.r;this.sum=0;this.cnt=0}}
if(this.out.length>=1600){const a=this.out.splice(0,1600);const b=new Int16Array(1600);for(let i=0;i<1600;i++){const v=Math.max(-1,Math.min(1,a[i]));b[i]=v<0?v*32768:v*32767}
const level=Math.sqrt(this.e/this.n);this.e=0;this.n=0;this.port.postMessage({pcm:b.buffer,level},[b.buffer])}return true}}
registerProcessor('pcm16',Pcm16)`;
  const SPEECH_LEVEL = 0.015, SILENCE_LEVEL = 0.008, SILENCE_MS = 1800, MAX_MS = 45000, FINAL_WAIT_MS = 6000;

  const supported = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.AudioWorklet && window.WebSocket);
  let session = null;

  function teardownAudio(s) {
    try { s.stream && s.stream.getTracks().forEach((t) => t.stop()); } catch (_) { /* already stopped */ }
    try { s.node && (s.node.port.onmessage = null, s.node.disconnect()); } catch (_) { /* ignore */ }
    try { s.ctx && s.ctx.state !== "closed" && s.ctx.close(); } catch (_) { /* ignore */ }
  }

  async function start(cb) {
    if (session) return;
    if (!supported) { cb.onError("This browser cannot capture audio. You can still type."); return; }
    const s = session = { cb, ws: null, stream: null, ctx: null, node: null, text: "", queue: [], stopping: false, done: false, speechSeen: false, lastVoice: 0, timers: [] };
    cb.onState("connecting");
    try {
      s.stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      s.ctx = new AudioContext();
      const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
      await s.ctx.audioWorklet.addModule(url);
      URL.revokeObjectURL(url);
      const src = s.ctx.createMediaStreamSource(s.stream);
      s.node = new AudioWorkletNode(s.ctx, "pcm16");
      const mute = s.ctx.createGain(); mute.gain.value = 0;
      src.connect(s.node); s.node.connect(mute); mute.connect(s.ctx.destination);

      s.ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/api/live`);
      s.ws.binaryType = "arraybuffer";
      s.ws.onopen = () => { s.queue.splice(0).forEach((b) => s.ws.send(b)); cb.onState("listening"); };
      s.ws.onmessage = (ev) => {
        let m; try { m = JSON.parse(ev.data); } catch (_) { return; }
        if (m.type === "transcript") { s.text = m.text; cb.onInterim(m.text); }
        else if (m.type === "final") finish(s, m.text || s.text);
        else if (m.type === "error") fail(s, m.message);
      };
      s.ws.onerror = () => fail(s, "Voice input could not connect. You can still type your question.");
      s.ws.onclose = () => { if (!s.done) finish(s, s.text); };

      s.node.port.onmessage = ({ data }) => {
        if (s.stopping || s.done) return;
        if (s.ws.readyState === 1) s.ws.send(data.pcm); else s.queue.push(data.pcm);
        cb.onLevel(Math.min(1, data.level * 6));
        const now = performance.now();
        if (data.level > SPEECH_LEVEL) { s.speechSeen = true; s.lastVoice = now; }
        else if (s.speechSeen && data.level < SILENCE_LEVEL && now - s.lastVoice > SILENCE_MS) stop();
      };
      s.timers.push(setTimeout(stop, MAX_MS));
    } catch (e) {
      fail(s, e && e.name === "NotAllowedError" ? "Microphone access was blocked. Allow it in the browser to use voice." : "Could not start the microphone.");
    }
  }

  function stop() {
    const s = session;
    if (!s || s.stopping || s.done) return;
    s.stopping = true;
    s.cb.onState("processing");
    teardownAudio(s);
    if (s.ws && s.ws.readyState === 1) s.ws.send(JSON.stringify({ type: "stop" }));
    s.timers.push(setTimeout(() => finish(s, s.text), FINAL_WAIT_MS));
  }

  function end(s) {
    s.done = true;
    s.timers.forEach(clearTimeout);
    teardownAudio(s);
    try { s.ws && s.ws.close(); } catch (_) { /* ignore */ }
    if (session === s) session = null;
  }
  function finish(s, text) { if (s.done) return; end(s); s.cb.onState("idle"); s.cb.onFinal((text || "").trim()); }
  function fail(s, message) { if (s.done) return; end(s); s.cb.onState("idle"); s.cb.onError(message); }
  function cancel() { const s = session; if (s && !s.done) { end(s); s.cb.onState("idle"); } }

  return { supported, start, stop, cancel, get active() { return !!session; } };
})();
