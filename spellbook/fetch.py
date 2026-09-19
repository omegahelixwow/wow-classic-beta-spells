"""Build-time: download everything the database is built from. Existing files are kept unless force=True."""
import io, json, time, urllib.error, urllib.request

from . import config as C, flagdefs

HEADERS = {"User-Agent": "Mozilla/5.0 (spellbook build)"}


def _open(url, timeout=300):
    return urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=timeout)


def wago_table(table, build, dest, force=False):
    """Download one DB2 table as CSV. Returns False when wago has no such table for that build."""
    if dest.exists() and not force:
        return True
    for attempt in range(4):                                  # wago rate-limits bursts: back off and retry on anything but "no such table"
        try:
            data = _open(C.WAGO_CSV.format(table=table, build=build)).read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return False
            time.sleep(2 ** attempt * 3)
            continue
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 ** attempt * 3)
            continue
        if data.lstrip().startswith(b'{"errors"'):
            return False
        dest.write_bytes(data)
        return True
    return False


def tables(force=False):
    C.CSV_DIR.mkdir(parents=True, exist_ok=True)
    missing = []
    for t in C.TABLES:
        if not wago_table(t, C.BUILD, C.CSV_DIR / f"{t}.csv", force):
            missing.append(t)
    return missing


def origin_tables(force=False):
    """SpellName and Item of the two reference builds (vanilla / SoD-era) -- only the ids are used."""
    C.ORIGIN_DIR.mkdir(parents=True, exist_ok=True)
    for b in (C.PRE_SOD_BUILD, C.SOD_ERA_BUILD):
        for table in ("SpellName", "Item"):
            if not wago_table(table, b, C.ORIGIN_DIR / f"{table}_{b}.csv", force):
                raise RuntimeError(f"{table} for build {b} is not available on wago.tools")


def icons(force=False):
    """FileDataID -> icon name, from the community listfile (streamed; only interface/icons/* is kept)."""
    dest = C.REF_DIR / "icons.json"
    if dest.exists() and not force:
        return
    C.REF_DIR.mkdir(parents=True, exist_ok=True)
    out = {}
    for line in io.TextIOWrapper(_open(C.LISTFILE_URL, 900), encoding="utf-8"):
        fid, _, path = line.rstrip("\n").partition(";")
        if path.startswith("interface/icons/") and path.endswith(".blp"):
            out[fid] = path[len("interface/icons/"):-4]
    dest.write_text(json.dumps(out))


def flags(force=False):
    if (C.REF_DIR / "flags.json").exists() and not force:
        return
    flagdefs.download_headers(force)
    flagdefs.generate()


def all(force=False):
    missing = tables(force)
    origin_tables(force)
    icons(force)
    flags(force)
    return missing
