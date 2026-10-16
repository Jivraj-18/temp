// Shared replay engine for the demos: plays timestamped events back on a simulated clock,
// with a step strip, live counters and an event log. Pages set --rp-* colours to match their theme.
//
//   const r = Replay.mount(el, { start, end, speeds: [[60, "60×"], ...], speed: 60, clock: t => "...",
//     stages: [["key", "Label", "hint"], ...], counters: [["key", "Label"], ...], note: "...",
//     events: [{ t, run: fast => {...} }], onReset, onDone });
//   r.stage(key, "active" | "done", detail)   r.count(key, value)   r.log(text)
//
// Times are in milliseconds of simulated time; speed is simulated ms per real ms.
// run(fast) gets fast = true when "Skip to end" replays the remaining events instantly.
(function () {
  const css = `
  .rp{border:1px solid var(--rp-line,#dde2ea);background:var(--rp-panel,#fff);border-radius:10px;padding:14px 16px;display:grid;gap:12px;font-family:ui-sans-serif,system-ui,"Segoe UI",sans-serif;color:var(--rp-ink,inherit)}
  .rp-bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
  .rp-bar button{font:inherit;font-size:13px;font-weight:600;cursor:pointer;border-radius:7px;padding:7px 13px;border:1px solid var(--rp-accent,#1d4f91);background:var(--rp-accent,#1d4f91);color:#fff}
  .rp-bar button.ghost{background:transparent;color:var(--rp-accent,#1d4f91)}
  .rp-speed{display:flex;gap:2px;border:1px solid var(--rp-line,#dde2ea);border-radius:7px;padding:2px}
  .rp-speed button{border:0;background:transparent;color:var(--rp-muted,#5a6473);padding:5px 9px;font-weight:600;font-size:12px}
  .rp-speed button.on{background:var(--rp-accent,#1d4f91);color:#fff}
  .rp-clock{margin-left:auto;font:700 18px ui-monospace,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}
  .rp-note{font-size:12px;color:var(--rp-muted,#5a6473);flex-basis:100%}
  .rp-steps{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(var(--rp-n,5),1fr);gap:14px}
  .rp-steps li{position:relative;border:1px solid var(--rp-line,#dde2ea);border-radius:8px;padding:8px 10px;font-size:12px;color:var(--rp-muted,#5a6473);min-height:58px;min-width:0;overflow-wrap:anywhere}
  .rp-steps li b{display:block;color:var(--rp-ink,inherit);font-size:12.5px}
  .rp-steps li:not(:last-child)::after{content:"→";position:absolute;right:-12px;top:50%;transform:translateY(-50%);color:var(--rp-muted,#5a6473)}
  .rp-steps li.active{border-color:var(--rp-accent,#1d4f91);box-shadow:0 0 0 3px color-mix(in srgb,var(--rp-accent,#1d4f91) 18%,transparent)}
  .rp-steps li.done{border-color:var(--rp-ok,#1c6b5a);background:color-mix(in srgb,var(--rp-ok,#1c6b5a) 8%,transparent)}
  .rp-steps li.done b::before{content:"✓ ";color:var(--rp-ok,#1c6b5a)}
  .rp-counters{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px}
  .rp-counters div{border:1px solid var(--rp-line,#dde2ea);border-radius:8px;padding:7px 10px}
  .rp-counters b{display:block;font:700 20px ui-monospace,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}
  .rp-counters span{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--rp-muted,#5a6473)}
  .rp-log{font:12px/1.5 ui-monospace,Menlo,Consolas,monospace;max-height:9.5em;overflow:hidden;color:var(--rp-muted,#5a6473)}
  .rp-log div:first-child{color:var(--rp-ink,inherit)}
  .rp-flash{animation:rp-flash 1.2s ease-out}
  @keyframes rp-flash{from{background:color-mix(in srgb,var(--rp-accent,#1d4f91) 22%,transparent)}to{background:transparent}}
  @media (prefers-reduced-motion:reduce){.rp-flash{animation:none}}
  @media (max-width:720px){.rp-steps{grid-template-columns:1fr 1fr}.rp-steps li::after{display:none}.rp-clock{margin-left:0}}`;

  function mount(el, o) {
    if (!document.getElementById("rp-css")) {
      const s = document.createElement("style");
      s.id = "rp-css";
      s.textContent = css;
      document.head.appendChild(s);
    }
    const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
    el.innerHTML = `<div class="rp">
      <div class="rp-bar"><button type="button" data-rp="play">▶ Replay</button><button type="button" class="ghost" data-rp="finish">Skip to end</button>
        <div class="rp-speed">${o.speeds.map(([v, l]) => `<button type="button" data-speed="${v}" class="${v === o.speed ? "on" : ""}">${esc(l)}</button>`).join("")}</div>
        <span class="rp-clock">${esc(o.clock(o.start))}</span>${o.note ? `<span class="rp-note">${esc(o.note)}</span>` : ""}</div>
      <ol class="rp-steps" style="--rp-n:${o.stages.length}">${o.stages.map(([k, l, h]) => `<li data-k="${k}"><b>${esc(l)}</b><span>${esc(h || "")}</span></li>`).join("")}</ol>
      <div class="rp-counters">${o.counters.map(([k, l]) => `<div><b data-c="${k}">–</b><span>${esc(l)}</span></div>`).join("")}</div>
      <div class="rp-log" aria-live="polite"></div></div>`;
    const $ = s => el.querySelector(s);
    const playBtn = $('[data-rp="play"]'), clockEl = $(".rp-clock"), logEl = $(".rp-log");
    const events = [...o.events].sort((a, b) => a.t - b.t);
    let t = o.start, i = 0, playing = false, started = false, last = 0, raf = 0, speed = o.speed;
    let eventT = o.start;   // time of the event being run, so log lines carry the real event time
    const runNext = fast => { const ev = events[i++]; eventT = ev.t; ev.run(fast); };

    const api = {
      stage(k, state, detail) {
        const li = el.querySelector(`.rp-steps li[data-k="${k}"]`);
        li.className = state || "";
        if (detail != null) li.querySelector("span").textContent = detail;
      },
      count(k, v) { el.querySelector(`[data-c="${k}"]`).textContent = v; },
      log(text) {
        const d = document.createElement("div");
        d.textContent = `${o.clock(eventT)}  ${text}`;
        logEl.prepend(d);
        while (logEl.children.length > 7) logEl.lastChild.remove();
      },
      get time() { return t; },
    };

    function setLabel() { playBtn.textContent = playing ? "❚❚ Pause" : started && i < events.length ? "▶ Resume" : "▶ Replay"; }
    function reset() {
      t = o.start; i = 0; logEl.innerHTML = "";
      o.stages.forEach(([k, , h]) => api.stage(k, "", h || ""));
      o.counters.forEach(([k]) => api.count(k, "0"));
      o.onReset && o.onReset(api);
    }
    function done() { playing = false; started = false; setLabel(); o.onDone && o.onDone(api); }
    function frame(now) {
      if (!playing) return;
      t = Math.min(o.end, t + (last ? now - last : 0) * speed);
      last = now;
      while (i < events.length && events[i].t <= t) runNext(false);
      clockEl.textContent = o.clock(t);
      if (t >= o.end && i >= events.length) return done();
      raf = requestAnimationFrame(frame);
    }
    function play() {
      if (!started) { reset(); started = true; }
      playing = true; last = 0; setLabel();
      raf = requestAnimationFrame(frame);
    }
    function pause() { playing = false; cancelAnimationFrame(raf); setLabel(); }

    playBtn.addEventListener("click", () => (playing ? pause() : play()));
    $('[data-rp="finish"]').addEventListener("click", () => {
      pause();
      if (!started) { reset(); started = true; }
      while (i < events.length) runNext(true);
      t = o.end; clockEl.textContent = o.clock(t);
      done();
    });
    el.querySelectorAll("[data-speed]").forEach(b => b.addEventListener("click", () => {
      speed = Number(b.dataset.speed);
      el.querySelectorAll("[data-speed]").forEach(x => x.classList.toggle("on", x === b));
    }));
    return api;
  }

  window.Replay = { mount };
})();
