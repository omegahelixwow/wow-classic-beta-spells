#!/usr/bin/env python3
"""Start the spell browser:  python3 run.py [--port 8765]   (build the database first with build.py)."""
import argparse, sys

from spellbook import config as C, server

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=C.PORT)
    args = ap.parse_args()
    if not C.DB_PATH.exists():
        sys.exit("data/spells.db not found - run: python3 build.py")
    server.serve(args.port)
