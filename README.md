# Spell Browser — WoW Classic beta (build 1.60.1.69913)

A local web app for browsing every spell in the Classic beta client: full spell detail, hover tooltips,
class / racial / skill lists, and the retail-model talent trees. Data comes from the client's DB2 tables via
[wago.tools](https://wago.tools).

```
python3 build.py            # fetch anything missing, rebuild data/spells.db (about 4 s from cache)
python3 run.py              # http://localhost:8765
```
`build.py --offline` never touches the network; `--refetch` re-downloads everything. Stop the server before rebuilding.

## Hosting on GitHub Pages
GitHub Pages serves static files only, so the Python server is replaced by a pre-rendered copy of its answers:

```
python3 build.py                    # data/spells.db from wago.tools
python3 export.py --out dist        # dist/ = the whole site as static files (~125 MB, ~64,000 small files, about 4 minutes)
python3 -m http.server -d dist      # try it locally
```
The page code is identical in both modes. On the static site `web/static.js` answers the `api()` calls from `dist/api/*.json`
and does the dynamic parts in the browser: name search, the SoD switch, list filtering, folding ranks into one tile.

The repository holds only code. `.github/workflows/pages.yml` runs `build.py` and `export.py` on every push to `main` and
publishes `dist/`, so the downloaded game data never enters git. One-time setup: create the repository, push, then
*Settings -> Pages -> Build and deployment -> Source: GitHub Actions*. Change `BUILD` in `spellbook/config.py` and push to
rebuild for a newer client build.

The exported site carries `noindex` and a `robots.txt` that disallows crawling, so search engines are asked to skip it. A
Pages site is still reachable by anyone with the link (Pages sites from private repositories are also public unless you are on
GitHub Enterprise Cloud).

## Layout
```
build.py  run.py  export.py  entry points (database / local server / static site)
spellbook/
  config.py                 paths, BUILD, reference builds, table list
  fetch.py  flagdefs.py     download wago tables / icon names / TrinityCore flag names        (build time)
  load.py                   CSV -> SQLite (all columns text) + indexes                          (build time)
  origins.py                vanilla / sod / new                                                (build time)
  classify.py               where each spell lives in the browser; what is hidden              (build time)
  db.py  flags.py  descriptions.py   query helpers, flag names, $-token resolver               (runtime)
  spells.py  browse.py  talents.py   spell detail + tooltip + search, lists, talent trees      (runtime)
  server.py                 JSON API (/api/...) + static files from web/
  export_static.py          pre-renders the API as JSON files for GitHub Pages
web/                        index.html, style.css, core/static/tooltip/nav/list/spell/talents/home/router .js
data/                       csv/ (raw tables), origins/, reference/ (icons.json, flags.json), spells.db
legacy/                     the previous single-file version, kept for reference
```

## Look and feel
Square corners, Monokai palette, monospaced type, no external fonts or CDNs (icons are the only remote assets). Responsive:
below 720px the bar stops being sticky, search gets its own line and the class/race rows scroll sideways; below 420px the spell
grid is three columns. Touch screens have no hover, so a tap on a ranked tile opens its rank strip and a second tap opens the
spell, and the talent trees get a **Tap: add / remove / open** button (desktop also has right-click and shift-click).
The home page (`#home`) shows the numbers and a card per class and race.

## Is it a Season of Discovery spell?
Decided by comparing spell ids across client builds, **not** by id range:

| origin | rule | spells |
|---|---|---|
| `vanilla` | exists in the last pre-SoD Era client (1.14.4.51829) | 16,929 |
| `sod` | first appears in the SoD-era client (1.15.9.69722), not before | 9,457 |
| `new` | exists in neither, i.e. introduced by this beta (e.g. Touch of the Grave) | 5,381 |

An id range would misclassify ~150 spells (SoD reuses low ids such as Earth Shield 974; 17 vanilla spells have ids above
400000). SoD spells are hidden in every list, in search and in related-spell links; the **Show SoD** switch brings them
back (marked with an SoD badge). A spell opened by id or link is always shown, labelled with its origin.
Caveat: the class talent trees themselves contain 38 SoD-origin spells (Hot Streak, Missile Barrage ...). They are part
of the beta's own trees, so they stay in place and are marked with a purple dot instead of being cut out.

## Where each spell is listed (`classify.py`)
* **Class** — `SkillLineAbility.ClassMask` (a skill line whose rows all name one class lets `ClassMask=0` rows inherit it), grouped by spec.
* **Racial** — skill lines named "... Racial", grouped by race.  **Skills** — professions, weapons, riding, pets, languages.
* **Test / Deprecated** and **NPC / Unknown** — the rest (behind the *Unknown* menu). "NPC / Unknown" is a leftover bucket:
  the client tables have no field saying a spell belongs to an NPC.
* **Linked** spells (no skill line of their own) inherit the home of the spell that triggers / mentions them.
* **Weapons & Armor** is one section in each class list: the weapon and armor skill lines (Axes, Daggers, Cloth, Mail, Shield ..., plus the
  relic proficiencies under GENERIC (DND)) share it instead of getting a heading each.
* **Mounts and riding** are not class spells. They are listed under Skills -> Mounts / Riding, except the four mounts a class trains
  itself (Summon Warhorse / Charger for Paladins, Summon Felsteed / Dreadsteed for Warlocks), which stay in that class.
  (A skill line whose rows name a single class lets its class-less rows inherit it -- but not the Mounts / Riding lines, whose
  three Paladin rows would otherwise claim every mount.)
* **Hidden from every list** (still findable by id; search also skips engraving / form-only / orphan / helper spells, but not talents):
  * engraving and rune spells;
  * **passive** talents (they live in the Talents tab): passives in the retail-model class trees or the classic `Talent` table, same-named
    ranks, and ranked passives in a class skill line ("Improved Flash of Light"). **Active** talents (Riptide, Stormstrike, Pyroblast,
    Consecration ...) are abilities you cast, so they are listed; the spell's own PASSIVE flag decides, not the talent table;
  * helper / effect spells: learned automatically (`SkillLineAbility.AcquireMethod` 3) with no cost, cooldown or global cooldown
    (Judgement of Light, the extra Flash of Light / Holy Light spells, "Hellfire Effect", "Jeff Dummy"). Real abilities that share
    that method (Execute, Readiness, Feral Charge (Bear)) have a cost or cooldown and stay;
  * spells that exist only inside Warlock's Metamorphosis form (found through the form spell's action-bar-override effects);
  * anything reachable only through one of those.
