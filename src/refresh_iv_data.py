#!/usr/bin/env python3
"""
Download Pokémon base stats from the PvPoke game master and save them to
data/cache/iv_data.json, which the web app reads (it also holds the CP multiplier
table, a fixed game constant that is kept from the existing file).

    python src/refresh_iv_data.py       # run when new Pokémon are added to the game

Mega, Shadow and Primal entries are skipped (Shadow CP is the same as normal, and the
others can't battle in PvP). Pokémon are named the way PvPoke names them; the web app
matches GO Hub names to these by their words.
"""
import json
import re
import sys
from pathlib import Path

import requests

GAMEMASTER = "https://raw.githubusercontent.com/pvpoke/pvpoke/master/src/data/gamemaster/pokemon.json"
USER_AGENT = "pogo-tier-script/1.0 (personal use, low volume)"
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "cache" / "iv_data.json"
REGIONS = ("Alolan", "Galarian", "Hisuian", "Paldean")


def display_name(species_name):
    """PvPoke "Ninetales (Alolan)" -> "Alolan Ninetales"; other forms stay "Giratina (Altered)"."""
    species_name = {"Nidoran Female": "Nidoran♀", "Nidoran Male": "Nidoran♂"}.get(species_name, species_name)
    m = re.match(r"^(.+?) \((.+)\)$", species_name)
    if m and m.group(2) in REGIONS:
        return f"{m.group(2)} {m.group(1)}"
    return species_name


def build_data():
    if not DATA_FILE.exists():
        sys.exit(f"{DATA_FILE} (with the CP multiplier table) is missing")
    cpm = json.loads(DATA_FILE.read_text(encoding="utf-8"))["cpm"]
    r = requests.get(GAMEMASTER, headers={"User-Agent": USER_AGENT}, timeout=60)
    r.raise_for_status()
    raw = [g for g in r.json()
           if not ({"mega", "shadow"} & set(g.get("tags") or []))
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
        name = display_name(g["speciesName"])
        if name in seen:
            continue
        seen.add(name)
        b = g["baseStats"]
        sid = g["speciesId"]
        mons.append({"id": ids[sid], "name": name, "atk": b["atk"], "def": b["def"], "sta": b["hp"],
                     "family": [i for i in lines[find(sid)] if i != ids[sid]]})
    if len(mons) < 800:
        sys.exit(f"only parsed {len(mons)} Pokémon from PvPoke; the data format may have changed")
    DATA_FILE.write_text(json.dumps({"cpm": cpm, "mons": mons}, ensure_ascii=False), encoding="utf-8")
    print(f"saved {len(mons)} Pokémon to {DATA_FILE}")


if __name__ == "__main__":
    build_data()
