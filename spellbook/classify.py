"""Build-time: give every spell a home in the browser.

    Class   -- learned by a class (SkillLineAbility.ClassMask), grouped by skill line / spec
    Racial  -- a racial skill line, grouped by race
    Skills  -- professions, weapons, riding, pets ... (skill lines with no class)
    Test / Deprecated, NPC / Unknown -- everything else

Spells with no skill-line entry inherit the home of the spell that triggers / mentions them ("linked").

Some spells are deliberately left out of every list (they stay reachable by search and by id):
    engraving / rune spells, talents (they live in the Talents tab), and spells that only work inside a
    shapeshift form (Warlock's Metamorphosis). Anything reachable *only* through a hidden spell is hidden with it.

Season-of-Discovery spells are NOT removed here: they are classified like any other spell and filtered at query time
through SpellOrigin, so the "Show SoD" switch can bring them back.
"""
import collections, re

from . import talents
from .db import class_names

FORM_METAMORPHOSIS = 22           # SpellShapeshiftForm id
MOUNT_LINES = {"Mounts", "Riding"}          # skill lines of mounts / riding: not a class's own, even when a few rows name a class
# the only mounts a class trains itself (matched by name; the beta / SoD copies share the names)
CLASS_MOUNTS = {"Summon Warhorse": "Paladin", "Summon Charger": "Paladin", "Summon Felsteed": "Warlock", "Summon Dreadsteed": "Warlock"}
RANK_TEXT = re.compile(r"^Rank \d+$")
TEST_NAME = re.compile(r"\((TEST|OLD|DND|NYI|PH|DEPRECATED|UNUSED|DEBUG)\)|^zz|^DEPRECATED|\bTEST\b|^OLD\b|\bDND\b", re.I)


def racial_names(mask, skill, races):
    r = [n for i, n in races.items() if i < 32 and mask & (1 << (i - 1))]
    if r:
        return r
    n = re.sub(r"\s*Racial\s*-?\s*|-", " ", skill).strip()             # "Skyborne Racial" / "Racial - Gnome"
    return [{"Dwarven": "Dwarf"}.get(n, n) or "Unknown race"]


def legacy_talents(con, names):
    """The classic-style Talent table, one entry per talent: {ranks, classes, tab, hide}. Only PASSIVE talents are hidden from
    the lists (they live in the Talents tab). An ACTIVE talent -- one you cast, like Riptide, or Consecration and Aimed Shot,
    which the beta's trees no longer list -- is an ordinary ability and stays listed (hide=False)."""
    tab = {r[0]: (int(r[1]), r[2]) for r in con.execute("select ID, ClassMask, Name_lang from TalentTab")}
    passive = {sp for sp, a0 in con.execute("select SpellID, Attributes_0 from SpellMisc") if int(a0) & 0x40}
    out = []
    for row in con.execute("select TabID, SpellRank_0, SpellRank_1, SpellRank_2, SpellRank_3, SpellRank_4, "
                           "SpellRank_5, SpellRank_6, SpellRank_7, SpellRank_8 from Talent"):
        ranks = [s for s in row[1:] if s not in ("", "0") and s in names]
        if not ranks:
            continue
        mask, tab_name = tab.get(row[0], (0, ""))
        out.append({"ranks": ranks, "classes": class_names(mask), "tab": tab_name, "hide": ranks[0] in passive})
    return out


