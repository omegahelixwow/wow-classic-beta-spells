"""Items: pages, lists, search, and how they tie to spells.

  item pages      quality, level, slot, stats, armor, weapon speed, the spells the item casts (with their text), restrictions.
                  Stats and armor are computed from the item's budget tables (RandPropPoints, ItemArmor*), which reproduces the
                  values the game shows. Weapon DAMAGE is not: this build has no table that gives it, so it is left out
                  (Wowhead shows the real numbers, and every item page links there).
  items that cast the item effects that cast a spell (use / equip / chance on hit / teach), so a spell can name its items.
  enchantments    imbues, poisons, weapon enchants: a spell applies an enchantment (SpellItemEnchantment), which may cast a spell
                  while equipped, or when it hits, or deal extra damage.
  SoD             an item is Season of Discovery when it first appears in the SoD-era client (ItemOrigin, see origins.py).
"""
import functools, re

from . import descriptions
from .db import class_names, icons, num, q, q1, races, rows, scalar
from .flags import label

QUALITY = {0: "Poor", 1: "Common", 2: "Uncommon", 3: "Rare", 4: "Epic", 5: "Legendary", 6: "Artifact", 7: "Heirloom"}
TRIGGER = {0: "Use", 1: "Equip", 2: "Chance on hit", 4: "Soulstone", 5: "Use (no delay)", 6: "Teaches"}
BONDING = {0: "", 1: "Binds when picked up", 2: "Binds when equipped", 3: "Binds when used", 4: "Quest item", 5: "Quest item"}
ENCHANT_EFFECTS = {53, 54, 92, 156, 360}          # ENCHANT_ITEM, _TEMPORARY, HELD_ITEM, _PRISMATIC, and this build's weapon-imbue effect
ENCHANT_KIND = {1: "may cast it when it hits", 3: "casts it while the item is equipped", 7: "casts it on use"}
# test / monster / placeholder items: "Monster - Wand, Basic", "90 Epic Frost Wand", "Fast Test Bow", "(OLD)...", "... DEPRECATED"
JUNK = re.compile(r"^monster\b|^\(dnt\)|\(old\)|deprecated|\bdep$|\btest\b|^\d+ |\[ph\]|^durability|^zz|^unused|^\[", re.I)
# inventory type -> column of RandPropPoints (the stat budget of the slot); see TrinityCore's GetRandomPropertyPoints
_BUDGET_SLOT = {1: 0, 5: 0, 7: 0, 20: 0, 17: 0, 15: 0, 25: 0, 26: 4,          # head chest legs robe 2H ranged thrown / wand
                3: 1, 6: 1, 8: 1, 10: 1, 12: 1,                                # shoulders waist feet hands trinket
                2: 2, 9: 2, 11: 2, 14: 2, 16: 2, 23: 2,                        # neck wrists finger shield cloak held
                13: 3, 21: 3, 22: 3, 28: 4}                                    # one-hand / main / off hand; relic
_GOOD = {2: "Good", 3: "Superior", 4: "Epic", 5: "Epic", 6: "Epic", 7: "Epic"}
INV_SHORT = {1: "Head", 2: "Neck", 3: "Shoulder", 4: "Shirt", 5: "Chest", 6: "Waist", 7: "Legs", 8: "Feet", 9: "Wrist", 10: "Hands",
             11: "Finger", 12: "Trinket", 13: "One-hand", 14: "Shield", 15: "Ranged", 16: "Back", 17: "Two-hand", 18: "Bag", 19: "Tabard",
             20: "Chest", 21: "Main hand", 22: "Off hand", 23: "Held in off-hand", 24: "Ammo", 25: "Thrown", 26: "Ranged", 27: "Quiver", 28: "Relic"}
MAX_LIST = 300


def _junk(name):
    return not name or bool(JUNK.search(name))


@functools.lru_cache(maxsize=None)
def class_name(cls):
    return scalar("select ClassName_lang from ItemClass where ClassID=?", (str(cls),)) or f"class {cls}"


@functools.lru_cache(maxsize=None)
def subclass_name(cls, sub):
    return scalar("select DisplayName_lang from ItemSubClass where ClassID=? and SubClassID=?", (str(cls), str(sub))) or f"type {sub}"


def is_weapon_damage(effect_id):
    name = label("SpellEffects", effect_id)
    return "WEAPON_DAMAGE" in name or "WEAPON_PERCENT" in name or "NORMALIZED_WEAPON" in name


def stat_name(t):
    n = label("ItemModType", t, "")
    return f"Stat {t}" if n.startswith("_") or not n else n.replace("_", " ").title().replace("Mp5", "MP5")


