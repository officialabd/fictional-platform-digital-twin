// Click behavior for the asset graph page. GraphVisualizer prepends `const META = {...}`.
// Traces 0..N-1 are the drawn edges (same order as META.edges), then one invisible
// hover trace per edge type (meta "edge-hover", name = rel), then the node trace last.
(function () {
  const gd = document.getElementById('{plot_id}');
  const edges = META.edges;
  const nodeTrace = gd.data.length - 1;
  const edgeTraces = edges.map((_, i) => i);
  const hoverTraces = gd.data.map((t, i) => t.meta === 'edge-hover' ? i : -1).filter(i => i >= 0);
  const nodeIds = gd.data[nodeTrace].customdata;
  const C = META.colors;

  // ---- info panel and legend ----
  const css = document.createElement('style');
  css.textContent = `
    #side { position: fixed; top: 70px; right: 16px; width: 340px; max-height: calc(100vh - 90px);
            overflow-y: auto; font: 13px/1.45 system-ui, sans-serif; color: #222; }
    #side > div { background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 14px 16px;
                  box-shadow: 0 2px 8px rgba(0,0,0,.08); margin-bottom: 10px; }
    #filters h3 { margin: 0 0 6px; font-size: 13px; }
    #filters label { display: inline-block; width: 50%; cursor: pointer; }
    #filters .count { color: #888; }
    #filters .links { margin-top: 6px; font-size: 12px; }
    #filters .links a { color: #2a78d6; cursor: pointer; margin-right: 10px; }
    #filters .ctl { margin-top: 6px; }
    #filters .ctl label { width: auto; margin-right: 10px; }
    #filters .ctl button { width: 24px; height: 22px; cursor: pointer; }
    #filters .ctl .val { display: inline-block; min-width: 18px; text-align: center; font-weight: 600; }
    #info h2 { margin: 0 0 2px; font-size: 17px; }
    #info .id { color: #666; font-family: monospace; }
    #info .type { display: inline-block; margin: 6px 0; padding: 1px 8px; border-radius: 10px;
                  background: #eef1f4; font-size: 12px; }
    #info .desc { margin: 6px 0 10px; }
    #info .facts { color: #444; margin-bottom: 10px; }
    #info h3 { margin: 12px 0 4px; font-size: 13px; }
    #info ul { margin: 0; padding-left: 18px; }
    #info li { margin-bottom: 4px; }
    #info .rel { font-family: monospace; font-size: 12px; color: #555; }
    #info .muted { color: #888; }
    .swatch { display: inline-block; width: 18px; height: 3px; vertical-align: middle; margin-right: 6px; }
  `;
  document.head.appendChild(css);

  const side = document.createElement('div');
  side.id = 'side';
  const filters = document.createElement('div');
  filters.id = 'filters';
  const panel = document.createElement('div');
  panel.id = 'info';
  side.append(filters, panel);
  document.body.appendChild(side);

  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));

  // ---- edge type filter ----
  // Hiding an edge type sets those edge traces to invisible. It only changes what
  // is drawn: the info panel still lists every edge of the selected node.
  const relCounts = {};
  edges.forEach(e => { relCounts[e[2]] = (relCounts[e[2]] || 0) + 1; });
  const rels = Object.keys(relCounts).sort();
  filters.innerHTML = '<h3>Edge types</h3>' + rels.map(r =>
    `<label><input type="checkbox" value="${esc(r)}" checked> ${esc(r)} <span class="count">(${relCounts[r]})</span></label>`
  ).join('') + '<div class="links"><a data-all="1">Show all</a><a data-all="0">Hide all</a></div>' + `
    <h3 style="margin-top:12px">Selection</h3>
    <div class="ctl">Depth <button data-step="-1">&minus;</button><span class="val" id="depth-val">1</span><button data-step="1">+</button>
      <span class="count" id="depth-max"></span></div>
    <div class="ctl">Expand <label><input type="radio" name="dir" value="both" checked> Both</label><label><input type="radio" name="dir" value="out"> Outputs</label><label><input type="radio" name="dir" value="in"> Inputs</label></div>`;
  const boxes = [...filters.querySelectorAll('input[type=checkbox]')];
  const shownRels = () => new Set(boxes.filter(b => b.checked).map(b => b.value));

  function applyFilter() {
    const shown = shownRels();
    Plotly.restyle(gd, {visible: edges.map(e => shown.has(e[2]))}, edgeTraces);
    Plotly.restyle(gd, {visible: hoverTraces.map(i => shown.has(gd.data[i].name))}, hoverTraces);
    if (selected) select(selected);  // the expansion only follows visible edge types
  }
  boxes.forEach(b => b.addEventListener('change', applyFilter));
  filters.querySelectorAll('a').forEach(a => a.addEventListener('click', () => {
    boxes.forEach(b => { b.checked = a.dataset.all === '1'; });
    applyFilter();
  }));

  function showHelp() {
    panel.innerHTML = `
      <h2>Asset graph</h2>
      <p class="muted">Click a node to see what it is and how it connects. Click anywhere else to deselect.
      Arrows in the middle of each edge show its direction. Hover an edge for its reason.</p>
      <div><span class="swatch" style="background:${C.in}"></span>Incoming edge</div>
      <div><span class="swatch" style="background:${C.out}"></span>Outgoing edge</div>
      <p class="muted">Expand picks which edges to highlight: both, outputs only or inputs only.
      Depth above 1 follows outputs of outputs and inputs of inputs through the edge types
      that are ticked. Each extra step is drawn lighter.</p>`;
  }

  function facts(n) {
    const rows = [];
    if (n.equipment) rows.push(`Equipment: ${esc(n.equipment)}`);
    if (n.unit && n.type === 'sensor') {
      const range = n.unit === 'on/off' ? 'normally off'
        : `normal ${n.normal_min} to ${n.normal_max} ${esc(n.unit)}`;
      rows.push(`Range: ${range}`);
    }
    if (n.fail_position) rows.push(`Fail position: ${esc(n.fail_position)}`);
    rows.push(`Purdue level: ${esc(n.purdue)}`);
    return rows.join('<br>');
  }

  function edgeList(items, other, color) {
    if (!items.length) return '<p class="muted">None</p>';
    return '<ul>' + items.map(e =>
      `<li style="list-style-color:${color}"><b>${esc(e[other])}</b> <span class="rel">${esc(e[2])}</span><br>
       <span class="muted">${esc(e[3])}</span></li>`).join('') + '</ul>';
  }

  function showNode(id, incoming, outgoing) {
    const n = META.nodes[id];
    panel.innerHTML = `
      <h2>${esc(n.name)}</h2>
      <div class="id">${esc(id)}</div>
      <span class="type">${esc(n.type.replace('_', ' '))}</span>
      <div class="desc">${esc(n.description)}</div>
      <div class="facts">${facts(n)}</div>
      <h3><span class="swatch" style="background:${C.in}"></span>Incoming (${incoming.length})</h3>
      ${edgeList(incoming, 0, C.in)}
      <h3><span class="swatch" style="background:${C.out}"></span>Outgoing (${outgoing.length})</h3>
      ${edgeList(outgoing, 1, C.out)}`;
  }

  // ---- selection ----
  function paint(colorOf, widthOf, nodeOpacity) {
    const colors = edges.map((e, i) => colorOf(e, i));
    const widths = edges.map((e, i) => widthOf(e, i));
    Plotly.restyle(gd, {'line.color': colors, 'marker.color': colors, 'line.width': widths}, edgeTraces);
    Plotly.restyle(gd, {'marker.opacity': [nodeOpacity]}, [nodeTrace]);
  }

  // ---- depth expansion ----
  let selected = null;
  let wanted = 1;   // depth the user asked for
  let depth = 1;    // depth applied to the current node (wanted, capped at its max)
  let dir = 'both'; // 'both', 'out' (outputs only) or 'in' (inputs only), from depth 1 up
  const depthVal = filters.querySelector('#depth-val');
  const depthMax = filters.querySelector('#depth-max');

  // Breadth first walk along visible edges. forward = follow arrows (outputs).
  // Every edge leaving a node reached at step k-1 is drawn at step k, even when
  // it points back to a node already reached (so loops stay visible).
  // Returns {levels: Map(edge index -> step), nodes: Set, steps: last step with edges}.
  function walk(id, forward, limit, shown) {
    const levels = new Map();
    const seen = new Set([id]);
    let frontier = new Set([id]);
    let steps = 0;
    for (let k = 1; k <= limit && frontier.size; k++) {
      const next = new Set();
      edges.forEach((e, i) => {
        if (!shown.has(e[2])) return;
        const from = forward ? e[0] : e[1];
        const to = forward ? e[1] : e[0];
        if (!frontier.has(from)) return;
        if (!levels.has(i)) levels.set(i, k);
        steps = k;
        if (!seen.has(to)) { seen.add(to); next.add(to); }
      });
      frontier = next;
    }
    return {levels, nodes: seen, steps};
  }

  // Lighter color for further steps: mix the base color towards white
  function lighter(hex, step) {
    // step 1: full color, step 2: 50% towards white, then +10% per step, capped at 80%
    const t = step <= 1 ? 0 : Math.min(0.8, 0.5 + 0.1 * (step - 2));
    const c = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
    return 'rgb(' + c.map(v => Math.round(v + (255 - v) * t)).join(',') + ')';
  }

  function updateDepthLabel(max) {
    depthVal.textContent = depth;
    depthMax.textContent = max ? `(max ${max})` : '';
  }

  function select(id) {
    selected = id;
    const shown = shownRels();
    const useOut = dir !== 'in';
    const useIn = dir !== 'out';
    // Deepest useful depth for this node in the chosen direction(s)
    const max = Math.max(1, walk(id, true, useOut ? Infinity : 0, shown).steps,
                         walk(id, false, useIn ? Infinity : 0, shown).steps);
    depth = Math.min(wanted, max);
    updateDepthLabel(max);

    const down = walk(id, true, useOut ? depth : 0, shown);
    const up = walk(id, false, useIn ? depth : 0, shown);
    // An edge reached both ways keeps the nearer step; ties count as output
    const style = edges.map((_, i) => {
      const o = down.levels.get(i), n = up.levels.get(i);
      if (o === undefined && n === undefined) return null;
      if (n === undefined || (o !== undefined && o <= n)) return {color: lighter(C.out, o), step: o};
      return {color: lighter(C.in, n), step: n};
    });
    const keep = new Set([...down.nodes, ...up.nodes]);
    paint(
      (_, i) => style[i] ? style[i].color : C.faded,
      (_, i) => style[i] ? Math.max(1.2, 2.5 - 0.4 * (style[i].step - 1)) : 1,
      nodeIds.map(n => keep.has(n) ? 1 : 0.2),
    );
    showNode(id, edges.filter(e => e[1] === id), edges.filter(e => e[0] === id));
  }

  function deselect() {
    selected = null;
    updateDepthLabel(0);
    paint(() => C.edge, () => 1, nodeIds.map(() => 1));
    showHelp();
  }

  filters.querySelectorAll('button[data-step]').forEach(b => b.addEventListener('click', () => {
    wanted = Math.max(1, (selected ? depth : wanted) + Number(b.dataset.step));
    if (selected) select(selected); else { depth = wanted; updateDepthLabel(0); }
  }));
  filters.querySelectorAll('input[name=dir]').forEach(r => r.addEventListener('change', () => {
    dir = r.value;
    if (selected) select(selected);
  }));

  // plotly_click fires only on data points. A DOM click that did not hit a node
  // (and was not the end of a pan or zoom drag) means "clicked somewhere else".
  let nodeClicked = false;
  let downAt = null;
  gd.on('plotly_click', ev => {
    const p = ev.points[0];
    if (p.curveNumber === nodeTrace) {
      nodeClicked = true;
      select(p.customdata);
    }
  });
  document.addEventListener('mousedown', ev => { downAt = [ev.clientX, ev.clientY]; nodeClicked = false; });
  document.addEventListener('click', ev => {
    const dragged = downAt && Math.hypot(ev.clientX - downAt[0], ev.clientY - downAt[1]) > 5;
    if (side.contains(ev.target) || dragged) return;
    setTimeout(() => {
      if (!nodeClicked) deselect();
      nodeClicked = false;
    }, 30);
  });

  showHelp();
})();
