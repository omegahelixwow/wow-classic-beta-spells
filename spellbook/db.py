"""Database access: one read connection per thread, plus small helpers shared by every module."""
import functools, json, sqlite3, threading
from pathlib import Path

from . import config as C

_path = C.DB_PATH
_local = threading.local()


_bulk = None            # None: query per call. A dict: whole tables are indexed in memory (static export)


def bulk(on=True):
    """Bulk mode makes rows()/one()/first() dictionary lookups instead of queries -- ~100x faster when every spell is rendered."""
    global _bulk
    _bulk = {} if on else None


def use(path):
    """Point the app at another database file (the build uses this to work on the file it is writing)."""
    global _path, _local, _bulk
    _bulk = None
    _path = Path(path)
    _local = threading.local()
    for fn in (columns, classes, races, skills, icons):
        fn.cache_clear()


def conn():
    c = getattr(_local, "c", None)
    if c is None:
        c = sqlite3.connect(_path)
        c.row_factory = sqlite3.Row
        _local.c = c
    return c


def q(sql, args=()):
    """All rows as dicts."""
    return [dict(r) for r in conn().execute(sql, args)]


def q1(sql, args=()):
    r = conn().execute(sql, args).fetchone()
    return dict(r) if r else None


def scalar(sql, args=()):
    r = conn().execute(sql, args).fetchone()
    return r[0] if r else None


@functools.lru_cache(maxsize=None)
def columns(table):
    return tuple(r[1] for r in conn().execute(f'pragma table_info("{table}")'))


def rows(table, key, val):
    """Rows of `table` where `key` equals `val` (all columns are text in this database)."""
    if key not in columns(table):
        return []
    if _bulk is not None:
        idx = _bulk.get((table, key))
        if idx is None:
            idx = {}
            for r in conn().execute(f'select * from "{table}"'):
                d = dict(r)
                idx.setdefault(d[key], []).append(d)
            _bulk[(table, key)] = idx
        return idx.get(str(val), [])
    return q(f'select * from "{table}" where "{key}"=?', (str(val),))


def one(table, id_):
    r = rows(table, "ID", id_)
    return r[0] if r else None


def first(table, key, val):
    r = rows(table, key, val)
    return r[0] if r else {}


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def nz(d):
    """Drop empty / zero fields."""
    return {k: v for k, v in d.items() if v not in ("", "0", 0)}


def fmt_ms(ms):
    ms = int(num(ms))
    if ms <= 0:
        return None
    return f"{ms / 1000:g} sec" if ms < 60000 else f"{ms / 60000:g} min"


# ---- small lookup tables, loaded once ----
@functools.lru_cache(maxsize=None)
def classes():
    return {int(r["ID"]): r["Name_lang"] for r in q("select ID, Name_lang from ChrClasses")}


@functools.lru_cache(maxsize=None)
def races():
    return {int(r["ID"]): r["Name_lang"] for r in q("select ID, Name_lang from ChrRaces")}


@functools.lru_cache(maxsize=None)
def skills():
    return {r["ID"]: r["DisplayName_lang"] for r in q("select ID, DisplayName_lang from SkillLine")}


@functools.lru_cache(maxsize=None)
def icons():
    p = C.REF_DIR / "icons.json"
    return json.loads(p.read_text()) if p.exists() else {}


def icon_of(spell_id):
    r = conn().execute("select SpellIconFileDataID from SpellMisc where SpellID=? limit 1", (str(spell_id),)).fetchone()
    return icons().get(r[0]) if r else None


def class_names(mask):
    return [n for i, n in classes().items() if mask & (1 << (i - 1))]
