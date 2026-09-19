"""How spells are linked to each other, in both directions.

  children (a spell "triggers / applies" them):
      * explicit  -- an effect names the spell (SpellEffect.EffectTriggerSpell): a trigger, a proc, a summon-like aura
      * duration  -- the text uses another spell's duration or period (`$17794d`): the referenced spell is the aura it applies.
                     Improved Shadow Bolt's proc is server logic; the client data only says "... for $17794d" (Shadow Vulnerability)
  parents (a spell is "triggered by" them): the reverse of both, plus
      * values    -- this spell's text takes numbers from another spell (`$1260189s1`): Touch of the Grave's active drain reads the
                     passive's 5%. The passive is what triggers it.

What a child does is shown as text, its effects, and what it affects: spells (class masks, see affects.py) or a damage school.
"""
import collections, re

from . import affects, descriptions
from .db import icon_of, num, q, rows, scalar
from .flags import label

SCHOOLS = {1: "Physical", 2: "Holy", 4: "Fire", 8: "Nature", 16: "Frost", 32: "Shadow", 64: "Arcane"}
# auras whose EffectMiscValue is a school mask, and which of them carry a percentage
SCHOOL_AURAS = {"13", "14", "22", "27", "39", "69", "74", "79", "87", "101", "118", "135", "142", "163", "270", "301"}
PERCENT_AURAS = {"79", "87", "101", "118", "142", "163", "270"}
REF = re.compile(r"\$(\d{3,})([a-zA-Z])")
DURATION_TOKENS = {"d", "t"}                        # $<id>d = duration, $<id>t = period: the referenced spell is applied by this one
MAX_CHILDREN, MAX_NESTED = 8, 4

_children = _parents = _sources = _users = _names = None


def _load():
    global _children, _parents, _sources, _users, _names
    if _children is not None:
        return
    _names = {r["ID"]: r["Name_lang"] for r in q("select ID, Name_lang from SpellName where Name_lang != ''")}
    _children, _sources = collections.defaultdict(list), collections.defaultdict(list)
    for r in q("select SpellID, EffectIndex, EffectTriggerSpell t from SpellEffect where EffectTriggerSpell not in ('', '0')"):
        if r["t"] != r["SpellID"] and r["t"] in _names:
            _children[r["SpellID"]].append((r["t"], f"effect {int(r['EffectIndex']) + 1} triggers it"))
    for r in q("select ID, Description_lang d, AuraDescription_lang a from Spell"):
        for ref, tok in REF.findall((r["d"] or "") + " " + (r["a"] or "")):
            if ref == r["ID"] or ref not in _names:
                continue
            if tok in DURATION_TOKENS:
                _children[r["ID"]].append((ref, "its text uses this spell's duration (it applies it)"))
            else:
                _sources[r["ID"]].append((ref, "its text takes numbers from this spell"))
    _users = collections.defaultdict(list)                          # spell -> spells whose text takes numbers from it
    for user, srcs in _sources.items():
        for src, _why in srcs:
            _users[src].append(user)
    _parents = collections.defaultdict(list)
    for parent, kids in _children.items():
        for kid, why in kids:
            _parents[kid].append((parent, why.replace("effect", "its effect").replace("triggers it", "triggers this spell")
                                  if why.startswith("effect") else "its text uses this spell's duration (it applies this spell)"))


def _unique(pairs, skip=()):
    seen, out = set(skip), []
    for sid, why in pairs:
        if sid not in seen:
            seen.add(sid)
            out.append((sid, why))
    return out


def _school_text(mask):
    if mask & 127 == 127:
        return "all schools"
    if mask & 126 == 126:
        return "all magic schools"
    return "/".join(n for b, n in SCHOOLS.items() if mask & b) or "no school"


