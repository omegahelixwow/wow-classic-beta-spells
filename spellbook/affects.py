"""Which spells does a spell (typically a talent) modify?

The game decides with class masks: a modifier aura's effect carries EffectSpellClassMask (4 x 32 bits), and it applies to every
spell of the same class family (SpellClassOptions.SpellClassSet) whose own SpellClassMask shares at least one bit with it.
Improved Frostbolt: mask 32 in class set 3 (Mage) -> every Frostbolt rank, since their class mask has bit 32.
"""
import collections, re

from .db import first, num, q, rows
from .flags import label

U32 = 0xFFFFFFFF
MODIFIER_AURAS = {"107": "flat", "108": "percent"}          # ADD_FLAT_MODIFIER / ADD_PCT_MODIFIER: EffectMiscValue_0 is a SpellModOp
MS_OPS = {"Duration", "ChangeCastTime", "Cooldown", "Period", "StartCooldown", "ProcCooldown", "Amplitude"}   # values stored in ms
OP_NAMES = {
    "HealingAndDamage": "Damage / healing", "PeriodicHealingAndDamage": "Periodic damage / healing", "ChangeCastTime": "Cast time",
    "PowerCost0": "Power cost", "PowerCost1": "Power cost", "PowerCost2": "Power cost", "CritChance": "Crit chance",
    "CritDamageAndHealing": "Crit damage / healing", "Points": "Effect value", "PointsIndex0": "Effect 1 value",
    "PointsIndex1": "Effect 2 value", "PointsIndex2": "Effect 3 value", "PointsIndex3": "Effect 4 value", "PointsIndex4": "Effect 5 value",
    "ResistPushback": "Pushback resistance", "TargetResistance": "Target resistance", "ProcChance": "Proc chance",
    "ProcCharges": "Proc charges", "ProcCooldown": "Proc cooldown", "ProcFrequency": "Proc frequency", "ChainTargets": "Chain targets",
    "MaxTargets": "Max targets", "MaxAuraStacks": "Max stacks", "BonusCoefficient": "Spell power coefficient", "Hate": "Threat",
    "DispelResistance": "Dispel resistance", "HitChance": "Hit chance", "StartCooldown": "Starting cooldown", "Doses": "Charges",
}
_index = _info = None


def _mask(row, prefix):
    return [int(num(row.get(f"{prefix}_{i}"))) & U32 for i in range(4)]


def _load():
    """One-time: spells with a class mask, by class family, and the facts needed to present a match."""
    global _index, _info
    if _index is not None:
        return
    _index = collections.defaultdict(list)
    for r in q("select SpellID, SpellClassSet s, SpellClassMask_0, SpellClassMask_1, SpellClassMask_2, SpellClassMask_3 from SpellClassOptions"):
        m = _mask(r, "SpellClassMask")
        if any(m):
            _index[r["s"]].append((r["SpellID"], m))
    # only spells that appear in a class list count as "affected" (not NPC copies, test spells or hidden helper spells)
    _info = {r["id"]: r for r in q(
        "select n.ID id, n.Name_lang name, s.NameSubtext_lang sub, o.Origin origin from SpellName n join Spell s on s.ID=n.ID "
        "join SpellOrigin o on o.SpellID=n.ID where n.Name_lang != '' and exists "
        "(select 1 from Classification c where c.SpellID=n.ID and c.Cat='Class')")}


def _value_text(aura, op, value):
    if aura == "108":
        return f"{value:+g}%"
    if op in MS_OPS:
        return f"{value / 1000:+g} sec"
    return f"{value:+g}"


def affected(sid):
    """[{effect, aura, op, value, spells: [{name, members: [{id, rank, origin}]}]}] -- one entry per effect that has a class mask.
    Members carry their origin so the page can hide Season of Discovery spells without asking again."""
    _load()
    sid = str(sid)
    cset = first("SpellClassOptions", "SpellID", sid).get("SpellClassSet")
    if cset in (None, "", "0"):
        return []
    out = []
    for e in sorted(rows("SpellEffect", "SpellID", sid), key=lambda e: int(e.get("EffectIndex") or 0)):
        em = _mask(e, "EffectSpellClassMask")
        if not any(em):
            continue
        by_name = collections.defaultdict(list)
        for target, m in _index.get(cset, ()):
            if target != sid and target in _info and any(m[i] & em[i] for i in range(4)):
                t = _info[target]
                mm = re.match(r"^Rank (\d+)$", t["sub"] or "")
                by_name[t["name"]].append({"id": int(target), "rank": int(mm.group(1)) if mm else 0, "origin": t["origin"]})
        if not by_name:
            continue
        aura = e.get("EffectAura")
        op = None
        value_text = None
        if aura in MODIFIER_AURAS:
            op_key = label("SpellModOp", int(num(e.get("EffectMiscValue_0"))))
            op = OP_NAMES.get(op_key) or re.sub(r"(?<=[a-z])(?=[A-Z])", " ", op_key).capitalize()
            value_text = _value_text(aura, op_key, num(e.get("EffectBasePointsF")))
        out.append({
            "effect": int(e.get("EffectIndex") or 0) + 1, "aura": label("AuraType", int(num(aura))), "op": op, "value": value_text,
            "spells": [{"name": n, "members": sorted(m, key=lambda x: (x["rank"], x["id"]))} for n, m in sorted(by_name.items())],
        })
    return out


def names(sid, limit=14):
    """Just the distinct affected spell names, for a compact tooltip line: [{name, origin}] (origin 'sod' when only SoD spells match)."""
    seen = {}
    for g in affected(sid):
        for s in g["spells"]:
            sod_only = all(m["origin"] == "sod" for m in s["members"])
            seen[s["name"]] = "sod" if sod_only and seen.get(s["name"], "sod") == "sod" else "other"
    return [{"name": n, "origin": o} for n, o in list(seen.items())[:limit * 4]]
