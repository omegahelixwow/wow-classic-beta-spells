/* Spell lists: an icon grid per class / race / skill, grouped by spec, loaded 300 at a time. */
const listImg = n => n ? icon(n, 'loading="lazy"') : '<span class="ph"></span>';
// A tile stands for one ability. When it has several ranks it shows the range and the level span of the ranks, and opens the top rank.
const tileLevel = s => s.ranks ? (s.levels[0] === s.levels[1] ? `L${s.levels[0]}` : `L${s.levels[0]}–${s.levels[1]}`) : (s.level && s.level !== '0' ? `L${s.level}` : '');
const tileRank = s => s.ranks ? `<span class="rk multi">Ranks ${s.rankRange[0]}–${s.rankRange[1]}</span>` : (s.subtext ? `<span class="rk">${esc(s.subtext)}</span>` : '');
// Hovering a ranked tile opens a strip of its ranks along the bottom (4 per row); each rank button opens that rank.
const rankStrip = s => s.ranks ? `<div class="rkpop">${s.rankList.map(r => `<button class="rkb${r.origin === 'sod' ? ' sod' : ''}" data-go="${r.id}" title="Rank ${r.rank} · level ${r.level}">${r.rank}</button>`).join('')}</div>` : '';
// (a <div>, not a <button>: buttons cannot contain buttons)
const listTile = s => `<div class="tile${s.linked ? ' lk' : ''}${s.origin === 'sod' ? ' sod' : ''}${s.ranks ? ' ranked' : ''}" data-go="${s.id}" tabindex="0" role="button">${sodBadge(s.origin)}${tileLevel(s) ? `<span class="lv">${tileLevel(s)}</span>` : ''}${listImg(s.icon)}<span class="nm">${s.name ? esc(s.name) : '<i class="dim">(unnamed)</i>'}</span>${tileRank(s)}${rankStrip(s)}</div>`;

/** Tiles for a page of items, with a full-width heading whenever the group changes (spec / linked). Returns [html, lastGroup]. */
function tileGrid(items, cat, last) {
  let html = '';
  for (const s of items) {
    const g = s.linked ? 'Linked spells (triggered / referenced)' : (cat === 'Class' ? s.via : '');
    if (g !== last) { if (g) html += `<div class="grp">${esc(g)}</div>`; last = g; }
    html += listTile(s);
  }
  return [html, last];
}

// tapping anywhere else closes an open rank strip (touch screens)
document.addEventListener('click', e => { if (!e.target.closest('.tile.open')) document.querySelectorAll('.tile.open').forEach(x => x.classList.remove('open')); });

async function renderList(cat, sub, q = '', limit = 300) {
  const seq = routeSeq;
  const page = (offset, n) => api('browse/list', {cat, sub, q, offset, limit: n});
  const r = await page(0, Math.max(300, limit));
  if (seq !== routeSeq) return;
  let [rows, lastGrp] = tileGrid(r.items, cat, null);
  listLoaded = r.items.length;
  $('#main').innerHTML = `<div class="lst"><h1>${esc(sub)}</h1><div class="sub">${esc(cat)} · ${r.total.toLocaleString()} ${r.total === 1 ? 'ability' : 'abilities'}${r.spells !== r.total ? ` <span title="ranks are folded into one tile">(${r.spells.toLocaleString()} spells incl. ranks)</span>` : ''}</div>${cat === 'Class' && talentTree(sub) ? viewTabs(sub, 'list') : ''}
    <input id="lq" placeholder="Filter within ${esc(sub)}…" value="${esc(q)}" style="margin:6px 0"><div class="sg" id="sg">${rows}</div>
    ${listLoaded < r.total ? `<button class="rel" id="more">Show more (${r.total - listLoaded} left)</button>` : ''}</div>`;
  $('#lq').onchange = e => go(listHash(cat, sub, e.target.value));
  const more = $('#more');
  if (more) more.onclick = async () => {
    const n = await page(listLoaded, 300);
    const [html, lg] = tileGrid(n.items, cat, lastGrp); lastGrp = lg;
    $('#sg').insertAdjacentHTML('beforeend', html);
    listLoaded += n.items.length;
    if (listLoaded >= r.total) more.remove(); else more.textContent = `Show more (${r.total - listLoaded} left)`;
    bindGo();
  };
  bindGo();
  navMark(cat, sub);
}
