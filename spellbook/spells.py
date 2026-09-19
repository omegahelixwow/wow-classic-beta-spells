"""Everything about one spell: the full detail page, the hover tooltip summary, and name / id search."""
import re

from . import affects, descriptions, links, talents
from .db import (class_names, columns, conn, first, fmt_ms, icon_of, nz, num, one, q, races, rows, scalar,
                 skills)
from .flags import decode, label

SCHOOLS = {1: "Physical", 2: "Holy", 4: "Fire", 8: "Nature", 16: "Frost", 32: "Shadow", 64: "Arcane"}
POWER = {0: "Mana", 1: "Rage", 2: "Focus", 3: "Energy", 4: "Combo Points", 6: "Runic Power"}
PERIODIC_RE = re.compile(r"PERIOD|TICK|HASTE_AFFECTS|DOT|HOT", re.I)
PROC_RE = re.compile(r"PROC", re.I)
ORIGIN_NOTE = {
    "vanilla": "Existed in Classic Era before Season of Discovery.",
    "sod": "Added by Season of Discovery (first appears in the SoD-era client).",
    "new": "Introduced by this beta; not in any Classic Era client.",
}
SEARCH_HIDDEN = ("engraving", "form-only", "orphan", "helper")          # hidden reasons that search also skips (talents stay searchable)


RANK_RE = re.compile(r"^Rank (\d+)$")


def ranks(sid, show_sod=False):
    """All ranks of the ability `sid` belongs to: same name, "Rank N" text, and the same home in the browser
    (so NPC / effect spells that happen to share the name are not mixed in). [] when it has a single rank."""
    sid = str(sid)
    sp = one("Spell", sid) or {}
    if not RANK_RE.match(sp.get("NameSubtext_lang", "")):
        return []
    name = scalar("select Name_lang from SpellName where ID=?", (sid,))
    cands = q("select n.ID id, s.NameSubtext_lang sub, o.Origin origin, "
              "(select SpellLevel from SpellLevels l where l.SpellID=n.ID limit 1) level "
              "from SpellName n join Spell s on s.ID=n.ID join SpellOrigin o on o.SpellID=n.ID "
              "where n.Name_lang=? and s.NameSubtext_lang like 'Rank %'", (name,))
    cands = [c for c in cands if RANK_RE.match(c["sub"])]                # "Rank 3" only, not e.g. "Rank Passive"
    # same home = same list AND the same kind of entry (a direct spell, or one linked in through another spell): the helper /
    # learn spells linked to a rank share its name and text but are not ranks themselves
    homes = {(r["Cat"], r["Sub"], r["Linked"]) for r in q("select Cat, Sub, Linked from Classification where SpellID=?", (sid,))}
    if homes:
        marks = ",".join("?" * len(cands))
        home_of = {}
        for r in q(f"select SpellID, Cat, Sub, Linked from Classification where SpellID in ({marks})", [c["id"] for c in cands]):
            home_of.setdefault(r["SpellID"], set()).add((r["Cat"], r["Sub"], r["Linked"]))
        cands = [c for c in cands if home_of.get(c["id"], set()) & homes]
    me = origin_of(sid)
    out = [{"id": int(c["id"]), "rank": int(RANK_RE.match(c["sub"]).group(1)), "level": int(c["level"] or 0), "origin": c["origin"],
            "current": c["id"] == sid} for c in cands]
    out.sort(key=lambda r: (r["rank"], r["id"]))
    if not show_sod and me != "sod":
        # with SoD hidden a SoD spell still fills a rank number that no other spell has (Frostfire Bolt rank 1)
        kept, taken = [r for r in out if r["origin"] != "sod"], set()
        taken = {r["rank"] for r in kept}
        for r in out:
            if r["origin"] == "sod" and r["rank"] not in taken:
                taken.add(r["rank"])
                kept.append(r)
        out = sorted(kept, key=lambda r: (r["rank"], r["id"]))
    return out if len(out) > 1 else []


def origin_of(sid):
    return scalar("select Origin from SpellOrigin where SpellID=?", (str(sid),)) or "new"


