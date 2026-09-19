"""Resolve the $-tokens in spell text: $s1 $m1 $o1 $t1 $d $a1 $x $h, $<spell>s1 cross references,
${expr}, "$/1000;S1" divisors and $lsingular:plural; forms. Values are scaled to MAX_LEVEL.
Talent ranks pass `overrides` ({effect number: value}) to replace the spell's own numbers."""
import ast, math, re

from . import config as C
from .db import fmt_ms, num, one, rows, scalar

_effects = {}

# Player stats that spell text refers to ($SPI, $AP ...). They depend on the caster, so they stay symbolic.
STATS = {"spi": "Spirit", "int": "Intellect", "str": "Strength", "agi": "Agility", "sta": "Stamina",
         "ap": "Attack Power", "rap": "Ranged Attack Power", "sp": "Spell Power", "mwb": "weapon damage", "pl": "your level",
         "sph": "Holy Spell Power", "spf": "Fire Spell Power", "spn": "Nature Spell Power", "spa": "Arcane Spell Power",
         "sps": "Shadow Spell Power"}
STAT_RE = re.compile(r"\$(" + "|".join(sorted(STATS, key=len, reverse=True)) + r")(?![A-Za-z])", re.I)


def _lin(node):
    """Evaluate an arithmetic expression whose unknowns are player stats, as a linear form {stat or '': coefficient}."""
    def const(x):
        return all(k == "" for k in x)

    def scale(x, f):
        return {k: v * f for k, v in x.items()}
    if isinstance(node, ast.Expression):
        return _lin(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return {"": float(node.value)}
    if isinstance(node, ast.Name) and node.id.startswith("V_"):
        return {node.id[2:].lower(): 1.0}
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return scale(_lin(node.operand), -1 if isinstance(node.op, ast.USub) else 1)
    if isinstance(node, ast.BinOp):
        a, b = _lin(node.left), _lin(node.right)
        if isinstance(node.op, (ast.Add, ast.Sub)):
            out, sign = dict(a), 1 if isinstance(node.op, ast.Add) else -1
            for k, v in b.items():
                out[k] = out.get(k, 0.0) + sign * v
            return out
        if isinstance(node.op, ast.Mult) and (const(a) or const(b)):
            return scale(b, a[""]) if const(a) else scale(a, b[""])
        if isinstance(node.op, ast.Div) and const(b) and b.get("", 0):
            return scale(a, 1 / b[""])
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("abs", "max", "min") and node.args:
        vals = [_lin(x) for x in node.args]
        if all(const(v) for v in vals):
            f = {"abs": abs, "max": max, "min": min}[node.func.id]
            return {"": float(f(*[v.get("", 0.0) for v in vals]))}
    raise ValueError("not a linear stat expression")


def _lin_text(lin):
    """{'': 30, 'spi': 1} -> "(30 + Spirit)";  {'ap': 0.3} -> "30% of Attack Power";  {'': 5} -> "5"."""
    terms = [(k, v) for k, v in lin.items() if k and abs(v) > 1e-12]
    const = lin.get("", 0.0)
    if not terms:
        return _fmt(const)
    parts = [_fmt(const)] if abs(const) > 1e-12 else []
    for k, v in terms:
        name = STATS.get(k, k)
        parts.append(name if v == 1 else f"{_fmt(v * 100)}% of {name}" if 0 < v < 10 else f"{_fmt(v)}×{name}")
    text = " + ".join(parts).replace("+ -", "- ")
    return f"({text})" if len(parts) > 1 else text


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


def render(text, sid, proc_chance=0, overrides=None, _depth=0):
    if not text:
        return ""

    def val(ref, kind, n):
        target = ref or sid
        es = effects_of(target)
        ov = overrides if str(target) == str(sid) else None
        per = int(num(es[n - 1].get("EffectAuraPeriod"))) if 1 <= n <= len(es) else 0
        if kind in "smSMwW":                                             # $w = an aura effect's points: same number as $s
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

    tok = re.compile(r"\$(?:([/*])(\d+);)?(\d+)?([smSMwWotadx])(\d)?(?![A-Za-z])")

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

    def expr(m):                                                         # ${ $s1 * 2 }  /  ${ ($m1 + $SPI) * 1.5 }
        inner = re.sub(r"\$(abs|max|min)\(", r"\1(", m.group(1))
        inner = STAT_RE.sub(lambda mm: "V_" + mm.group(1).upper(), inner)        # before $s / $m, or "$SPI" is misread as "$S"

        def var(mm):
            v = val(mm.group(1), mm.group(2), int(mm.group(3) or 1))
            return "0" if v is None else repr(v)
        e = re.sub(r"\$(\d+)?([smSMwWotdx])(\d)?", var, inner)
        try:
            return _lin_text(_lin(ast.parse(e.strip(), mode="eval")))
        except (SyntaxError, ValueError, ZeroDivisionError):
            return m.group(0)                                            # leave anything we cannot evaluate as written

    t = re.sub(r"\$\{([^{}]*)\}(?:\.(\d))?", expr, text)

    # $@spellname<id> is that spell's name, $@spelldesc<id> its description (resolved in turn; depth-limited against loops)
    def other_spell(m):
        kind, target = m.group(1), m.group(2)
        if kind == "name":
            return scalar("select Name_lang from SpellName where ID=?", (target,)) or m.group(0)
        d = scalar("select Description_lang from Spell where ID=?", (target,))
        return render(d, target, 0, None, _depth + 1) if d and _depth < 3 else m.group(0)
    t = re.sub(r"\$@spell(name|desc)(\d+)", other_spell, t)

    # Every later step works only on the text *outside* a ${...} block: one that could not be evaluated is left exactly as written.
    def outside(fn, text):
        return "".join(p if p.startswith("${") else fn(p) for p in re.split(r"(\$\{[^{}]*\})", text))
    t = outside(lambda p: STAT_RE.sub(lambda mm: f"[{STATS[mm.group(1).lower()]}]", p), t)   # a bare $AP / $SPI
    t = outside(lambda p: tok.sub(sub, p), t)
    t = outside(lambda p: re.sub(r"\$[hH](\d*)", (f"{proc_chance:g}" if proc_chance else "$h"), p), t)

    def plural(m):                                                       # $lsingular:plural; agrees with the number before it
        prev = re.findall(r"[\d.]+", t[:m.start()])
        return m.group(1) if prev and num(prev[-1]) == 1 else m.group(2)
    return re.sub(r"\$l([^:;]*):([^;]*);", plural, t)
