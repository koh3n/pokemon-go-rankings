#!/usr/bin/env python3
"""
How closely does moveset_model.py reproduce GO Hub's neutral-boss numbers?

    python src/validate_model.py --props-dir /path/to/props

For every Pokémon: fit K, predict DPS for every moveset and compare with GO Hub's.
Reports the DPS error, whether our best moveset is GO Hub's best (or within 2% of it
by GO Hub's own numbers), and how often GO Hub's best is in our top three.
"""
import argparse
import json
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import moveset_model as mm  # noqa: E402


def load(props_dir):
    out = {}
    for f in sorted(Path(props_dir).glob("*.json")):
        text = f.read_text(encoding="utf-8")
        if text != "null":
            out[f.stem] = json.loads(text)
    return out


def evaluate(props):
    k, fac = mm.fit_k(props), mm.edps_factor(props)
    if k is None or fac is None:
        return None
    by = {m["id"]: m for m in props["moves"]}
    rows = [r for r in props["results"] if r["dps"] > 0.5 and r["cm"]["name"] not in mm.UNUSABLE
            and r["qm"]["id"] in by and r["cm"]["id"] in by]
    errs = [abs(mm.cycle_dps(by[r["qm"]["id"]], by[r["cm"]["id"]], k) / r["dps"] - 1) * 100 for r in rows]
    truth = sorted(rows, key=lambda r: -r["dps"])
    ours = mm.rank_movesets(props, k, fac)
    best_truth = (truth[0]["qm"]["id"], truth[0]["cm"]["id"])
    our_top = [(a["id"], b["id"]) for a, b, _, _ in ours[:3]]
    # GO Hub's eDPS for the moveset we picked as best, relative to GO Hub's real best
    pick = (ours[0][0]["id"], ours[0][1]["id"])
    picked = next(r for r in rows if (r["qm"]["id"], r["cm"]["id"]) == pick)
    return {"mean": st.mean(errs), "worst": max(errs), "top1": pick == best_truth, "top3": best_truth in our_top,
            "loss": (1 - picked["dps"] / truth[0]["dps"]) * 100, "n": len(rows)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--props-dir", required=True)
    args = ap.parse_args()
    data = load(args.props_dir)
    res = {slug: evaluate(p) for slug, p in data.items()}
    res = {s: r for s, r in res.items() if r}
    means = sorted(r["mean"] for r in res.values())
    loss = sorted(r["loss"] for r in res.values())
    print(f"{len(res)} Pokémon with a moveset table, {sum(r['n'] for r in res.values())} movesets")
    print(f"DPS error per moveset:  mean of means {st.mean(means):.2f}%  median {st.median(means):.2f}%  "
          f"90th pct {means[int(len(means) * .9)]:.2f}%")
    print(f"our #1 is GO Hub's #1:   {100 * sum(r['top1'] for r in res.values()) / len(res):.1f}%")
    print(f"GO Hub's #1 in our top 3: {100 * sum(r['top3'] for r in res.values()) / len(res):.1f}%")
    print(f"when our #1 differs, it costs (GO Hub's DPS): mean {st.mean(loss):.2f}%  "
          f"95th pct {loss[int(len(loss) * .95)]:.2f}%  worst {loss[-1]:.2f}%")
    worst = sorted(res.items(), key=lambda kv: -kv[1]["mean"])[:6]
    print("hardest to fit:", [(s, round(r["mean"], 1)) for s, r in worst])


if __name__ == "__main__":
    main()
