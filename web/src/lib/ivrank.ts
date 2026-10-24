// PvP IV rank calculator (Great / Ultra / Master League). Port of src/ivrank.py.
//
// For each of the 4096 IV combinations the highest level (<= the level cap) that
// keeps CP under the league limit is found, and combinations are ordered by stat
// product (attack x defense x floor(HP)). Equal stat products share a rank.

export interface Mon {
  id: number
  name: string
  atk: number
  def: number
  sta: number
  family: number[]
}

export interface IvData {
  cpm: number[]
  mons: Mon[]
}

export type LeagueKey = 'great' | 'ultra' | 'master'

export const LEAGUES: { key: LeagueKey; label: string; cpCap: number | null }[] = [
  { key: 'great', label: 'Great League', cpCap: 1500 },
  { key: 'ultra', label: 'Ultra League', cpCap: 2500 },
  { key: 'master', label: 'Master League', cpCap: null },
]
export const LEVEL_CAPS = [40, 41, 50, 51] as const
export const DEFAULT_CAP = 50

/** [rank, atkIv, defIv, hpIv, level, cp, percent, atk, def, hp] */
export type SpreadRow = [number, number, number, number, number, number, number, number, number, number]

export interface LeagueRank {
  league: string
  cp_cap: number | null
  rank: number
  of: number
  level: number
  cp: number
  percent: number
  capped: boolean
}

type Table = Record<LeagueKey, [number, number, number][]> // [statProduct, level, cp] by a*256+d*16+s

/**
 * Python's round(x, 2): correctly rounded from the exact binary value, with true ties going to
 * the even hundredth. toFixed also rounds the exact value but sends ties up, so ties are fixed here.
 */
function round2(x: number): number {
  const scaled = x * 100
  // far from a rounding boundary the plain result is exact; only the exact check below is slow
  if (Math.abs(scaled - Math.floor(scaled) - 0.5) > 1e-6) return Math.round(scaled) / 100
  // eslint-disable-next-line -- toFixed takes up to 100 digits in every current engine
  const [int, frac] = x.toFixed(40).split('.')
  if (frac.slice(2) === '5' + '0'.repeat(37) && Number(frac[1]) % 2 === 0) return Number(`${int}.${frac.slice(0, 2)}`)
  return Number(x.toFixed(2))
}

const cp = (A: number, D: number, S: number, c: number) =>
  Math.max(10, Math.floor((A * Math.sqrt(D * S) * c * c) / 10))

const NOISE = new Set(['shadow', 'form', 'forme', 'mode', 'style', 'size', 'breed', 'mask'])
const NOT_PVP = new Set(['mega', 'primal', 'dynamax', 'gigantamax', 'eternamax'])
const SYNONYMS: Record<string, string> = { sunny: 'sunshine', sword: 'blade' } // GO Hub wording -> PvPoke wording

export function normName(s: string): string {
  return s
    .toLowerCase()
    .replace(/é/g, 'e')
    .replace(/[^a-z0-9]+/g, '')
}

/** The set of words in a name, ignoring order, accents, "Shadow" and filler like "Forme". */
export function nameWords(name: string): Set<string> {
  const s = name
    .toLowerCase()
    .replace(/♀/g, ' f')
    .replace(/♂/g, ' m')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
  const out = new Set<string>()
  for (const w of s.split(/[^a-z0-9]+/)) {
    if (w && !NOISE.has(w)) out.add(SYNONYMS[w] ?? w)
  }
  return out
}

const isSubset = (a: Set<string>, b: Set<string>) => [...a].every((w) => b.has(w))

export class IvRanker {
  readonly cpm: number[]
  readonly mons: Mon[]
  private words: [Set<string>, Mon][]
  private tables = new Map<string, Table>()

  constructor(data: IvData) {
    this.cpm = data.cpm
    this.mons = data.mons
    this.words = data.mons.map((m) => [nameWords(m.name), m])
  }

  /** Match by exact name, Pokédex number (all forms), or unique prefix/substring. */
  findMons(query: string): Mon[] {
    const q = query.trim()
    if (/^\d+$/.test(q)) return this.mons.filter((m) => m.id % 10000 === Number(q))
    const n = normName(q)
    const exact = this.mons.filter((m) => normName(m.name) === n)
    if (exact.length) {
      // "raichu" also finds "Alolan Raichu"
      const forms = this.mons.filter(
        (m) => !exact.includes(m) && m.name.toLowerCase().endsWith(' ' + q.toLowerCase()),
      )
      return [...exact, ...forms]
    }
    return this.mons.filter((m) => n && normName(m.name).includes(n))
  }

