"""Paths, build numbers and the list of DB2 tables the app depends on."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CSV_DIR = DATA / "csv"            # raw wago.tools tables for BUILD
ORIGIN_DIR = DATA / "origins"     # SpellName tables of the reference builds (vanilla / SoD)
REF_DIR = DATA / "reference"      # icons.json, flags.json (generated from public sources)
CACHE_DIR = DATA / "cache"        # downloaded headers etc.
DB_PATH = DATA / "spells.db"
WEB_DIR = ROOT / "web"

# The client this database describes (Classic beta, product wow_classic_beta).
BUILD = "1.60.1.69913"

# Reference builds used to decide where a spell came from:
#   in PRE_SOD_BUILD                     -> "vanilla"  (existed before Season of Discovery)
#   in SOD_ERA_BUILD but not in PRE_SOD  -> "sod"      (added by Season of Discovery, 1.15.0 onwards)
#   in neither (only in BUILD)           -> "new"      (introduced by the beta itself)
PRE_SOD_BUILD = "1.14.4.51829"    # last Classic Era client before SoD launched (1.15.0, Nov 2023)
SOD_ERA_BUILD = "1.15.9.69722"    # latest Era client; contains every SoD phase

WAGO_CSV = "https://wago.tools/db2/{table}/csv?build={build}"
LISTFILE_URL = "https://github.com/wowdev/wow-listfile/releases/latest/download/community-listfile.csv"
TC_RAW = "https://raw.githubusercontent.com/TrinityCore/TrinityCore/master/src/server/game/"
TC_HEADERS = ["Spells/SpellDefines.h", "Spells/SpellMgr.h", "Spells/Auras/SpellAuraDefines.h",
              "Miscellaneous/SharedDefines.h", "Entities/Item/ItemTemplate.h"]

SPELL_TABLES = [
    "Spell", "SpellName", "SpellMisc", "SpellEffect", "SpellCooldowns", "SpellPower", "SpellCategories",
    "SpellCastTimes", "SpellDuration", "SpellRange", "SpellRadius", "SpellLevels", "SpellAuraOptions",
    "SpellClassOptions", "SpellXSpellVisual", "SpellDescriptionVariables", "SpellCastingRequirements",
    "SpellReagents", "SpellInterrupts", "SpellEquippedItems", "SpellLabel", "SpellShapeshift",
    "SpellShapeshiftForm", "SpellTargetRestrictions", "SpellProceduralEffect", "SpellItemEnchantment",
    "SkillLine", "SkillLineAbility", "ChrRaces", "ChrClasses", "ChrSpecialization",
    "Talent", "TalentTab",        # the classic-style talent table: every rank of every talent, per class tab
]
TALENT_TABLES = [
    "TraitTree", "TraitNode", "TraitNodeEntry", "TraitNodeGroup", "TraitNodeGroupXTraitNode",
    "TraitNodeXTraitNodeEntry", "TraitNodeXTraitCond", "TraitNodeGroupXTraitCond", "TraitEdge",
    "TraitDefinition", "TraitDefinitionEffectPoints", "TraitCond", "TraitCost", "TraitCurrency",
    "TraitCurrencySource", "TraitTreeXTraitCurrency", "TraitSystem", "Curve", "CurvePoint",
]
ITEM_TABLES = [
    "Item", "ItemSparse", "ItemClass", "ItemSubClass", "ItemEffect", "ItemXItemEffect",   # items, their types, the spells they cast
    "RandPropPoints", "ItemArmorTotal", "ItemArmorQuality", "ItemArmorShield", "ArmorLocation",   # stat budgets and armor (verified)
]
TABLES = SPELL_TABLES + TALENT_TABLES + ITEM_TABLES

MAX_LEVEL = 60        # level used when scaling $s tokens (EffectRealPointsPerLevel)
PORT = 8765