# ---------------------------------------------------------------- pieces of the detail page
def _scaling(sid, e, duration_ms):
    """What a player wants to know about one effect: its value at level 60, the damage range, spell-power / attack-power
    coefficients, and for periodic effects the per-tick and total figures (ticks = duration / period).
    EffectBonusCoefficient is per tick on a periodic effect, so the total is coefficient x ticks."""
    value = descriptions.effect_value(sid, e)          # from the row itself: an effect's position in the list can differ from its index
    period = int(num(e.get("EffectAuraPeriod")))
    variance = num(e.get("Variance"))
    sp, ap = round(num(e.get("EffectBonusCoefficient")), 4), round(num(e.get("BonusCoefficientFromAP")), 4)
    out = {"value": value, "periodic": period > 0, "range": None, "period": None, "ticks": None,
           "perTick": None, "total": None, "sp": sp or None, "ap": ap or None, "spTotal": None, "apTotal": None}
    if period > 0:
        ticks = round(duration_ms / period) if duration_ms > 0 else 0
        out.update(period=period / 1000, ticks=ticks or None, perTick=value, total=value * ticks if ticks else None,
                   spTotal=sp * ticks if sp and ticks else None, apTotal=ap * ticks if ap and ticks else None)
    elif variance and value:
        out["range"] = [round(value * (1 - variance / 2)), round(value * (1 + variance / 2))]
    return out


def _effects(sid, effects, duration_ms):
    out = []
    for e in effects:
        eid, aid = int(e.get("Effect") or 0), int(e.get("EffectAura") or 0)
        out.append({
            "index": int(e.get("EffectIndex", 0)) + 1,
            "effect": f"{label('SpellEffects', eid)} ({eid})",
            "aura": f"{label('AuraType', aid)} ({aid})" if aid else None,
            "auraPeriod(ms)": e.get("EffectAuraPeriod"),
            "effectAttributes": decode("SpellEffectAttributes", e.get("EffectAttributes")),
            "mechanic": label("Mechanics", e["EffectMechanic"]) if int(e.get("EffectMechanic") or 0) else None,
            "basePoints": e.get("EffectBasePointsF"),
            "scaling": _scaling(sid, e, duration_ms),
            "amplitude(ms)": e.get("EffectAmplitude"),
            "targets": [label("Targets", e[f"ImplicitTarget_{i}"]) for i in (0, 1) if int(e.get(f"ImplicitTarget_{i}") or 0)],
            "triggerSpell": e.get("EffectTriggerSpell"),
            "misc": [e.get(f"EffectMiscValue_{i}") for i in (0, 1)],
            "raw": nz(e),
        })
    return out


def _proc(aura):
    ptm, ptm2 = int(aura.get("ProcTypeMask_0") or 0), int(aura.get("ProcTypeMask_1") or 0)
    if not (ptm or ptm2):
        return None
    return {"chance": num(aura.get("ProcChance")), "cooldown": fmt_ms(aura.get("ProcCategoryRecovery")),
            "charges": aura.get("ProcCharges"), "ppmID": aura.get("SpellProcsPerMinuteID"),
            "triggers": decode("ProcFlags", ptm), "triggers2": decode("ProcFlags2", ptm2)}


def _proc_notes(proc, aura, attr_names):
    if not proc:
        return ["No SpellAuraOptions row: a flat passive/effect, not a proc."] if not aura else \
               ["No proc flags set: this aura does not trigger on combat events."]
    notes = ["CAN_PROC_FROM_PROCS is set: this can be triggered by an event that was itself a proc."
             if "CAN_PROC_FROM_PROCS" in attr_names else
             "CAN_PROC_FROM_PROCS is NOT set: it can only be triggered by a real cast or swing, not by another proc."]
    ticks = {x["name"] for x in proc["triggers"]} & {"DEAL_HARMFUL_PERIODIC", "DEAL_HELPFUL_PERIODIC"}
    notes.append("Your own periodic ticks can trigger it (" + ", ".join(sorted(ticks)) + ")." if ticks
                 else "Your own periodic ticks (DoT/HoT) cannot trigger it.")
    notes.append(f"Internal cooldown {proc['cooldown']}: at most one proc per that interval." if proc["cooldown"]
                 else "No internal cooldown: limited only by the chance.")
    ppm = aura.get("SpellProcsPerMinuteID")
    notes.append("Flat chance (no procs-per-minute rate)." if ppm in (None, "", "0") else f"Uses procs-per-minute rate #{ppm}.")
    return notes


def _attributes(misc):
    attrs = {}
    for i in range(17):
        d = decode(f"SpellAttr{i}", misc.get(f"Attributes_{i}"))
        if d:
            attrs[f"SpellAttr{i}"] = d
    return attrs


