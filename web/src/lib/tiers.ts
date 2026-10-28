// Tier rankings + evolution tree from the saved snapshot. Port of build_from_snapshot()
// and assemble() in src/pogo_tiers.py; the scraper itself stays in Python.

export const BASE = 'https://db.pokemongohub.net'
export const TIER_ORDER = ['SS', 'S+', 'S', 'A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'E', 'F']
const TIER_INDEX = new Map(TIER_ORDER.map((t, i) => [t, i]))
const REGIONAL_TAGS = new Set(['alola', 'alolan', 'galar', 'galarian', 'hisui', 'hisuian', 'paldea', 'paldean'])
export const FORM_GROUPS = [
  'shadow',
  'regional',
  'regional-shadow',
  'mega',
  'primal',
  'dynamax',
  'gigantamax',
  'other',
] as const

export interface Ranking {
  mode: string
  tier: string
  rank: number | null
  off_type?: boolean // from GO Hub's per-type list, not a tile on the Pokémon's own page
}

export interface SnapshotPokemon {
  slug: string
  name: string
  group: string
  dex: number
  url: string
  rankings: Ranking[]
  unranked_modes: string[]
}

export interface Snapshot {
  source: string
  scraped_at: string
  per_pokemon: SnapshotPokemon[]
  evolutions: { from: string; to: string; requires: string | null }[]
}

export interface RankRow {
  pokemon: string
  slug: string
  mode: string
  tier: string
  rank: number | null
  position: number
  iv?: { rank: number; level: number; cp: number; percent: number; capped: boolean }
}

export interface EvoNode {
  slug: string
  name: string
  url: string
  requires: string | null
  evolves_to: EvoNode[]
  forms: { slug: string; name: string; group: string; url: string }[]
}

export interface TierResult {
  query: string
  resolved_slug: string
  source: string
  tier_order_best_to_worst: string[]
  evolution_tree: EvoNode[]
  rankings: Record<string, RankRow[]>
  per_pokemon: SnapshotPokemon[]
}

// ---- slugs / forms ----
export function splitSlug(slug: string): [number | null, string | null] {
  const m = /^(\d+)(?:-(.+))?$/.exec(slug)
  return m ? [Number(m[1]), m[2] ?? null] : [null, null]
}

export function formGroup(slug: string): string {
  const [, tag] = splitSlug(slug)
  if (!tag) return 'normal'
  const parts = tag.split('_').map((p) => p.toLowerCase())
  if (REGIONAL_TAGS.has(parts[0])) return parts.includes('shadow') ? 'regional-shadow' : 'regional'
  if (['shadow', 'mega', 'primal', 'dynamax', 'gigantamax'].includes(parts[0])) return parts[0]
  return 'other'
}

/** The plain Pokémon a form belongs to (regional forms count as their own base). */
function baseSlug(slug: string): string {
  const [dex, tag] = splitSlug(slug)
  if (tag && REGIONAL_TAGS.has(tag.split('_')[0].toLowerCase())) return `${dex}-${tag.split('_')[0]}`
  return String(dex)
}

export function norm(text: string): string {
  return text
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '')
}

const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0)

function groupRankings(per: SnapshotPokemon[]): Record<string, RankRow[]> {
  const byGroup: Record<string, (RankRow & { dex: number })[]> = {}
  for (const p of per)
    for (const r of p.rankings)
      (byGroup[p.group] ??= []).push({
        pokemon: p.name,
        slug: p.slug,
        dex: p.dex,
        mode: r.mode,
        tier: r.tier,
        rank: r.rank,
        position: 0,
      })
  const out: Record<string, RankRow[]> = {}
  for (const [g, items] of Object.entries(byGroup)) {
    items.sort(
      (a, b) =>
        (TIER_INDEX.get(a.tier) ?? TIER_ORDER.length) - (TIER_INDEX.get(b.tier) ?? TIER_ORDER.length) ||
        (a.rank ?? 1e9) - (b.rank ?? 1e9) ||
        a.dex - b.dex ||
        cmp(a.mode, b.mode),
    )
    out[g] = items.map(({ dex: _dex, ...r }, i) => ({ ...r, position: i + 1 }))
  }
  return out
}

