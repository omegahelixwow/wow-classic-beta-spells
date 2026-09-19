"""The class / racial / skills / unknown lists. SoD spells are filtered here (unless show_sod)."""
import re

from .db import conn, icons, q, scalar

CAT_ORDER = ["Class", "Racial", "Skills", "Test / Deprecated", "NPC / Unknown"]

RANK = re.compile(r"^Rank (\d+)$")
VIA_ID = re.compile(r" \(\d+\)$")
_rows_cache = {}


def raw_rows(cat, sub):
    """Every classified row of one list, SoD included, in display order. `origin` / `via_origin` let callers filter SoD."""
    key = (cat, sub)
    if key not in _rows_cache:
        _rows_cache[key] = q(
            "select c.SpellID id, n.Name_lang name, s.NameSubtext_lang subtext, c.Linked linked, c.Via via, o.Origin origin, "
            "coalesce((select v.Origin from SpellOrigin v where v.SpellID=c.ViaID), '') via_origin, "
            "(select SpellIconFileDataID from SpellMisc m where m.SpellID=c.SpellID limit 1) icon, "
            "(select SpellLevel from SpellLevels l where l.SpellID=c.SpellID limit 1) level, "
            "exists(select 1 from SpellMisc m where m.SpellID=c.SpellID and (cast(m.Attributes_0 as integer) & 64) != 0) passive "
            "from Classification c join SpellName n on n.ID=c.SpellID join SpellOrigin o on o.SpellID=c.SpellID "
            "left join Spell s on s.ID=c.SpellID where c.Cat=? and c.Sub=? "
            "order by c.Linked, c.Via, (n.Name_lang=''), n.Name_lang, cast(c.SpellID as integer)", (cat, sub))
    return _rows_cache[key]


def fold(rows, offset=0, limit=300):
    """One entry per ability: the ranks of a spell ("Rank 1".."Rank 11") are folded into a single entry that stands for
    the highest rank and carries `ranks` (count), `rankRange`, `levels` and `rankList`. Paging counts abilities, not spells.
    (web/static.js has a line-for-line port of this function for the static site -- keep them in step.)"""
    ic = icons()
    fams = {}                                            # family key -> members (dicts keep first-seen order)
    for r in rows:
        m = RANK.match(r["subtext"] or "")
        linked = bool(int(r["linked"]))
        # ranks of the same ability share a name and a home; linked ranks may come through different source ranks
        key = (r["name"], linked, VIA_ID.sub("", r["via"]) if linked else r["via"]) if m else (r["id"],)
        fams.setdefault(key, []).append((int(m.group(1)) if m else 0, int(r["level"] or 0), r))
    items = []
    for members in fams.values():
        members = sorted(members, key=lambda t: (t[0], int(t[2]["id"])))
        rank, level, r = members[-1]                      # the highest rank stands for the ability
        ranked = [t for t in members if t[0]]
        item = {"id": int(r["id"]), "name": r["name"], "subtext": r["subtext"] or "", "linked": bool(int(r["linked"])),
                "via": r["via"], "origin": r["origin"], "icon": ic.get(r["icon"] or ""), "level": r["level"],
                "passive": bool(int(r["passive"])), "ranks": len(ranked) if len(ranked) > 1 else 0}
        if item["ranks"]:
            item["rankRange"] = [ranked[0][0], ranked[-1][0]]
            item["levels"] = [min(t[1] for t in ranked), max(t[1] for t in ranked)]
            item["rankList"] = [{"id": int(t[2]["id"]), "rank": t[0], "level": t[1], "origin": t[2]["origin"]} for t in ranked]
        items.append(item)
    # An ability you cast often has same-named helper spells linked to it (the effect / aura spells that carry the numbers).
    # Listing them shows the ability twice, so a linked spell is dropped when a directly listed CASTABLE one has its name.
    # (A passive with a castable linked spell -- Touch of the Grave -- keeps both: the linked one is the real ability.)
    direct_castable = {it["name"] for it in items if not it["linked"] and not it["passive"]}
    items = [it for it in items if not (it["linked"] and it["name"] in direct_castable)]
    return {"total": len(items), "spells": len({r["id"] for r in rows}), "offset": offset, "items": items[offset:offset + limit]}


def _rank(r):
    m = RANK.match(r["subtext"] or "")
    return int(m.group(1)) if m else None


def _family(r):
    """Key shared by the ranks of one ability (None for a spell without "Rank N"); same key as fold() groups by."""
    if _rank(r) is None:
        return None
    linked = bool(int(r["linked"]))
    return (r["name"], linked, VIA_ID.sub("", r["via"]) if linked else r["via"])


def with_sod_ranks(all_rows, show_sod):
    """The rows to list. With SoD hidden, a SoD spell still fills a missing rank of an ability whose other ranks are shown
    (Frostfire Bolt: rank 1 is a SoD spell, ranks 2-3 are new in this beta) -- but never duplicates a rank that exists."""
    if show_sod:
        return all_rows
    taken = {}
    for r in all_rows:
        if visible(r, False) and _family(r):
            taken.setdefault(_family(r), set()).add(_rank(r))
    out = []
    for r in all_rows:
        if visible(r, False):
            out.append(r)
        elif r["origin"] == "sod" and _family(r) in taken and _rank(r) not in taken[_family(r)]:
            taken[_family(r)].add(_rank(r))
            out.append(r)
    return out


def visible(r, show_sod):
    """A row shows when SoD is on, or when neither the spell nor the spell it was linked through is SoD."""
    return show_sod or (r["origin"] != "sod" and r["via_origin"] != "sod")


def listing(cat, sub, text="", offset=0, limit=300, show_sod=False):
    rows = raw_rows(cat, sub)
    if text:
        t = text.lower()
        rows = [r for r in rows if t in (r["name"] or "").lower() or r["id"] == text]
    return fold(with_sod_ranks(rows, show_sod), offset, limit)


def tree(show_sod=False):
    """[{cat, count, subs: [{sub, count}]}] for the navigation."""
    sod = 1 if show_sod else 0
    BASE = ("from Classification c join SpellName n on n.ID=c.SpellID join SpellOrigin o on o.SpellID=c.SpellID "
            "where (? or (o.Origin != 'sod' and not exists "
            "(select 1 from SpellOrigin v where v.SpellID=c.ViaID and v.Origin='sod')))")
    subs, totals = {}, {}
    for r in q("select c.Cat cat, c.Sub sub, count(distinct c.SpellID) n " + BASE + " group by c.Cat, c.Sub", (sod,)):
        subs.setdefault(r["cat"], []).append({"sub": r["sub"], "count": r["n"]})
    for r in q("select c.Cat cat, count(distinct c.SpellID) n " + BASE + " group by c.Cat", (sod,)):
        totals[r["cat"]] = r["n"]
    return [{"cat": c, "count": totals[c], "subs": sorted(subs[c], key=lambda x: x["sub"])} for c in CAT_ORDER if c in subs]


def meta():
    """Build info + how many spells of each origin exist (for the header line)."""
    m = {r["key"]: r["value"] for r in q("select key, value from Meta")}
    m["origins"] = {r["o"]: r["n"] for r in q("select Origin o, count(*) n from SpellOrigin group by Origin")}
    return m
