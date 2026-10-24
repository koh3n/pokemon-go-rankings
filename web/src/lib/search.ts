// The search box: resolve a name against the snapshot, build the tier result and attach IV
// ranks. Port of run_search(), add_ivs(), run_iv() and snapshot_slug() in src/pogo_ui.py.
import { DEFAULT_CAP, IvRanker, LEAGUES, LEVEL_CAPS, nameWords, type LeagueRank } from './ivrank'
import { FORM_GROUPS, buildFromSnapshot, type Snapshot, type TierResult } from './tiers'

export interface IvMon {
  name: string
  id: number
  base: [number, number, number]
  leagues: LeagueRank[]
  selected: boolean
}

export interface SearchResult extends TierResult {
  ivs?: { values: [number, number, number]; cap: number; error?: string }
  iv?: IvMon[]
}

const LEAGUE_MODES: Record<string, number> = { 'Great League': 0, 'Ultra League': 1, 'Master League': 2 }

/**
 * Slug of the snapshot entry whose name has the same words as q, or null. Lets form names
 * the plain lookup misses work in the search box: the autocomplete offers "Aegislash (Blade)"
 * (GO Hub: "Aegislash Sword Forme") and "Galarian Corsola" (a form page, not a species page).
 * loose also accepts entries with extra words, so "Aegislash" finds its first form.
 */
export function snapshotSlug(snap: Snapshot, q: string, loose = false): string | null {
  if (/^\d+(-\w+)?$/.test(q.trim())) return null
  const want = nameWords(q)
  if (!want.size) return null
  const names = snap.per_pokemon.map((p) => [nameWords(p.name), p] as const)
  const covers = (w: Set<string>, sub: Set<string>) => [...sub].every((x) => w.has(x))
  let hits = names.filter(([w]) => (loose ? covers(w, want) : w.size === want.size && covers(w, want))).map(([, p]) => p)
  if (!hits.length && loose && q.includes('(')) {
    // a PvPoke form the GO Hub has no page for
    const base = nameWords(q.split('(')[0])
    hits = names.filter(([w]) => covers(w, base)).map(([, p]) => p)
  }
  hits.sort(
    (a, b) =>
      +(a.group !== 'normal') - +(b.group !== 'normal') ||
      +a.name.toLowerCase().includes('shadow') - +b.name.toLowerCase().includes('shadow'),
  )
  if (!hits.length) return null
  const slug = hits[0].slug
  // the lookup only accepts plain slugs; forms like "741-Pa'u" start from the species instead
  return /^\d+(-[A-Za-z0-9_]+)?$/.test(slug) ? slug : String(hits[0].dex)
}

/** PvP IV ranks for a Pokémon (and every stage of its line). */
export function runIv(ranker: IvRanker, q: string, ivs: [number, number, number], cap: number): IvMon[] {
  let mons = ranker.findMons(q)
  if (!mons.length) {
    const exact = ranker.findExact(q) // e.g. "Shadow Cursola", "Galarian Shadow Meowth"
    if (exact) mons = [exact]
  }
  if (!mons.length) throw new Error(`No Pokémon matches '${q}' in the IV data.`)
  if (mons.length > 6) throw new Error(`'${q}' matches ${mons.length} Pokémon; be more specific.`)
  const seen = new Set<number>()
  const out: IvMon[] = []
  for (const base of mons)
    for (const m of ranker.lineOf(base)) {
      if (seen.has(m.id)) continue
      seen.add(m.id)
      out.push({
        name: m.name,
        id: m.id % 10000,
        base: [m.atk, m.def, m.sta],
        leagues: ranker.rankIvs(m, ...ivs, cap),
        selected: m.id === base.id,
      })
    }
  return out
}

function addIvs(result: SearchResult, ranker: IvRanker, q: string, ivs: [number, number, number], cap: number) {
  result.ivs = { values: ivs, cap }
  try {
    result.iv = runIv(ranker, q, ivs, cap)
  } catch (e) {
    result.iv = []
    result.ivs.error = (e as Error).message
  }
  const cache = new Map<string, LeagueRank[] | null>()
  const ranksFor = (name: string) => {
    if (!cache.has(name)) {
      // shadow Pokémon rank like their normal form (findExact ignores "Shadow")
      const mon = ranker.findExact(name)
      cache.set(name, mon ? ranker.rankIvs(mon, ...ivs, cap) : null)
    }
    return cache.get(name)!
  }
  for (const rows of Object.values(result.rankings))
    for (const r of rows) {
      const i = LEAGUE_MODES[r.mode]
      const ranks = i !== undefined ? ranksFor(r.pokemon) : null
      if (ranks) {
        const x = ranks[i]
        r.iv = { rank: x.rank, level: x.level, cp: x.cp, percent: x.percent, capped: x.capped }
      }
    }
}

export function runSearch(
  snap: Snapshot,
  ranker: IvRanker,
  q: string,
  forms: 'all' | 'none' | string[] = 'all',
  ivs: [number, number, number] | null = null,
  cap: number = DEFAULT_CAP,
): SearchResult {
  const wanted = new Set<string>(forms === 'all' ? FORM_GROUPS : forms === 'none' ? [] : forms)
  let slug = snapshotSlug(snap, q)
  let result: SearchResult
  try {
    result = buildFromSnapshot(snap, slug ?? q, wanted)
  } catch (e) {
    slug = slug ?? snapshotSlug(snap, q, true)
    if (!slug) throw e
    result = buildFromSnapshot(snap, slug, wanted)
  }
  result.query = q
  if (ivs) addIvs(result, ranker, q, ivs, cap)
  return result
}

/** "11/2/3", "11 2 3", "11,2,3" and "11-2-3" all work. Returns null for a blank box. */
export function parseIvs(raw: string): [number, number, number] | null {
  const text = raw.trim()
  if (!text) return null
  const parts = text.split(/[\s/,\-.]+/).filter(Boolean)
  if (parts.length !== 3 || !parts.every((p) => /^\d{1,2}$/.test(p) && Number(p) <= 15))
    throw new Error('IVs should be three numbers from 0 to 15, like 11/2/3 or 11 2 3.')
  return parts.map(Number) as [number, number, number]
}

export { LEAGUES, LEVEL_CAPS }