def _flags(sid, attrs, misc):
    flat = [dict(x, group=g) for g, xs in attrs.items() for x in xs]
    intr = first("SpellInterrupts", "SpellID", sid)

    def with2(f1, f2, mask1, mask2):
        return decode(f1, mask1) + [dict(x, name=x["name"] + " (2)") for x in decode(f2, mask2)]
    return {
        "periodic": [x for x in flat if PERIODIC_RE.search(x["name"])],
        "proc": [x for x in flat if PROC_RE.search(x["name"])],
        "interrupt": decode("SpellInterruptFlags", intr.get("InterruptFlags")),
        "auraInterrupt": with2("SpellAuraInterruptFlags", "SpellAuraInterruptFlags2", intr.get("AuraInterruptFlags_0"), intr.get("AuraInterruptFlags_1")),
        "channelInterrupt": with2("SpellAuraInterruptFlags", "SpellAuraInterruptFlags2", intr.get("ChannelInterruptFlags_0"), intr.get("ChannelInterruptFlags_1")),
        "targets": decode("SpellCastTargetFlags", first("SpellTargetRestrictions", "SpellID", sid).get("Targets")),
    }


def _learn(sid):
    out = []
    for r in rows("SkillLineAbility", "Spell", sid):
        cm, rm = int(r.get("ClassMask") or 0), int(r.get("RaceMasks_0") or 0)
        out.append({"skill": skills().get(r["SkillLine"], r["SkillLine"]),
                    "classes": class_names(cm) if cm > 0 else [],
                    "races": [n for i, n in races().items() if rm & (1 << (i - 1))] if rm > 0 else [],
                    "supercedes": r.get("SupercedesSpell") if r.get("SupercedesSpell") not in (None, "", "0") else None})
    return out


def _costs(sid):
    costs = []
    for p in sorted(rows("SpellPower", "SpellID", sid), key=lambda r: int(r["OrderIndex"] or 0)):
        pt = POWER.get(int(p["PowerType"] or 0), f"Power {p['PowerType']}")
        if num(p["ManaCost"]):
            costs.append(f"{p['ManaCost']} {pt}")
        if num(p["PowerCostPct"]):
            costs.append(f"{p['PowerCostPct']}% of base {pt}")
        if num(p["ManaPerSecond"]):
            costs.append(f"{p['ManaPerSecond']} {pt}/sec")
    return costs


_refs = None


def referenced_by(sid, limit=12):
    """Spells whose text mentions this one ($<id>s1 ...). Built once from all descriptions instead of scanning per call."""
    global _refs
    if _refs is None:
        _refs = {}
        for r in q("select ID, Description_lang d, AuraDescription_lang a from Spell"):
            for m in set(re.findall(r"\$(\d{3,})[a-zA-Z]", (r["d"] or "") + " " + (r["a"] or ""))):
                _refs.setdefault(m, []).append(r["ID"])
    return [i for i in _refs.get(str(sid), []) if i != str(sid)][:limit]


def _link_ids(sid):
    """Ids already shown as triggered / triggering spells, so "Related spells" does not repeat them."""
    ids = {str(c["id"]) for c in links.triggers(sid)} | {str(p["id"]) for p in links.triggered_by(sid)}
    for u in links.used_by(sid):
        ids |= {str(m["id"]) for m in u["members"]}
    return ids


def _related(sid, name, effects, sp, show_sod, skip=()):
    """Spells linked to this one: triggered by an effect, mentioned in the text, mentioning this one, or same-name labelled."""
    rel = {}

    def add(i, why):
        i = str(i)
        if not i or i == "0" or i == sid or i in rel or i in skip:
            return
        n = one("SpellName", i)
        if n and (show_sod or origin_of(i) != "sod"):
            rel[i] = {"id": int(i), "name": n["Name_lang"], "why": why, "icon": icon_of(i), "origin": origin_of(i)}
    for e in effects:
        add(e.get("EffectTriggerSpell"), "triggered by an effect")
    for i in re.findall(r"\$(\d{3,})[a-zA-Z]", sp.get("Description_lang", "") + " " + sp.get("AuraDescription_lang", "")):
        add(i, "referenced in the description")
    for i in referenced_by(sid):
        add(i, "references this spell in its description")
    for r in rows("SpellLabel", "SpellID", sid):
        for x in q("select l.SpellID from SpellLabel l join SpellName n on n.ID=l.SpellID where l.LabelID=? and n.Name_lang=? limit 12",
                   (r["LabelID"], name)):
            add(x["SpellID"], f"same name, shares label {r['LabelID']}")
    return list(rel.values())


_spell_tables = None


def _raw_tables(sid):
    """Every table's rows for this spell (the "Raw table rows" section)."""
    global _spell_tables
    if _spell_tables is None:
        _spell_tables = []
        for (t,) in conn().execute("select name from sqlite_master where type='table' order by name").fetchall():
            cols = columns(t)
            key = "SpellID" if "SpellID" in cols else "Spell" if t == "SkillLineAbility" else None
            if key:
                _spell_tables.append((t, key))
    out = {}
    for t, key in _spell_tables:
        rs = [nz(r) for r in rows(t, key, sid)]
        if rs:
            out[t] = rs
    return out


