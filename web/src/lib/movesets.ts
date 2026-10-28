// Which fast + charged move is best when the boss takes a given effectiveness multiplier from a type?
// Port of src/moveset_model.py (the formulas and constants are described there). Move stats come from
// data/movesets.json; K and f per Pokémon were fitted to GO Hub's own neutral-boss numbers.

export type MoveRow = [name: string, type: string, power: number, energy: number, durationMs: number, fast: 0 | 1]

export interface MovesetEntry {
  t: string[] // the Pokémon's types
  k: number // attack scale (level, Shadow/Mega boosts folded in)
  f: number // eDPS / DPS
  e: number // mean % error of the fit; the tier view is hidden above MAX_FIT_ERROR
  m: [moveId: number, legacy: 0 | 1][]
}

export interface MovesetData {
  moves: Record<string, MoveRow>
  pokemon: Record<string, MovesetEntry>
}

export const STEPS = [1, 1.6, 2.56] as const
export const MAX_FIT_ERROR = 8
const STAB = 1.2
const UNUSABLE = new Set(['Frustration']) // Shadow-only; GO Hub scores it as zero
// Calibrated against GO Hub's numbers: the plain model is slightly high for 100-energy charged moves
// and slightly low for 33-energy ones.
const BAR_CORRECTION = { 1: 0.9585, 2: 1.0062, 3: 1.0217 } as const

interface Move {
  name: string
  type: string
  power: number
  energy: number
  duration: number
  fast: boolean
  legacy: boolean
  stab: boolean
}

export interface Pick {
  fast: string
  fastType: string
  charged: string
  chargedType: string
  fastLegacy: boolean
  chargedLegacy: boolean
  edps: number
}

export interface TierResult {
  step: number
  picks: Pick[] // best first, at most two
}

const secs = (ms: number) => Math.max(0.5, Math.round((ms / 1000) * 2) / 2) // raid durations are whole half-seconds

const bars = (c: Move) => (c.energy >= 100 ? 1 : c.energy >= 50 ? 2 : 3)

function hit(m: Move, k: number, mult: number) {
  return 0.5 * m.power * k * (m.stab ? STAB : 1) * mult + 0.5
}

function cycleDps(fast: Move, charged: Move, k: number, mults: Record<string, number>) {
  if (fast.energy <= 0) return 0
  let n = charged.energy / fast.energy
  if (charged.energy >= 100) n = Math.ceil(n - 1e-9) // a full bar is capped at 100, so overflow energy is wasted
  const damage = n * hit(fast, k, mults[fast.type] ?? 1) + hit(charged, k, mults[charged.type] ?? 1)
  return (BAR_CORRECTION[bars(charged)] * damage) / (n * secs(fast.duration) + secs(charged.duration))
}

function movesOf(data: MovesetData, e: MovesetEntry): Move[] {
  const out: Move[] = []
  for (const [id, legacy] of e.m) {
    const row = data.moves[String(id)]
    if (!row) continue
    const [name, type, power, energy, duration, fast] = row
    if (UNUSABLE.has(name)) continue
    out.push({ name, type, power, energy, duration, fast: fast === 1, legacy: legacy === 1, stab: e.t.includes(type) && name !== 'Hidden Power' })
  }
  return out
}

/** The types of the Pokémon's usable moves: the choices for "the boss is weak to ...". */
export function moveTypes(data: MovesetData, slug: string): string[] {
  const e = data.pokemon[slug]
  return e ? [...new Set(movesOf(data, e).map((m) => m.type))].sort() : []
}

/** The tier view is only shown when the calculator reproduces GO Hub's numbers for this Pokémon. */
export function hasTierView(data: MovesetData, slug: string): boolean {
  const e = data.pokemon[slug]
  return !!e && e.e <= MAX_FIT_ERROR && moveTypes(data, slug).length > 0
}

/** Best movesets at 1x / 1.6x / 2.56x when `featuredType` hits at that multiplier and every other type at 1x. */
export function tierView(data: MovesetData, slug: string, featuredType: string, allowLegacy = true): TierResult[] {
  const e = data.pokemon[slug]
  if (!e) return []
  const moves = movesOf(data, e)
  const fast = moves.filter((m) => m.fast)
  const charged = moves.filter((m) => !m.fast)
  return STEPS.map((step) => {
    const mults = { [featuredType]: step }
    const rows: { f: Move; c: Move; dps: number }[] = []
    for (const f of fast)
      for (const c of charged) {
        if (!allowLegacy && (f.legacy || c.legacy)) continue
        rows.push({ f, c, dps: cycleDps(f, c, e.k, mults) })
      }
    rows.sort((a, b) => b.dps - a.dps) // stable, like the Python version
    return {
      step,
      picks: rows.slice(0, 2).map((r) => ({
        fast: r.f.name,
        fastType: r.f.type,
        charged: r.c.name,
        chargedType: r.c.type,
        fastLegacy: r.f.legacy,
        chargedLegacy: r.c.legacy,
        edps: r.dps * e.f,
      })),
    }
  })
}

/** The neutral-boss result. No move type is favoured, so it is the same whichever type is featured. */
export function neutralView(data: MovesetData, slug: string, allowLegacy = true): TierResult | undefined {
  const first = moveTypes(data, slug)[0]
  return first === undefined ? undefined : tierView(data, slug, first, allowLegacy)[0]
}

/** Default featured type among `types`: the one whose boost helps this Pokémon most at 1.6x. */
export function defaultType(data: MovesetData, slug: string, types: string[] = moveTypes(data, slug)): string {
  let best = types[0] ?? ''
  let bestScore = -1
  for (const t of types) {
    const score = tierView(data, slug, t)[1]?.picks[0]?.edps ?? 0
    if (score > bestScore) {
      best = t
      bestScore = score
    }
  }
  return best
}

// the defender types each attacking type hits super effectively (same chart as src/moveset_model.py)
const SUPER_EFFECTIVE: Record<string, string[]> = {
  normal: [],
  fire: ['grass', 'ice', 'bug', 'steel'],
  water: ['fire', 'ground', 'rock'],
  electric: ['water', 'flying'],
  grass: ['water', 'ground', 'rock'],
  ice: ['grass', 'ground', 'flying', 'dragon'],
  fighting: ['normal', 'ice', 'rock', 'dark', 'steel'],
  poison: ['grass', 'fairy'],
  ground: ['fire', 'electric', 'poison', 'rock', 'steel'],
  flying: ['grass', 'fighting', 'bug'],
  psychic: ['fighting', 'poison'],
  bug: ['grass', 'psychic', 'dark'],
  rock: ['fire', 'ice', 'flying', 'bug'],
  ghost: ['psychic', 'ghost'],
  dragon: ['dragon'],
  dark: ['psychic', 'ghost'],
  steel: ['ice', 'rock', 'fairy'],
  fairy: ['fighting', 'dragon', 'dark'],
}

export const superEffectiveAgainst = (type: string): string[] => SUPER_EFFECTIVE[type] ?? []
