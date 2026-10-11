---
title: GO Tier Lookup
emoji: 📊
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# GO Tier Lookup

Look up Pokémon GO tier rankings (from https://db.pokemongohub.net) and PvP IV
ranks for a Pokémon, its whole evolution line, and its forms. Runs on your own
computer, or as a small hosted app (see Deploying).

## Quick start

```
pip install -r requirements.txt     # once; needs Python 3.8+
python refresh_data.py              # once; downloads every ranking (~3 min)
python pogo_ui.py                   # opens http://127.0.0.1:8000
```

On macOS you can double-click `Start.command` (or `Start.bat` on Windows) instead of the last step.

`refresh_data.py` saves `all_rankings.json` (~1 MB). The UI only reads that
file, so searches are instant and need no network, and the UI never scrapes
anything itself. To update the data, run `python refresh_data.py` again
(`Start.command` / `Start.bat` do it automatically on first run). It keeps the old file if
the new scrape looks incomplete.

## Web UI

Type a Pokémon name or Pokédex number and pick which forms to include.

- **Rankings**: one tab per group (Normal, Shadow, Regional, Mega, ...), sorted
  best to worst, with a mode filter.
- **PvP IV rank** (below the rankings): enter your IVs (Atk/Def/HP, e.g.
  `11/2/3`) and a level cap. You get Great, Ultra and Master League rank out of
  4096, level, CP and stat product for every stage of the line, plus a "Your IV
  rank" column on the league rows of the tier table. Shadow Pokémon use the
  normal form's rank.
- **Evolution tree**: the full line, with each stage's forms.

Options: `--port 9000`, `--no-browser`, `--snapshot PATH`, `--host 0.0.0.0`.

## Deploying (Hugging Face Spaces)

The repo includes a `Dockerfile` and the Spaces config at the top of this file.
Create a Docker Space, push this repo (with `all_rankings.json` and
`pogo_cache/iv_data.json` committed) and it serves on port 7860. In hosted mode
(`--hosted`) the server re-scrapes the whole site itself every night at 03:00
UTC (`--refresh-hour N` to change), at low parallelism, and swaps the new data in
without a restart. Free Spaces have ephemeral disk, so after a restart it starts
from the committed file again until the next nightly run; re-run
`refresh_data.py` and push occasionally to keep that file recent.

## Command line

```
python pogo_tiers.py charmander
python pogo_tiers.py 4 --forms shadow,regional -o charmander.json
python pogo_tiers.py charmander --forms none
python refresh_data.py                     # whole site -> all_rankings.json
python ivrank.py azumarill 0 15 15         # IV ranks only
```

`--forms` takes `all` (default), `none`, or a comma list of: shadow, regional,
regional-shadow, mega, primal, dynamax, gigantamax, other.

`refresh_data.py` options: `--workers N` (parallel downloads, default 8),
`--delay SECONDS`, `--snapshot FILE`. (`pogo_tiers.py --all` is the lower-level
version of the same scrape and also takes `--keep-html`.)

## Files

| File | Purpose |
|---|---|
| `pogo_ui.py` | Local web UI |
| `pogo_tiers.py` | Scraper and parser (single line or `--all`) |
| `refresh_data.py` | Updates `all_rankings.json` (run from a terminal) |
| `Dockerfile` | Container for Hugging Face Spaces / any host |
| `ivrank.py` | PvP IV rank calculator |
| `all_rankings.json` | Output of `refresh_data.py`; what the UI reads |
| `pogo_cache/` | Name index and IV data (`iv_data.json` is committed so a host needn't download it) |
| `Start.command` | macOS double-click launcher |
| `Start.bat` | Windows double-click launcher |

## Output JSON

Single line (`pogo_tiers.py <pokemon>`):

- `evolution_tree`: nested evolutions, each node with its `forms`
- `rankings`: one list per group, sorted by tier (S+ ... F) then rank number
- `per_pokemon`: raw rankings for every page scraped

`--all` file: `rankings` and `per_pokemon` as above for every page, plus
`evolutions` (every evolution link and what it requires), `pages_scraped` and
`pages_failed`.

Rank numbers aren't comparable across modes (e.g. Fire-type #38 vs Great League
#259), so ordering inside one tier is only a rough tiebreak.

## Notes

- **IV data** comes from https://iv4u.lima-city.de (downloaded once, cached in
  `pogo_cache/iv_data.json`); ranks are computed locally. Checked against IV4U's
  own PvP tables: ~99.99% of spreads match exactly, the rest are off by one tie
  group. Mega and Primal forms are skipped since they can't battle.
- **Rate limits**: if the site answers HTTP 429 the scraper backs off and
  retries. Use `--delay` or `--workers` to go slower.
- **Name search** uses the site's generation lists. If a name isn't found, use
  the Pokédex number.
- **If a page says "no 'Tier Ranking' section found"** and it should have one,
  the site's markup changed; the parser is `parse_rankings()` in
  `pogo_tiers.py`. Dynamax and Gigantamax pages have no ranking section, so
  that warning is normal for them.
