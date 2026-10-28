#!/usr/bin/env python3
"""
Download every Pokémon page and build data/movesets.json from the moveset data embedded in it.

    python src/refresh_movesets.py                     # fetch all pages (~2 minutes), write data/movesets.json
    python src/refresh_movesets.py --props-dir DIR     # also keep the raw per-page data in DIR (reused next time)
    python src/refresh_movesets.py --props-dir DIR --offline   # rebuild from what is already in DIR

Each page holds the Pokémon's types and stats, its moves, and GO Hub's neutral-boss ranking of every
moveset. moveset_model.py fits a calculator to that ranking so the web app can re-rank movesets for other
effectiveness multipliers. The old file is kept if the new data looks incomplete.
"""
import argparse
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import moveset_model  # noqa: E402
import movesets  # noqa: E402
import pogo_tiers as pt  # noqa: E402
import validate_model  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"


def fetch_all(slugs, props_dir, workers, delay, offline):
    props_dir.mkdir(parents=True, exist_ok=True)
    fetch = pt.Fetcher(props_dir / "_cache", delay, store=False)
    done = {"n": 0, "none": 0, "failed": []}

    def one(slug):
        path = props_dir / f"{slug}.json"
        if path.exists():
            return
        if offline:
            return
        try:
            props = movesets.parse_moveset_props(fetch.get(f"/pokemon/{slug}"))
        except (SystemExit, requests.RequestException) as e:
            done["failed"].append((slug, str(e)))
            return
        path.write_text(json.dumps(props, separators=(",", ":")) if props else "null", encoding="utf-8")
        done["n"] += 1
        if props is None:
            done["none"] += 1
        if done["n"] % 200 == 0:
            print(f"  {done['n']}/{len(slugs)} pages", file=sys.stderr)

    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, slugs))
    return done


def load_props(props_dir):
    return validate_model.load(props_dir)


def write_dataset(props_dir, out_path):
    """Fit the calculator for every Pokémon and write the compact dataset; keep the old file if it shrank."""
    props = load_props(props_dir)
    errors = {}
    for slug, p in props.items():
        r = validate_model.evaluate(p)
        if r:
            errors[slug] = r["mean"]
    data = moveset_model.build_dataset(props, errors)
    out = Path(out_path)
    old_n = 0
    if out.exists():
        try:
            old_n = len(json.loads(out.read_text(encoding="utf-8"))["pokemon"])
        except (OSError, ValueError, KeyError):
            pass
    n = len(data["pokemon"])
    if n < 0.9 * old_n or n < 500:
        return False, f"kept old data: new build has {n} Pokémon, old had {old_n}"
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, out)
    return True, f"saved {n} Pokémon and {len(data['moves'])} moves"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--props-dir", help="where to keep the raw per-page data (default: a temporary folder)")
    ap.add_argument("--out", default=str(DATA / "movesets.json"))
    ap.add_argument("--snapshot", default=str(DATA / "all_rankings.json"))
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--delay", type=float, default=0.05)
    ap.add_argument("--offline", action="store_true", help="don't fetch, use the props already saved")
    args = ap.parse_args()

    snap = pt.load_snapshot(args.snapshot)
    if not snap:
        sys.exit(f"can't read {args.snapshot}")
    slugs = [p["slug"] for p in snap["per_pokemon"]]
    tmp = None if args.props_dir else tempfile.TemporaryDirectory()
    props_dir = Path(args.props_dir or tmp.name)
    t0 = time.time()
    done = fetch_all(slugs, props_dir, args.workers, args.delay, args.offline)
    print(f"fetched {done['n']} pages ({done['none']} without a moveset table, "
          f"{len(done['failed'])} failed) in {time.time() - t0:.0f}s")
    for slug, err in done["failed"][:10]:
        print("  failed:", slug, err)
    if len(done["failed"]) > 0.05 * len(slugs):
        sys.exit("too many pages failed; keeping the old data")
    ok, msg = write_dataset(props_dir, args.out)
    print(("Done: " if ok else "Not updated: ") + msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
