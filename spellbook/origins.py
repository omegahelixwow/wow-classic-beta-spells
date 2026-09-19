"""Build-time: decide where each spell came from, by comparing spell ids across client builds.

    vanilla : the spell already existed in the last pre-Season-of-Discovery Classic Era client
    sod     : it first appears in the SoD-era client (1.15.0+) and was not there before
    new     : it exists in neither Era client -- it was introduced by this beta

Comparing builds is deliberately used instead of an id range: some SoD spells reuse low ids (Earth Shield 974,
Prayer of Mending 41637...) and some vanilla spells have ids above 400000, so id ranges misclassify ~150 spells.
"""
import csv, sqlite3

from . import config as C


def _ids(path):
    with open(path, encoding="utf-8", newline="") as fh:
        r = csv.reader(fh)
        next(r)
        return {row[0] for row in r}


def build(con):
    pre = _ids(C.ORIGIN_DIR / f"SpellName_{C.PRE_SOD_BUILD}.csv")
    sod_era = _ids(C.ORIGIN_DIR / f"SpellName_{C.SOD_ERA_BUILD}.csv")
    rows = []
    for (sid,) in con.execute("select ID from SpellName"):
        origin = "vanilla" if sid in pre else "sod" if sid in sod_era else "new"
        rows.append((sid, origin))
    con.execute("drop table if exists SpellOrigin")
    con.execute("create table SpellOrigin (SpellID text primary key, Origin text)")
    con.executemany("insert into SpellOrigin values (?,?)", rows)
    con.execute("create index i_origin on SpellOrigin(Origin)")
    con.commit()
    return {o: n for o, n in con.execute("select Origin, count(*) from SpellOrigin group by Origin")}
