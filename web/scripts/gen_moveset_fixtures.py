#!/usr/bin/env python3
"""
Reference output from the Python calculator, for the TypeScript tests.

    .venv/bin/python web/scripts/gen_moveset_fixtures.py

Reads web/test/data/movesets.json and writes web/test/moveset_fixtures.json: a SHA-256 digest of
every Pokémon's tier results (every featured type, legacy moves allowed and hidden) plus a few results
spelled out in full.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import moveset_model as mm  # noqa: E402

data = json.loads((ROOT / "web" / "test" / "data" / "movesets.json").read_text(encoding="utf-8"))


def line(slug, t, legacy, step, picks):
    body = ",".join(f"{f}/{c}/{e:.2f}" for f, c, e in picks)
    return f"{slug}|{t}|{int(legacy)}|{step}|{body}"


def raw_tier_view(slug, t, legacy):
    """Unrounded eDPS (rounded only when formatted), same order as the TS port."""
    props, k, f = mm.entry_props(data, slug)
    out = {}
    for step in mm.STEPS:
        ranked = mm.rank_movesets(props, k, f, mm.tier_multipliers(t, step), legacy)
        out[step] = [(fm["name"], cm["name"], e) for fm, cm, _, e in ranked[:2]]
    return out


digests, samples = {}, {}
for slug in sorted(data["pokemon"]):
    lines = []
    for t in mm.move_types(data, slug):
        for legacy in (True, False):
            for step, picks in raw_tier_view(slug, t, legacy).items():
                lines.append(line(slug, t, legacy, step, picks))
    digests[slug] = hashlib.sha256("\n".join(lines).encode()).hexdigest()

for slug, t in [("76-Alola_Shadow", "electric"), ("94", "poison"), ("6", "fire"), ("68-Shadow", "fighting")]:
    if slug in data["pokemon"]:
        samples[f"{slug}|{t}"] = {str(s): [[f, c, round(e, 2)] for f, c, e in picks]
                                  for s, picks in raw_tier_view(slug, t, True).items()}

out = ROOT / "web" / "test" / "moveset_fixtures.json"
out.write_text(json.dumps({"digests": digests, "samples": samples}), encoding="utf-8")
print(len(digests), "Pokémon digests;", len(samples), "samples")
