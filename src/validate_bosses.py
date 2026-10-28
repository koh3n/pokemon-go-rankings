#!/usr/bin/env python3
"""
Does the calculator reproduce GO Hub's results against specific bosses?

    python src/validate_bosses.py --props-dir /path/to/props

tests/fixtures/boss_truth.json holds GO Hub's top movesets (with eDPS) for five attackers against five
bosses, read from its Pokémon pages with "Opponent: Pokémon". For each table the exact type multipliers
of that boss are applied. A boss also has its own Defense, so one defence factor per boss and one overall
scale per table are fitted; what is compared is the ratios between movesets, i.e. which moveset wins and
by how much.
"""
import argparse
import json
import math
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import moveset_model as mm  # noqa: E402

FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "boss_truth.json"


def parse(table):
    out = []
    for part in table.split(";"):
        names, val = part.rsplit(":", 1)
        fast, charged = names.split("/")
        out.append((fast.replace("*", ""), charged.replace("*", ""), float(val)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--props-dir", required=True)
    args = ap.parse_args()
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pk = {}
    for slug in fx["tables"]:
        p = json.loads((Path(args.props_dir) / f"{slug}.json").read_text(encoding="utf-8"))
        pk[slug] = (mm.fit_k(p), {m["name"]: m for m in p["moves"]})

    def rows_for(slug, boss):
        k, by = pk[slug]
        return [(by[f], by[c], v) for f, c, v in parse(fx["tables"][slug][boss]) if f in by and c in by]

    def table_error(slug, boss, mults, r):
        k, _ = pk[slug]
        rows = rows_for(slug, boss)
        pred = [mm.cycle_dps(f, c, k * r, mults) for f, c, _ in rows]
        if min(pred) <= 0:
            return None
        scale = math.exp(st.mean(math.log(v / p) for (_, _, v), p in zip(rows, pred)))
        return st.mean(abs(p * scale / v - 1) * 100 for (_, _, v), p in zip(rows, pred))

    errors, agree, near, total = [], 0, 0, 0
    for boss, types in fx["boss_types"].items():
        mults = mm.multipliers_for_boss(*types)
        best_r, best = None, None
        for r in [x / 20 for x in range(3, 160)]:           # the boss's Defense relative to GO Hub's neutral dummy
            errs = [table_error(s, boss, mults, r) for s in fx["tables"]]
            if None in errs:
                continue
            if best is None or st.mean(errs) < best:
                best, best_r = st.mean(errs), r
        errors.append(best)
        for slug in fx["tables"]:
            k, _ = pk[slug]
            scored = [(mm.cycle_dps(f, c, k * best_r, mults), f["name"], c["name"], v) for f, c, v in rows_for(slug, boss)]
            ours, truth = max(scored), max(scored, key=lambda x: x[3])
            total += 1
            agree += ours[1:3] == truth[1:3]
            near += ours[3] >= 0.97 * truth[3]
        print(f"  {boss:9s} {str(types):22s} defence factor {best_r:.2f}  mean error {best:.2f}%")
    print(f"mean error over {len(errors) * len(fx['tables'])} tables: {st.mean(errors):.2f}%")
    print(f"our best moveset is GO Hub's best: {agree}/{total};  within 3% of GO Hub's best: {near}/{total}")


if __name__ == "__main__":
    main()
