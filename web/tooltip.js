/* Hover tooltips: a condensed spell summary (spell tiles, search results, related spells) and talent-node tooltips. */
const tipEl = $('#tip'), tipCache = {};
let tipTimer, tipId = null, tipXY = [0, 0];

function tipHtml(t) {
  let h = `<div class="t">${icon(t.icon)}<div><div class="n">${esc(t.name) || '(unnamed)'} ${sodBadge(t.origin)}</div><div class="s">Spell ${t.id}${t.subtext ? ' · ' + esc(t.subtext) : ''} · ${esc(t.school)}</div></div></div>`;
  if (t.line1.length) h += `<div class="l">${t.line1.map(esc).join(' · ')}</div>`;
  if (t.description) h += `<div class="d">${esc(t.description)}</div>`;
  if (t.aura) h += `<div class="a">${esc(t.aura)}</div>`;
  if (t.ranks && t.ranks.length > 1) { const a = t.ranks[0], z = t.ranks[t.ranks.length - 1]; h += `<div class="l">Ranks ${a.rank}–${z.rank} · levels ${a.level}–${z.level}</div>`; }
  if (t.effects.length) h += `<div class="e">${t.effects.map(esc).join('<br>')}</div>`;
  if (t.proc) h += `<div class="p">Proc <b>${t.proc.chance}%</b>${t.proc.cooldown ? ' · ICD ' + esc(t.proc.cooldown) : ''}<br>${t.proc.flags.map(f => `<span class="fl">${esc(f)}</span>`).join('')}${t.proc.note ? `<div class="s">${esc(t.proc.note)}</div>` : ''}</div>`;
  if (t.keyFlags.length) h += `<div class="w">${t.keyFlags.map(f => `<span class="fl hot">${esc(f)}</span>`).join('')}</div>`;
  const w = t.learn.concat(t.where);
  if (w.length) h += `<div class="w s">${w.map(esc).join(' · ')}</div>`;
  return h + '<div class="hint">Click for the full page</div>';
}

function tipPlace() {
  const [x, y] = tipXY, w = tipEl.offsetWidth, h = tipEl.offsetHeight;
  let l = x + 16, t = y + 16;
  if (l + w > innerWidth - 8) l = Math.max(8, x - w - 16);
  if (t + h > innerHeight - 8) t = Math.max(8, innerHeight - h - 8);
  tipEl.style.left = l + 'px'; tipEl.style.top = t + 'px';
}
const tipHide = () => { tipId = null; clearTimeout(tipTimer); tipEl.hidden = true; };

async function tipShow(id) {
  if (!tipCache[id]) { try { tipCache[id] = await api('tip/' + id); } catch (e) { tipCache[id] = null; } }
  if (tipId !== id || !tipCache[id]) return;
  tipEl.innerHTML = tipHtml(tipCache[id]); tipEl.hidden = false; tipPlace();
}

// spell tiles / related buttons carry data-go, search results carry data-id
const tipTarget = e => {
  const el = e.target.closest('[data-go],#res button[data-id]');
  if (el && el.classList.contains('tile') && e.target.closest('.rkpop') && !e.target.closest('.rkb')) return null;   // strip chrome: keep the current tooltip
  return el && {el, id: el.dataset.go || el.dataset.id};
};
document.addEventListener('mouseover', e => {
  const t = tipTarget(e); if (!t || t.id === tipId) return;
  tipId = t.id; tipXY = [e.clientX, e.clientY]; clearTimeout(tipTimer);
  tipTimer = setTimeout(() => tipShow(t.id), tipCache[t.id] ? 0 : 150);
});
document.addEventListener('mousemove', e => { tipXY = [e.clientX, e.clientY]; if (!tipEl.hidden) tipPlace(); });
document.addEventListener('mouseout', e => { const t = tipTarget(e); if (t && !t.el.contains(e.relatedTarget)) tipHide(); });
document.addEventListener('click', tipHide);
document.addEventListener('scroll', tipHide, true);