def hidden_spells(con, names, sla, skill_name, line_class):
    """{reason: set(spell ids)} of spells that get no place in the lists."""
    # 1. engraving / runes
    engraving = {sp for sp, sl, *_ in sla if skill_name.get(sl) in ("Engraving", "Runes")}

    # 2. talents: every spell a talent table / class tree grants, plus same-named ranks that class learns
    by_name = collections.defaultdict(list)
    for sid, n in names.items():
        by_name[n].append(sid)
    learned_by = collections.defaultdict(set)                            # spell -> classes that learn it
    for sp, sl, cm, *_ in sla:
        if "acial" in skill_name.get(sl, ""):
            continue
        mask = int(cm) if int(cm) > 0 else line_class.get(sl, 0)
        learned_by[sp].update(class_names(mask))
    passive = {sp for sp, a0 in con.execute("select SpellID, Attributes_0 from SpellMisc") if int(a0) & 0x40}
    talent = set()
    # 2a. the classic-style Talent table (see legacy_talents)
    for t in legacy_talents(con, names):
        if t["hide"]:
            talent.update(t["ranks"])
    # 2b. the new retail-model trees
    #     Only passive entries are hidden; an active one (Riptide, Stormstrike ...) is an ability you cast, so it is listed.
    for cls, entries in talents.entries_by_class().items():
        for sid, name in entries:
            if sid in passive:
                talent.add(sid)
                talent.update(s for s in by_name.get(name, ()) if cls in learned_by.get(s, ()) and s in passive)

    # 3. spells that exist only inside Warlock's Metamorphosis form. The form spell (aura SHAPESHIFT) carries
    #    OVERRIDE_ACTIONBAR_SPELLS effects (aura 332): while transformed, MiscValue's spell is replaced by BasePoints'
    #    spell. Those replacements, the "Metamorphosis : X" placeholders, and anything whose shapeshift mask requires
    #    the form are form-only. The form spell itself stays: it starts the form, it does not need it.
    form_spells = {sp for sp, mv in con.execute("select SpellID, EffectMiscValue_0 from SpellEffect where EffectAura='36'")
                   if int(mv) == FORM_METAMORPHOSIS}
    form_only = set()
    for g in form_spells:
        for bp, mv in con.execute("select EffectBasePointsF, EffectMiscValue_0 from SpellEffect where SpellID=? and EffectAura='332'", (g,)):
            form_only.add(str(int(float(bp))))
            if "Metamorphosis" in names.get(mv, ""):
                form_only.add(mv)
    for sp, m0 in con.execute("select SpellID, ShapeshiftMask_0 from SpellShapeshift"):
        if int(m0) & (1 << (FORM_METAMORPHOSIS - 1)):
            form_only.add(sp)
    form_only = (form_only & set(names)) - form_spells
    # 4. talent-style passives the talent tables do not list: a ranked passive ("Improved Flash of Light", "Improved Pummel")
    #    in a class skill line is a talent's rank. Pet training lines are left alone.
    subtext = {r[0]: r[1] or "" for r in con.execute("select ID, NameSubtext_lang from Spell")}
    lines_of = collections.defaultdict(set)
    for sp, sl, *_ in sla:
        lines_of[sp].add(skill_name.get(sl, ""))
    for sp in learned_by:
        if sp in passive and RANK_TEXT.match(subtext.get(sp, "")) and \
                not any(l.startswith("Pet") or l == "Beast Training" for l in lines_of[sp]):
            talent.add(sp)

    # 5. helper / effect spells: learned "automatically" (SkillLineAbility.AcquireMethod 3) and with no cost, no cooldown
    #    and no global cooldown -- Judgement of Light, the extra Flash of Light / Holy Light spells, "Hellfire Effect" ...
    #    A real ability has a cost, a cooldown or a GCD (Execute, Readiness, Feral Charge (Bear) are method 3 too, but real).
    acquire = collections.defaultdict(set)
    for sp, _sl, _cm, _rm, am in sla:
        acquire[sp].add(am)
    real = {r[0] for r in con.execute("select SpellID from SpellPower where cast(ManaCost as real) > 0 or cast(PowerCostPct as real) > 0")}
    real |= {r[0] for r in con.execute("select SpellID from SpellCooldowns where cast(RecoveryTime as integer) > 0 "
                                       "or cast(CategoryRecoveryTime as integer) > 0 or cast(StartRecoveryTime as integer) > 0")}
    helper = {sp for sp, ams in acquire.items() if ams == {"3"} and sp in learned_by and sp not in real}

    return {"engraving": engraving, "talent": talent, "form-only": form_only, "helper": helper}


