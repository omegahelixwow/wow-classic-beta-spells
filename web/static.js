/* Static-site backend. On GitHub Pages there is no server, so api() is answered from the pre-rendered JSON files under
   api/, and the few dynamic parts the Python server does per request are done here: SoD filtering, text filtering,
   folding ranks into one tile, and name search. Only active when index.html sets window.SPELLBOOK_STATIC. */
const jsonCache = {};
const getJSON = path => jsonCache[path] || (jsonCache[path] = fetch(path).then(r => r.ok ? r.json() : null).catch(() => null));

async function staticApi(path, p) {
  let m;
  if (path === 'meta') return getJSON('api/meta.json');
  if (path === 'browse') return getJSON(`api/browse-${state.sod ? 1 : 0}.json`);
  if (path === 'talents') return getJSON('api/talents.json');
  if ((m = path.match(/^talents\/(\d+)$/))) return getJSON(`api/talents/${m[1]}.json`);
  if ((m = path.match(/^tip\/(\d+)$/))) return getJSON(`api/tip/${m[1]}.json`);
  if ((m = path.match(/^spell\/(\d+)$/))) return staticSpell(m[1]);
  if (path === 'search') return staticSearch(p.q || '');
  if (path === 'browse/list') return staticList(p);
  return null;
}

// The exported spell pages include SoD ranks / related spells; hide them unless the switch is on (same rule as spells.py).
// A SoD rank still fills a rank number nothing else has (Frostfire Bolt rank 1), so an ability is not shown starting at rank 2.
function visibleRanks(ranks, me) {
  if (state.sod || me === 'sod') return ranks;
  const kept = ranks.filter(r => r.origin !== 'sod'), taken = new Set(kept.map(r => r.rank));
  for (const r of ranks) if (r.origin === 'sod' && !taken.has(r.rank)) { taken.add(r.rank); kept.push(r); }
  return kept.sort((a, b) => a.rank - b.rank || a.id - b.id);
}
async function staticSpell(id) {
  const s0 = await getJSON(`api/spell/${id}.json`);
  if (!s0) return null;
  const s = {...s0};
  if (!state.sod) {
    s.related = s.related.filter(r => r.origin !== 'sod');
    s.ranks = visibleRanks(s.ranks, s.origin);
    if (s.ranks.length < 2) s.ranks = [];
  }
  return s;
}

// name search over one index: [id, name, origin, hidden]. Ids are always honoured; SoD and hidden spells are skipped otherwise.
let searchRows = null;
async function staticSearch(q) {
  q = q.trim();
  if (!q) return [];
  if (!searchRows) {
    const rows = await getJSON('api/search.json') || [];
    searchRows = rows.map(r => ({id: r[0], name: r[1], origin: r[2], hidden: r[3], low: r[1].toLowerCase()}));
  }
  if (/^\d+$/.test(q)) { const r = searchRows.find(x => x.id === +q); return r ? [{id: r.id, name: r.name, origin: r.origin}] : []; }
  const t = q.toLowerCase(), out = [];
  for (const r of searchRows) {
    if (r.hidden || (!state.sod && r.origin === 'sod') || !r.low.includes(t)) continue;
    out.push({id: r.id, name: r.name, origin: r.origin});
    if (out.length >= 50) break;
  }
  return out;
}

// ---- lists: filter, then fold ranks (a port of browse.fold / browse.listing in spellbook/browse.py; keep in step) ----
const RANK_RE = /^Rank (\d+)$/, VIA_ID = / \(\d+\)$/;

async function listRows(cat, sub) {
  const tree = await getJSON('api/browse-1.json') || [];
  const c = tree.find(x => x.cat === cat), s = c && c.subs.find(x => x.sub === sub);
  if (!s) return [];
  const rows = await getJSON(`api/lists/${s.file}.json`) || [];
  return rows.map(r => ({id: r[0], name: r[1], subtext: r[2], linked: r[3], via: r[4], origin: r[5], via_origin: r[6], icon: r[7], level: r[8]}));
}

function foldRows(rows, offset, limit) {
  const fams = new Map();
  for (const r of rows) {
    const m = RANK_RE.exec(r.subtext || ''), linked = !!r.linked;
    const key = m ? JSON.stringify([r.name, linked, linked ? r.via.replace(VIA_ID, '') : r.via]) : 'id' + r.id;
    if (!fams.has(key)) fams.set(key, []);
    fams.get(key).push([m ? +m[1] : 0, r.level || 0, r]);
  }
  const items = [];
  for (const members of fams.values()) {
    members.sort((a, b) => a[0] - b[0] || a[2].id - b[2].id);
    const [, , r] = members[members.length - 1];                   // the highest rank stands for the ability
    const ranked = members.filter(t => t[0]);
    const item = {id: r.id, name: r.name, subtext: r.subtext || '', linked: !!r.linked, via: r.via, origin: r.origin,
                  icon: r.icon, level: String(r.level || 0), ranks: ranked.length > 1 ? ranked.length : 0};
    if (item.ranks) {
      item.rankRange = [ranked[0][0], ranked[ranked.length - 1][0]];
      item.levels = [Math.min(...ranked.map(t => t[1])), Math.max(...ranked.map(t => t[1]))];
      item.rankList = ranked.map(t => ({id: t[2].id, rank: t[0], level: t[1], origin: t[2].origin}));
    }
    items.push(item);
  }
  // a linked ranked family that duplicates a direct ranked one (same name) is a helper-spell copy: drop it
  const directRanked = new Set(items.filter(i => i.ranks && !i.linked).map(i => i.name));
  const kept = items.filter(i => !(i.linked && i.ranks && directRanked.has(i.name)));
  return {total: kept.length, spells: new Set(rows.map(r => r.id)).size, offset, items: kept.slice(offset, offset + limit)};
}

// port of browse.with_sod_ranks: with SoD hidden, a SoD spell still fills a missing rank number of a visible ability
const famKey = r => {
  const m = RANK_RE.exec(r.subtext || '');
  if (!m) return null;
  const linked = !!r.linked;
  return JSON.stringify([r.name, linked, linked ? r.via.replace(VIA_ID, '') : r.via]);
};
const rankNum = r => +RANK_RE.exec(r.subtext)[1];
function withSodRanks(all, show) {
  if (show) return all;
  const vis = r => r.origin !== 'sod' && r.via_origin !== 'sod', taken = new Map();
  for (const r of all) if (vis(r) && famKey(r)) { const k = famKey(r); if (!taken.has(k)) taken.set(k, new Set()); taken.get(k).add(rankNum(r)); }
  return all.filter(r => {
    if (vis(r)) return true;
    const k = famKey(r);
    if (r.origin !== 'sod' || !k || !taken.has(k) || taken.get(k).has(rankNum(r))) return false;
    taken.get(k).add(rankNum(r));
    return true;
  });
}

async function staticList(p) {
  let rows = await listRows(p.cat, p.sub);
  if (p.q) { const t = String(p.q).toLowerCase(); rows = rows.filter(r => (r.name || '').toLowerCase().includes(t) || String(r.id) === String(p.q)); }
  return foldRows(withSodRanks(rows, state.sod), +(p.offset || 0), +(p.limit || 300));
}
