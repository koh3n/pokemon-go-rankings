import { useMemo } from 'react'
import { pctClass } from '../lib/format'
import type { SearchResult } from '../lib/search'
import { BASE } from '../lib/tiers'
import { ExtraLinks } from './ExtraLinks'
import { Sprite } from './Sprite'

export function TierTable({
  result,
  group,
  mode,
  onMode,
  onIv,
  onMoves,
  hasMoves,
}: {
  result: SearchResult
  group: string
  mode: string
  onMode: (m: string) => void
  onIv: (name: string) => void
  onMoves?: (slug: string, name: string, type?: string) => void
  hasMoves?: (slug: string) => boolean
}) {
  const all = useMemo(() => result.rankings[group] ?? [], [result, group])
  const modes = useMemo(() => [...new Set(all.map((r) => r.mode))], [all])
  const active = modes.includes(mode) ? mode : ''
  const rows = active ? all.filter((r) => r.mode === active) : all
  const hasIv = !!result.ivs && rows.some((r) => r.iv)
  const unranked = result.per_pokemon.filter((p) => p.group === group && p.unranked_modes.length)

  return (
    <>
      <div className="toolbar">
        <label>
          Mode:{' '}
          <select value={active} onChange={(e) => onMode(e.target.value)}>
            <option value="">All modes</option>
            {modes.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
        <span style={{ color: 'var(--muted)', fontSize: 13 }}>
          {rows.length ? `${rows.length} ranking${rows.length === 1 ? '' : 's'}, best first` : ''}
        </span>
      </div>
      {!rows.length ? (
        <div className="empty">No rankings for this group — these Pokémon aren't ranked in any mode on the site.</div>
      ) : (
        <div className="scroll">
<table>
          <thead>
            <tr>
              <th>#</th>
              <th>Pokémon</th>
              <th>Mode</th>
              <th>Tier</th>
              <th>Rank</th>
              {hasIv && <th>Your IV rank</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.slug}|${r.mode}`}>
                <td className="num">{i + 1}</td>
                <td>
                  <span className="who">
                    <Sprite dex={r.slug} />
                    <a href={`${BASE}/pokemon/${encodeURIComponent(r.slug)}`} target="_blank" rel="noopener" style={{ color: 'inherit' }}>
                      {r.pokemon}
                    </a>
                  </span>
                  <ExtraLinks
                    slug={r.slug}
                    name={r.pokemon}
                    mode={r.mode}
                    onIv={onIv}
                    onMoves={onMoves && hasMoves?.(r.slug) ? () => onMoves(r.slug, r.pokemon, /^(\w+)-type$/i.exec(r.mode)?.[1].toLowerCase()) : undefined}
                  />
                </td>
                <td>{r.mode}</td>
                <td>
                  <span className={`badge tier-${r.tier[0].toLowerCase()}`}>{r.tier}</span>
                </td>
                <td className="rank">{r.rank == null ? '' : `#${r.rank}`}</td>
                {hasIv &&
                  (r.iv ? (
                    <td className="rank">
                      <b className={pctClass(r.iv.percent)}>#{r.iv.rank}</b>{' '}
                      <small>
                        {r.iv.percent}% · L{r.iv.level} · {r.iv.cp} CP
                      </small>
                    </td>
                  ) : (
                    <td className="dim"></td>
                  ))}
              </tr>
            ))}
          </tbody>
        </table>
</div>
      )}
      {unranked.length > 0 && (
        <details>
          <summary>Not ranked in</summary>
          {unranked.map((p) => (
            <div key={p.slug}>
              <b>{p.name}</b>: {p.unranked_modes.join(', ')}
            </div>
          ))}
        </details>
      )}
    </>
  )
}
