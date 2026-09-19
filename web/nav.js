/* Top bar: class / racial buttons, the "Unknown" menu, search, the SoD switch. */
let NAV = null, TI = null;                                   // navigation counts, talent-tree index
const talentTree = cls => TI && TI.find(t => t.class === cls);

async function loadNav() {
  if (NAV) return;
  const [nav, ti] = await Promise.all([api('browse'), api('talents')]);
  NAV = nav; TI = ti;
  const cat = c => NAV.find(x => x.cat === c) || {subs: [], count: 0};
  const btn = (c, s) => `<button class="nb" data-cat="${esc(c)}" data-sub="${esc(s.sub)}" title="${s.count.toLocaleString()} spells">${esc(s.sub)}</button>`;
  const item = (c, s, label) => `<button class="it" data-cat="${esc(c)}" data-sub="${esc(s.sub)}">${esc(label || s.sub)}<small>${s.count.toLocaleString()}</small></button>`;
  const skills = cat('Skills'), test = cat('Test / Deprecated'), npc = cat('NPC / Unknown');
  $('#nav').innerHTML =
    `<div class="navrows"><div class="grp2"><span class="lab">Classes</span>${cat('Class').subs.map(s => btn('Class', s)).join('')}</div>` +
    `<div class="grp2"><span class="lab">Racials</span>${cat('Racial').subs.map(s => btn('Racial', s)).join('')}</div></div>` +
    `<div class="unk"><button class="nb" id="unk-btn">Unknown ▾</button><div class="menu" id="unk-menu" hidden>` +
      (skills.subs.length ? `<details><summary>Skills &amp; professions <small>${skills.count.toLocaleString()}</small></summary><div class="in">${skills.subs.map(s => item('Skills', s)).join('')}</div></details>` : '') +
      test.subs.map(s => item('Test / Deprecated', s, 'Test / deprecated')).join('') +
      npc.subs.map(s => item('NPC / Unknown', s, 'NPC / unknown')).join('') +
    `</div></div>`;
}

function navMark(cat, sub) {
  document.querySelectorAll('#nav [data-cat]').forEach(x => x.classList.toggle('on', x.dataset.cat === cat && x.dataset.sub === sub));
  const u = $('#unk-btn'); if (u) u.classList.toggle('on', !!document.querySelector('#unk-menu [data-cat].on'));
}

$('#nav').addEventListener('click', e => {
  if (e.target.closest('#unk-btn')) { const m = $('#unk-menu'); m.hidden = !m.hidden; return; }
  const b = e.target.closest('[data-cat]'); if (!b) return;
  $('#unk-menu').hidden = true; go(listHash(b.dataset.cat, b.dataset.sub));
});
document.addEventListener('click', e => {                      // click-away closes the dropdowns
  if (!e.target.closest('.unk') && $('#unk-menu')) $('#unk-menu').hidden = true;
  if (!e.target.closest('.srch')) $('#res').hidden = true;
});

// Spells | Talents pills on a class page
const viewTabs = (cls, active) => `<div class="vt"><button data-vt="list" data-cls="${esc(cls)}" class="${active === 'list' ? 'on' : ''}">Spells</button><button data-vt="tal" data-cls="${esc(cls)}" class="${active === 'tal' ? 'on' : ''}">Talents</button></div>`;
document.addEventListener('click', e => {
  const b = e.target.closest('[data-vt]'); if (!b) return;
  if (b.dataset.vt === 'tal') { const t = talentTree(b.dataset.cls); if (t) go('#talents/' + t.id); }
  else go(listHash('Class', b.dataset.cls));
});

// ---- search ----
let searchTimer;
async function search(q, quiet) {
  const r = q.trim() ? await api('search', {q}) : [];
  $('#res').innerHTML = r.map(s => `<button data-id="${s.id}">${esc(s.name)} ${sodBadge(s.origin)}<small>${s.id}</small></button>`).join('')
    || '<small class="dim" style="padding:6px 8px;display:block">No matches</small>';
  $('#res').hidden = quiet || !q.trim();
  return r;
}
$('#q').oninput = e => { clearTimeout(searchTimer); searchTimer = setTimeout(() => search(e.target.value), 150); };
$('#q').onfocus = e => { if (e.target.value.trim() && $('#res').children.length) $('#res').hidden = false; };
$('#q').onkeydown = e => {
  if (e.key === 'Escape') $('#res').hidden = true;
  if (e.key === 'Enter') { const b = $('#res button'); if (b) { $('#res').hidden = true; go('#spell/' + b.dataset.id); } }
};
$('#res').onclick = e => { const b = e.target.closest('button'); if (b) { $('#res').hidden = true; go('#spell/' + b.dataset.id); } };

// ---- SoD switch + build info ----
$('#sod').checked = state.sod;
$('#sod').onchange = e => { setSod(e.target.checked); NAV = null; if ($('#q').value.trim()) search($('#q').value); route(); };
api('meta').then(m => {
  const o = m.origins || {};
  $('#meta').textContent = `Build ${m.build} · ${(o.vanilla || 0).toLocaleString()} vanilla · ${(o.new || 0).toLocaleString()} new · ${(o.sod || 0).toLocaleString()} SoD`;
  $('#meta').title = `vanilla = existed before Season of Discovery (${m.pre_sod_build}); SoD = added since (${m.sod_era_build}); new = only in this beta`;
});
