// Click behavior for the asset graph page. GraphVisualizer prepends `const META = {...}`.
// Traces 0..N-1 are edges (same order as META.edges), trace N is the node trace.
(function () {
  const gd = document.getElementById('{plot_id}');
  const edges = META.edges;
  const nodeTrace = edges.length;
  const edgeTraces = edges.map((_, i) => i);
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
  ).join('') + '<div class="links"><a data-all="1">Show all</a><a data-all="0">Hide all</a></div>';
  const boxes = [...filters.querySelectorAll('input')];

  function applyFilter() {
    const shown = new Set(boxes.filter(b => b.checked).map(b => b.value));
    Plotly.restyle(gd, {visible: edges.map(e => shown.has(e[2]))}, edgeTraces);
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
      <div><span class="swatch" style="background:${C.out}"></span>Outgoing edge</div>`;
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
    const colors = edges.map(colorOf);
    Plotly.restyle(gd, {'line.color': colors, 'marker.color': colors, 'line.width': edges.map(widthOf)}, edgeTraces);
    Plotly.restyle(gd, {'marker.opacity': [nodeOpacity]}, [nodeTrace]);
  }

  function select(id) {
    const incoming = edges.filter(e => e[1] === id);
    const outgoing = edges.filter(e => e[0] === id);
    const keep = new Set([id, ...incoming.map(e => e[0]), ...outgoing.map(e => e[1])]);
    paint(
      e => e[1] === id ? C.in : e[0] === id ? C.out : C.faded,
      e => (e[0] === id || e[1] === id) ? 2.5 : 1,
      nodeIds.map(n => keep.has(n) ? 1 : 0.2),
    );
    showNode(id, incoming, outgoing);
  }

  function deselect() {
    paint(() => C.edge, () => 1, nodeIds.map(() => 1));
    showHelp();
  }

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
