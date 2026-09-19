"""Pre-render the whole app as static files (for GitHub Pages).

The live server answers /api/... from SQLite. A static host cannot, so this writes those answers as JSON and the
browser does the small dynamic parts itself (see web/static.js): SoD filtering, text filtering, rank folding, search.

    api/meta.json  api/browse-0.json  api/browse-1.json   navigation + counts (SoD hidden / shown)
    api/talents.json  api/talents/<tree>.json             talent trees
    api/lists/<slug>.json                                 every row of one class / race / skill list
    api/search.json                                       [id, name, origin, hidden] for every spell
    api/spell/<id>.json  api/tip/<id>.json                spell page and hover tooltip
    api/items.json  api/item-lists/<cls>-<sub>.json       item navigation, every row of one item type
    api/item-search.json  api/item/<id>.json  api/itip/<id>.json
"""
import json, re, shutil, sys, time
from pathlib import Path

from . import browse, config as C, db, items, spells, talents


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")


def slug(cat, sub):
    return re.sub(r"[^a-z0-9]+", "-", f"{cat} {sub}".lower()).strip("-")


def copy_site(out):
    """The web/ files, made static-aware: a flag the scripts read, and a request to search engines not to index it."""
    for f in C.WEB_DIR.iterdir():
        if f.is_file():
            shutil.copy2(f, out / f.name)
    idx = out / "index.html"
    html = idx.read_text(encoding="utf-8")
    html = html.replace("<head>", '<head>\n<meta name="robots" content="noindex,nofollow">\n<script>window.SPELLBOOK_STATIC = true;</script>', 1)
    idx.write_text(html, encoding="utf-8")
    (out / ".nojekyll").write_text("")                                   # serve files as they are (no Jekyll processing)
    (out / "robots.txt").write_text("User-agent: *\nDisallow: /\n")


def export(out, progress=True, site_only=False):
    """Write the whole static site to `out`. site_only=True refreshes just the web/ files in an existing export."""
    out = Path(out)
    if site_only:
        copy_site(out)
        print(f"site files refreshed -> {out}")
        return
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    t0 = time.time()
    copy_site(out)
    api = out / "api"
    db.bulk(True)

    _write(api / "meta.json", browse.meta())

    # navigation + one file per list
    ic = db.icons()
    used = {}
    trees = {}
    for sod in (0, 1):
        tree = browse.tree(bool(sod))
        for cat in tree:
            for s in cat["subs"]:
                fn = used.setdefault((cat["cat"], s["sub"]), slug(cat["cat"], s["sub"]))
                s["file"] = fn
        trees[sod] = tree
    assert len(set(used.values())) == len(used), "list file names collide"
    for sod, tree in trees.items():
        _write(api / f"browse-{sod}.json", tree)
    for (cat, sub), fn in used.items():
        rows = [[int(r["id"]), r["name"], r["subtext"] or "", int(r["linked"]), r["via"], r["origin"], r["via_origin"],
                 ic.get(r["icon"] or ""), int(r["level"] or 0), int(r["passive"])]
                for r in browse.raw_rows(cat, sub)]
        _write(api / "lists" / f"{fn}.json", rows)
    if progress:
        print(f"  navigation + {len(used)} lists   {time.time() - t0:5.0f}s")

    # talents
    idx = talents.index()
    _write(api / "talents.json", idx)
    for t in idx:
        _write(api / "talents" / f"{t['id']}.json", talents.tree(t["id"]))

    # search index
    index = spells.search_index()
    _write(api / "search.json", index)
    if progress:
        print(f"  talents + search index ({len(index):,} names)   {time.time() - t0:5.0f}s")

    # every spell page and tooltip (built with SoD shown; the browser filters it out when the switch is off)
    ids = [r["ID"] for r in db.q("select ID from SpellName order by cast(ID as integer)")]
    for n, sid in enumerate(ids, 1):
        s = spells.spell(sid, show_sod=True)
        _write(api / "spell" / f"{sid}.json", s)
        _write(api / "tip" / f"{sid}.json", spells.tip_from(s))
        if progress and n % 4000 == 0:
            print(f"  spells {n:6,} / {len(ids):,}   {time.time() - t0:5.0f}s")

    # items: navigation (SoD hidden / shown), one file per item type, search index, item pages and tooltips
    for sod in (0, 1):
        _write(api / f"items-{sod}.json", items.tree(bool(sod)))
    for cat in items.tree(True):
        for s in cat["subs"]:
            _write(api / "item-lists" / f"{cat['cls']}-{s['sub']}.json", [r[:7] + [items.INV_SHORT.get(r[9], "")] for r in items.list_rows(cat["cls"], s["sub"])])
    _write(api / "item-search.json", items.search_index())
    item_ids = [r["ID"] for r in db.q("select ID from ItemSparse where Display_lang != '' order by cast(ID as integer)")]
    for n, iid in enumerate(item_ids, 1):
        it = items.item(iid)
        if it:
            _write(api / "item" / f"{iid}.json", it)
            _write(api / "itip" / f"{iid}.json", items.tip_from(it))
        if progress and n % 5000 == 0:
            print(f"  items {n:6,} / {len(item_ids):,}   {time.time() - t0:5.0f}s")
    db.bulk(False)
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    files = sum(1 for f in out.rglob("*") if f.is_file())
    print(f"done: {files:,} files, {size / 1e6:.0f} MB in {time.time() - t0:.0f}s -> {out}")
