#!/usr/bin/env python3
"""
Download the latest tier rankings for every Pokemon and save them to
all_rankings.json, which the web UI reads.

    python refresh_data.py              # takes ~3 minutes
    python refresh_data.py --workers 4  # gentler on the site

The old file is only replaced if the new scrape looks complete, and it is
replaced atomically, so a running UI never sees a half-written file.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # find pogo_tiers.py next to this file
import pogo_tiers as pt  # noqa: E402


def main():
    data = Path(__file__).resolve().parent.parent / "data"
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", default=str(data / "all_rankings.json"),
                    help="file to write (default: data/all_rankings.json)")
    ap.add_argument("--cache-dir", default=str(data / "cache"))
    ap.add_argument("--workers", type=int, default=8, help="parallel downloads (default 8)")
    ap.add_argument("--delay", type=float, default=0.0,
                    help="seconds between request starts (default 0)")
    args = ap.parse_args()

    ok, msg = pt.refresh_snapshot(args.snapshot, args.cache_dir, args.workers, args.delay)
    print(("Done: " if ok else "Not updated: ") + msg)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
