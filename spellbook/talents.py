"""Talent trees, from the retail (Trait*) data model.

    TraitTree -> TraitNode (position, gating groups) -> TraitNodeEntry -> TraitDefinition (the spell)
    TraitEdge            = prerequisites between nodes
    TraitNodeGroup*/Cond = "spend N points in group G" row gates
    TraitDefinitionEffectPoints + Curve/CurvePoint = per-rank values of a talent's effects

Only the class trees are built (tree currency 3820, ~50 nodes, 3 tabs); the partial / general trees in the data are ignored.
"""
import collections

from . import descriptions
from .db import class_names, classes, icons, num, q, q1, scalar

NODE_TYPES = {0: "Single", 1: "Tiered", 2: "Choice"}
SHAPES = {0: "hex", 1: "square", 2: "circle", 3: "small circle", 6: "diamond"}      # TraitNodeEntry.NodeEntryType
EDGE_TYPES = {0: "visual only", 1: "rank connection", 2: "sufficient", 3: "required", 4: "mutually exclusive"}
CLASS_TREE_CURRENCY = "3820"      # the currency that funds class talents (51 points, levels 10-60)
TAB_GAP = 1400                    # PosX gap that separates one spec column from the next
TAB_ALIASES = {"Elemental Combat": "Elemental", "Shadow Magic": "Shadow"}        # skill line name -> classic tab name
IGNORE_LINES = {"Engraving", "Runes", "Pet - Generic", "Beast Training"}

_cache = {}


def cluster(values, gap):
    """Unique values -> {value: 1-based cluster}; values within `gap` of their neighbour share a cluster."""
    out, idx, prev = {}, 0, None
    for v in sorted(set(values)):
        if prev is None or v - prev > gap:
            idx += 1
        out[v], prev = idx, v
    return out


def curve_at(curve_id, x):
    pts = sorted((num(p["Pos_0"]), num(p["Pos_1"])) for p in q("select Pos_0, Pos_1 from CurvePoint where CurveID=?", (curve_id,)))
    if not pts:
        return None
    for px, py in pts:
        if px == x:
            return py
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 < x < x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def spell_classes():
    """spell id -> class names, straight from SkillLineAbility.ClassMask."""
    m = collections.defaultdict(set)
    for r in q("select Spell, ClassMask from SkillLineAbility where cast(ClassMask as integer) > 0"):
        m[r["Spell"]].update(class_names(int(r["ClassMask"])))
    return m


def index():
    """The class trees: [{id, class, nodes, points}]."""
    if "index" in _cache:
        return _cache["index"]
    cur_of = collections.defaultdict(list)
    for r in q("select TraitTreeID, TraitCurrencyID from TraitTreeXTraitCurrency"):
        cur_of[r["TraitTreeID"]].append(r["TraitCurrencyID"])
    curmax = {r["ID"]: int(num(r["SourcedMax"])) for r in q("select ID, SourcedMax from TraitCurrency")}
    cls = spell_classes()
    out = []
    for t in q("select ID from TraitTree order by cast(ID as integer)"):
        n_nodes = scalar("select count(*) from TraitNode where TraitTreeID=?", (t["ID"],))
        spells = [r["SpellID"] for r in q(
            "select d.SpellID from TraitNode n join TraitNodeXTraitNodeEntry x on x.TraitNodeID=n.ID "
            "join TraitNodeEntry e on e.ID=x.TraitNodeEntryID join TraitDefinition d on d.ID=e.TraitDefinitionID "
            "where n.TraitTreeID=?", (t["ID"],))]
        votes = collections.Counter(c for s in spells for c in cls.get(s, ()))
        if votes and CLASS_TREE_CURRENCY in cur_of[t["ID"]] and n_nodes >= 40:
            out.append({"id": int(t["ID"]), "class": votes.most_common(1)[0][0], "nodes": n_nodes,
                        "points": sum(curmax.get(c, 0) for c in cur_of[t["ID"]])})
    _cache["index"] = out
    return out


def entries_by_class():
    """{class name: [(spell id, talent name)]} -- cheap version of tree() used by the classifier."""
    out = collections.defaultdict(list)
    for info in index():
        for r in q("select d.SpellID sid, d.OverrideName_lang oname, (select Name_lang from SpellName where ID=d.SpellID) name "
                   "from TraitNode n join TraitNodeXTraitNodeEntry x on x.TraitNodeID=n.ID "
                   "join TraitNodeEntry e on e.ID=x.TraitNodeEntryID join TraitDefinition d on d.ID=e.TraitDefinitionID "
                   "where n.TraitTreeID=?", (str(info["id"]),)):
            out[info["class"]].append((r["sid"], r["oname"] or r["name"] or ""))
    return out


