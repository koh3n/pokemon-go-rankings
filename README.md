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
