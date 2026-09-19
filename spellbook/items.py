"""Item data as it relates to spells.

  weapon damage   a spell with a WEAPON_DAMAGE effect takes its damage from the weapon you hold. An item's damage per second comes
                  from its item level and quality (ItemDamage<Type>); times its speed, spread by its variance, gives min-max.
                  This turns "Shoot scales with the wand" into concrete numbers for every wand.
  items that cast the item effects that cast a spell (use / equip / chance on hit / teach), so a spell can name its items.
  enchantments    imbues, poisons, weapon enchants: a spell applies an enchantment (SpellItemEnchantment), which may cast a spell
                  while equipped, or when it hits, or deal extra damage.
"""
import functools, re

from .db import num, q, q1, rows, scalar
from .flags import label

QUALITY = {0: "Poor", 1: "Common", 2: "Uncommon", 3: "Rare", 4: "Epic", 5: "Legendary", 6: "Artifact", 7: "Heirloom"}
DAMAGE_TYPE = {0: "Physical", 1: "Holy", 2: "Fire", 3: "Nature", 4: "Frost", 5: "Shadow", 6: "Arcane"}
# weapon subclass (ItemSubClass with ClassID 2) -> the table that turns item level + quality into damage per second
DAMAGE_TABLE = {19: "ItemDamageWand", 2: "ItemDamageRanged", 3: "ItemDamageRanged", 18: "ItemDamageRanged", 16: "ItemDamageThrown"}
RANGED_DEFAULT = (2, 3, 18)                       # a spell that uses the ranged slot without naming a weapon: bow / gun / crossbow
TRIGGER = {0: "on use", 1: "on equip", 2: "chance on hit", 4: "soulstone", 5: "on use (no delay)", 6: "teaches it"}
ENCHANT_EFFECTS = {53, 54, 92, 156, 360}          # ENCHANT_ITEM, _TEMPORARY, HELD_ITEM, _PRISMATIC, and this build's weapon-imbue effect
ENCHANT_KIND = {1: "may cast it when it hits", 3: "casts it while the item is equipped", 7: "casts it on use"}
# test / monster / placeholder items: "Monster - Wand, Basic", "90 Epic Frost Wand", "Fast Test Bow", "(OLD)...", "... DEPRECATED"
JUNK = re.compile(r"^monster\b|^\(dnt\)|\(old\)|deprecated|\bdep$|\btest\b|^\d+ |\[ph\]|^durability", re.I)
MAX_ITEMS = 150


def is_weapon_damage(effect_id):
    name = label("SpellEffects", effect_id)
    return "WEAPON_DAMAGE" in name or "WEAPON_PERCENT" in name or "NORMALIZED_WEAPON" in name


@functools.lru_cache(maxsize=None)
def subclass_name(sub):
    return scalar("select DisplayName_lang from ItemSubClass where ClassID='2' and SubClassID=?", (str(sub),)) or f"weapon {sub}"


@functools.lru_cache(maxsize=None)
def _dps_table(table):
    return {r["ItemLevel"]: r for r in q(f'select * from "{table}"')}


@functools.lru_cache(maxsize=None)
def _weapons(sub):
    """All weapons of one subclass with their computed damage: [id, name, item level, quality, speed, school, min, max, dps]."""
    table = _dps_table(DAMAGE_TABLE[sub])
    out = []
    for r in q("select s.ID id, s.Display_lang name, s.ItemLevel lvl, s.OverallQualityID qual, s.ItemDelay delay, s.DmgVariance var, "
               "s.DamageType dt from Item i join ItemSparse s on s.ID=i.ID where i.ClassID='2' and i.SubclassID=? and s.Display_lang != ''",
               (str(sub),)):
        if JUNK.search(r["name"]):
            continue
        d = table.get(r["lvl"])
        if not d:
            continue
        quality, delay, var = int(num(r["qual"])), int(num(r["delay"])) / 1000, num(r["var"])
        dps = num(d.get(f"Quality_{min(quality, 6)}"))
        avg = dps * delay
        out.append([int(r["id"]), r["name"], int(num(r["lvl"])), quality, delay, DAMAGE_TYPE.get(int(num(r["dt"])), "Physical"),
                    round(avg * (1 - var / 2)), round(avg * (1 + var / 2)), round(dps, 1)])
    out.sort(key=lambda w: (w[2], w[1]))
    return out


def weapon_reference(effects, equipped, attrs_ranged):
    """For a spell with a weapon-damage effect: the weapon types it uses and the damage of each weapon of that type.
    `equipped` = the SpellEquippedItems rows; `attrs_ranged` = the spell uses the ranged slot."""
    if not any(is_weapon_damage(int(num(e.get("Effect")))) for e in effects):
        return []
    subs = set()
    for r in equipped:
        if r.get("EquippedItemClass") == "2":
            mask = int(num(r.get("EquippedItemSubclass")))
            subs |= {b for b in DAMAGE_TABLE if mask >> b & 1}
    if not subs and attrs_ranged:
        subs = set(RANGED_DEFAULT)
    out = []
    for sub in sorted(subs):
        items = _weapons(sub)
        if items:
            out.append({"weapon": subclass_name(sub), "table": DAMAGE_TABLE[sub], "count": len(items), "items": items[-MAX_ITEMS:]})
    return out


def used_by_items(spell_id, limit=20):
    """Items with an effect that casts this spell: [{id, name, level, quality, how}]."""
    out = []
    for r in q("select s.ID id, s.Display_lang name, s.ItemLevel lvl, s.OverallQualityID qual, e.TriggerType t "
               "from ItemEffect e join ItemXItemEffect x on x.ItemEffectID=e.ID join ItemSparse s on s.ID=x.ItemID "
               "where e.SpellID=? and s.Display_lang != '' order by cast(s.ItemLevel as integer) desc, s.Display_lang limit ?",
               (str(spell_id), limit)):
        out.append({"id": int(r["id"]), "name": r["name"], "level": int(num(r["lvl"])), "quality": QUALITY.get(int(num(r["qual"])), "?"),
                    "how": TRIGGER.get(int(num(r["t"])), f"trigger {r['t']}")})
    return out


def enchant(enchant_id):
    """What an item enchantment does: {id, name, duration, lines: [{kind, spell, points}]}, or None."""
    en = q1("select * from SpellItemEnchantment where ID=?", (str(enchant_id),))
    if not en:
        return None
    lines = []
    for i in range(3):
        kind, arg, pts = int(num(en.get(f"Effect_{i}"))), en.get(f"EffectArg_{i}"), num(en.get(f"EffectPointsMin_{i}"))
        if kind in ENCHANT_KIND and arg not in ("", "0"):
            lines.append({"kind": ENCHANT_KIND[kind], "spell": int(arg), "name": scalar("select Name_lang from SpellName where ID=?", (arg,)) or arg})
        elif kind == 2 and pts:
            lines.append({"kind": f"adds {pts:g} weapon damage", "spell": None, "name": None})
    return {"id": int(en["ID"]), "name": en["Name_lang"], "duration": int(num(en["Duration"])), "lines": lines}