def tree(tree_id):
    tree_id = str(tree_id)
    if tree_id in _cache:
        return _cache[tree_id]
    info = next((t for t in index() if str(t["id"]) == tree_id), None)
    if not info:
        return None

    nodes = q("select * from TraitNode where TraitTreeID=?", (tree_id,))
    ids = {n["ID"] for n in nodes}

    # ---- node -> entries (one for single nodes, several for choice nodes) ----
    ent = collections.defaultdict(list)
    for r in q("select x.TraitNodeID nid, x._Index idx, e.ID eid, e.MaxRanks, e.NodeEntryType, d.ID did, d.SpellID, "
               "d.OverrideName_lang oname, d.OverrideDescription_lang odesc, d.OverrideIcon oicon "
               "from TraitNodeXTraitNodeEntry x join TraitNodeEntry e on e.ID=x.TraitNodeEntryID "
               "join TraitDefinition d on d.ID=e.TraitDefinitionID "
               "where x.TraitNodeID in (select ID from TraitNode where TraitTreeID=?)", (tree_id,)):
        ent[r["nid"]].append(r)

    # ---- positions. A few nodes carry coordinates 10x too large (data slips): kept, but off the grid ----
    for n in nodes:
        n["_x"], n["_y"] = int(num(n["PosX"])), int(num(n["PosY"]))
        n["_off"] = n["_x"] > 20000 or n["_y"] > 20000
        n["_gx"] = n["_x"] // 10 if n["_x"] > 20000 else n["_x"]          # x used to pick the tab
    grid = [n for n in nodes if not n["_off"]]

    # ---- tabs = columns of nodes separated by a wide X gap; rows / columns tolerate small jitter ----
    xs = sorted({n["_x"] for n in grid})
    bounds, start = [], 0
    for i in range(1, len(xs) + 1):
        if i == len(xs) or xs[i] - xs[i - 1] > TAB_GAP:
            bounds.append((xs[start], xs[i - 1]))
            start = i

    def tab_of_x(x):
        return next((i for i, (a, b) in enumerate(bounds) if a - 400 <= x <= b + 400), 0)

    row_of_y = cluster((n["_y"] for n in grid), 300)
    col_of_x = [cluster((x for x in xs if a <= x <= b), 150) for a, b in bounds]

    # ---- tab names: the skill line most of the tab's talent spells belong to ----
    sla = collections.defaultdict(list)
    for r in q("select Spell, SkillLine from SkillLineAbility"):
        sla[r["Spell"]].append(r["SkillLine"])
    from .db import skills
    votes = [collections.Counter() for _ in bounds]
    for n in nodes:
        for e in ent[n["ID"]]:
            for line in sla.get(e["SpellID"], []):
                name = skills().get(line, "")
                if name and name not in IGNORE_LINES:
                    votes[tab_of_x(n["_gx"])][name] += 1
    tab_names = [TAB_ALIASES.get(v.most_common(1)[0][0], v.most_common(1)[0][0]) if v else f"Tab {i + 1}"
                 for i, v in enumerate(votes)]

    # ---- row gates: "spend N points in group G" ----
    members, node_groups = collections.defaultdict(set), collections.defaultdict(list)
    for r in q("select TraitNodeGroupID g, TraitNodeID n from TraitNodeGroupXTraitNode "
               "where TraitNodeID in (select ID from TraitNode where TraitTreeID=?)", (tree_id,)):
        members[r["g"]].add(r["n"])
        node_groups[r["n"]].append(r["g"])
    gate_of_group = collections.defaultdict(list)
    for r in q("select gc.TraitNodeGroupID g, c.TraitNodeGroupID cg, c.SpentAmountRequired need "
               "from TraitNodeGroupXTraitCond gc join TraitCond c on c.ID=gc.TraitCondID where c.TraitTreeID=?", (tree_id,)):
        if int(num(r["need"])) > 0:
            gate_of_group[r["g"]].append((r["cg"], int(num(r["need"]))))

    # ---- edges = prerequisites (left node must be maxed before the right node can be spent in) ----
    prereq = collections.defaultdict(list)
    for r in q("select * from TraitEdge where LeftTraitNodeID in (select ID from TraitNode where TraitTreeID=?)", (tree_id,)):
        prereq[r["RightTraitNodeID"]].append({"node": int(r["LeftTraitNodeID"]), "type": int(r["Type"]),
                                              "kind": EDGE_TYPES.get(int(r["Type"]), f"type {r['Type']}")})

    row_by_node = {n["ID"]: row_of_y[n["_y"]] for n in grid}
    tab_size = collections.Counter(tab_of_x(n["_gx"]) for n in grid)
    out_nodes = []
    for n in sorted(nodes, key=lambda n: (n["_off"], n["_y"], n["_x"])):
        tab = tab_of_x(n["_gx"])
        gates = []
        for g in node_groups[n["ID"]]:
            for cg, need in gate_of_group.get(g, []):
                mem = sorted(int(i) for i in members.get(cg, ()) if i in ids)
                rows_in = sorted({row_by_node[str(i)] for i in mem if str(i) in row_by_node})
                where = ""
                if mem and len(mem) < 0.8 * tab_size[tab]:                # a slice of the tab, not the whole tab
                    where = f" (row {rows_in[0]}" + (f"–{rows_in[-1]}" if len(rows_in) > 1 else "") + ")"
                gates.append({"points": need, "group": int(cg), "nodes": mem, "text": f"{need} points in {tab_names[tab]}{where}"})
        out_nodes.append({
            "id": int(n["ID"]), "tab": tab, "row": None if n["_off"] else row_of_y[n["_y"]],
            "col": None if n["_off"] else col_of_x[tab][n["_x"]], "offGrid": n["_off"],
            "x": n["_x"], "y": n["_y"], "type": NODE_TYPES.get(int(num(n["Type"])), f"type {n['Type']}"),
            "flags": int(num(n["Flags"])), "gates": gates, "prereqs": prereq.get(n["ID"], []),
            "entries": [_entry(e) for e in sorted(ent[n["ID"]], key=lambda e: int(num(e["idx"])))],
        })
    rows_total = max(row_of_y.values())
    res = dict(info, title=f"{info['class']} Talents", rows=rows_total, nodes_list=out_nodes,
               tabs=[{"index": i, "name": nm, "cols": max(col_of_x[i].values()), "x": bounds[i]} for i, nm in enumerate(tab_names)])
    _cache[tree_id] = res
    return res


