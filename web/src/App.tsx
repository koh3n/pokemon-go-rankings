import { useCallback, useEffect, useMemo, useState } from 'react'
import { EvolutionTree } from './components/EvolutionTree'
import { IvPanel } from './components/IvPanel'
import { IvSection } from './components/IvSection'
import { MovesetSection, type TypeRank } from './components/MovesetSection'
import { NameInput } from './components/NameInput'
import { TierTable } from './components/TierTable'
import { DEFAULT_CAP, IvRanker, LEVEL_CAPS, type IvData } from './lib/ivrank'
import type { MovesetData } from './lib/movesets'
import { parseIvs, runSearch, type SearchResult } from './lib/search'
import { trackSearch } from './lib/track'
import { FORM_GROUPS, type EvoNode, type Snapshot } from './lib/tiers'
import type { ListRow } from './lib/movesets'

const LABELS: Record<string, string> = {
  normal: 'Normal',
  shadow: 'Shadow',
  regional: 'Regional',
  'regional-shadow': 'Regional Shadow',
  mega: 'Mega',
  primal: 'Primal',
  dynamax: 'Dynamax',
  gigantamax: 'Gigantamax',
  other: 'Other forms',
}
const label = (g: string) => LABELS[g] ?? g

interface Loaded {
  snap: Snapshot
  ranker: IvRanker
  movesets: MovesetData | null // optional: the rest of the site works without it
}

function treeNames(nodes: EvoNode[], out: string[] = []): string[] {
  for (const n of nodes) {
    if (!out.includes(n.name)) out.push(n.name)
    treeNames(n.evolves_to, out)
  }
  return out
}

async function loadJson<T>(path: string): Promise<T> {
  const res = await fetch(`${import.meta.env.BASE_URL}data/${path}`)
  if (!res.ok) throw new Error(`Couldn't load ${path} (${res.status}).`)
  return res.json()
}

