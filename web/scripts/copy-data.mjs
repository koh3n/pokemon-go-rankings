// Copy the scraped data into public/ so the app can fetch it as static files.
import { cpSync, mkdirSync } from 'node:fs'

const out = new URL('../public/data/', import.meta.url)
mkdirSync(out, { recursive: true })
cpSync(new URL('../../data/all_rankings.json', import.meta.url), new URL('all_rankings.json', out))
cpSync(new URL('../../data/cache/iv_data.json', import.meta.url), new URL('iv_data.json', out))
console.log('copied data into public/data')