def effect_brief(sid, e):
    """One effect as a short line: {effect, aura, detail}. detail says what it changes and by how much."""
    aura = e.get("EffectAura") or "0"
    value = descriptions.effect_value(sid, e)
    detail = None
    if aura in affects.MODIFIER_AURAS:                              # a class-mask modifier: cast time -0.1 sec ...
        op = label("SpellModOp", int(num(e.get("EffectMiscValue_0"))))
        detail = f"{affects.OP_NAMES.get(op, op)} {affects._value_text(aura, op, value)}"
    elif aura in SCHOOL_AURAS:                                      # a school-based aura: Shadow +4% ...
        v = f"{value:+g}%" if aura in PERCENT_AURAS else f"{value:+g}"
        detail = f"{_school_text(int(num(e.get('EffectMiscValue_0'))))}: {v}"
    elif value:
        detail = f"{value:+g}"
    return {"effect": label("SpellEffects", int(num(e.get("Effect")))), "aura": label("AuraType", int(num(aura))) if aura != "0" else None,
            "detail": detail}


def _brief(cid, why, depth, seen):
    sp = rows("Spell", "ID", cid)[0] if rows("Spell", "ID", cid) else {}
    text = descriptions.render(sp.get("AuraDescription_lang") or sp.get("Description_lang") or "", cid)
    effs = [effect_brief(cid, e) for e in sorted(rows("SpellEffect", "SpellID", cid), key=lambda e: int(e.get("EffectIndex") or 0))]
    item = {"id": int(cid), "name": _names.get(cid, cid), "subtext": sp.get("NameSubtext_lang") or "",
            "origin": scalar("select Origin from SpellOrigin where SpellID=?", (cid,)) or "new", "icon": icon_of(cid),
            "why": why, "text": text, "effects": [x for x in effs if x["aura"] or x["detail"]][:5], "affects": affects.affected(cid)}
    if depth < 1:                                                    # one more level: what the child in turn applies
        seen = seen | {cid}
        item["children"] = [_brief(k, w, depth + 1, seen) for k, w in _unique(_children.get(cid, ()), seen)[:MAX_NESTED]]
    else:
        item["children"] = []
    return item


def triggers(sid):
    """Spells this one triggers or applies, each with its effects and what it affects (one nested level)."""
    _load()
    sid = str(sid)
    return [_brief(k, w, 0, {sid}) for k, w in _unique(_children.get(sid, ()), {sid})[:MAX_CHILDREN]]


def triggered_by(sid):
    """Spells that trigger / apply this one, and spells whose numbers this one takes: [{id, name, origin, icon, why}]."""
    _load()
    sid = str(sid)
    pairs = _unique(list(_parents.get(sid, ())) + list(_sources.get(sid, ())), {sid})[:MAX_CHILDREN * 2]
    return [{"id": int(p), "name": _names.get(p, p), "why": why, "icon": icon_of(p),
             "origin": scalar("select Origin from SpellOrigin where SpellID=?", (p,)) or "new"} for p, why in pairs]


def used_by(sid, limit=12):
    """Spells that read this one's numbers -- the castable spell behind a passive proc, or the spell a talent modifies:
    [{name, members: [{id, rank, origin}]}], grouped by name so the ranks of one spell make one entry."""
    _load()
    sid = str(sid)
    by_name = collections.defaultdict(list)
    for u in dict.fromkeys(_users.get(sid, ())):
        if u == sid:
            continue
        r = rows("Spell", "ID", u)
        m = re.match(r"^Rank (\d+)$", (r[0].get("NameSubtext_lang") if r else "") or "")
        by_name[_names.get(u, u)].append({"id": int(u), "rank": int(m.group(1)) if m else 0,
                                          "origin": scalar("select Origin from SpellOrigin where SpellID=?", (u,)) or "new"})
    return [{"name": n, "members": sorted(m, key=lambda x: (x["rank"], x["id"]))} for n, m in sorted(by_name.items())][:limit]


def applies(sid, limit=3):
    """Short lines for a talent tooltip: the auras this spell applies, [{name, text, origin}]."""
    out = []
    for c in triggers(sid):
        if c["text"] or c["effects"]:
            text = c["text"] or "; ".join(f"{x['aura'] or x['effect']} {x['detail'] or ''}".strip() for x in c["effects"][:2])
            out.append({"name": c["name"], "text": text[:160], "origin": c["origin"]})
    return out[:limit]
