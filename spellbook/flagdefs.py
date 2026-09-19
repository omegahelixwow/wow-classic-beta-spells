"""Build-time: turn TrinityCore's public enum headers into data/reference/flags.json (names for every flag/enum)."""
import json, re, urllib.request

from . import config as C

# enum -> (header file, prefix to strip)
WANT = {
    **{f"SpellAttr{i}": ("SharedDefines.h", f"SPELL_ATTR{i}_") for i in range(17)},
    "ProcFlags": ("SpellMgr.h", "PROC_FLAG_"), "ProcFlags2": ("SpellMgr.h", "PROC_FLAG_2_"),
    "SpellInterruptFlags": ("SpellDefines.h", ""), "SpellAuraInterruptFlags": ("SpellDefines.h", ""),
    "SpellAuraInterruptFlags2": ("SpellDefines.h", ""), "SpellCastTargetFlags": ("SpellDefines.h", "TARGET_FLAG_"),
    "AuraType": ("SpellAuraDefines.h", "SPELL_AURA_"), "SpellEffects": ("SharedDefines.h", "SPELL_EFFECT_"),
    "Targets": ("SharedDefines.h", "TARGET_"), "Mechanics": ("SharedDefines.h", "MECHANIC_"),
    "DispelType": ("SharedDefines.h", "DISPEL_"),
    "SpellModOp": ("SpellDefines.h", ""),
    "ItemModType": ("ItemTemplate.h", "ITEM_MOD_"), "InventoryType": ("ItemTemplate.h", "INVTYPE_"),
    "ItemBondingType": ("ItemTemplate.h", "BIND_"),                # item stat type / slot / binding names               # what a class-mask modifier aura changes (cast time, cooldown, cost ...)
}
LINE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(0x[0-9A-Fa-f]+|\d+)\s*,?\s*(?://\s*(.*))?$")


def download_headers(force=False):
    d = C.CACHE_DIR / "tc"
    d.mkdir(parents=True, exist_ok=True)
    for h in C.TC_HEADERS:
        dest = d / h.rsplit("/", 1)[1]
        if force or not dest.exists():
            req = urllib.request.Request(C.TC_RAW + h, headers={"User-Agent": "spellbook build"})
            dest.write_bytes(urllib.request.urlopen(req, timeout=120).read())
    return d


def generate(src_dir=None):
    src = src_dir or C.CACHE_DIR / "tc"
    out = {}
    for enum, (file, prefix) in WANT.items():
        txt = (src / file).read_text(encoding="utf-8")
        m = re.search(rf"enum (?:class )?{enum}\b[^{{;]*\{{(.*?)\n\}};", txt, re.S)
        if not m:
            print("  flags: enum not found:", enum)
            continue
        items = []
        for ln in m.group(1).splitlines():
            r = LINE.match(ln)
            if not r:
                continue
            name, val, comment = r.group(1), int(r.group(2), 0), r.group(3) or ""
            title, desc = None, ""
            t = re.match(r"TITLE (.*?)(?: DESCRIPTION (.*))?$", comment)   # TrinityCore's "TITLE x DESCRIPTION y" comments
            if t:
                title, desc = t.group(1), t.group(2) or ""
            elif comment:
                desc = comment
            items.append([val, name[len(prefix):] if name.startswith(prefix) else name, title, desc])
        out[enum] = items
    C.REF_DIR.mkdir(parents=True, exist_ok=True)
    (C.REF_DIR / "flags.json").write_text(json.dumps(out, indent=0))
    return {k: len(v) for k, v in out.items()}
