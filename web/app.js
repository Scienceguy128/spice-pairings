(function () {
  const F = window.PairingFilters;
  const data = window.PAIRINGS_DATA;
  const panel = document.getElementById("panel");
  const statusEl = document.getElementById("status");
  const minInput = document.getElementById("minShared");
  const cuisineInput = document.getElementById("cuisine");
  const searchInput = document.getElementById("search");

  if (!data) {
    panel.innerHTML = '<p class="warn">No data found. Run <code>python data_pipeline.py</code> to generate web/data/pairings.js.</p>';
    return;
  }

  const meta = data.meta;
  const pairKey = (a, b) => (a < b ? a + "|" + b : b + "|" + a);
  let cuisine = "";
  let current, N, nodeById, covered, uncovered, pairByKey, maxLift, maxCount;
  let minShared = F.DEFAULT_MIN_SHARED;
  let thresholdChanged = false;
  let selected = null;
  minInput.value = minShared;

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const label = (id) => nodeById.get(id).label;
  const fmt = (x) => (x >= 10 ? x.toFixed(1) : x.toFixed(2));

  cuisineInput.innerHTML += Object.keys(data.cuisines).sort((a, b) => a.localeCompare(b))
    .map((name) => `<option value="${esc(name)}">${esc(name)}</option>`).join("");

  function setActiveData(name) {
    cuisine = name;
    current = F.cuisineData(data, name);
    N = current.eligible_recipes;
    nodeById = new Map(current.nodes.map((n) => [n.id, n]));
    covered = current.nodes.filter((n) => n.count > 0);
    uncovered = current.nodes.filter((n) => n.count === 0);
    pairByKey = new Map(current.pairs.map((p) => [pairKey(p.a, p.b), p]));
    const supportedLifts = current.pairs.filter((p) => p.shared >= 3).map((p) => p.lift);
    maxLift = Math.max(1.0001, ...(supportedLifts.length ? supportedLifts : current.pairs.map((p) => p.lift)));
    maxCount = Math.max(1, ...covered.map((n) => n.count));
    document.getElementById("names").innerHTML = covered.map((n) => `<option value="${esc(n.label)}">`).join("");
  }

  const graphNodes = () => covered.map((n) => ({ data: { id: n.id, label: n.label, type: n.type, count: n.count } }));
  setActiveData("");

  const cy = cytoscape({
    container: document.getElementById("cy"),
    elements: graphNodes(),
    minZoom: 0.2,
    maxZoom: 3,
    style: [
      { selector: "node", style: {
          label: "data(label)", "font-size": 11, "text-valign": "center", "text-halign": "center",
          "text-outline-color": "#fff", "text-outline-width": 2, color: "#1f2328",
          width: (n) => 14 + 46 * Math.sqrt(n.data("count") / maxCount),
          height: (n) => 14 + 46 * Math.sqrt(n.data("count") / maxCount),
          "background-color": (n) => (n.data("type") === "herb" ? "#3f9b4a" : "#d9822b"),
          "border-width": 1, "border-color": "#fff" } },
      { selector: "node.isolated", style: { opacity: 0.35 } },
      { selector: "edge", style: {
          width: "data(width)", "line-color": "#8c959f", opacity: 0.55, "curve-style": "haystack" } },
      { selector: "edge.sparse", style: { "line-style": "dashed", "line-color": "#c9a227" } },
      { selector: ".faded", style: { opacity: 0.08 } },
      { selector: "node.focus", style: { "border-width": 4, "border-color": "#0969da", opacity: 1 } },
      { selector: "node.neighbor", style: { opacity: 1 } },
      { selector: "edge.highlight", style: { opacity: 0.95, "line-color": "#0969da", "z-index": 10 } },
      { selector: "edge.highlight.sparse", style: { "line-color": "#b07d00" } },
    ],
  });

  function syncEdges() {
    const edges = F.visibleEdges(current.pairs, minShared).filter((p) => nodeById.get(p.a).count && nodeById.get(p.b).count);
    cy.batch(() => {
      cy.edges().remove();
      cy.add(edges.map((p) => ({
        group: "edges",
        classes: F.isSparse(p) ? "sparse" : "",
        data: { id: pairKey(p.a, p.b), source: p.a, target: p.b, width: F.edgeWidth(p.lift, maxLift) },
      })));
      cy.nodes().forEach((n) => n.toggleClass("isolated", n.degree() === 0));
    });
    const isolated = cy.nodes(".isolated").length;
    statusEl.textContent = `${N} ${cuisine ? cuisine + " " : ""}recipes · ${edges.length} pairings shown · ${isolated} ingredient(s) without a shown pairing`;
    applyHighlight();
  }

  function runLayout() {
    if (!cy.nodes().length) return;
    cy.layout({ name: "cose", animate: false, randomize: true, nodeRepulsion: () => 9000, idealEdgeLength: () => 90,
      edgeElasticity: () => 80, gravity: 0.6, numIter: 2500, fit: true, padding: 30 }).run();
  }

  function applyHighlight() {
    cy.elements().removeClass("faded focus neighbor highlight");
    if (!selected || !cy.getElementById(selected).length) return;
    const node = cy.getElementById(selected);
    cy.elements().addClass("faded");
    node.removeClass("faded").addClass("focus");
    node.connectedEdges().removeClass("faded").addClass("highlight");
    node.neighborhood("node").removeClass("faded").addClass("neighbor");
  }

  function statusTag(p) {
    const s = F.pairStatus(p, minShared);
    if (s === "below-threshold") return '<span class="tag sparse">below threshold</span>';
    if (s === "non-positive") return '<span class="tag neg">no positive association</span>';
    if (F.isSparse(p)) return '<span class="tag sparse">sparse evidence</span>';
    return "";
  }

  function showIngredient(id) {
    selected = id;
    applyHighlight();
    const n = nodeById.get(id);
    const partners = current.pairs.filter((p) => p.a === id || p.b === id)
      .map((p) => ({ p, other: p.a === id ? p.b : p.a }));
    const shown = partners.filter((x) => F.pairStatus(x.p, minShared) === "shown").sort((x, y) => y.p.lift - x.p.lift);
    const hidden = partners.filter((x) => F.pairStatus(x.p, minShared) !== "shown")
      .sort((x, y) => y.p.shared - x.p.shared);
    const unobserved = covered.filter((m) => m.id !== id && !pairByKey.has(pairKey(id, m.id)));
    const row = ({ p, other }) => `<tr class="pair" data-a="${p.a}" data-b="${p.b}"><td>${esc(label(other))} ${statusTag(p)}</td>
      <td class="num">${fmt(p.lift)}</td><td class="num">${p.shared}</td></tr>`;
    panel.innerHTML = `
      <h2><span class="swatch" style="background:${n.type === "herb" ? "var(--herb)" : "var(--spice)"}"></span> ${esc(n.label)}</h2>
      <p class="muted">${n.type} · in ${n.count} of ${N} ${cuisine ? esc(cuisine) + " " : ""}recipes (${(100 * n.count / N).toFixed(1)}%)</p>
      <h3>Strongest supported pairings (${shown.length})</h3>
      ${shown.length ? `<table><tr><th>Partner</th><th class="num">Lift</th><th class="num">Shared</th></tr>${shown.map(row).join("")}</table>`
        : `<p class="warn">No pairing meets the current filter (≥ ${minShared} shared recipes and lift &gt; 1). This means insufficient evidence in this corpus, not that ${esc(n.label)} pairs badly.</p>`}
      <h3>Other observed pairs, not drawn (${hidden.length})</h3>
      ${hidden.length ? `<details><summary>Show</summary><table><tr><th>Partner</th><th class="num">Lift</th><th class="num">Shared</th></tr>${hidden.map(row).join("")}</table></details>` : '<p class="muted">None.</p>'}
      <h3>Never seen together (${unobserved.length})</h3>
      <p class="muted">${unobserved.map((m) => esc(m.label)).join(", ") || "None."}</p>
      <p class="muted">Unobserved means no recipe in the current selection uses both—not evidence that they clash.</p>`;
    bindRows();
  }

  function showPair(a, b) {
    const p = pairByKey.get(pairKey(a, b));
    const A = nodeById.get(p.a), B = nodeById.get(p.b);
    const examples = p.examples.map((i) => data.recipes[i]);
    panel.innerHTML = `
      <p><a href="#" id="back">← ${selected ? esc(label(selected)) : "Overview"}</a></p>
      <h2>${esc(A.label)} + ${esc(B.label)} ${statusTag(p)}</h2>
      <table>
        <tr><td>Lift (observed ÷ expected)</td><td class="num"><b>${fmt(p.lift)}</b></td></tr>
        <tr><td>Recipes with both</td><td class="num">${p.shared}</td></tr>
        <tr><td>Expected if independent</td><td class="num">${p.expected.toFixed(1)}</td></tr>
        <tr><td>Recipes with ${esc(A.label)}</td><td class="num">${A.count}</td></tr>
        <tr><td>Recipes with ${esc(B.label)}</td><td class="num">${B.count}</td></tr>
        <tr><td>${cuisine ? esc(cuisine) + " recipes" : "Recipes in corpus"} (N)</td><td class="num">${N}</td></tr>
      </table>
      <p class="muted">${p.lift > 1 ? `Used together ${fmt(p.lift)}× as often as their individual popularity predicts.`
        : "Used together no more often than their individual popularity predicts."}
      ${F.isSparse(p) ? " Fewer than 10 shared recipes: treat as sparse evidence." : ""}</p>
      <h3>Example recipes</h3>
      <ul>${examples.map((r) => `<li><a href="${esc(r.u)}" target="_blank" rel="noopener">${esc(r.t)}</a></li>`).join("")}</ul>`;
    document.getElementById("back").onclick = (e) => { e.preventDefault(); selected ? showIngredient(selected) : showOverview(); };
  }

  function showOverview() {
    selected = null;
    applyHighlight();
    const top = F.visibleEdges(current.pairs, minShared).sort((x, y) => y.lift - x.lift).slice(0, 15);
    const blends = Object.entries(current.excluded_blends).slice(0, 12);
    panel.innerHTML = `
      <h2>How to read this</h2>
      ${cuisine ? `<p class="muted">Scores, counts and examples use ${N} recipes classified by Wikibooks as ${esc(cuisine)} or an included subcategory; ${current.recipes_with_tracked_ingredients} contain a tracked spice or herb.</p>` : ""}
      <p><span class="swatch" style="background:var(--spice)"></span> spice &nbsp;
         <span class="swatch" style="background:var(--herb)"></span> herb &nbsp; Node size = number of recipes.</p>
      <p>An edge means the two appear together in at least <b>${minShared}</b> recipes <i>and</i> more often than their
         individual popularity predicts (<b>lift</b> &gt; 1). Thicker = higher lift (log scale).
         Dashed gold edges have fewer than 10 shared recipes (sparse evidence).</p>
      <p class="warn">This is <b>recipe-based pairing affinity</b> from one corpus, not a measured taste score. Missing edges mean
         too little evidence, not a bad pairing. Positions on the canvas come from the layout algorithm and are not
         taste distances.</p>
      ${!covered.length ? '<p class="warn">No tracked spices or herbs were found in this selection.</p>' : ""}
      <h3>Highest-lift pairings shown</h3>
      ${top.length ? `<table><tr><th>Pair</th><th class="num">Lift</th><th class="num">Shared</th></tr>
        ${top.map((p) => `<tr class="pair" data-a="${p.a}" data-b="${p.b}"><td>${esc(label(p.a))} + ${esc(label(p.b))} ${statusTag(p)}</td>
        <td class="num">${fmt(p.lift)}</td><td class="num">${p.shared}</td></tr>`).join("")}</table>`
        : '<p class="muted">No pairings meet this threshold.</p>'}
      <h3>Not scored</h3>
      <p class="muted">Blends are counted but not split into components: ${blends.map(([k, v]) => `${esc(k)} (${v})`).join(", ") || "none"}.</p>
      ${uncovered.length ? `<p class="muted">No recipes in this selection found for: ${uncovered.map((n) => esc(n.label)).join(", ")}.</p>` : ""}
      <p class="muted">Click an ingredient or edge for details.</p>`;
    bindRows();
  }

  function bindRows() {
    panel.querySelectorAll("tr.pair").forEach((tr) => { tr.onclick = () => showPair(tr.dataset.a, tr.dataset.b); });
  }

  cy.on("tap", "node", (e) => showIngredient(e.target.id()));
  cy.on("tap", "edge", (e) => showPair(e.target.data("source"), e.target.data("target")));
  cy.on("tap", (e) => { if (e.target === cy) showOverview(); });

  cuisineInput.addEventListener("change", () => {
    setActiveData(cuisineInput.value);
    if (!thresholdChanged) {
      minShared = cuisine ? F.cuisineDefaultMinShared(current.pairs) : F.DEFAULT_MIN_SHARED;
      minInput.value = minShared;
    }
    if (selected && !nodeById.get(selected).count) selected = null;
    searchInput.value = "";
    cy.batch(() => {
      cy.elements().remove();
      cy.add(graphNodes());
    });
    syncEdges();
    runLayout();
    selected ? showIngredient(selected) : showOverview();
  });
  minInput.addEventListener("change", () => {
    const v = Math.round(Number(minInput.value));
    if (Number.isFinite(v) && v >= 1) {
      minShared = v;
      thresholdChanged = true;
    } else {
      minShared = cuisine ? F.cuisineDefaultMinShared(current.pairs) : F.DEFAULT_MIN_SHARED;
      thresholdChanged = false;
    }
    minInput.value = minShared;
    syncEdges();
    selected ? showIngredient(selected) : showOverview();
  });
  searchInput.addEventListener("change", (e) => {
    const q = e.target.value.trim().toLowerCase();
    if (!q) { showOverview(); return; }
    const hit = covered.find((n) => n.label.toLowerCase() === q) || covered.find((n) => n.label.toLowerCase().includes(q));
    if (hit) { showIngredient(hit.id); cy.animate({ center: { eles: cy.getElementById(hit.id) }, duration: 250 }); }
    else statusEl.textContent = `No tracked ingredient in this selection matches “${e.target.value}”.`;
  });
  document.getElementById("relayout").onclick = runLayout;
  document.getElementById("reset").onclick = () => { searchInput.value = ""; showOverview(); };

  document.getElementById("footer").innerHTML =
    `${meta.eligible_recipes} recipes (${meta.recipes_with_tracked_ingredients} with a tracked spice/herb) from
     <a href="https://en.wikibooks.org/wiki/Cookbook:Table_of_Contents" target="_blank" rel="noopener">Wikibooks Cookbook</a>,
     retrieved ${esc(meta.retrieved_at.slice(0, 10))}. Recipe text © Wikibooks contributors,
     <a href="${esc(meta.license_url)}" target="_blank" rel="noopener">CC BY-SA 4.0</a>; derived statistics shared under the same license.`;

  syncEdges();
  runLayout();
  showOverview();
})();