  /**
   * One Pokémon by name, spelled however the GO Hub spells it. Matching is by the set of words,
   * so word order, "Shadow" and filler like "Forme" don't matter. The best match is the Pokémon
   * whose words are all in the query and are the most numerous; a bare species name falls back
   * to its first listed form. Mega/Primal/Dynamax/Gigantamax can't battle in PvP, so match nothing.
   */
  findExact(name: string): Mon | null {
    const q = nameWords(name)
    if (!q.size || [...q].some((w) => NOT_PVP.has(w))) return null
    let best: Mon | null = null
    let bestKey: [number, number] | null = null
    for (const [w, m] of this.words) {
      if (!isSubset(w, q)) continue
      const key: [number, number] = [w.size, [...w].reduce((n, x) => n + x.length, 0)]
      if (!bestKey || key[0] > bestKey[0] || (key[0] === bestKey[0] && key[1] > bestKey[1])) {
        best = m
        bestKey = key
      }
    }
    if (best) return best
    const letters = [...q].join('').split('').sort().join('') // PvPoke writes "Irontreads", the GO Hub "Iron Treads"
    for (const [w, m] of this.words) {
      if ([...w].join('').split('').sort().join('') === letters) return m
    }
    for (const [w, m] of this.words) if (isSubset(q, w)) return m
    return null
  }

  /** The Pokémon plus its relatives, in evolution order. */
  lineOf(mon: Mon): Mon[] {
    const byId = new Map(this.mons.map((m) => [m.id, m]))
    const out = [mon]
    for (const i of mon.family) {
      const m = byId.get(i)
      if (m && i !== mon.id) out.push(m)
    }
    // base-stat product grows along an evolution line, so it gives evolution order
    return out.sort((a, b) => a.atk * a.def * a.sta - b.atk * b.def * b.sta)
  }

  private capIndex(levelCap: number) {
    if (!(LEVEL_CAPS as readonly number[]).includes(levelCap))
      throw new Error(`level cap must be one of ${LEVEL_CAPS.join(', ')}`)
    return Math.min(Math.trunc((levelCap - 1) * 2), this.cpm.length - 1)
  }

  private table(mon: Mon, capIdx: number): Table {
    const key = `${mon.id}:${capIdx}`
    const hit = this.tables.get(key)
    if (hit) return hit
    const out = {} as Table
    for (const { key: league, cpCap } of LEAGUES) {
      const rows: [number, number, number][] = []
      for (let ia = 0; ia < 16; ia++)
        for (let idf = 0; idf < 16; idf++)
          for (let ist = 0; ist < 16; ist++) {
            const A = mon.atk + ia
            const D = mon.def + idf
            const S = mon.sta + ist
            let best = -1
            for (let i = capIdx; i >= 0; i--) {
              // highest level first
              if (cpCap === null || cp(A, D, S, this.cpm[i]) <= cpCap) {
                best = i
                break
              }
            }
            if (best < 0) best = 0 // can't get under the cap at all
            const c = this.cpm[best]
            rows.push([round2(A * c * (D * c) * Math.floor(S * c)), best / 2 + 1, cp(A, D, S, c)])
          }
      out[league] = rows
    }
    this.tables.set(key, out)
    return out
  }

  /** Rank of one IV spread for one species, per league. */
  rankIvs(mon: Mon, ia: number, idf: number, ist: number, levelCap = DEFAULT_CAP): LeagueRank[] {
    for (const v of [ia, idf, ist]) if (!(v >= 0 && v <= 15)) throw new Error('IVs must be between 0 and 15')
    const tab = this.table(mon, this.capIndex(levelCap))
    const idx = ia * 256 + idf * 16 + ist
    return LEAGUES.map(({ key, label, cpCap }) => {
      const rows = tab[key]
      const [sp, level, cpv] = rows[idx]
      let better = 0
      let best = 0
      for (const r of rows) {
        if (r[0] > sp) better++
        if (r[0] > best) best = r[0]
      }
      // "capped": the CP limit actually restricts this species (15/15/15 would exceed it)
      const capped = cpCap === null || rows[4095][2] > cpCap || rows[4095][1] < levelCap
      return {
        league: label,
        cp_cap: cpCap,
        rank: 1 + better,
        of: 4096,
        level,
        cp: cpv,
        percent: round2((sp / best) * 100),
        capped,
      }
    })
  }

  /**
   * Every one of the 4096 IV spreads for one league, best first. Ties share a rank.
   * The last three columns are the in-battle stats.
   */
  allSpreads(mon: Mon, league: LeagueKey, levelCap = DEFAULT_CAP): SpreadRow[] {
    const rows = this.table(mon, this.capIndex(levelCap))[league]
    const order = Array.from({ length: 4096 }, (_, i) => i).sort((a, b) => rows[b][0] - rows[a][0])
    const best = rows[order[0]][0]
    const out: SpreadRow[] = []
    let rank = 0
    let prev: number | null = null
    order.forEach((i, pos) => {
      const [sp, lvl, cpv] = rows[i]
      if (sp !== prev) {
        rank = pos + 1
        prev = sp
      }
      const c = this.cpm[Math.round((lvl - 1) * 2)]
      out.push([
        rank,
        i >> 8,
        (i >> 4) & 15,
        i & 15,
        lvl,
        cpv,
        round2((sp / best) * 100),
        round2((mon.atk + (i >> 8)) * c),
        round2((mon.def + ((i >> 4) & 15)) * c),
        Math.floor((mon.sta + (i & 15)) * c),
      ])
    })
    return out
  }
}
