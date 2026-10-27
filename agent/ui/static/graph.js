/* Graph pane: census tracts and their demographic groups as a Neo4j-style node and relationship graph. */
(function () {
  "use strict";
  const { h, $, fmt, offsetCss, getJson, state, bus, script } = HP;
  // Neo4j Browser's label colours for the group nodes; tracts take the heat scale.
  const LABEL_COLOR = { HeatBand: "#F79767", PovertyLevel: "#C990C0", CarAccess: "#57C7E3", AgeBand: "#8DCC93" };
  const g = { net: null, nodes: null, edges: null, started: false, maxAbs: 3 };
  const message = (text, bad) => { const el = $("#graphMsg"); el.textContent = text || ""; el.hidden = !text; el.className = "overlay-msg" + (bad ? " err" : ""); };

  function visNode(n) {
    if (n.label === "Tract") {
      const size = 11 + Math.sqrt(n.total_pop || 0) * 0.3;
      return { id: n.id, label: n.name, shape: "dot", size, color: { background: offsetCss(n.offset_f, g.maxAbs), border: "rgba(255,255,255,.55)", highlight: { background: offsetCss(n.offset_f, g.maxAbs), border: "#22d3ee" } },
        font: { size: 9, color: "#8d9ab1", vadjust: -size - 6 }, borderWidth: 1.5, props: n };
    }
    return { id: n.id, label: n.name.replace(/ /g, "\n"), shape: "circle", color: { background: LABEL_COLOR[n.label], border: "rgba(0,0,0,.35)", highlight: { background: LABEL_COLOR[n.label], border: "#22d3ee" } },
      font: { size: 12, color: "#10131c", face: "Inter, sans-serif" }, margin: 12, borderWidth: 1.5, props: n };
  }

  function legend(data) {
    const chips = Object.entries(LABEL_COLOR).map(([label, color]) => h("span", { class: "gl" }, h("i", { style: `background:${color}` }), label));
    chips.unshift(h("span", { class: "gl" }, h("i", { class: "grad" }), `Tract · hottest ${data.tracts_shown} of ${data.tracts_total}`));
    $("#graphLegend").replaceChildren(...chips);
  }

  function focus(id) {
    const linked = new Set([id, ...g.net.getConnectedNodes(id)]), edgeIds = new Set(g.net.getConnectedEdges(id));
    g.nodes.update(g.nodes.get().map((n) => ({ id: n.id, opacity: linked.has(n.id) ? 1 : 0.14 })));
    g.edges.update(g.edges.get().map((e) => ({ id: e.id, font: { size: edgeIds.has(e.id) ? 9 : 0, color: "#8d9ab1", strokeWidth: 0 }, color: { color: edgeIds.has(e.id) ? "#22d3ee" : "#475069", opacity: edgeIds.has(e.id) ? 1 : 0.2 } })));
  }
  function clear() {
    g.nodes.update(g.nodes.get().map((n) => ({ id: n.id, opacity: 1 })));
    g.edges.update(g.edges.get().map((e) => ({ id: e.id, font: { size: 0 }, color: { color: "#56627a", opacity: 0.8 } })));
  }

  function draw(data) {
    g.maxAbs = Math.max(1, ...data.nodes.filter((n) => n.label === "Tract").map((n) => Math.abs(n.offset_f)));
    g.nodes = new vis.DataSet(data.nodes.map(visNode));
    g.edges = new vis.DataSet(data.edges.map((e, i) => ({ id: i, from: e.from, to: e.to, label: e.type.replace(/_/g, " "), arrows: { to: { enabled: true, scaleFactor: 0.45 } }, font: { size: 0, align: "middle" }, color: { color: "#56627a", opacity: 0.8 }, width: 1, smooth: false })));
    if (g.net) g.net.destroy();
    g.net = new vis.Network($("#graph"), { nodes: g.nodes, edges: g.edges }, { physics: { solver: "forceAtlas2Based", forceAtlas2Based: { gravitationalConstant: -55, springLength: 100, springConstant: 0.05 }, stabilization: { iterations: 180 } }, interaction: { hover: true, tooltipDelay: 120 } });
    g.net.on("selectNode", (p) => {
      const id = p.nodes[0], n = g.nodes.get(id);
      focus(id);
      if (n.props.label === "Tract") bus.emit("place", { lat: n.props.lat, lon: n.props.lon, geo_id: n.props.name && n.props.id ? n.props.id : String(n.id).replace("tract:", ""), offset_f: n.props.offset_f, drivers: n.props.drivers, tract: n.props, source: "graph", fly: true });
    });
    g.net.on("deselectNode", clear);
    legend(data);
  }

  async function load() {
    message("Building the graph…");
    try {
      if (!window.vis) await script("https://cdn.jsdelivr.net/npm/vis-network@9.1.9/standalone/umd/vis-network.min.js");
      draw(await getJson(`/api/graph?limit=${$("#graphLimit").value}`));
      message("");
    } catch (e) { message(e.message, true); }
  }

  $("#graphLimit").addEventListener("input", (e) => { $("#graphLimitVal").textContent = e.target.value; });
  $("#graphLimit").addEventListener("change", load);
  bus.on("layout", () => { if (g.net) { g.net.redraw(); g.net.fit({ animation: false }); } });
  bus.on("place", (p) => { if (g.net && p.geo_id && g.nodes.get(`tract:${p.geo_id}`) && p.source !== "graph") { g.net.selectNodes([`tract:${p.geo_id}`]); focus(`tract:${p.geo_id}`); } });
  load();
})();
