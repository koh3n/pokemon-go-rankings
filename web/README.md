# GO Tier Lookup (web)

A static React + TypeScript + Vite version of the app. Everything runs in the browser: it loads
`data/all_rankings.json` (the GO Hub rankings scraped by `src/refresh_data.py`) and
`data/cache/iv_data.json` (PvPoke base stats and CP multipliers, from `src/refresh_iv_data.py`) as static files, and calculates
the IV ranks and spreads itself. There is no server.

```bash
cd web
npm install
npm run dev       # copies the data in, then starts the dev server
npm run build     # type-checks and writes the static site to web/dist
npm test          # compares the TS port against the Python implementation
```

`web/dist` is plain files and can be hosted anywhere static (Hugging Face Static Spaces,
Cloudflare Pages, Netlify, GitHub Pages...).

## How the port is tested

`src/lib/` is a port of the Python code (`ivrank.py`, `pogo_tiers.py`, `pogo_ui.py`).
`scripts/gen_fixtures.py` runs the Python version and writes `test/fixtures.json`: SHA-256
digests of all 4096 IV spreads for every Pokémon in every league, plus rank lookups, name
lookups and complete search results. `npm test` checks that the TypeScript output is identical.

The Python implementation was removed from `main` after the port was verified; it is kept in the
`python-final` tag. The tests run against pinned copies of the data in `test/data/` (the Oct 2026 snapshot the fixtures were made from), so they don't change when the nightly job updates `data/`. The committed `test/fixtures.json` is what they compare against.
Regenerating it (only needed if the data's shape changes) means checking `src/` out of that tag
first; see the top of `scripts/gen_fixtures.py`.

## Layout

- `src/lib/ivrank.ts` – IV math (stat product, levels, CP, all 4096 spreads) and name matching
- `src/lib/tiers.ts` – tier rankings and evolution tree from the snapshot
- `src/lib/search.ts` – the search box: name resolution, IV ranks on ranking rows
- `src/components/`, `src/App.tsx` – the UI
