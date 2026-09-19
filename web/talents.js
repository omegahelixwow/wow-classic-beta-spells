/* Talent trees: each tab on its own grid, prerequisite lines, per-rank tooltips, and point allocation that
   enforces the row gates and prerequisites. Left-click adds a rank, right-click removes, shift-click opens the spell. */
const STEP = 72, SZ = 52, PAD = 8;
let TT = null, TA = {};                                // the open tree, and the allocation {nodeId: rank}
// What a plain click / tap does. Desktop also has right-click (remove) and shift-click (open); touch screens use this switch.
const TAP_MODES = ['add', 'remove', 'open'];
let tapMode = 0;
const ttKey = id => 'talents:' + id;
const nodeMax = n => n.entries.length ? n.entries[0].maxRanks : 0;
const spentIn = ids => ids.reduce((s, i) => s + (TA[i] || 0), 0);

/** What still blocks spending a point in node n, given allocation A. */
function nodeIssues(n, A = TA) {
  const out = [];
  for (const g of n.gates) { const have = g.nodes.reduce((s, i) => s + (A[i] || 0), 0); if (have < g.points) out.push(`Requires ${g.text} (have ${have})`); }
  for (const p of n.prereqs) {
    if (p.type !== 2 && p.type !== 3) continue;          // "sufficient" / "required": the previous talent must be maxed
    const pn = TT.byId[p.node];
    if (pn && (A[p.node] || 0) < nodeMax(pn)) out.push(`Requires ${pn.entries[0]?.name || '#' + p.node} at max rank`);
  }
  return out;
}
function allocValid(A) {
  let total = 0;
  for (const n of TT.nodes_list) { const r = A[n.id] || 0; if (r < 0 || r > nodeMax(n)) return false; total += r; if (r && nodeIssues(n, A).length) return false; }
  return total <= TT.points;
}
const saveAlloc = () => { try { localStorage.setItem(ttKey(TT.id), JSON.stringify(TA)); } catch (e) {} };

async function renderTalents(id) {
  if (!id) { const t = TI && TI[0]; if (t) { history.replaceState(null, '', '#talents/' + t.id); return route(); } return; }
  const seq = routeSeq;
  const t = await api('talents/' + id);
  if (seq !== routeSeq) return;
  TT = t; t.byId = {}; t.nodes_list.forEach(n => t.byId[n.id] = n);
  try { TA = JSON.parse(localStorage.getItem(ttKey(id)) || '{}'); } catch (e) { TA = {}; }
  if (!allocValid(TA)) TA = {};
  navMark('Class', t.class);
  drawTalents();
}

function drawTalents() {
  const t = TT, spent = spentIn(Object.keys(TA).map(Number));
  let h = `${viewTabs(t.class, 'tal')}<div class="tt-head"><h1>${esc(t.title)}</h1><div class="pts"><b>${spent}</b> / ${t.points} points${spent ? ` · requires level ${9 + spent}` : ''}</div></div>
    <div class="sub">${t.tabs.length} tabs · ${t.nodes_list.length} talents · tree ${t.id} · click adds a rank, right-click removes, shift-click opens the spell (or use the Tap button on touch screens) · <span class="badge">SoD</span> dot = spell that came from Season of Discovery</div>
    <div class="tt-btns"><button id="tt-mode" title="what a click / tap does">Tap: ${TAP_MODES[tapMode]}</button><button id="tt-reset">Reset</button></div><div class="tt-tabs">`;
  for (const tab of t.tabs) {
    const ns = t.nodes_list.filter(n => n.tab === tab.index);
    const W = tab.cols * STEP - (STEP - SZ) + PAD * 2, H = t.rows * STEP - (STEP - SZ) + PAD * 2;
    const cx = n => PAD + (n.col - 1) * STEP + SZ / 2, cy = n => PAD + (n.row - 1) * STEP + SZ / 2;
    let lines = '', btns = '', off = '';
    for (const n of ns) {
      const e = n.entries[0], r = TA[n.id] || 0, mx = nodeMax(n);
      const sodCls = e && e.origin === 'sod' ? ' sod' : '';
      if (n.offGrid) { off += `<button class="tn off${sodCls}" style="position:static;display:inline-block;margin:0 8px 8px 0" data-n="${n.id}">${e ? icon(e.icon) : ''}<span class="rk">${r}/${mx}</span></button>`; continue; }
      for (const p of n.prereqs) {
        const pn = t.byId[p.node]; if (!pn || pn.offGrid || pn.tab !== n.tab) continue;
        const met = (TA[pn.id] || 0) >= nodeMax(pn);
        lines += `<line x1="${cx(pn)}" y1="${cy(pn)}" x2="${cx(n)}" y2="${cy(n)}" stroke="${met ? '#f5c451' : '#4a5060'}" stroke-width="4" stroke-linecap="round" ${p.type === 0 ? 'stroke-dasharray="4 5"' : ''}/>`;
      }
      const cls = r >= mx && mx ? 'max' : r > 0 ? 'part' : nodeIssues(n).length ? '' : 'open';
      btns += `<button class="tn ${e && e.shape === 'circle' ? 'circle' : ''} ${cls}${sodCls}" style="left:${PAD + (n.col - 1) * STEP}px;top:${PAD + (n.row - 1) * STEP}px" data-n="${n.id}">${e ? icon(e.icon) : ''}<span class="rk">${r}/${mx}</span></button>`;
    }
    const inTab = ns.reduce((s, n) => s + (TA[n.id] || 0), 0);
    h += `<div class="tt-tab"><h3>${esc(tab.name)}<small>${inTab} points</small></h3><div class="tt-grid" style="width:${W}px;height:${H}px"><svg width="${W}" height="${H}">${lines}</svg>${btns}</div>${off ? `<div class="dim" style="font-size:11px;margin:6px 0 2px">Off-grid nodes (bad coordinates in the data)</div>${off}` : ''}</div>`;
  }
  $('#main').innerHTML = h + '</div>';
  $('#tt-reset').onclick = () => { TA = {}; saveAlloc(); drawTalents(); };
  $('#tt-mode').onclick = e => { tapMode = (tapMode + 1) % TAP_MODES.length; e.target.textContent = 'Tap: ' + TAP_MODES[tapMode]; };
}

