/* Items: the item page, the hover tooltip, and the browse lists (Items menu in the top bar). */
const itemListHash = (cls, sub, q) => '#items/' + cls + '/' + sub + (q ? '?q=' + enc(q) : '');
const qcolor = q => QUALITY_COLOR[QUALITY[q]] || 'inherit';
const moneyHtml = m => m ? [['g', m.g], ['s', m.s], ['c', m.c]].filter(([, v]) => v).map(([k, v]) => `<span class="m${k}">${v}${k}</span>`).join(' ') : '';
const statLine = s => `+${s.value} ${esc(s.name)}`;
const itemMeta = t => [t.slot, t.subName && t.subName !== t.slot ? t.subName : ''].filter(Boolean).map(esc).join(' · ');

/** The lines both the tooltip and the page show: slot, armor / speed, stats, what it casts, restrictions. */
function itemBody(t, full) {
  let h = `<div class="l">Item level ${t.level}${t.reqLevel ? ' · requires level ' + t.reqLevel : ''}${t.bonding ? ' · ' + esc(t.bonding) : ''}</div>`;
  if (itemMeta(t)) h += `<div class="l">${itemMeta(t)}${t.speed ? ` · Speed ${t.speed.toFixed(2)}` : ''}${t.armor ? ` · ${t.armor} Armor` : ''}</div>`;
  else if (t.armor) h += `<div class="l">${t.armor} Armor</div>`;
  if (t.stats.length) h += `<div class="e">${t.stats.map(statLine).join('<br>')}</div>`;
  if (t.effects.length) h += `<div class="d">${t.effects.map(e => `<b>${esc(e.how)}:</b> ${esc(e.text || e.name || '')}${full ? '' : ''}`).join('<br>')}</div>`;
  if (t.classes.length) h += `<div class="l">Classes: ${t.classes.map(esc).join(', ')}</div>`;
  if (t.races.length) h += `<div class="l">Races: ${t.races.map(esc).join(', ')}</div>`;
  if (t.description) h += `<div class="l"><i>"${esc(t.description)}"</i></div>`;
  return h;
}
function itemTipHtml(t) {
  return `<div class="t">${icon(t.icon)}<div><div class="n" style="color:${qcolor(t.quality)}">${esc(t.name)} ${sodBadge(t.origin)}</div><div class="s">Item ${t.id} · ${esc(t.qualityName)} · ${esc(t.className)}</div></div></div>`
    + itemBody(t) + '<div class="hint">Click for the full page</div>';
}

async function renderItem(id) {
  const seq = routeSeq;
  const t = await api('item/' + id);
  if (seq !== routeSeq) return;
  if (!t) { $('#main').innerHTML = `<div class="lst"><h1>No item ${esc(id)}</h1></div>`; return; }
  let h = `<div class="head">${icon(t.icon)}<div><h1 style="color:${qcolor(t.quality)}">${esc(t.name)}</h1><div class="sub" style="margin:0">Item ${t.id} · <a class="ext" href="${itemUrl(t.id)}" target="_blank" rel="noopener noreferrer" title="Open this item on Wowhead (Forever): it shows the weapon damage, which is not in the client tables we read">Wowhead ↗</a></div></div></div>`;
  const tags = [`<span class="tag${t.origin === 'sod' ? ' sod' : ''}">${ORIGIN_LABEL[t.origin] || t.origin}</span>`, `<span class="tag" style="color:${qcolor(t.quality)}">${esc(t.qualityName)}</span>`,
    `<a class="tag good" href="${itemListHash(t.cls, t.sub)}">${esc(t.className)}: ${esc(t.subName)}</a>`];
  if (t.junk) tags.push('<span class="tag" title="Looks like a test / monster / placeholder item; left out of the lists">test item</span>');
  h += chips(tags);
  h += `<div class="desc">${itemBody(t, true)}</div>`;
  h += '<div class="grid">' + stat('Item level', t.level) + (t.reqLevel ? stat('Requires level', t.reqLevel) : '') + (t.slot ? stat('Slot', t.slot) : '') + stat('Type', `${t.className} / ${t.subName}`)
    + (t.armor ? stat('Armor', t.armor) : '') + (t.speed ? stat('Speed', t.speed.toFixed(2)) : '') + (t.stack > 1 ? stat('Stack', t.stack) : '') + (t.unique ? stat('Unique', 'yes') : '')
    + (t.skillName ? stat('Requires', `${t.skillName} ${t.skillRank}`) : '') + (t.sell ? `<div class="stat"><b>Sells for</b>${moneyHtml(t.sell)}</div>` : '') + stat('Icon FileDataID', t.iconFileDataID) + '</div>';
  if (t.cls === 2) h += `<p class="dim" style="font-size:12px">Weapon damage is not shown: this client's tables do not give it in a form we can read. The Wowhead link above has the real numbers.</p>`;
  if (t.effects.length) h += '<h2>Spells this item casts</h2>' + t.effects.map(e => `<button class="rel" data-go="${e.spell}"><span>${esc(e.name)}</span> ${sodBadge(e.origin)}<small>${esc(e.how)}${e.charges ? ` · ${Math.abs(e.charges)} charge${Math.abs(e.charges) > 1 ? 's' : ''}` : ''}${e.cooldown ? ` · ${e.cooldown}s cooldown` : ''}</small></button>`).join('');
  $('#main').innerHTML = h;
  bindGo();
  itemNavMark(t.cls, t.sub);
}

const itemTile = s => `<div class="tile itile${s.origin === 'sod' ? ' sod' : ''}" data-item="${s.id}" tabindex="0" role="button">${sodBadge(s.origin)}<span class="lv">${s.reqLevel ? 'L' + s.reqLevel : ''}</span>${listImg(s.icon)}<span class="nm" style="color:${qcolor(s.quality)}">${esc(s.name)}</span><span class="rk">${s.slot ? esc(s.slot) + ' · ' : ''}ilvl ${s.level}</span></div>`;

async function renderItemList(cls, sub, q = '', limit = 300) {
  const seq = routeSeq;
  const page = (offset, n) => api('items/list', {cls, sub, q, offset, limit: n});
  const r = await page(0, Math.max(300, limit));
  if (seq !== routeSeq) return;
  const c = (IT || []).find(x => String(x.cls) === String(cls)), s = c && c.subs.find(x => String(x.sub) === String(sub));
  const title = s ? `${c.name}: ${s.name}` : 'Items';
  listLoaded = r.items.length;
  $('#main').innerHTML = `<div class="lst"><h1>${esc(title)}</h1><div class="sub">Items · ${r.total.toLocaleString()} ${r.total === 1 ? 'item' : 'items'} · sorted by required level</div>
    <input id="lq" placeholder="Filter within ${esc(title)}…" value="${esc(q)}" style="margin:6px 0"><div class="sg" id="sg">${r.items.map(itemTile).join('')}</div>
    ${listLoaded < r.total ? `<button class="rel" id="more">Show more (${r.total - listLoaded} left)</button>` : ''}</div>`;
  $('#lq').onchange = e => go(itemListHash(cls, sub, e.target.value));
  const more = $('#more');
  if (more) more.onclick = async () => {
    const n = await page(listLoaded, 300);
    $('#sg').insertAdjacentHTML('beforeend', n.items.map(itemTile).join(''));
    listLoaded += n.items.length;
    if (listLoaded >= r.total) more.remove(); else more.textContent = `Show more (${r.total - listLoaded} left)`;
    bindGo();
  };
  bindGo();
  itemNavMark(cls, sub);
}
