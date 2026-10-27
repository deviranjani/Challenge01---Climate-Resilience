/* Workspace chrome: full-screen for any pane. The conversation stays on the left; the right side is the canvas. */
(function () {
  "use strict";
  const { $, $$, bus } = HP;
  let open = null;

  function toggle(pane) {
    const panes = $("#panes");
    if (open === pane) { pane.classList.remove("max"); panes.classList.remove("has-max"); document.body.classList.remove("max-open"); open = null; }
    else {
      if (open) open.classList.remove("max");
      pane.classList.add("max"); panes.classList.add("has-max"); document.body.classList.add("max-open"); open = pane;
    }
    // Let the layout settle, then tell maps and graphs to resize.
    requestAnimationFrame(() => requestAnimationFrame(() => bus.emit("layout")));
  }

  $$("[data-max]").forEach((b) => b.addEventListener("click", () => toggle(b.closest(".pane"))));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && open && !HP.voice.active) toggle(open); });
  window.addEventListener("resize", () => bus.emit("layout"));
})();