def build(con):
    names = {r[0]: r[1] for r in con.execute("select ID, Name_lang from SpellName")}
    skill_name = {r[0]: r[1] for r in con.execute("select ID, DisplayName_lang from SkillLine")}
    races = {int(r[0]): r[1] for r in con.execute("select ID, Name_lang from ChrRaces")}
    sla = con.execute("select Spell, SkillLine, ClassMask, RaceMasks_0, AcquireMethod from SkillLineAbility").fetchall()

    # a skill line whose rows all name the same single class lets its ClassMask=0 rows inherit that class
    masks = collections.defaultdict(set)
    for sp, sl, cm, *_ in sla:
        if int(cm) > 0 and "acial" not in skill_name.get(sl, "") and skill_name.get(sl) not in MOUNT_LINES:
            masks[sl].add(int(cm))
    line_class = {sl: next(iter(m)) for sl, m in masks.items() if len(m) == 1}

    hidden = hidden_spells(con, names, sla, skill_name, line_class)
    excluded = set().union(*hidden.values())

    # ---- direct homes, from the skill line each spell is learned through ----
    out = collections.defaultdict(set)                                   # spell -> {(cat, sub, linked, via, via_id)}
    for sp, sl, cm, rm, _am in sla:
        if sp in excluded:
            continue
        line, cm = skill_name.get(sl, f"Skill {sl}"), int(cm)
        if line in MOUNT_LINES:                                  # mounts and riding are not class spells ...
            owner = CLASS_MOUNTS.get(names.get(sp))              # ... except the two mounts Paladins and Warlocks train
            out[sp].add(("Class", owner, 0, line, "") if owner else ("Skills", line, 0, "", ""))
        elif "acial" in line:
            for r in racial_names(int(rm or 0), line, races):
                out[sp].add(("Racial", r, 0, "", ""))
        elif cm > 0 or sl in line_class:
            for c in class_names(cm if cm > 0 else line_class[sl]):
                out[sp].add(("Class", c, 0, line, ""))
        else:
            out[sp].add(("Skills", line, 0, "", ""))

    # a legacy talent that is an ordinary ability here but has no skill-line row (Sanctity Aura) still belongs to its class
    for t in legacy_talents(con, names):
        if not t["hide"]:
            for sp in t["ranks"]:
                if sp not in out and sp not in excluded:
                    for c in t["classes"]:
                        out[sp].add(("Class", c, 0, t["tab"], ""))

    # ---- links: an edge (a, b) means spell a triggers / mentions spell b ----
    edges = set()
    for sid, d, ad in con.execute("select ID, Description_lang, AuraDescription_lang from Spell"):
        for m in re.findall(r"\$(\d{3,})[a-zA-Z]", (d or "") + " " + (ad or "")):
            if m != sid and m in names:
                edges.add((sid, m))
    for sp, trig in con.execute("select SpellID, EffectTriggerSpell from SpellEffect where EffectTriggerSpell not in ('','0')"):
        if trig != sp and trig in names:
            edges.add((sp, trig))

    # ---- inherit the home of a linked spell (two rounds, both directions) ----
    for _ in range(2):
        add = collections.defaultdict(set)
        for a, b in edges:
            for src, dst in ((a, b), (b, a)):
                if src in out and dst not in out and dst not in excluded:
                    for cat, sub, _l, _v, _i in out[src]:
                        add[dst].add((cat, sub, 1, f"{names[src]} ({src})", src))
        for k, v in add.items():
            out[k] |= v

    # ---- anything still unclassified that is only reachable through a hidden spell is hidden too ----
    orphans = {dst for a, b in edges for src, dst in ((a, b), (b, a)) if src in excluded and dst not in out and dst not in excluded}
    excluded |= orphans

    for sid, n in names.items():
        if sid not in out and sid not in excluded:
            home = "Test / Deprecated" if TEST_NAME.search(n or "") else "NPC / Unknown"
            out[sid].add((home, home, 0, "", ""))

    # record why a spell is hidden: the lists never show them, and search skips all but talents (which people look up by name)
    hidden_rows = [(s, reason) for reason, ids in hidden.items() for s in ids] + [(s, "orphan") for s in orphans]
    con.execute("drop table if exists Hidden")
    con.execute("create table Hidden (SpellID text, Reason text)")
    con.executemany("insert into Hidden values (?,?)", hidden_rows)
    con.execute("create index i_hidden on Hidden(SpellID)")

    con.execute("drop table if exists Classification")
    con.execute("create table Classification (SpellID text, Cat text, Sub text, Linked integer, Via text, ViaID text)")
    con.executemany("insert into Classification values (?,?,?,?,?,?)", [(s, *t) for s, ts in out.items() for t in ts])
    con.execute("create index i_cls_home on Classification(Cat, Sub)")
    con.execute("create index i_cls_spell on Classification(SpellID)")
    con.commit()
    return {"hidden": {k: len(v) for k, v in hidden.items()}, "hidden orphans": len(orphans), "classified": len(out)}
