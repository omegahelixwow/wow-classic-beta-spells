"""Resolve the $-tokens in spell text: $s1 $m1 $o1 $t1 $d $a1 $x $h, $<spell>s1 cross references,
${expr}, "$/1000;S1" divisors and $lsingular:plural; forms. Values are scaled to MAX_LEVEL.
Talent ranks pass `overrides` ({effect number: value}) to replace the spell's own numbers."""
import math, re

from . import config as C
from .db import fmt_ms, num, one, rows

_effects = {}


def effects_of(spell_id):
    k = str(spell_id)
    if k not in _effects:
        _effects[k] = sorted(rows("SpellEffect", "SpellID", k), key=lambda e: int(e.get("EffectIndex") or 0))
    return _effects[k]


def duration_of(spell_id):
    misc = (rows("SpellMisc", "SpellID", spell_id) or [{}])[0]
    return int(num((one("SpellDuration", misc.get("DurationIndex", "0")) or {}).get("Duration")))


def eff_points(spell_id, n, level=C.MAX_LEVEL, overrides=None):
    """Base points of effect n (1-based), scaled by EffectRealPointsPerLevel up to the spell's MaxLevel / `level`."""
    if overrides and n in overrides:
        return overrides[n]
    es = effects_of(spell_id)
    if not 1 <= n <= len(es):
        return None
    e = es[n - 1]
    v = num(e.get("EffectBasePointsF"))
    per = num(e.get("EffectRealPointsPerLevel"))
    if per:
        lv = (rows("SpellLevels", "SpellID", spell_id) or [{}])[0]
        base = int(num(lv.get("BaseLevel"), 1)) or int(num(lv.get("SpellLevel"), 1)) or 1
        cap = int(num(lv.get("MaxLevel"))) or level
        v += per * max(0, min(level, cap) - base)
        v = math.ceil(v - 1e-9) if v >= 0 else -math.ceil(-v - 1e-9)
    return v


def _fmt(v):
    return f"{v:g}" if abs(v - round(v)) > 1e-9 else str(int(round(v)))


def render(text, sid, proc_chance=0, overrides=None):
    if not text:
        return ""

    def val(ref, kind, n):
        target = ref or sid
        es = effects_of(target)
        ov = overrides if str(target) == str(sid) else None
        per = int(num(es[n - 1].get("EffectAuraPeriod"))) if 1 <= n <= len(es) else 0
        if kind in "smSM":
            v = eff_points(target, n, overrides=ov)
            return None if v is None else abs(v)
        if kind == "o":
            v = eff_points(target, n, overrides=ov)
            d = duration_of(target)
            return None if v is None or not per or d <= 0 else abs(v) * (d / per)
        if kind == "t":
            return per / 1000 if per else None
        if kind == "d":
            d = duration_of(target)
            return d / 1000 if d > 0 else None
        if kind == "x":
            return int(num(es[n - 1].get("EffectChainTargets"))) if 1 <= n <= len(es) else None
        return None

    tok = re.compile(r"\$(?:([/*])(\d+);)?(\d+)?([smSMotadx])(\d)?")

    def sub(m):
        op, opn, ref, kind, n = m.group(1), m.group(2), m.group(3), m.group(4), int(m.group(5) or 1)
        if kind == "a":                                                  # radius in yards
            es = effects_of(ref or sid)
            idx = es[n - 1].get("EffectRadiusIndex_0") if 1 <= n <= len(es) else None
            r = one("SpellRadius", idx) if idx not in (None, "", "0") else None
            return _fmt(num(r["Radius"])) if r else m.group(0)
        if kind == "d":                                                  # duration with units
            d = duration_of(ref or sid)
            return fmt_ms(d) if d > 0 else m.group(0)
        v = val(ref, kind, n)
        if v is None:
            return m.group(0)
        if op:                                                           # "$/1000;S1" divides, "$*N;" multiplies
            v = v / int(opn) if op == "/" else v * int(opn)
        return _fmt(v)

    def expr(m):                                                         # ${ $s1 * 2 }
        def var(mm):
            v = val(mm.group(1), mm.group(2), int(mm.group(3) or 1))
            return "0" if v is None else repr(v)
        e = re.sub(r"\$(\d+)?([smSMotdx])(\d)?", var, m.group(1))
        if not re.fullmatch(r"[0-9.+\-*/() ]+", e):
            return m.group(0)
        try:
            return _fmt(eval(e, {"__builtins__": {}}))
        except Exception:
            return m.group(0)

    t = re.sub(r"\$\{([^{}]*)\}(?:\.(\d))?", expr, text)
    t = tok.sub(sub, t)
    t = re.sub(r"\$[hH](\d*)", (f"{proc_chance:g}" if proc_chance else "$h"), t)

    def plural(m):                                                       # $lsingular:plural; agrees with the number before it
        prev = re.findall(r"[\d.]+", t[:m.start()])
        return m.group(1) if prev and num(prev[-1]) == 1 else m.group(2)
    return re.sub(r"\$l([^:;]*):([^;]*);", plural, t)