export default function App() {
  const [data, setData] = useState<Loaded | null>(null)
  const [loadError, setLoadError] = useState('')
  const [q, setQ] = useState('')
  const [ivText, setIvText] = useState('')
  const [cap, setCap] = useState(DEFAULT_CAP)
  const [forms, setForms] = useState<Set<string>>(() => new Set(FORM_GROUPS))
  const [status, setStatus] = useState<{ text: string; error: boolean }>({ text: '', error: false })
  const [result, setResult] = useState<SearchResult | null>(null)
  const [group, setGroup] = useState('normal')
  const [mode, setMode] = useState('')
  // "IV spreads" links: which section to open, plus extra sections for Pokémon outside the tree
  const [ivReq, setIvReq] = useState<{ name: string; nonce: number }>({ name: '', nonce: 0 })
  const [extras, setExtras] = useState<string[]>([])
  // "Movesets" links: same idea, keyed by the Pokémon's page slug
  const [moveReq, setMoveReq] = useState<{ slug: string; nonce: number; type?: string }>({ slug: '', nonce: 0 })
  const [moveExtras, setMoveExtras] = useState<{ slug: string; name: string }[]>([])

  const search = useCallback(
    (d: Loaded, query: string, ivRaw: string, capValue: number, formSet: Set<string>, track = true) => {
      const text = query.trim()
      if (!text) return setStatus({ text: 'Type a Pokémon name or number.', error: true })
      try {
        const ivs = parseIvs(ivRaw)
        const res = runSearch(d.snap, d.ranker, text, formSet.size ? [...formSet] : 'none', ivs, capValue)
        if (track) trackSearch(text)
        setResult(res)
        setGroup('normal')
        setMode('')
        setExtras([])
        setIvReq({ name: '', nonce: 0 })
        setMoveExtras([])
        setMoveReq({ slug: '', nonce: 0 })
        setStatus({ text: '', error: false })
        const params = new URLSearchParams({ q: text })
        if (ivs) Object.entries({ iv: ivs.join('/'), cap: String(capValue) }).forEach(([k, v]) => params.set(k, v))
        history.replaceState(null, '', `?${params}`)
      } catch (e) {
        setStatus({ text: (e as Error).message, error: true })
      }
    },
    [],
  )

  useEffect(() => {
    Promise.all([
      loadJson<Snapshot>('all_rankings.json'),
      loadJson<IvData>('iv_data.json'),
      loadJson<MovesetData>('movesets.json').catch(() => null),
    ])
      .then(([snap, iv, movesets]) => {
        const d = { snap, ranker: new IvRanker(iv), movesets }
        setData(d)
        // run the search in the address bar (?q=azumarill&iv=0/15/15&cap=50)
        const p = new URLSearchParams(location.search)
        const q0 = p.get('q')
        if (!q0) return
        const cap0 = Number(p.get('cap')) || DEFAULT_CAP
        setQ(q0)
        setIvText(p.get('iv') ?? '')
        setCap(cap0)
        search(d, q0, p.get('iv') ?? '', cap0, new Set(FORM_GROUPS), false)
      })
      .catch((e: Error) => setLoadError(e.message))
  }, [search])

  const groups = useMemo(
    () => (result ? ['normal', ...FORM_GROUPS].filter((g) => result.rankings[g]?.length) : []),
    [result],
  )
  const activeGroup = groups.includes(group) ? group : (groups[0] ?? 'normal')
  const root = result?.evolution_tree[0]
  const sections = useMemo(() => {
    if (!result) return []
    const names = treeNames(result.evolution_tree)
    return [...names, ...extras.filter((n) => !names.includes(n))]
  }, [result, extras])

  const openIv = useCallback(
    (name: string) => {
      const base = name.replace(/^Shadow /i, '')
      setExtras((x) => (x.includes(base) ? x : [...x, base]))
      setIvReq((r) => ({ name: base.toLowerCase(), nonce: r.nonce + 1 }))
    },
    [setExtras],
  )

  const moveSections = useMemo(() => {
    if (!result) return []
    const nodes: { slug: string; name: string }[] = []
    const walk = (ns: EvoNode[]) =>
      ns.forEach((n) => {
        if (!nodes.some((x) => x.slug === n.slug)) nodes.push({ slug: n.slug, name: n.name })
        walk(n.evolves_to)
      })
    walk(result.evolution_tree)
    return [...nodes, ...moveExtras.filter((e) => !nodes.some((n) => n.slug === e.slug))]
  }, [result, moveExtras])

  const openMoves = useCallback((slug: string, name: string, type?: string) => {
    setMoveExtras((x) => (x.some((e) => e.slug === slug) ? x : [...x, { slug, name }]))
    setMoveReq((r) => ({ slug, type, nonce: r.nonce + 1 }))
  }, [])
  // the type lists each Pokémon is ranked in ("Rock-type" -> rock) with its tier and rank: the only types the moveset card offers
  const rankedTypes = useMemo(() => {
    const m = new Map<string, TypeRank[]>()
    for (const p of data?.snap.per_pokemon ?? []) {
      const best = new Map<string, TypeRank>()
      for (const r of p.rankings) {
        const type = /^(\w+)-type$/i.exec(r.mode)?.[1].toLowerCase()
        if (type && !best.has(type)) best.set(type, { type, tier: r.tier, rank: r.rank })
      }
      m.set(p.slug, [...best.values()])
    }
    return m
  }, [data])
  const typeLists = useMemo(() => {
    const m = new Map<string, ListRow[]>()
    for (const p of data?.snap.per_pokemon ?? [])
      for (const r of p.rankings) {
        const type = /^(\w+)-type$/i.exec(r.mode)?.[1].toLowerCase()
        if (!type) continue
        const rows = m.get(type) ?? m.set(type, []).get(type)!
        if (!rows.some((x) => x.slug === p.slug)) rows.push({ slug: p.slug, tier: r.tier, rank: r.rank })
      }
    return m
  }, [data])
  const hasMoves = useCallback((slug: string) => !!data?.movesets?.pokemon[slug], [data])

  const names = useMemo(() => (data ? [...new Set(data.ranker.mons.map((m) => m.name))].sort() : []), [data])
  const asOf = data?.snap.scraped_at ? `· Rankings as of ${data.snap.scraped_at.slice(0, 10)}` : ''

  return (
    <>
      <main>
        <h1>GO Tier Lookup</h1>
        <p className="sub">
          Tier rankings for a Pokémon, its whole evolution line and its forms — from db.pokemongohub.net, with IV spreads
          calculated in your browser.
        </p>

        <div className="card">
          <form
            className="row"
            id="form"
            onSubmit={(e) => {
              e.preventDefault()
              if (data) search(data, q, ivText, cap, forms)
            }}
          >
            <NameInput
              value={q}
              onChange={setQ}
              names={names}
              onSubmit={() => data && search(data, q, ivText, cap, forms)}
            />
            <button className="primary" type="submit" disabled={!data}>
              Search
            </button>
          </form>
          <div className="row ivrow">
            <span className="hint" style={{ margin: 0 }}>
              Your IVs (optional):
            </span>
            <input
              className="ivtext"
              type="text"
              form="form"
              placeholder="e.g. 11/2/3 or 11 2 3"
              aria-label="IVs: attack, defense, HP"
              autoComplete="off"
              value={ivText}
              onChange={(e) => setIvText(e.target.value)}
            />
            <select form="form" aria-label="Level cap" title="Highest level you'd power it to" value={cap} onChange={(e) => setCap(Number(e.target.value))}>
              {LEVEL_CAPS.map((c) => (
                <option key={c} value={c}>
                  Lv {c}
                </option>
              ))}
            </select>
          </div>
          <div className="forms">
            <span>Include forms:</span>
            {FORM_GROUPS.map((g) => (
              <label key={g}>
                <input
                  type="checkbox"
                  checked={forms.has(g)}
                  onChange={(e) =>
                    setForms((s) => {
                      const next = new Set(s)
                      if (e.target.checked) next.add(g)
                      else next.delete(g)
                      return next
                    })
                  }
                />{' '}
                {label(g)}
              </label>
            ))}
          </div>
        </div>

        <p id="status" className={status.error || loadError ? 'error' : ''} role="status">
          {loadError || status.text || (!data ? 'Loading data…' : '')}
        </p>

        {result && (
          <div>
            <div className="card">
              <div className="toolbar">
                <h2 style={{ margin: 0 }}>{root ? `${root.name} line` : result.query}</h2>
              </div>
              <div className="tabs" role="tablist">
                {(groups.length ? groups : ['normal']).map((g) => (
                  <button
                    key={g}
                    type="button"
                    className="tab"
                    role="tab"
                    aria-selected={g === activeGroup}
                    onClick={() => {
                      setGroup(g)
                      setMode('')
                    }}
                  >
                    {label(g)}
                    <small>{(result.rankings[g] ?? []).length}</small>
                  </button>
                ))}
              </div>
              <TierTable
                result={result}
                group={activeGroup}
                mode={mode}
                onMode={setMode}
                onIv={openIv}
                onMoves={openMoves}
                hasMoves={hasMoves}
              />
            </div>

            <IvPanel result={result} onIv={openIv} />

            <div className="card">
              <h2>Evolution tree</h2>
              <EvolutionTree roots={result.evolution_tree} labelOf={label} onIv={openIv} onMoves={openMoves} hasMoves={hasMoves} />
            </div>

            {data?.movesets && (
              <div className="card" id="movesets-card">
                <h2>Best movesets (PvE)</h2>
                <p className="hint" style={{ margin: '0 0 6px' }}>
                  The best moveset for each Pokémon in PvE.
                </p>
                <div>
                  {moveSections.map((m) => (
                    <MovesetSection
                      key={`${result.query}|${m.slug}`}
                      slug={m.slug}
                      name={m.name}
                      data={data.movesets!}
                      ranked={rankedTypes.get(m.slug) ?? []}
                      lists={typeLists}
                      openNonce={moveReq.slug === m.slug ? moveReq.nonce : 0}
                      preset={moveReq.slug === m.slug ? moveReq.type : undefined}
                    />
                  ))}
                </div>
              </div>
            )}

            {data && (
              <div className="card" id="ivspreads-card">
                <h2>IV spreads</h2>
                <p className="hint" style={{ margin: '0 0 6px' }}>
                  Every IV combination for each Pokémon in the line, best first. Expand one to see Great, Ultra and Master League.
                </p>
                <div>
                  {sections.map((name) => (
                    <IvSection
                      key={`${result.query}|${name}`}
                      name={name}
                      ranker={data.ranker}
                      openNonce={ivReq.name === name.toLowerCase() ? ivReq.nonce : 0}
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </main>
      <footer className="foot">
        Data: <a href="https://db.pokemongohub.net" target="_blank" rel="noopener">Pokémon GO Hub</a> · Base stats:{' '}
        <a href="https://pvpoke.com" target="_blank" rel="noopener">PvPoke</a> · Sprites:{' '}
        <a href="https://github.com/PokeAPI/sprites" target="_blank" rel="noopener">PokeAPI</a> <span>{asOf}</span>
      </footer>
    </>
  )
}
