"""Build-time: load every CSV in data/csv into SQLite (all columns text) and index the join keys."""
import csv, sqlite3, time

from . import config as C

# extra indexes besides "ID" / "SpellID" which are indexed on every table that has them
EXTRA_INDEXES = [
    ("SkillLineAbility", "Spell"), ("SkillLineAbility", "SupercedesSpell"), ("SpellName", "Name_lang"),
    ("SpellEffect", "EffectTriggerSpell"), ("SpellLabel", "LabelID"),
    ("TraitNode", "TraitTreeID"), ("TraitNodeXTraitNodeEntry", "TraitNodeID"),
    ("TraitNodeGroupXTraitNode", "TraitNodeID"), ("TraitNodeGroupXTraitNode", "TraitNodeGroupID"),
    ("TraitNodeGroupXTraitCond", "TraitNodeGroupID"), ("TraitEdge", "LeftTraitNodeID"),
    ("TraitTreeXTraitCurrency", "TraitTreeID"), ("TraitCond", "TraitTreeID"),
    ("TraitDefinitionEffectPoints", "TraitDefinitionID"), ("CurvePoint", "CurveID"),
    ("Item", "SubclassID"), ("ItemEffect", "SpellID"), ("ItemXItemEffect", "ItemEffectID"), ("ItemXItemEffect", "ItemID"),
    ("ItemSubClass", "ClassID"), ("ItemClass", "ClassID"), ("RandPropPoints", "ID"), ("ArmorLocation", "ID"), ("ItemArmorTotal", "ItemLevel"),]


def build(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    n_rows = 0
    for f in sorted(C.CSV_DIR.glob("*.csv")):
        table = f.stem
        with open(f, encoding="utf-8", newline="") as fh:
            r = csv.reader(fh)
            head = next(r)
            con.execute(f'create table "{table}" ({",".join(chr(34) + c + chr(34) for c in head)})')
            con.executemany(f'insert into "{table}" values ({",".join("?" * len(head))})', r)
        n_rows += con.execute(f'select count(*) from "{table}"').fetchone()[0]
        for col in ("ID", "SpellID"):
            if col in head:
                con.execute(f'create index "i_{table}_{col}" on "{table}"("{col}")')
    for table, col in EXTRA_INDEXES:
        con.execute(f'create index if not exists "i_{table}_{col}" on "{table}"("{col}")')
    con.execute("create table Meta (key text primary key, value text)")
    con.executemany("insert into Meta values (?,?)", [
        ("build", C.BUILD), ("pre_sod_build", C.PRE_SOD_BUILD), ("sod_era_build", C.SOD_ERA_BUILD),
        ("built_at", time.strftime("%Y-%m-%d %H:%M:%S"))])
    con.commit()
    con.close()
    return n_rows
