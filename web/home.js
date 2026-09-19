/* The home page: what this is, the numbers, and a door into every class and race. */
const CLASS_COLOR = {Druid: '#ff7c0a', Hunter: '#aad372', Mage: '#3fc7eb', Paladin: '#f48cba', Priest: '#f8f8f2',
                     Rogue: '#fff468', Shaman: '#0070dd', Warlock: '#8788ee', Warrior: '#c69b6d'};
const EXAMPLES = [
  [1260189, 'Touch of the Grave', 'new in this beta: the Undead racial'],
  [25306, 'Fireball', 'twelve ranks, hover the tile on the Mage page'],
  [20577, 'Cannibalize', 'a racial with a linked aura'],
  [10901, 'Power Word: Shield', 'an absorb shield with ten ranks'],
];

async function renderHome() {
  const seq = routeSeq;
  const m = await api('meta');
  if (seq !== routeSeq) return;
  const cat = c => NAV.find(x => x.cat === c) || {subs: [], count: 0};
  const o = m.origins || {}, n = x => (x || 0).toLocaleString();
  const talentNodes = TI.reduce((s, t) => s + t.nodes, 0);
  const classCard = s => {
    const t = talentTree(s.sub), col = CLASS_COLOR[s.sub] || 'var(--acc)';
    return `<div class="cc" style="--cc:${col}"><span class="n">${esc(s.sub)}</span><span class="c">${n(s.count)} spells${t ? ` · ${t.nodes} talents` : ''}</span>
      <span class="go"><a href="${listHash('Class', s.sub)}">Spells</a>${t ? `<a href="#talents/${t.id}">Talents</a>` : ''}</span></div>`;
  };
  const raceCard = s => `<div class="cc" style="--cc:var(--blue)"><span class="n">${esc(s.sub)}</span><span class="c">${n(s.count)} spells</span><span class="go"><a href="${listHash('Racial', s.sub)}">Racials</a></span></div>`;
  const other = (c, s, label) => `<a class="link" href="${listHash(c, s.sub)}">${esc(label || s.sub)} <span class="dim">${n(s.count)}</span></a>`;
  const skills = cat('Skills'), test = cat('Test / Deprecated'), npc = cat('NPC / Unknown');

  $('#main').innerHTML = `<section class="home">
    <div class="hero">
      <div class="prompt"><b>$</b> spellbook <i>--build</i> ${esc(m.build)}</div>
      <h1>Spell Browser</h1>
      <p class="lead">Every spell in the WoW Classic beta client: abilities by class and race, hover tooltips with the real numbers, ranks folded into one tile, and the retail-model talent trees you can spend points in.</p>
      <div class="stats">
        <div class="s g"><b>${n(cat('Class').count)}</b><span>class spells</span></div>
        <div class="s b"><b>${n(cat('Racial').count)}</b><span>racial spells</span></div>
        <div class="s y"><b>${n((IT || []).reduce((a, c) => a + c.count, 0))}</b><span>items</span></div>
        <div class="s y"><b>${TI.length} / ${n(talentNodes)}</b><span>talent trees / talents</span></div>
        <div class="s"><b>${n(o.vanilla)}</b><span>vanilla spells</span></div>
        <div class="s y"><b>${n(o.new)}</b><span>new in this beta</span></div>
        <div class="s p"><b>${n(o.sod)}</b><span>Season of Discovery (${state.sod ? 'shown' : 'hidden'})</span></div>
      </div>
    </div>

    <h2>Classes</h2>
    <div class="cards">${cat('Class').subs.map(classCard).join('')}</div>

    <h2>Racials</h2>
    <div class="cards">${cat('Racial').subs.map(raceCard).join('')}</div>

    <h2>Items</h2>
    <div class="cards">${(IT || []).filter(c => [2, 4, 0, 7].includes(c.cls)).map(c => `<div class="cc" style="--cc:var(--yellow,#e6db74)"><span class="n">${esc(c.name)}</span><span class="c">${n(c.count)} items</span><span class="go">${c.subs.slice(0, 4).map(s => `<a href="${itemListHash(c.cls, s.sub)}">${esc(s.name)}</a>`).join('')}</span></div>`).join('')}</div>
    <p class="dim">Every other item type is in the <b>Items</b> menu in the bar. Item pages list stats, armor, and the spells an item casts.</p>

    <h2>Try these</h2>
    <div class="cards">${EXAMPLES.map(([id, name, why]) => `<div class="cc" style="--cc:var(--green)"><span class="n">${esc(name)}</span><span class="c">${esc(why)}</span><span class="go"><a href="#spell/${id}">Open</a></span></div>`).join('')}</div>

    <h2>Everything else</h2>
    <div class="linkrow">
      ${skills.subs.length ? `<a class="link" href="${listHash('Skills', skills.subs[0].sub)}">Skills &amp; professions <span class="dim">${n(skills.count)}</span></a>` : ''}
      ${test.subs.map(s => other('Test / Deprecated', s, 'Test / deprecated')).join('')}
      ${npc.subs.map(s => other('NPC / Unknown', s, 'NPC / unknown')).join('')}
    </div>
    <p class="dim">These live in the <b>Unknown</b> menu too. NPC / unknown is a leftover bucket: the client tables have no field that says a spell belongs to an NPC.</p>

    <h2>About the data</h2>
    <ul>
      <li>Source: the client's own DB2 tables via wago.tools, build <code>${esc(m.build)}</code>. Flag names are TrinityCore's.</li>
      <li><b>Season of Discovery</b> spells are hidden everywhere by default. A spell counts as SoD if it first appears in the SoD-era client (<code>${esc(m.sod_era_build)}</code>) and was not in the last pre-SoD one (<code>${esc(m.pre_sod_build)}</code>). Tick <b>Show SoD</b> in the bar to bring them back.</li>
      <li>Engraving spells, talents (they have their own tab), and Warlock's Metamorphosis form abilities are left out of the lists. They can still be found by search or id.</li>
      <li>Hover any spell for a summary. On touch screens, tap a ranked tile once to see its ranks, again to open it.</li>
    </ul>
  </section>`;
  navMark();
}