function assemble(
  query: string,
  start: string,
  keep: Map<string, string>,
  edges: Snapshot['evolutions'],
  pageOf: (slug: string) => SnapshotPokemon,
): TierResult {
  // species the site only lists as forms (Shellos) count as "normal"
  const plain = new Set([...keep.keys()].filter((s) => /^\d+$/.test(s)).map((s) => splitSlug(s)[0]))
  const grp = (slug: string) => {
    const g = formGroup(slug)
    return g === 'other' && !plain.has(splitSlug(slug)[0]) ? 'normal' : g
  }

  const per: SnapshotPokemon[] = [...keep.keys()]
    .sort((a, b) => splitSlug(a)[0]! - splitSlug(b)[0]! || +(grp(a) !== 'normal') - +(grp(b) !== 'normal') || cmp(a, b))
    .map((slug) => {
      const page = pageOf(slug)
      return {
        slug,
        name: keep.get(slug)!,
        group: grp(slug),
        dex: splitSlug(slug)[0]!,
        url: `${BASE}/pokemon/${slug}`,
        rankings: page.rankings,
        unranked_modes: page.unranked_modes ?? [],
      }
    })

  // evolution tree. Mega/Primal rows in the chart are forms, not evolutions -> excluded here.
  const nodes = new Map<string, EvoNode>()
  for (const [slug, name] of keep)
    if (['normal', 'regional'].includes(grp(slug)))
      nodes.set(slug, { slug, name, url: `${BASE}/pokemon/${slug}`, requires: null, evolves_to: [], forms: [] })
  const hasParent = new Set<string>()
  for (const e of edges) {
    const from = nodes.get(e.from)
    const to = nodes.get(e.to)
    if (from && to) {
      to.requires = e.requires
      if (!from.evolves_to.some((c) => c.slug === e.to)) from.evolves_to.push(to)
      hasParent.add(e.to)
    }
  }
  for (const [slug, name] of keep) {
    const g = grp(slug)
    if (g === 'normal' || g === 'regional') continue
    const owner = nodes.get(baseSlug(slug)) ?? nodes.get(String(splitSlug(slug)[0]))
    owner?.forms.push({ slug, name, group: g, url: `${BASE}/pokemon/${slug}` })
  }
  // regional nodes are also forms of their plain Pokémon
  for (const [slug, node] of nodes) {
    if (grp(slug) === 'regional' && !hasParent.has(slug)) {
      const owner = nodes.get(String(splitSlug(slug)[0]))
      owner?.forms.push({ slug, name: node.name, group: 'regional', url: node.url })
    }
  }
  const roots = [...nodes].filter(([s]) => !hasParent.has(s) && grp(s) === 'normal').map(([, n]) => n)
  roots.push(...[...nodes].filter(([s]) => !hasParent.has(s) && grp(s) === 'regional').map(([, n]) => n))

  return {
    query,
    resolved_slug: start,
    source: BASE,
    tier_order_best_to_worst: TIER_ORDER,
    evolution_tree: roots,
    rankings: groupRankings(per),
    per_pokemon: per,
  }
}

export function buildFromSnapshot(snap: Snapshot, query: string, wanted: Set<string>): TierResult {
  const bySlug = new Map(snap.per_pokemon.map((p) => [p.slug, p]))
  const q = query.trim()
  let start: string
  if (/^\d+$/.test(q)) start = String(Number(q))
  else if (/^\d+-[A-Za-z0-9_]+$/.test(q)) start = q
  else {
    const names = new Map<string, string>()
    for (const p of snap.per_pokemon) {
      if (/^\d+$/.test(p.slug)) {
        if (!names.has(norm(p.name))) names.set(norm(p.name), p.slug)
      } else if (p.group === 'normal') {
        // species the site only lists as forms
        const base = norm(p.name.replace(/\s*\(.*\)\s*$/, ''))
        if (!names.has(base)) names.set(base, p.slug)
      }
    }
    const key = norm(q)
    const hit = names.get(key)
    if (hit === undefined) {
      const close = [...names.keys()]
        .filter((n) => key && n.includes(key))
        .sort()
        .slice(0, 8)
      const hint = close.length ? ` Did you mean one of: ${close.join(', ')}?` : ''
      throw new Error(`Couldn't find '${query}'.${hint} You can also pass the Pokedex number (e.g. 4).`)
    }
    start = hit
  }
  if (!bySlug.has(start)) throw new Error(`'${query}' isn't in the saved rankings (try 'Refresh data').`)

  const adj = new Map<number, Set<number>>()
  for (const e of snap.evolutions) {
    const a = splitSlug(e.from)[0]!
    const b = splitSlug(e.to)[0]!
    ;(adj.get(a) ?? adj.set(a, new Set()).get(a)!).add(b)
    ;(adj.get(b) ?? adj.set(b, new Set()).get(b)!).add(a)
  }
  const dexes = new Set<number>()
  const todo = [splitSlug(start)[0]!]
  while (todo.length) {
    const d = todo.pop()!
    if (!dexes.has(d)) {
      dexes.add(d)
      todo.push(...(adj.get(d) ?? []))
    }
  }

  const keep = new Map<string, string>()
  for (const p of snap.per_pokemon)
    if (dexes.has(p.dex) && (p.group === 'normal' || wanted.has(p.group))) keep.set(p.slug, p.name)
  if (!keep.has(start)) keep.set(start, bySlug.get(start)!.name)
  const lineEdges = snap.evolutions.filter((e) => dexes.has(splitSlug(e.from)[0]!) && dexes.has(splitSlug(e.to)[0]!))
  return assemble(query, start, keep, lineEdges, (slug) => bySlug.get(slug)!)
}
