# GO Tier Lookup

Look up Pokémon GO tier rankings (from [GO Hub](https://db.pokemongohub.net)) and PvP IV ranks for a Pokémon, its evolution line, and its forms. Static site (React + TypeScript + Vite in `web/`), with a small Python scraper to keep the data fresh.

## Features

- Tier rankings per group (Normal, Shadow, Regional, Mega, etc.)
- PvP IV rank for Great/Ultra/Master League
- Evolution tree with forms
- Best PvE movesets vs neutral or type-weak bosses
- All 4096 IV spreads per league, with an IV finder
- Shareable links (search is kept in the URL)

## Run it

```
pip install -r requirements.txt
python src/refresh_data.py          # ~3 min
cd web
npm install
npm run dev                         # http://localhost:5173
```

`npm run build` outputs to `web/dist`.

## Updating data

```
python src/refresh_data.py        # rankings
python src/refresh_iv_data.py     # PvPoke base stats
python src/refresh_movesets.py    # movesets
```

A weekly GitHub Action does this automatically and commits the result. The site deploys to GitHub Pages from `main`.

## License

Code is MIT (see `LICENSE`). Data comes from [Pokémon GO Hub](https://db.pokemongohub.net) and [PvPoke](https://pvpoke.com) and stays under their own terms. Pokémon and Pokémon GO are trademarks of their respective owners.
