#!/usr/bin/env python3
"""
PvP IV rank calculator (Great / Ultra / Master League).

Base stats and the CP multiplier table come from https://iv4u.lima-city.de
(list/list.js and cpm.js). They are downloaded once and cached in
data/cache/iv_data.json. Ranks are computed locally: for each of the 4096 IV
combinations the highest level (<= the level cap) that keeps CP under the
league limit is found, and combinations are ordered by stat product
(attack x defense x floor(HP)). Equal stat products share a rank.

    python ivrank.py charizard 0 15 14
"""
import json
import re
import sys
from functools import lru_cache
from pathlib import Path

import requests

BASE = "https://iv4u.lima-city.de"
USER_AGENT = "pogo-tier-script/1.0 (personal use, low volume)"
LEAGUES = [("great", "Great League", 1500), ("ultra", "Ultra League", 2500),
           ("master", "Master League", None)]
LEVEL_CAPS = (40, 41, 50, 51)
DEFAULT_CAP = 50
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "cache" / "iv_data.json"

_ROW_RE = re.compile(r'^\[(\d+),(\d+),"([^"]*)","([^"]*)",(\d+),(\d+),(\d+),"([^"]*)","([^"]*)","[^"]*",\d+,\d+,"([^"]*)"',
                     re.M)


def _get(path):
    r = requests.get(f"{BASE}/{path}", headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def build_data():
    """Download base stats + CP multipliers and cache them."""
    cpm_js = _get("cpm.js")
    m = re.search(r"var cpm\s*=\s*\[([^\]]+)\]", cpm_js)
    if not m:
        raise RuntimeError("couldn't find the CP multiplier table on iv4u")
    cpm = [float(x) for x in m.group(1).split(",")]

    mons = []
    for row in _ROW_RE.finditer(_get("list/list.js")):
        _, dex, _de, en, a, d, s, _t1, _t2, fam = row.groups()
        if en.startswith(("Mega ", "Primal ")):      # can't battle in PvP
            continue
        mons.append({"id": int(dex), "name": en,
                     "atk": int(a), "def": int(d), "sta": int(s),
                     "family": [int(x) for x in fam.split(",") if x]})
    if len(mons) < 500:
        raise RuntimeError(f"only parsed {len(mons)} Pokémon from iv4u; the page format may have changed")
    data = {"cpm": cpm, "mons": mons}
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


@lru_cache(maxsize=1)
def load_data(refresh=False):
    if DATA_FILE.exists() and not refresh:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return build_data()


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower().replace("é", "e"))


def find_mons(query):
    """Match by exact name, Pokédex number (all forms), or unique prefix/substring."""
    q = query.strip()
    mons = load_data()["mons"]
    if q.isdigit():
        return [m for m in mons if m["id"] % 10000 == int(q)]
    n = norm(q)
    exact = [m for m in mons if norm(m["name"]) == n]
    if exact:       # "raichu" also finds "Alolan Raichu"
        forms = [m for m in mons if m not in exact and m["name"].lower().endswith(" " + q.lower())]
        return exact + forms
    return [m for m in mons if n and n in norm(m["name"])]


@lru_cache(maxsize=512)
def _table(atk, dfn, sta, cap_cpm_idx):
    """Per league: list of 4096 (stat_product, level, cp) indexed by a*256+d*16+s."""
    cpm = load_data()["cpm"]
    out = {}
    for key, _label, cp_cap in LEAGUES:
        rows = []
        for ia in range(16):
            for idf in range(16):
                for ist in range(16):
                    A, D, S = atk + ia, dfn + idf, sta + ist
                    best = None
                    for i in range(cap_cpm_idx, -1, -1):       # highest level first
                        c = cpm[i]
                        cp = max(10, int(A * (D * S) ** 0.5 * c * c / 10))
                        if cp_cap is None or cp <= cp_cap:
                            best = i
                            break
                    if best is None:                            # can't get under the cap at all
                        best = 0
                    c = cpm[best]
                    cp = max(10, int(A * (D * S) ** 0.5 * c * c / 10))
                    sp = round((A * c) * (D * c) * int(S * c), 2)   # rounding merges float-noise ties
                    rows.append((sp, best / 2 + 1, cp))
        out[key] = rows
    return out


def rank_ivs(mon, ia, idf, ist, level_cap=DEFAULT_CAP):
    """Rank of one IV spread for one species, per league."""
    if level_cap not in LEVEL_CAPS:
        raise ValueError(f"level cap must be one of {LEVEL_CAPS}")
    for v in (ia, idf, ist):
        if not 0 <= v <= 15:
            raise ValueError("IVs must be between 0 and 15")
    cpm = load_data()["cpm"]
    cap_idx = min(int((level_cap - 1) * 2), len(cpm) - 1)
    tab = _table(mon["atk"], mon["def"], mon["sta"], cap_idx)
    idx = ia * 256 + idf * 16 + ist
    res = {}
    for key, label, cp_cap in LEAGUES:
        rows = tab[key]
        sp, lvl, cp = rows[idx]
        rank = 1 + sum(1 for r in rows if r[0] > sp)          # ties share a rank
        best = max(r[0] for r in rows)
        # "capped": the CP limit actually restricts this species (15/15/15 would exceed it)
        capped = cp_cap is None or rows[4095][2] > cp_cap or rows[4095][1] < level_cap
        res[key] = {"league": label, "cp_cap": cp_cap, "rank": rank, "of": 4096,
                    "level": lvl, "cp": cp, "percent": round(sp / best * 100, 2),
                    "capped": capped}
    return res


def line_of(mon):
    """The Pokémon plus its relatives (pre-evolutions, evolutions, same-line forms)."""
    mons = load_data()["mons"]
    by_id = {m["id"]: m for m in mons}
    out = [mon] + [by_id[i] for i in mon.get("family", []) if i in by_id and i != mon["id"]]
    # base-stat product grows along an evolution line, so it gives evolution order
    return sorted(out, key=lambda m: m["atk"] * m["def"] * m["sta"])


def _main():
    if len(sys.argv) != 5:
        sys.exit("usage: python ivrank.py <pokemon|dex#> <atk> <def> <sta>")
    mons = find_mons(sys.argv[1])
    if not mons:
        sys.exit("no such Pokémon")
    ivs = [int(x) for x in sys.argv[2:]]
    for m in mons:
        print(f"{m['name']}  ({m['atk']}/{m['def']}/{m['sta']})")
        for r in rank_ivs(m, *ivs).values():
            print(f"  {r['league']:<14} rank {r['rank']:>4}/4096  L{r['level']:<5} CP {r['cp']:<5} {r['percent']}%")


if __name__ == "__main__":
    _main()
