import { useEffect, useMemo, useRef, useState } from 'react'
import { LEAGUES, LEVEL_CAPS, type IvRanker, type LeagueKey } from '../lib/ivrank'
import { pctClass } from '../lib/format'

const PAGE = 100

/** "0/15/15", "0 15 15", "*\/14/*", or a partial like "15/15"; * matches anything. */
function matcher(text: string): ((ivs: number[]) => boolean) | null {
  const parts = text.split(/[\s/,\-.]+/).filter(Boolean)
  if (!parts.length) return null
  if (parts.length === 3) return (ivs) => parts.every((p, i) => p === '*' || Number(p) === ivs[i])
  return (ivs) => ivs.join('/').includes(parts.join('/'))
}

function Spreads({ name, ranker }: { name: string; ranker: IvRanker }) {
  const [league, setLeague] = useState<LeagueKey>('great')
  const [cap, setCap] = useState(50)
  const [find, setFind] = useState('')
  const [shown, setShown] = useState(PAGE)

  const mon = useMemo(() => ranker.findExact(name), [ranker, name])
  const rows = useMemo(() => (mon ? ranker.allSpreads(mon, league, cap) : []), [ranker, mon, league, cap])
  const filtered = useMemo(() => {
    const m = matcher(find)
    return m ? rows.filter((r) => m([r[1], r[2], r[3]])) : rows
  }, [rows, find])

  if (!mon) return <p className="hint error">No Pokémon named '{name}' in the IV data.</p>
  const info = LEAGUES.find((l) => l.key === league)!
  const best = rows[0]
  const left = filtered.length - Math.min(shown, filtered.length)

  return (
    <>
      <div className="tabs">
        {LEAGUES.map((l) => (
          <button
            key={l.key}
            type="button"
            className="tab"
            role="tab"
            aria-selected={l.key === league}
            onClick={() => {
              setLeague(l.key)
              setShown(PAGE)
            }}
          >
            {l.label}
          </button>
        ))}
      </div>
      <div className="toolbar">
        <div className="row">
          <label>
            Level cap:{' '}
            <select
              value={cap}
              onChange={(e) => {
                setCap(Number(e.target.value))
                setShown(PAGE)
              }}
            >
              {LEVEL_CAPS.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
          <input
            className="flt"
            type="text"
            placeholder="Find IVs, e.g. 0/15/15 or */14/*"
            aria-label="Find an IV spread"
            autoComplete="off"
            value={find}
            onChange={(e) => {
              setFind(e.target.value)
              setShown(PAGE)
            }}
          />
        </div>
        <span style={{ color: 'var(--muted)', fontSize: 13 }}>
          {find.trim() ? `${filtered.length} of ${rows.length}` : `${rows.length} spreads`}
        </span>
      </div>
      <p className="hint" style={{ margin: '0 0 8px' }}>
        {info.cpCap ? `Highest level ≤ ${cap} that keeps CP at or under ${info.cpCap}. ` : `Powered to the level cap (${cap}). `}
        Best spread: {best[1]}/{best[2]}/{best[3]}
        {info.cpCap ? ` at L${best[4]} (${best[5]} CP).` : '.'} Base stats {mon.atk}/{mon.def}/{mon.sta}.
      </p>
      {!filtered.length ? (
        <div className="empty">No spreads match.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Rank</th>
              <th>IVs (Atk/Def/HP)</th>
              <th>%</th>
              <th>Level</th>
              <th>CP</th>
              <th>Atk</th>
              <th>Def</th>
              <th>HP</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, shown).map((r) => (
              <tr key={`${r[1]}/${r[2]}/${r[3]}`}>
                <td className="n">
                  <b>#{r[0]}</b>
                </td>
                <td className="iv">
                  {r[1]}/{r[2]}/{r[3]}
                </td>
                <td className={`n ${pctClass(r[6])}`}>{r[6].toFixed(2)}%</td>
                <td className="n">{r[4]}</td>
                <td className="n">{r[5]}</td>
                <td className="n">{r[7].toFixed(2)}</td>
                <td className="n">{r[8].toFixed(2)}</td>
                <td className="n">{r[9]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {left > 0 && (
        <div className="more">
          <button type="button" onClick={() => setShown(shown + PAGE)}>
            Show {Math.min(PAGE, left)} more
          </button>
          <button type="button" onClick={() => setShown(filtered.length)}>
            Show all ({left} left)
          </button>
        </div>
      )}
    </>
  )
}

/** One collapsible per Pokémon. The spreads are only computed once it has been opened. */
export function IvSection({ name, ranker, openNonce }: { name: string; ranker: IvRanker; openNonce: number }) {
  const ref = useRef<HTMLDetailsElement>(null)
  const [opened, setOpened] = useState(false)

  useEffect(() => {
    if (!openNonce || !ref.current) return
    ref.current.open = true
    setOpened(true)
    ref.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [openNonce])

  return (
    <details className="ivsec" ref={ref} onToggle={(e) => e.currentTarget.open && setOpened(true)}>
      <summary>{name}</summary>
      <div className="ivbody">{opened && <Spreads name={name} ranker={ranker} />}</div>
    </details>
  )
}
