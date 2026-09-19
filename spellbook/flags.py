"""Runtime: turn flag masks / enum values into the names TrinityCore uses (data/reference/flags.json)."""
import functools, json

from . import config as C


@functools.lru_cache(maxsize=None)
def _by_value():
    data = json.loads((C.REF_DIR / "flags.json").read_text())
    return {enum: {v[0]: v for v in items} for enum, items in data.items()}


def label(enum, val, dflt="?"):
    """Name of one enum value, e.g. label('AuraType', 4) -> 'DUMMY'."""
    v = _by_value().get(enum, {}).get(int(val))
    return v[1] if v else f"{dflt}_{val}"


def decode(enum, mask):
    """Set bits of `mask` -> [{bit, hex, name, title, desc}]. Bits without a public name are named UNK_0x..."""
    mask = int(mask or 0)
    table = _by_value().get(enum, {})
    out = []
    for bit in range(32):
        if mask >> bit & 1:
            v = table.get(1 << bit)
            out.append({"bit": bit, "hex": hex(1 << bit), "name": v[1] if v else f"UNK_{hex(1 << bit)}",
                        "title": v[2] if v else None, "desc": v[3] if v else ""})
    return out