* **Helper copies are not listed twice.** A linked spell (one with no skill-line row of its own) whose name matches a directly listed *castable*
  ability is dropped from the list (Holy Light's effect spell). A passive with a castable linked spell keeps both: Touch of the Grave's
  active drain is the real ability.
* **Ranks folded into one tile.** With SoD hidden, a SoD spell still fills a rank number that nothing else has (Frostfire Bolt rank 1 is a
  SoD spell, ranks 2-3 are new in this beta), so an ability never starts at rank 2 -- but a SoD rank never duplicates an existing one.
  The Python (`browse.with_sod_ranks`) and browser (`static.js`) versions are checked against each other.

## Talent trees (`talents.py`)
Retail `Trait*` model: nodes carry positions and groups; edges are prerequisites; conditions gate rows ("N points in this
tab"); per-rank values come from curves. Only the nine class trees (currency 3820, 51 points, 3 tabs x 7 rows) are built.
Tabs are the columns of nodes, named after the skill line most of their spells belong to. Three nodes have coordinates 10x
too large in the data (2 Hunter, 1 Priest); they are shown separately as "off-grid".

## What a talent affects (`affects.py`)
Found the way the game does it, through class masks: an effect's `EffectSpellClassMask` is matched against every spell's
`SpellClassOptions` mask in the same class family (`SpellClassSet`). Improved Frostbolt has mask 32 in family 3 (Mage), so it
affects each Frostbolt rank. For flat / percentage modifier auras the effect's misc value names *what* changes (cast time,
cooldown, power cost ... from TrinityCore's `SpellModOp`), shown with the value. Only spells that appear in a class list count as
affected (not NPC copies or helper spells). The spell page has an **Affects** section, and talent tooltips list the spells.

## Trigger links (`links.py`)
Every spell page shows how it connects to other spells, from the client data alone:
* **Triggers / applies** -- child spells, each with its text, its effects and what it affects (class-mask spells, or a damage school
  for auras like Shadow Vulnerability's "Shadow: +4%"), plus one nested level. A child is a spell an effect names
  (`EffectTriggerSpell`), or one whose *duration* the text uses (`$17794d`): Improved Shadow Bolt's proc is server logic, so its text
  is the only link to the debuff it applies.
* **Triggered by** -- the parents: the reverse of the above, plus spells whose numbers this one takes (`$1260189s1`: Touch of the
  Grave's active drain reads the passive's 5%).
* **Used by** -- spells whose text takes its numbers from this one (the drain behind a passive proc).
Talent tooltips add an "Applies ..." line for the aura the talent applies.

## Items (`items.py`, `web/items.js`)
Items are first-class: an **Items** menu in the top bar (by item class and subclass), item pages (`#item/<id>`), hover tooltips, item
results in search, and links from spell pages ("Items that use this spell"). Tables: `Item`, `ItemSparse`, `ItemClass`, `ItemSubClass`,
`ItemEffect`, `ItemXItemEffect`, `RandPropPoints`, `ItemArmorTotal`, `ItemArmorQuality`, `ArmorLocation`.
* **SoD items** are found the same way as SoD spells: by which Era build first has the item id (`ItemOrigin`); hidden unless "Show SoD" is on.
* **Stats** = the item's `StatPercentEditor` share of the slot budget in `RandPropPoints[item level]` (Good / Superior / Epic column by quality,
  slot column by inventory type). **Armor** = `ItemArmorTotal x ItemArmorQuality x ArmorLocation`. Both reproduce Wowhead's numbers for the
  items checked (Brightcloth Robe 70 armor, Inferno Gloves 55 armor / +9 Intellect). Stats with no public name (id 85) are spell effects and are
  left to the item's spell list. Test / monster / placeholder items are hidden from lists and search (pages still open by id).
* **Weapon damage is not shown.** It is not derivable from these tables (an earlier attempt computed numbers that did not match Wowhead and was
  removed); item pages link to Wowhead instead. A weapon-damage spell (Shoot, Auto Shot) says it scales with the equipped weapon and links to
  the weapon lists it uses. The spell data has no coefficient for a wand; in game a base damage stat such as spell power is added on top
  (reported from play, not in the tables).
* **Items that use this spell** -- items with an effect that casts it (use / equip / chance on hit / teach).
* **Enchantments.** A spell that applies an item enchantment (poisons, imbues, weapon enchants; effect types 53, 54, 92, 156 and this build's
  360) shows the enchantment, and the spells it casts become children in the trigger links: Scroll of Imbue Quickening -> Imbue Quickening ->
  enchantment "Quickening" -> the proc aura -> +40% ranged attack speed.

## Links out
Every spell page links to the same spell on Wowhead's Forever database (`wowhead.com/forever/spell=<id>`), which tracks this game version.

## Known limits
* Description text resolves `$s $m $o $t $d $a $x $h`, `${expr}`, `$/N;`, `$l..:..;`; conditionals (`$?s...`) stay raw.
  Values scale to level 60 but are capped at each spell's own MaxLevel, as the client does.
* Flag names are TrinityCore's (server naming); bits it has no name for show as `UNK_0x...`.
* Icons load from Wowhead's CDN, so the page needs internet for images.