def _entry(e):
    sid, ranks = e["SpellID"], int(num(e["MaxRanks"]))
    name = e["oname"] or scalar("select Name_lang from SpellName where ID=?", (sid,)) or f"Spell {sid}"
    raw = e["odesc"] or scalar("select Description_lang from Spell where ID=?", (sid,)) or ""
    icon = icons().get(e["oicon"]) if num(e["oicon"]) else None
    if not icon:
        r = q1("select SpellIconFileDataID i from SpellMisc where SpellID=? limit 1", (sid,))
        icon = icons().get(r["i"]) if r else None
    eff_pts = q("select EffectIndex, CurveID from TraitDefinitionEffectPoints where TraitDefinitionID=?", (e["did"],))
    texts = []
    for rank in range(1, max(ranks, 1) + 1):
        ov = {}
        for p in eff_pts:
            v = curve_at(p["CurveID"], rank)
            if v is not None:
                ov[int(num(p["EffectIndex"])) + 1] = v
        texts.append(descriptions.render(raw, sid, 0, ov or None))
    return {"entryId": int(e["eid"]), "spell": int(sid), "name": name, "maxRanks": ranks,
            "shape": SHAPES.get(int(num(e["NodeEntryType"])), f"type {e['NodeEntryType']}"),
            "icon": icon, "ranks": texts, "scaled": bool(eff_pts), "origin": origin_of(sid)}


def origin_of(sid):
    return scalar("select Origin from SpellOrigin where SpellID=?", (str(sid),)) or "new"


def spell_talents():
    """spell id -> [{tree, node, title, tab, row, maxRanks}] for the spell page."""
    if "by_spell" in _cache:
        return _cache["by_spell"]
    m = collections.defaultdict(list)
    for info in index():
        t = tree(info["id"])
        for n in t["nodes_list"]:
            for e in n["entries"]:
                m[str(e["spell"])].append({"tree": info["id"], "node": n["id"], "title": t["title"],
                                           "tab": t["tabs"][n["tab"]]["name"], "row": n["row"], "maxRanks": e["maxRanks"]})
    _cache["by_spell"] = m
    return m