# ---------------------------------------------------------------- public API
def spell(sid, show_sod=False):
    sid = str(sid)
    name = one("SpellName", sid)
    if not name:
        return None
    sp = one("Spell", sid) or {}
    misc = first("SpellMisc", "SpellID", sid)
    effects = sorted(rows("SpellEffect", "SpellID", sid), key=lambda e: int(e.get("EffectIndex", 0)))
    aura = first("SpellAuraOptions", "SpellID", sid)
    cast = one("SpellCastTimes", misc.get("CastingTimeIndex", "0")) or {}
    dur = one("SpellDuration", misc.get("DurationIndex", "0")) or {}
    rng = one("SpellRange", misc.get("RangeIndex", "0")) or {}
    cd = first("SpellCooldowns", "SpellID", sid)
    cats = first("SpellCategories", "SpellID", sid)
    shift = first("SpellShapeshift", "SpellID", sid)
    mask = int(misc.get("SchoolMask") or 0)

    proc = _proc(aura)
    attrs = _attributes(misc)
    flat_names = {x["name"] for xs in attrs.values() for x in xs}
    cooldown = max(int(num(cd.get("RecoveryTime"))), int(num(cd.get("CategoryRecoveryTime"))))
    hidden = scalar("select Reason from Hidden where SpellID=? limit 1", (sid,))

    return {
        "id": int(sid), "name": name["Name_lang"], "subtext": sp.get("NameSubtext_lang", ""),
        "origin": origin_of(sid), "originNote": ORIGIN_NOTE[origin_of(sid)], "hidden": hidden,
        "description": descriptions.render(sp.get("Description_lang", ""), sid, proc["chance"] if proc else 0),
        "descriptionRaw": sp.get("Description_lang", ""),
        "auraDescription": descriptions.render(sp.get("AuraDescription_lang", ""), sid),
        "iconFileDataID": misc.get("SpellIconFileDataID"), "icon": icon_of(sid),
        "classification": q("select Cat, Sub, Linked, Via from Classification where SpellID=?", (sid,)),
        "talents": talents.spell_talents().get(sid, []),
        "learn": _learn(sid), "ranks": ranks(sid, show_sod),
        "supercededBy": [x["Spell"] for x in q("select Spell from SkillLineAbility where SupercedesSpell=?", (sid,))],
        "cooldown": fmt_ms(cooldown),
        "gcd": fmt_ms(cd.get("StartRecoveryTime")) if int(num(cd.get("StartRecoveryTime"))) else ("Off GCD" if cd else None),
        "costs": _costs(sid),
        "equipped": [{"class": r["EquippedItemClass"], "subclassMask": r["EquippedItemSubclass"], "invTypeMask": r["EquippedItemInvTypes"]}
                     for r in rows("SpellEquippedItems", "SpellID", sid)],
        "stances": decode("SpellShapeshiftMask", shift.get("ShapeshiftMask_0")) if int(shift.get("ShapeshiftMask_0") or 0) else [],
        "related": _related(sid, name["Name_lang"], effects, sp, show_sod, skip=_link_ids(sid)),
        "procNotes": _proc_notes(proc, aura, flat_names),
        "cast": fmt_ms(cast.get("Base")) or "Instant",
        "duration": fmt_ms(dur.get("Duration")) or "—",
        "range": rng.get("DisplayName_lang") or ("Self" if misc.get("RangeIndex") == "1" else f"Range #{misc.get('RangeIndex')}"),
        "rangeYards": [rng.get("RangeMax_0"), rng.get("RangeMax_1")] if rng else None,
        "schools": [n for b, n in SCHOOLS.items() if mask & b] or ["None"],
        "speed": misc.get("Speed"),
        "attributes": attrs, "flags": _flags(sid, attrs, misc),
        "categories": {"mechanic": label("Mechanics", cats["Mechanic"]) if int(cats.get("Mechanic") or 0) else None,
                       "dispel": label("DispelType", cats["DispelType"]) if int(cats.get("DispelType") or 0) else None},
        "level": first("SpellLevels", "SpellID", sid).get("SpellLevel"),
        "proc": proc, "effects": _effects(sid, effects, int(num(dur.get("Duration")))), "tables": _raw_tables(sid),
        "affects": affects.affected(sid),
        "triggers": links.triggers(sid), "triggeredBy": links.triggered_by(sid), "usedBy": links.used_by(sid),
    }