function bumpNode(id, d) {
  const n = TT.byId[id]; if (!n) return;
  const A = Object.assign({}, TA); A[id] = (A[id] || 0) + d; if (A[id] <= 0) delete A[id];
  if (d > 0 && nodeIssues(n, A).length) return;          // cannot spend yet
  if (!allocValid(A)) return;                            // would break a gate / prerequisite / the point budget
  TA = A; saveAlloc(); drawTalents(); showNodeTip(id);
}

function nodeTipHtml(n) {
  const e = n.entries[0]; if (!e) return '<div class="s">No entry</div>';
  const r = TA[n.id] || 0, mx = e.maxRanks, issues = nodeIssues(n);
  let h = `<div class="t">${icon(e.icon)}<div><div class="n">${esc(e.name)} ${sodBadge(e.origin)}</div><div class="s">Rank ${r}/${mx} · ${esc(n.type)} · ${esc(e.shape)}${e.scaled ? ' · scales with rank' : ''}</div></div></div>`;
  if (r > 0) h += `<div class="d">${esc(e.ranks[r - 1] || '')}</div>`;
  if (r < mx) h += `<div class="nx"><span class="s">${r ? 'Next rank' : 'Rank 1'}:</span> ${esc(e.ranks[r] || '')}</div>`;
  if (mx > 1 && r === 0) h += `<div class="s" style="margin-top:6px">Max rank: ${esc(e.ranks[mx - 1] || '')}</div>`;
  const aff = (e.affects || []).filter(a => state.sod || a.origin !== 'sod').map(a => a.name);
  if (aff.length) h += `<div class="aff">Affects: ${esc(aff.slice(0, 10).join(', '))}${aff.length > 10 ? ` +${aff.length - 10} more` : ''}</div>`;
  h += issues.length ? issues.map(i => `<div class="bad">${esc(i)}</div>`).join('') : (r < mx ? '<div class="ok">Available</div>' : '');
  return h + `<div class="hint">Spell ${e.spell} · shift-click to open</div>`;
}
function showNodeTip(id) { const n = TT && TT.byId[id]; if (!n) return; tipEl.innerHTML = nodeTipHtml(n); tipEl.hidden = false; tipPlace(); }

document.addEventListener('mouseover', e => { const b = e.target.closest('.tn'); if (b) { tipId = null; tipXY = [e.clientX, e.clientY]; showNodeTip(b.dataset.n); } });
document.addEventListener('mouseout', e => { const b = e.target.closest('.tn'); if (b && !b.contains(e.relatedTarget)) tipEl.hidden = true; });
document.addEventListener('click', e => {
  const b = e.target.closest('.tn'); if (!b || !TT) return;
  e.stopPropagation();
  const open = () => { const en = TT.byId[b.dataset.n].entries[0]; if (en) go('#spell/' + en.spell); };
  if (e.shiftKey || TAP_MODES[tapMode] === 'open') return open();
  bumpNode(b.dataset.n, TAP_MODES[tapMode] === 'remove' ? -1 : 1);
}, true);
document.addEventListener('contextmenu', e => { const b = e.target.closest('.tn'); if (!b || !TT) return; e.preventDefault(); bumpNode(b.dataset.n, -1); });
