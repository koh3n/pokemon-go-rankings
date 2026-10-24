#!/usr/bin/env python3
"""Dump reference outputs from the Python implementation for the TypeScript tests.

    .venv/bin/python web/scripts/gen_fixtures.py

Writes web/test/fixtures.json: IV spread digests, per-league ranks, name lookups and
full search results, so the TS port can be checked against the original.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import ivrank  # noqa: E402
import pogo_tiers as pt  # noqa: E402
import pogo_ui  # noqa: E402

pogo_ui.CONFIG.update(snapshot=str(ROOT / "data" / "all_rankings.json"))

SPREAD_MONS = ["Azumarill", "Galarian Corsola", "Cursola", "Aegislash (Blade)", "Medicham", "Registeel",
               "Charizard", "Alolan Ninetales", "Giratina (Altered)", "Mewtwo", "Zubat", "Shuckle",
               "Machamp", "Skarmory", "Tauros (Aqua)", "Deoxys (Defense)", "Sableye", "Bastiodon"]
CAPS = [40, 50, 51]

NAMES = ["Galarian Shadow Meowth", "Therian Forme Tornadus", "Minior (Blue Core)", "Ogerpon (Teal Mask)",
         "Nidoran♀", "Shadow Cursola", "Iron Treads", "Cherrim (Sunny Form)", "Aegislash Sword Forme",
         "Zygarde Complete Form (10%)", "Raichu", "Alolan Raichu", "Giratina", "Lycanroc", "Mega Absol",
         "Dynamax Machamp", "Mr. Mime", "Galarian Mr. Mime", "Farfetch'd", "Hisuian Shadow Samurott",
         "Azumarill", "Corsola", "Nope"]

QUERIES = ["galarian corsola", "Aegislash (Blade)", "Aegislash", "Corsola", "Alolan Raichu", "4", "charmander",
           "Shadow Cursola", "Giratina (Altered)", "Minior (Blue Core)", "Oricorio (Pa'u)", "azumarill",
           "meowth", "Galarian Meowth", "Shellos", "eevee", "Mr. Mime", "Zorp", "26", "Pikachu"]


def digest(rows):
    """SHA-256 over every row in a fixed text format (the TS tests build the same string)."""
    text = "\n".join(f"{r[0]},{r[1]},{r[2]},{r[3]},{r[4]:.1f},{r[5]},{r[6]:.2f},{r[7]:.2f},{r[8]:.2f},{r[9]}"
                     for r in rows)
    return hashlib.sha256(text.encode()).hexdigest()


def mon_json(m):
    return None if m is None else {"id": m["id"], "name": m["name"]}


out = {"spreads": [], "ranks": [], "names": {}, "find_mons": {}, "lines": {}, "searches": [], "all_digests": {}}

for n in SPREAD_MONS:
    m = ivrank.find_exact(n)
    assert m, n
    for cap in CAPS:
        for league in ("great", "ultra", "master"):
            rows = ivrank.all_spreads(m, league, cap)
            out["spreads"].append({"name": m["name"], "league": league, "cap": cap, "count": len(rows),
                                   "sha256": digest(rows), "head": rows[:40]})
    out["lines"][m["name"]] = [x["name"] for x in ivrank.line_of(m)]
    for ivs in [(0, 15, 15), (15, 15, 15), (3, 7, 1), (0, 0, 0), (15, 0, 14)]:
        for cap in (40, 50):
            out["ranks"].append({"name": m["name"], "ivs": ivs, "cap": cap,
                                 "result": ivrank.rank_ivs(m, *ivs, cap)})

# every Pokémon, every league, cap 50: digest only
for m in ivrank.load_data()["mons"]:
    for league in ("great", "ultra", "master"):
        out["all_digests"][f"{m['name']}|{league}"] = digest(ivrank.all_spreads(m, league, 50))

for n in NAMES:
    out["names"][n] = mon_json(ivrank.find_exact(n))

for q in ["raichu", "pikachu", "25", "alolan raichu", "corsola", "meowth", "zzz", "azu", "nidoran", "4"]:
    out["find_mons"][q] = [m["name"] for m in ivrank.find_mons(q)]

for q in QUERIES:
    for ivs in (None, (0, 15, 15)):
        try:
            res = pogo_ui.run_search(q, "all", ivs, 50)
            out["searches"].append({"q": q, "ivs": ivs, "result": res})
        except (ValueError, SystemExit) as e:
            out["searches"].append({"q": q, "ivs": ivs, "error": str(getattr(e, "code", e))})

(ROOT / "web" / "test" / "fixtures.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
print("spreads", len(out["spreads"]), "ranks", len(out["ranks"]), "searches", len(out["searches"]))
