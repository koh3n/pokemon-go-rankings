import { pctClass } from '../lib/format'
import type { IvMon, SearchResult } from '../lib/search'
import { ExtraLinks } from './ExtraLinks'
import { Sprite } from './Sprite'

function Mon({ m, onIv }: { m: IvMon; onIv: (name: string) => void }) {
  return (
    <div className={`ivmon${m.selected ? ' sel' : ''}`}>
      <h3>
        <Sprite dex={m.id} />
        {m.name}
        <small>
          #{m.id} · base {m.base.join('/')}
        </small>
        <ExtraLinks slug={m.id} name={m.name} onIv={onIv} />
      </h3>
      <div className="scroll">
<table>
        <thead>
          <tr>
            <th>League</th>
            <th>Rank</th>
            <th>Stat product</th>
            <th>Level</th>
            <th>CP</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {m.leagues.map((l) => (
            <tr key={l.league}>
              <td>{l.league}</td>
              <td className="r1">
                <b>#{l.rank}</b> <span style={{ color: 'var(--muted)' }}>/ {l.of}</span>
              </td>
              <td className={pctClass(l.percent)}>{l.percent}%</td>
              <td>L{l.level}</td>
              <td>{l.cp} CP</td>
              <td className="dim">{l.cp_cap && !l.capped ? `maxes out under ${l.cp_cap} CP` : ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
</div>
    </div>
  )
}

export function IvPanel({ result, onIv }: { result: SearchResult; onIv: (name: string) => void }) {
  const info = result.ivs
  if (!info) return null
  return (
    <div className="card">
      <h2>PvP IV rank</h2>
      <p className={`hint${info.error ? ' error' : ''}`}>
        {info.error ?? `IVs ${info.values.join('/')} at level cap ${info.cap}. Rank 1 is the best of 4096 spreads; ties share a rank.`}
      </p>
      <div>
        {(result.iv ?? []).map((m) => (
          <Mon key={m.name} m={m} onIv={onIv} />
        ))}
      </div>
    </div>
  )
}
