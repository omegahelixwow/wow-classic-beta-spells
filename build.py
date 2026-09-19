#!/usr/bin/env python3
"""Build data/spells.db from wago.tools tables.

    python3 build.py             fetch anything missing, then rebuild the database
    python3 build.py --offline   rebuild from the files already in data/ (no network)
    python3 build.py --refetch   re-download everything first

Stop the web server before rebuilding (the database file is replaced).
"""
import argparse, os, sqlite3, sys, time

from spellbook import classify, config as C, db, fetch, load, origins


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="do not download anything")
    ap.add_argument("--refetch", action="store_true", help="re-download every source file")
    args = ap.parse_args()
    t0 = time.time()

    if not args.offline:
        print(f"[1/4] fetching sources for build {C.BUILD} ...")
        missing = fetch.all(force=args.refetch)
        if missing:
            print("      not available for this build (skipped):", ", ".join(missing))
    else:
        print("[1/4] offline: using the files already in data/")

    tmp = C.DB_PATH.with_suffix(".db.new")
    print("[2/4] loading tables into SQLite ...")
    rows = load.build(tmp)
    print(f"      {rows:,} rows")

    db.use(tmp)                                   # the runtime modules the classifier uses must read the new file
    con = sqlite3.connect(tmp)
    print("[3/4] spell origins (vanilla / SoD / new) ...")
    print("     ", origins.build(con))
    print("[4/4] classifying ...")
    print("     ", classify.build(con))

    print("\nsummary")
    for cat, n, linked in con.execute("select Cat, count(distinct SpellID), sum(Linked) from Classification group by Cat order by 2 desc"):
        print(f"  {cat:20} {n:6,}  ({linked} linked)")
    print("  spells in the lists, by origin (SoD is hidden by default in the app):")
    for o, n in con.execute("select o.Origin, count(distinct c.SpellID) from Classification c join SpellOrigin o on o.SpellID=c.SpellID "
                            "join SpellName n on n.ID=c.SpellID group by o.Origin"):
        print(f"    {o:8} {n:6,}")
    con.close()
    db.use(C.DB_PATH)
    os.replace(tmp, C.DB_PATH)
    print(f"\ndone in {time.time() - t0:.0f}s -> {C.DB_PATH}")


if __name__ == "__main__":
    sys.exit(main())
