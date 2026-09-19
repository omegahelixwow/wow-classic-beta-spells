/* Shared helpers, state, and the tiny API client. Loaded first. */
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const enc = encodeURIComponent, dec = decodeURIComponent;
const ICON_URL = n => `https://wow.zamimg.com/images/wow/icons/large/${esc(n)}.jpg`;
const icon = (n, extra = '') => n ? `<img src="${ICON_URL(n)}" alt="" ${extra} onerror="this.style.visibility='hidden'">` : '';
const kv = o => '<div class="tablewrap"><table>' + Object.entries(o).map(([k, v]) => `<tr><th>${esc(k)}</th><td>${esc(typeof v === 'object' ? JSON.stringify(v) : v)}</td></tr>`).join('') + '</table></div>';
const stat = (k, v) => `<div class="stat"><b>${k}</b>${esc(v)}</div>`;
const flag = (x, hot) => `<span class="flag${hot ? ' hot' : ''}" title="${esc([x.title, x.desc, (x.group ? x.group + ' ' : '') + 'bit ' + x.bit].filter(Boolean).join(' — '))}">${esc(x.name)}<i>${x.hex}</i></span>`;
const sodBadge = o => o === 'sod' ? '<span class="badge" title="Season of Discovery">SoD</span>' : '';

// ---- "Show SoD": Season of Discovery spells are hidden unless this is on (remembered in the browser) ----
const SOD_KEY = 'spellbook:showSod';
const state = {sod: false};
try { state.sod = localStorage.getItem(SOD_KEY) === '1'; } catch (e) {}
const setSod = on => { state.sod = on; try { localStorage.setItem(SOD_KEY, on ? '1' : '0'); } catch (e) {} };

/** Ask the backend: the live Python server (GET api/<path>), or, on the static site, the pre-rendered files (static.js).
 *  The SoD switch is added to every request. Resolves to null when there is no such thing. */
async function api(path, params = {}) {
  if (window.SPELLBOOK_STATIC) return staticApi(path, params);
  const u = new URLSearchParams(params);
  if (state.sod) u.set('sod', '1');
  const qs = u.toString();
  const r = await fetch('api/' + path + (qs ? '?' + qs : ''));
  return r.json();
}

// ---- routing helpers. Views: #spell/<id>  #list/<cat>/<sub>[?q=]  #talents/<treeId> ----
let routeSeq = 0;            // a newer navigation cancels renders still in flight
let listLoaded = 0;          // rows currently loaded in the open list (restored on Back)
const listHash = (cat, sub, q) => '#list/' + enc(cat) + '/' + enc(sub) + (q ? '?q=' + enc(q) : '');
const navSave = () => { try { history.replaceState({n: listLoaded, y: scrollY}, ''); } catch (e) {} };
function go(h) { navSave(); if (location.hash === h) route(); else location.hash = h; }
// Every [data-go] element opens its spell. A click only counts for the innermost one (a rank button inside a tile
// opens that rank, not the tile's top rank); Enter / Space on a focused tile does the same.
const touchOnly = () => !!window.matchMedia && matchMedia('(hover: none)').matches;
const bindGo = () => document.querySelectorAll('[data-go],[data-item]').forEach(b => {
  const dest = () => b.dataset.item ? '#item/' + b.dataset.item : '#spell/' + b.dataset.go;
  b.onclick = e => {
    if (e.target.closest('[data-go],[data-item]') !== b) return;
    // no hover on touch screens: the first tap on a ranked tile opens its rank strip, the second opens the spell
    if (touchOnly() && b.classList.contains('ranked') && !b.classList.contains('open')) {
      document.querySelectorAll('.tile.open').forEach(x => x.classList.remove('open'));
      b.classList.add('open'); return;
    }
    go(dest());
  };
  b.onkeydown = e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === b) { e.preventDefault(); go(dest()); } };
});