def computed_stats(sp, level, quality, inv):
    """[(stat id, value)] from the item's percentages of its slot budget. Empty when the budget is unknown."""
    slot, col = _BUDGET_SLOT.get(inv), _GOOD.get(quality)
    rp = q1("select * from RandPropPoints where ID=?", (str(level),))
    if slot is None or not col or not rp:
        return []
    budget = num(rp.get(f"{col}_{slot}"))
    out = []
    for i in range(10):
        t, pct = int(num(sp.get(f"StatModifier_bonusStat_{i}"), -1)), num(sp.get(f"StatPercentEditor_{i}"))
        if t >= 0 and pct and not label("ItemModType", t, "").startswith("_"):        # stats without a public name (85) are spell effects: shown by the item's spells
            out.append((t, int(round(budget * pct / 10000))))
    return out


def computed_armor(level, quality, inv, cls, sub):
    if cls != 4 or sub not in (1, 2, 3, 4):
        return 0
    tot, qual, loc = (q1(f"select * from {t} where ID=?", (str(k),)) for t, k in
                      (("ItemArmorTotal", level), ("ItemArmorQuality", level), ("ArmorLocation", 5 if inv == 20 else inv)))   # a robe is a chest piece
    if not (tot and qual and loc):
        return 0
    base = num(tot.get(("Cloth", "Leather", "Mail", "Plate")[sub - 1]))
    mod = num(loc.get(("Clothmodifier", "Leathermodifier", "Chainmodifier", "Platemodifier")[sub - 1]))
    return int(round(base * num(qual.get(f"Qualitymod_{min(quality, 6)}")) * mod))


def money(copper):
    c = int(num(copper))
    g, s, c = c // 10000, c // 100 % 100, c % 100
    return {"g": g, "s": s, "c": c} if c or s or g else None