_tip_cache = {}


def tip(sid):
    """Condensed summary for the hover tooltip."""
    sid = str(sid)
    if sid in _tip_cache:
        return _tip_cache[sid]
    s = spell(sid, show_sod=True)
    if not s:
        return None
    t = tip_from(s)
    if len(_tip_cache) > 2000:
        _tip_cache.clear()
    _tip_cache[sid] = t
    return t


def _n(x, places=3):
    return f"{x:.{places}f}".rstrip("0").rstrip(".") or "0"


def coef_note(sc):
    """" · SP 0.2/tick = 1 over 5 ticks" -- the coefficient summary shown in tooltips."""
    bits = []
    for key, name in (("sp", "SP"), ("ap", "AP")):
        if sc[key]:
            bits.append(f"{name} {_n(sc[key])}/tick = {_n(sc[key + 'Total'])} over {sc['ticks']} ticks" if sc["periodic"] and sc["ticks"]
                        else f"{name} {_n(sc[key])}")
    return " · " + " · ".join(bits) if bits else ""


def tip_from(s):
    """The tooltip summary of an already-built spell() result."""
    p, f = s["proc"], s["flags"]
    return {
        "id": s["id"], "name": s["name"], "subtext": s["subtext"], "icon": s["icon"], "origin": s["origin"],
        "ranks": [{"rank": r["rank"], "level": r["level"]} for r in s["ranks"]],
        "line1": [x for x in (s["cast"], s["range"] if s["range"] != "Self" else None, s["cooldown"] and f"{s['cooldown']} cooldown",
                              s["duration"] if s["duration"] != "—" else None, ", ".join(s["costs"]) or None) if x],
        "school": ", ".join(s["schools"]), "description": s["description"], "aura": s["auraDescription"],
        "effects": [e["effect"].split(" (")[0] + (f" → {e['aura'].split(' (')[0]}" if e["aura"] else "")
                    + (f" [{e['basePoints']}]" if e["basePoints"] not in (None, "0") else "") + coef_note(e["scaling"])
                    for e in s["effects"]][:4],
        "proc": p and {"chance": p["chance"], "cooldown": p["cooldown"], "flags": [x["name"] for x in p["triggers"]][:6],
                       "note": s["procNotes"][0] if s["procNotes"] else None},
        "keyFlags": [x["name"] for x in f["periodic"] + f["proc"]][:6],
        "where": [f"{c['Cat']}: {c['Sub']}" + (" (linked)" if c["Linked"] else "") for c in s["classification"]],
        "learn": [" / ".join(l["races"] + l["classes"]) for l in s["learn"] if l["races"] or l["classes"]],
    }


def search_index():
    """[(id, name, origin, hidden)] for every named spell, sorted like search() -- the static site searches this in the browser."""
    marks = ",".join("?" * len(SEARCH_HIDDEN))
    rows = q("select n.ID id, n.Name_lang name, o.Origin origin, "
             f"exists(select 1 from Hidden h where h.SpellID=n.ID and h.Reason in ({marks})) hid "
             "from SpellName n join SpellOrigin o on o.SpellID=n.ID where n.Name_lang != ''", SEARCH_HIDDEN)
    rows.sort(key=lambda r: (r["name"], int(r["id"])))
    return [[int(r["id"]), r["name"], r["origin"], int(r["hid"])] for r in rows]


def search(text, show_sod=False, limit=50):
    """By name (substring) or exact id. SoD and hidden spells are left out unless asked for by id."""
    text = text.strip()
    if not text:
        return []
    if text.isdigit():                                         # an explicit id is always honoured
        sql, args = ("select n.ID id, n.Name_lang name, o.Origin origin from SpellName n join SpellOrigin o on o.SpellID=n.ID "
                     "where n.ID=?", (text,))
    else:
        reasons = ",".join("?" * len(SEARCH_HIDDEN))
        sql = ("select n.ID id, n.Name_lang name, o.Origin origin from SpellName n join SpellOrigin o on o.SpellID=n.ID "
               "where n.Name_lang like ? and (? or o.Origin != 'sod') "
               f"and not exists (select 1 from Hidden h where h.SpellID=n.ID and h.Reason in ({reasons})) "
               "order by n.Name_lang, cast(n.ID as integer) limit ?")
        args = (f"%{text}%", 1 if show_sod else 0, *SEARCH_HIDDEN, limit)
    return [{"id": int(r["id"]), "name": r["name"], "origin": r["origin"]} for r in q(sql, args)]
