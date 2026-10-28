// Copy the scraped data into public/ so the app can fetch it as static files.
import { cpSync, existsSync, mkdirSync } from 'node:fs'

const out = new URL('../public/data/', import.meta.url)
mkdirSync(out, { recursive: true })
cpSync(new URL('../../data/all_rankings.json', import.meta.url), new URL('all_rankings.json', out))
cpSync(new URL('../../data/cache/iv_data.json', import.meta.url), new URL('iv_data.json', out))
// optional: the raid moveset data (src/refresh_movesets.py); the site works without it
const movesets = new URL('../../data/movesets.json', import.meta.url)
if (existsSync(movesets)) cpSync(movesets, new URL('movesets.json', out))
console.log('copied data into public/data')