def _effects(item_id):
    out = []
    for r in q("select e.* from ItemEffect e join ItemXItemEffect x on x.ItemEffectID=e.ID where x.ItemID=? order by cast(e.LegacySlotIndex as integer)", (str(item_id),)):
        sid = r["SpellID"]
        name = scalar("select Name_lang from SpellName where ID=?", (sid,))
        if name is None:
            continue
        sp = q1("select Description_lang, NameSubtext_lang from Spell where ID=?", (sid,)) or {}
        out.append({"spell": int(sid), "name": name, "how": TRIGGER.get(int(num(r["TriggerType"])), f"trigger {r['TriggerType']}"),
                    "text": descriptions.render(sp.get("Description_lang", ""), sid), "charges": int(num(r["Charges"])),
                    "cooldown": int(num(r["CoolDownMSec"])) // 1000, "origin": scalar("select Origin from SpellOrigin where SpellID=?", (sid,)) or ""})
    return out


def item(item_id):
    """Everything one item page shows, or None."""
    sp = q1("select * from ItemSparse where ID=?", (str(item_id),))
    it = q1("select * from Item where ID=?", (str(item_id),))
    if not sp or not it:
        return None
    cls, sub, inv = int(num(it["ClassID"])), int(num(it["SubclassID"])), int(num(sp["InventoryType"]))
    quality, level = int(num(sp["OverallQualityID"])), int(num(sp["ItemLevel"]))
    ic = icons().get(it["IconFileDataID"])
    mask_c = int(num(sp.get("AllowableClass"), -1))
    mask_r = int(num(sp.get("AllowableRace_0"), -1))
    classes = class_names(mask_c) if mask_c > 0 and mask_c & 0x7FF != 0x7FF and mask_c != 1535 else []
    races_ = [n for i, n in races().items() if mask_r > 0 and mask_r & (1 << (i - 1))]
    if len(races_) >= 8:
        races_ = []
    stats = computed_stats(sp, level, quality, inv)
    weapon = cls == 2
    return {
        "id": int(item_id), "name": sp["Display_lang"], "quality": quality, "qualityName": QUALITY.get(quality, "?"), "level": level,
        "reqLevel": int(num(sp["RequiredLevel"])), "icon": ic, "iconFileDataID": it["IconFileDataID"],
        "origin": scalar("select Origin from ItemOrigin where ItemID=?", (str(item_id),)) or "",
        "bonding": BONDING.get(int(num(sp["Bonding"])), ""), "cls": cls, "sub": sub, "className": class_name(cls), "subName": subclass_name(cls, sub),
        "slot": INV_SHORT.get(inv, "") if inv else "", "inventoryType": label("InventoryType", inv).replace("_", " ").title() if inv else "",
        "armor": computed_armor(level, quality, inv, cls, sub), "speed": int(num(sp["ItemDelay"])) / 1000 if weapon else 0,
        "stats": [{"id": t, "name": stat_name(t), "value": v} for t, v in stats],
        "effects": _effects(item_id), "classes": classes, "races": races_,
        "description": sp["Description_lang"], "sell": money(sp["SellPrice"]), "maxCount": int(num(sp["MaxCount"])),
        "stack": int(num(sp["Stackable"])), "requiresSkill": int(num(sp["RequiredSkill"])) or None,
        "skillName": (scalar("select DisplayName_lang from SkillLine where ID=?", (sp["RequiredSkill"],)) if num(sp["RequiredSkill"]) else None),
        "skillRank": int(num(sp["RequiredSkillRank"])), "junk": _junk(sp["Display_lang"]),
        "unique": int(num(sp["MaxCount"])) == 1 and cls != 12,
    }


# ---- lists ----
_ROWS = None


def _all_rows():
    """Every named, non-junk item: [id, name, quality, item level, required level, origin, icon, cls, sub, inventory type]."""
    global _ROWS
    if _ROWS is None:
        ic = icons()
        out = []
        for r in q("select s.ID id, s.Display_lang name, s.OverallQualityID qual, s.ItemLevel lvl, s.RequiredLevel req, o.Origin origin, "
                   "i.IconFileDataID icon, i.ClassID cls, i.SubclassID sub, s.InventoryType inv "
                   "from ItemSparse s join Item i on i.ID=s.ID join ItemOrigin o on o.ItemID=s.ID where s.Display_lang != ''"):
            if _junk(r["name"]):
                continue
            out.append([int(r["id"]), r["name"], int(num(r["qual"])), int(num(r["lvl"])), int(num(r["req"])), r["origin"], ic.get(r["icon"]),
                        int(r["cls"]), int(r["sub"]), int(num(r["inv"]))])
        out.sort(key=lambda x: (x[4], x[3], x[1], x[0]))
        _ROWS = out
    return _ROWS


def _visible(rows_, show_sod):
    return rows_ if show_sod else [r for r in rows_ if r[5] != "sod"]


def tree(show_sod=False):
    """Navigation: [{cls, name, count, subs: [{sub, name, count}]}] over the visible items."""
    counts = {}
    for r in _visible(_all_rows(), show_sod):
        counts[(r[7], r[8])] = counts.get((r[7], r[8]), 0) + 1
    out = []
    for cls in sorted({c for c, _ in counts}):
        subs = [{"sub": s, "name": subclass_name(cls, s), "count": n} for (c, s), n in sorted(counts.items()) if c == cls]
        out.append({"cls": cls, "name": class_name(cls), "count": sum(s["count"] for s in subs), "subs": subs})
    return out


def list_rows(cls, sub):
    """Every item of one type, SoD included (the static export writes this; callers filter)."""
    return [r for r in _all_rows() if r[7] == int(cls) and r[8] == int(sub)]


def _dict(r):
    return {"id": r[0], "name": r[1], "quality": r[2], "level": r[3], "reqLevel": r[4], "origin": r[5], "icon": r[6], "slot": INV_SHORT.get(r[9], "")}


def listing(cls, sub, text="", offset=0, limit=MAX_LIST, show_sod=False):
    rows_ = _visible(list_rows(cls, sub), show_sod)
    t = text.strip().lower()
    if t:
        rows_ = [r for r in rows_ if t in r[1].lower() or t == str(r[0])]
    return {"total": len(rows_), "offset": offset, "items": [_dict(r) for r in rows_[offset:offset + limit]]}


def search_index():
    """[id, name, origin, quality] for every listed item, for the static site's search."""
    rows_ = sorted(_all_rows(), key=lambda r: (r[1], r[0]))
    return [[r[0], r[1], r[5], r[2]] for r in rows_]


def search(text, show_sod=False, limit=25):
    text = text.strip()
    if not text:
        return []
    if text.isdigit():
        r = q1("select s.ID id, s.Display_lang name, o.Origin origin, s.OverallQualityID qual from ItemSparse s join ItemOrigin o on o.ItemID=s.ID where s.ID=?", (text,))
        return [{"id": int(r["id"]), "name": r["name"], "origin": r["origin"], "quality": int(num(r["qual"]))}] if r and r["name"] else []
    t = text.lower()
    hits = [r for r in _visible(_all_rows(), show_sod) if t in r[1].lower()]
    hits.sort(key=lambda r: (r[1], r[0]))
    return [{"id": r[0], "name": r[1], "origin": r[5], "quality": r[2]} for r in hits[:limit]]


def tip_from(it):
    """The hover summary of an item() result."""
    return {k: it[k] for k in ("id", "name", "quality", "qualityName", "level", "reqLevel", "icon", "origin", "bonding", "slot", "subName", "className",
                               "armor", "speed", "stats", "classes", "races", "description")} | {
        "effects": [{"how": e["how"], "text": e["text"] or e["name"]} for e in it["effects"]]}


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


def weapon_types(effects, equipped, attrs_ranged):
    """For a spell with a weapon-damage effect: the weapon types it uses, as [{weapon, sub}] (each links to that weapon list)."""
    if not any(is_weapon_damage(int(num(e.get("Effect")))) for e in effects):
        return []
    subs = set()
    for r in equipped:
        if r.get("EquippedItemClass") == "2":
            mask = int(num(r.get("EquippedItemSubclass")))
            subs |= {b for b in range(21) if mask >> b & 1}
    if not subs and attrs_ranged:
        subs = {2, 3, 18}
    return [{"weapon": subclass_name(2, s), "sub": s} for s in sorted(subs)]


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
