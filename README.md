# GO Tier Lookup

Look up Pokémon GO tier rankings (from https://db.pokemongohub.net) and PvP IV
ranks for a Pokémon, its whole evolution line, and its forms. It is a static
website (React + TypeScript + Vite in `web/`): everything runs in the browser, so
it can be hosted anywhere that serves plain files. A small Python scraper keeps the
data fresh.

## Quick start

```
pip install -r requirements.txt     # once; needs Python 3.8+ (for the scraper)
python src/refresh_data.py          # once; downloads every ranking (~3 min)
cd web
npm install
npm run dev                         # http://localhost:5173
```

`npm run build` writes the static site to `web/dist`. See `web/README.md` for
details and for how the TypeScript code is tested against the original Python.

## What the site does

Type a Pokémon name or Pokédex number and pick which forms to include.

- **Rankings**: one tab per group (Normal, Shadow, Regional, Mega, ...), sorted
  best to worst, with a mode filter.
- **PvP IV rank**: enter your IVs (Atk/Def/HP, e.g. `11/2/3`) and a level cap. You
  get Great, Ultra and Master League rank out of 4096, level, CP and stat
  product for every stage of the line, plus a "Your IV rank" column on the league
  rows of the tier table. Shadow Pokémon use the normal form's rank.
- **Evolution tree**: the full line, with each stage's forms.
- **Best movesets (PvE)**: a collapsible per Pokémon showing its best fast + charged move against a
  neutral boss (1×, the same whatever the type) and when the boss is weak to a type (1.6×), with the tier
  and rank for that type, what the type is super effective against, a picker for the types it is ranked
  for and a "hide legacy moves" toggle. A "Movesets" link on every ranking row opens it (on a "Fire-type"
  row it preselects Fire).
  See "Raid movesets" below.
- **IV spreads**: a collapsible per Pokémon under the tree listing all 4096 spreads
  for each league (rank, level, CP, stat product %, in-battle stats), with a
  level-cap picker and an IV finder (`0/15/15`, `*/14/*`).

The search is kept in the address bar (`?q=azumarill&iv=0/15/15&cap=50`), so
results can be linked.

## Updating the data

```
python src/refresh_data.py        # GO Hub rankings -> data/all_rankings.json (~3 min)
python src/refresh_iv_data.py     # PvPoke base stats -> data/cache/iv_data.json
python src/refresh_movesets.py    # GO Hub movesets -> data/movesets.json (~2 min)
```

`refresh_data.py` also reads GO Hub's 18 per-type lists and adds the *off-type* attackers that are in the top 50
of a list (a Pokémon's own page only has tiles for its own types, but the lists also include any Pokémon with a move
of that type: Mega Mewtwo Y is #2 in Ghost). They're marked `off_type` in the data, and `--lists-only` re-reads just
those lists. It keeps the old file if the new scrape looks incomplete. Options:
`--workers N` (parallel downloads, default 8), `--delay SECONDS`, `--snapshot FILE`.
Run `refresh_iv_data.py` when new Pokémon are added to the game. Both files are
committed, and `npm run dev` / `npm run build` copy them into the site. A nightly
GitHub Action (`.github/workflows/refresh-data.yml`) does the scrape and commits the result.

## Command line scraper

```
python src/pogo_tiers.py charmander
python src/pogo_tiers.py 4 --forms shadow,regional -o charmander.json
python src/pogo_tiers.py charmander --forms none
```

`--forms` takes `all` (default), `none`, or a comma list of: shadow, regional,
regional-shadow, mega, primal, dynamax, gigantamax, other. (`pogo_tiers.py --all`
is the lower-level version of `refresh_data.py` and also takes `--keep-html`.)

## Files

| File | Purpose |
|---|---|
| `web/` | The website (React + TypeScript + Vite) |
| `src/pogo_tiers.py` | Scraper and parser (single line or `--all`) |
| `src/refresh_data.py` | Updates `data/all_rankings.json` |
| `src/refresh_iv_data.py` | Updates `data/cache/iv_data.json` from PvPoke |
| `src/refresh_movesets.py`, `movesets.py`, `moveset_model.py` | Scrape each Pokémon page's moves and build `data/movesets.json` |
| `src/validate_model.py`, `validate_bosses.py` | Check the moveset calculator against GO Hub's numbers |
| `data/all_rankings.json` | Output of `refresh_data.py`; what the site reads |
| `data/cache/iv_data.json` | Base stats and CP multipliers (committed) |
| `data/movesets.json` | Moves and per-Pokémon calculator settings for the raid moveset view (committed) |
| `.github/workflows/` | Nightly data refresh and the GitHub Pages deploy |

## Hosting

The site is published with GitHub Pages by `.github/workflows/deploy-site.yml`: it builds `web/` and
deploys it whenever `main` changes and after each nightly data refresh. One-time setup: repo
Settings → Pages → Source: GitHub Actions. The published site is public even though the repository is private.

## Raid movesets

GO Hub ranks raid attackers per type using each Pokémon's best moveset for that type, averaged over the
bosses weak to it, so the moveset it shows can differ from the best one against the boss you're facing
(for example Shadow Alolan Golem's Electric moveset uses Rock moves, which beat Electric ones against Flying
bosses but not against Water ones). The raid movesets card answers "what if the boss is weak to type X?"
directly: it re-ranks every fast + charged combination with that type hitting at 1×, 1.6× or 2.56× and every
other type at 1×.

How it works: each GO Hub Pokémon page embeds the Pokémon's types and stats, its moves, and GO Hub's own
neutral-boss ranking of every moveset. `src/moveset_model.py` fits a small calculator (damage per hit, the
fast/charged energy cycle, a per-Pokémon scale) to that ranking, and the web app (`web/src/lib/movesets.ts`)
runs the same calculator in the browser. The data (`data/movesets.json`) is 240 KB.

How accurate it is, from `src/validate_model.py` and `src/validate_bosses.py`:

- against GO Hub's neutral numbers for all 1,954 Pokémon (19,299 movesets): median DPS error 1.0%; its #1
  moveset is GO Hub's #1 for 88% of Pokémon, and when it isn't, the pick is on average 0.3% lower in GO Hub's DPS
- against 25 tables of GO Hub's results vs specific bosses (Water, Water/Flying, Fire/Flying, Psychic, Ground):
  the ratios between movesets are within 1.9% on average, and its best moveset is within 3% of GO Hub's best in all 25
- 58 Pokémon (such as Abra) fit worse than 8% because GO Hub scores them as never reaching a charged move; the
  card says so instead of showing a view for them

Limits: only the chosen type is boosted, so a boss where another of the Pokémon's types is also super effective
isn't captured; damage is continuous, while the game rounds each hit to whole numbers (small bonuses can vanish
against bulky bosses); eDPS is on GO Hub's neutral-boss scale (Level 40, 15/15/15, default settings).

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

- **IV data**: base stats come from the PvPoke game master and are cached in
  `data/cache/iv_data.json` together with the CP multiplier table; ranks are
  calculated in the browser. GO Hub names are matched to PvPoke's by their words, so
  form and Shadow wording differences don't matter. Mega, Primal, Dynamax and
  Gigantamax forms are skipped since they can't battle in PvP.
- **Rate limits**: if the site answers HTTP 429 the scraper backs off and
  retries. Use `--delay` or `--workers` to go slower.
- **Name search** uses the site's generation lists. If a name isn't found, use
  the Pokédex number.
- **If a page says "no 'Tier Ranking' section found"** and it should have one,
  the site's markup changed; the parser is `parse_rankings()` in
  `pogo_tiers.py`. Dynamax and Gigantamax pages have no ranking section, so
  that warning is normal for them.

## License

The code is MIT licensed (see `LICENSE`). The ranking and base-stat data come from
[Pokémon GO Hub](https://db.pokemongohub.net) and [PvPoke](https://pvpoke.com) and stay
under their own terms; Pokémon and Pokémon GO are trademarks of their respective owners.
