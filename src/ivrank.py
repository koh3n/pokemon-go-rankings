#!/usr/bin/env python3
"""
PvP IV rank calculator (Great / Ultra / Master League).

Base stats come from the PvPoke game master (pokemon.json). They are downloaded
once and cached, together with the CP multiplier table, in
data/cache/iv_data.json. Ranks are computed locally: for each of the 4096 IV
combinations the highest level (<= the level cap) that keeps CP under the
league limit is found, and combinations are ordered by stat product
(attack x defense x floor(HP)). Equal stat products share a rank.

    python ivrank.py charizard 0 15 14
"""
import json
import re
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path

import requests

GAMEMASTER = "https://raw.githubusercontent.com/pvpoke/pvpoke/master/src/data/gamemaster/pokemon.json"
USER_AGENT = "pogo-tier-script/1.0 (personal use, low volume)"
LEAGUES = [("great", "Great League", 1500), ("ultra", "Ultra League", 2500),
           ("master", "Master League", None)]
LEVEL_CAPS = (40, 41, 50, 51)
DEFAULT_CAP = 50
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "cache" / "iv_data.json"
REGIONS = ("Alolan", "Galarian", "Hisuian", "Paldean")


def _display_name(species_name):
    """PvPoke "Ninetales (Alolan)" -> "Alolan Ninetales"; other forms stay "Giratina (Altered)"."""
    species_name = {"Nidoran Female": "Nidoran♀", "Nidoran Male": "Nidoran♂"}.get(species_name, species_name)
    m = re.match(r"^(.+?) \((.+)\)$", species_name)
    if m and m.group(2) in REGIONS:
        return f"{m.group(2)} {m.group(1)}"
    return species_name


def build_data():
    """Download base stats from the PvPoke game master and cache them with the CP multipliers.

    The CP multiplier table is a fixed game constant, so it is kept from the existing cache.
    """
    if not DATA_FILE.exists():
        raise RuntimeError(f"{DATA_FILE} (with the CP multiplier table) is missing")
    cpm = json.loads(DATA_FILE.read_text(encoding="utf-8"))["cpm"]
    r = requests.get(GAMEMASTER, headers={"User-Agent": USER_AGENT}, timeout=60)
    r.raise_for_status()
    raw = [g for g in r.json()
           if not ({"mega", "shadow"} & set(g.get("tags") or []))      # can't battle / same CP as normal
           and not g["speciesId"].endswith(("_shadow", "_xs", "_xl"))]
    raw.sort(key=lambda g: (g["dex"], "_" in g["speciesId"], g["speciesId"]))

    # ids: the Pokédex number, or 10000*n + dex for further forms of the same number
    ids, used, seen = {}, {}, set()
    for g in raw:
        n = used.get(g["dex"], 0)
        used[g["dex"]] = n + 1
        ids[g["speciesId"]] = g["dex"] + 10000 * n
    # evolution lines: connect parents and evolutions, then group
    parent = {sid: sid for sid in ids}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for g in raw:
        fam = g.get("family") or {}
        for other in [fam.get("parent"), *(fam.get("evolutions") or [])]:
            if other in ids:
                parent[find(g["speciesId"])] = find(other)
    lines = {}
    for sid in ids:
        lines.setdefault(find(sid), []).append(ids[sid])

    mons = []
    for g in raw:
        name = _display_name(g["speciesName"])
        if name in seen:
            continue
        seen.add(name)
        b = g["baseStats"]
        sid = g["speciesId"]
        mons.append({"id": ids[sid], "name": name, "atk": b["atk"], "def": b["def"], "sta": b["hp"],
                     "family": [i for i in lines[find(sid)] if i != ids[sid]]})
    if len(mons) < 800:
        raise RuntimeError(f"only parsed {len(mons)} Pokémon from PvPoke; the data format may have changed")
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


_NOISE = {"shadow", "form", "forme", "mode", "style", "size", "breed", "mask"}
_SYNONYMS = {"sunny": "sunshine", "sword": "blade"}      # GO Hub wording -> PvPoke wording
_NOT_PVP = {"mega", "primal", "dynamax", "gigantamax", "eternamax"}


def name_words(name):
    s = name.lower().replace("♀", " f").replace("♂", " m")
    s = unicodedata.normalize("NFD", s)
    words = re.split(r"[^a-z0-9]+", "".join(c for c in s if not unicodedata.combining(c)))
    return frozenset(_SYNONYMS.get(w, w) for w in words if w and w not in _NOISE)


@lru_cache(maxsize=1)
def _word_index():
    return [(name_words(m["name"]), m) for m in load_data()["mons"]]


def find_exact(name):
    """One Pokémon by name, spelled however the GO Hub spells it. Matching is by the set of
    words, so word order, "Shadow" and filler like "Forme" don't matter ("Galarian Shadow Meowth",
    "Therian Forme Tornadus"). The best match is the Pokémon whose words are all in the query
    and are the most numerous ("Minior (Blue Core)" -> "Minior (Core)", "Ogerpon (Teal Mask)" ->
    "Ogerpon"); a bare species name falls back to its first listed form. Mega/Primal/Dynamax
    and Gigantamax Pokémon can't battle in PvP, so they match nothing."""
    q = name_words(name)
    if not q or q & _NOT_PVP:
        return None
    index = _word_index()
    inside = [(w, m) for w, m in index if w <= q]
    if inside:
        return max(inside, key=lambda x: (len(x[0]), sum(map(len, x[0]))))[1]
    letters = sorted("".join(q))          # PvPoke writes "Irontreads", the GO Hub "Iron Treads"
    for w, m in index:
        if sorted("".join(w)) == letters:
            return m
    over = [m for w, m in index if q <= w]
    return over[0] if over else None


def all_spreads(mon, league, level_cap=DEFAULT_CAP):
    """Every one of the 4096 IV spreads for one league, best first.

    Each row: [rank, atk_iv, def_iv, hp_iv, level, cp, percent, atk, def, hp]
    where the last three are the in-battle stats. Ties share a rank.
    """
    if league not in {k for k, _l, _c in LEAGUES}:
        raise ValueError("league must be great, ultra or master")
    if level_cap not in LEVEL_CAPS:
        raise ValueError(f"level cap must be one of {LEVEL_CAPS}")
    cpm = load_data()["cpm"]
    cap_idx = min(int((level_cap - 1) * 2), len(cpm) - 1)
    rows = _table(mon["atk"], mon["def"], mon["sta"], cap_idx)[league]
    order = sorted(range(4096), key=lambda i: -rows[i][0])
    best = rows[order[0]][0]
    out, rank, prev = [], 0, None
    for pos, i in enumerate(order):
        sp, lvl, cp = rows[i]
        if sp != prev:
            rank, prev = pos + 1, sp
        ia, idf, ist = i >> 8, (i >> 4) & 15, i & 15
        c = cpm[int(round((lvl - 1) * 2))]
        out.append([rank, ia, idf, ist, lvl, cp, round(sp / best * 100, 2),
                    round((mon["atk"] + ia) * c, 2), round((mon["def"] + idf) * c, 2),
                    int((mon["sta"] + ist) * c)])
    return out


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
