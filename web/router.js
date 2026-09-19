/* Hash router: every view has its own address, so Back / Forward work.  Loaded last; starts the app. */
const HOME = '#home';

async function route() {
  const seq = ++routeSeq;
  await loadNav();
  const hs = location.hash.slice(1), st = history.state || {};
  let m;
  navMark();
  if (!/^(item|items)\//.test(hs)) itemNavMark();
  if (hs === '' || hs === 'home') await renderHome();
  else if ((m = hs.match(/^spell\/(\d+)$/)) || (m = hs.match(/^(\d+)$/))) await renderSpell(m[1]);
  else if (m = hs.match(/^item\/(\d+)$/)) await renderItem(m[1]);
  else if (m = hs.match(/^items\/(\d+)\/(\d+)(?:\?q=(.*))?$/)) await renderItemList(m[1], m[2], m[3] ? dec(m[3]) : '', st.n || 300);
  else if (m = hs.match(/^talents(?:\/(\d+))?$/)) await renderTalents(m[1]);
  else if (m = hs.match(/^list\/([^/]+)\/([^?]*)(?:\?q=(.*))?$/)) await renderList(dec(m[1]), dec(m[2]), m[3] ? dec(m[3]) : '', st.n || 300);
  else { history.replaceState(null, '', HOME); return route(); }
  if (seq === routeSeq) scrollTo(0, st.y || 0);         // restore scroll on Back, unless a newer navigation took over
}
addEventListener('hashchange', route);
route();
