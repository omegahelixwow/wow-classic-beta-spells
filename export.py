#!/usr/bin/env python3
"""Write the static site (for GitHub Pages):  python3 export.py [--out dist]   (run build.py first)."""
import argparse, sys

from spellbook import config as C, export_static

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(C.ROOT / "dist"), help="output folder (replaced if it exists)")
    ap.add_argument("--site-only", action="store_true", help="only refresh the page code (web/*) in an existing export")
    args = ap.parse_args()
    if not args.site_only and not C.DB_PATH.exists():
        sys.exit("data/spells.db not found - run: python3 build.py")
    export_static.export(args.out, site_only=args.site_only)
