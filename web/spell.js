/* The full detail page of one spell. */
const chips = items => items.length ? `<div style="margin-top:10px">${items.join('')}</div>` : '';
const bullets = xs => `<ul style="margin:8px 0 0;padding-left:18px" class="dim">${xs.map(n => `<li>${esc(n)}</li>`).join('')}</ul>`;
const ORIGIN_LABEL = {vanilla: 'Vanilla', sod: 'Season of Discovery', new: 'New in this beta'};

async function renderSpell(id) {
  const seq = routeSeq;
  const s = await api('spell/' + id);
  if (seq !== routeSeq) return;

  let h = `<div class="head">${icon(s.icon)}<div><h1>${esc(s.name)}</h1><div class="sub" style="margin:0">Spell ${s.id}${s.subtext ? ' · ' + esc(s.subtext) : ''}</div></div></div>`;
  const tags = [`<span class="tag${s.origin === 'sod' ? ' sod' : ''}" title="${esc(s.originNote)}">${ORIGIN_LABEL[s.origin]}</span>`];
  if (s.hidden) tags.push(`<span class="tag" title="This spell is left out of the lists">hidden from lists: ${esc(s.hidden)}</span>`);
  s.talents.forEach(t => tags.push(`<a class="tag acc" href="#talents/${t.tree}">Talent · ${esc(t.title)} · ${esc(t.tab)} · row ${t.row || '?'} · ${t.maxRanks} rank${t.maxRanks > 1 ? 's' : ''}</a>`));
  s.classification.forEach(c => tags.push(`<span class="tag good" title="${c.Linked == 1 ? 'inherited via ' + esc(c.Via) : esc(c.Via)}">${esc(c.Cat)}: ${esc(c.Sub)}${c.Linked == 1 ? ' (linked)' : ''}</span>`));
  s.learn.forEach(l => {
    tags.push(`<span class="tag">${esc(l.skill)}</span>`, ...l.races.map(r => `<span class="tag">${esc(r)}</span>`), ...l.classes.map(c => `<span class="tag acc">${esc(c)}</span>`));
    if (l.supercedes) tags.push(`<span class="tag">replaces #${l.supercedes}</span>`);
  });
  s.supercededBy.forEach(i => tags.push(`<span class="tag">replaced by #${i}</span>`));
  h += chips(tags);
  if (s.ranks.length) h += `<div class="rkstrip"><b>Ranks</b>${s.ranks.map(r => `<button class="rkc${r.current ? ' on' : ''}${r.origin === 'sod' ? ' sod' : ''}" data-go="${r.id}">R${r.rank}<small>L${r.level}</small></button>`).join('')}</div>`;

  if (s.description || s.auraDescription)
    h += `<div class="desc">${esc(s.description)}${s.description !== s.descriptionRaw ? `<div class="raw">${esc(s.descriptionRaw)}</div>` : ''}${s.auraDescription ? `<div style="margin-top:8px;color:var(--good)">Aura: ${esc(s.auraDescription)}</div>` : ''}</div>`;

  h += '<div class="grid">' + stat('Cast', s.cast) + stat('Duration', s.duration) + stat('Range', s.range) + stat('School', s.schools.join(', '))
    + (s.level && s.level !== '0' ? stat('Spell level', s.level) : '') + (s.cooldown ? stat('Cooldown', s.cooldown) : '') + (s.gcd ? stat('GCD', s.gcd) : '')
    + (s.costs.length ? stat('Cost', s.costs.join(', ')) : '') + stat('Icon FileDataID', s.iconFileDataID) + '</div>';

  if (s.proc) h += `<h2>Proc</h2><div class="card">Chance: <b>${s.proc.chance}%</b>${s.proc.cooldown ? ` · Cooldown: <b>${s.proc.cooldown}</b>` : ''}${s.proc.charges && s.proc.charges !== '0' ? ` · Charges: <b>${s.proc.charges}</b>` : ''}<div class="grp"><b>ProcFlags</b>${s.proc.triggers.map(x => flag(x)).join('') || '—'}</div>${s.proc.triggers2.length ? `<div class="grp"><b>ProcFlags2</b>${s.proc.triggers2.map(x => flag(x)).join('')}</div>` : ''}${bullets(s.procNotes)}</div>`;
  else if (s.procNotes.length) h += `<h2>Proc</h2><div class="card">${bullets(s.procNotes)}</div>`;

  h += '<h2>Effects</h2>' + (s.effects.map(e => `<div class="card"><b>#${e.index} ${esc(e.effect)}</b>${e.aura ? ' → ' + esc(e.aura) : ''}
      <div class="dim">Base points: ${esc(e.basePoints)} · Targets: ${esc(e.targets.join(', ') || '—')}${e.triggerSpell && e.triggerSpell !== '0' ? ' · Triggers spell ' + e.triggerSpell : ''}</div>
      ${e['auraPeriod(ms)'] && e['auraPeriod(ms)'] !== '0' ? `<div class="dim">Tick period: ${e['auraPeriod(ms)']} ms</div>` : ''}${e.mechanic ? `<div class="dim">Mechanic: ${esc(e.mechanic)}</div>` : ''}
      ${e.effectAttributes.length ? `<div class="grp"><b>EffectAttrs</b>${e.effectAttributes.map(x => flag(x)).join('')}</div>` : ''}
      <details><summary>raw</summary>${kv(e.raw)}</details></div>`).join('') || '<p class="dim">None</p>');

  const F = s.flags, sec = (t, xs, hot) => xs.length ? `<div class="grp"><b>${t}</b>${xs.map(x => flag(x, hot)).join('')}</div>` : '';
  const key = sec('Periodic', F.periodic, 1) + sec('Proc', F.proc, 1) + sec('Interrupt', F.interrupt) + sec('Aura interrupt', F.auraInterrupt) + sec('Channel interrupt', F.channelInterrupt) + sec('Target flags', F.targets)
    + (s.categories.mechanic ? `<div class="grp"><b>Mechanic</b>${esc(s.categories.mechanic)}</div>` : '') + (s.categories.dispel ? `<div class="grp"><b>Dispel</b>${esc(s.categories.dispel)}</div>` : '');
  if (key) h += `<h2>Key flags</h2><div class="card">${key}</div>`;

  if (Object.keys(s.attributes).length) h += '<h2>Attributes</h2><div class="card">' + Object.entries(s.attributes).map(([g, xs]) => `<div class="grp"><b>${g}</b>${xs.map(x => flag(x)).join('')}</div>`).join('') + '</div><p class="dim" style="font-size:12px">Hover a flag for its description. UNK_ = bit with no public name.</p>';
  if (s.related.length) h += '<h2>Related spells</h2>' + s.related.map(r => `<button class="rel" data-go="${r.id}">${icon(r.icon)}<span>${esc(r.name)}</span> ${sodBadge(r.origin)}<small>${r.id} · ${esc(r.why)}</small></button>`).join('');
  h += '<h2>Raw table rows</h2>' + Object.entries(s.tables).map(([t, rs]) => `<details><summary>${t} (${rs.length})</summary>${rs.map(kv).join('')}</details>`).join('');
  $('#main').innerHTML = h;
  bindGo();
}
