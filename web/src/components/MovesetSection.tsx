import { useEffect, useMemo, useRef, useState } from 'react'
import { Sprite } from './Sprite'
import { TypeIcon } from './TypeIcon'
import { MAX_FIT_ERROR, defaultType, hasTierView, moveTypes, neutralView, superEffectiveAgainst, tierView, type MovesetData, type Pick, type TierResult } from '../lib/movesets'

export interface TypeRank {
  type: string
  tier: string
  rank: number | null
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

function Moves({ p }: { p: Pick }) {
  const star = (legacy: boolean) =>
    legacy ? (
      <abbr title="Legacy move: needs an Elite TM" style={{ textDecoration: 'none' }}>
        *
      </abbr>
    ) : null
  return (
    <>
      <span className="mv">
        <TypeIcon type={p.fastType} />
        <span>
          {p.fast}
          {star(p.fastLegacy)}
        </span>
      </span>
      <span className="mv-sep">/</span>
      <span className="mv">
        <TypeIcon type={p.chargedType} />
        <span>
          {p.charged}
          {star(p.chargedLegacy)}
        </span>
      </span>
    </>
  )
}

function Badge({ r }: { r: TypeRank | undefined }) {
  return r ? (
    <span className={`badge tier-${r.tier[0].toLowerCase()}`}>
      {r.tier}
      {r.rank != null && ` #${r.rank}`}
    </span>
  ) : null
}

function TierCard({ title, mult, tier, rank, type }: { title: string; mult: string; tier: TierResult | undefined; rank?: TypeRank; type?: string }) {
  const [best, second] = tier?.picks ?? []
  const against = type ? superEffectiveAgainst(type) : undefined
  const close = second && best && second.edps >= best.edps * 0.97
  return (
    <div className="tier-card">
      <div className="tier-head">
        <b>{title}</b>
        <span className="tier-mult">
          <Badge r={rank} /> {mult}
        </span>
      </div>
      {best ? (
        <>
          <div className="tier-moves">
            <Moves p={best} />
          </div>
          <div className="tier-edps">{best.edps.toFixed(1)} eDPS</div>
          {close && (
            <div className="hint tier-close">
              Close call: <Moves p={second} /> ({second.edps.toFixed(1)})
            </div>
          )}
          {against && (
            <div className="se">
              <span>Super effective against</span>
              {against.length ? (
                against.map((t) => (
                  <span key={t} className="chip se-chip" title={cap(t)}>
                    <TypeIcon type={t} />
                    {cap(t)}
                  </span>
                ))
              ) : (
                <span className="chip se-chip">nothing</span>
              )}
            </div>
          )}
        </>
      ) : (
        <div className="hint">No moveset without legacy moves.</div>
      )}
    </div>
  )
}

function Tiers({ data, slug, ranked, preset }: { data: MovesetData; slug: string; ranked: TypeRank[]; preset?: string }) {
  // only the types GO Hub ranks this Pokémon for (and that it has a move of)
  const types = useMemo(() => moveTypes(data, slug).filter((t) => ranked.some((r) => r.type === t)), [data, slug, ranked])
  const [picked, setPicked] = useState<string | null>(null) // the user's own choice, if any
  const type = picked ?? (preset && types.includes(preset) ? preset : defaultType(data, slug, types))
  const rankOf = (t: string) => ranked.find((r) => r.type === t)
  const [hideLegacy, setHideLegacy] = useState(false)
  const neutral = useMemo(() => neutralView(data, slug, !hideLegacy), [data, slug, hideLegacy])
  const weak = useMemo(() => (type ? tierView(data, slug, type, !hideLegacy) : []), [data, slug, type, hideLegacy])

  return (
    <>
      <label className="legacy">
        <input type="checkbox" checked={hideLegacy} onChange={(e) => setHideLegacy(e.target.checked)} /> Hide legacy moves (no Elite TM)
      </label>

      <div className="tiers one">
        <TierCard title="Neutral damage" mult="1×" tier={neutral} />
      </div>

      {types.length === 0 ? (
        <p className="hint" style={{ margin: 0 }}>
          GO Hub doesn't rank this Pokémon in any type list, so there's no weakness view for it.
        </p>
      ) : (
        <>
          <div className="tabs" role="tablist" aria-label="Type the boss is weak to">
            {types.map((t) => (
              <button key={t} type="button" className="tab tab-type" role="tab" aria-selected={t === type} onClick={() => setPicked(t)}>
                <TypeIcon type={t} />
                {cap(t)}
              </button>
            ))}
          </div>
          <div className="tiers two">
            <TierCard title={`Super effective ${cap(type)}`} mult="1.6×" tier={weak[1]} rank={rankOf(type)} type={type} />
            <TierCard title={`Double super effective ${cap(type)}`} mult="2.56×" tier={weak[2]} rank={rankOf(type)} type={type} />
          </div>
        </>
      )}
    </>
  )
}

/** One collapsible per Pokémon. Nothing is calculated until it has been opened. */
export function MovesetSection({
  slug,
  name,
  data,
  ranked,
  openNonce,
  preset,
}: {
  slug: string
  name: string
  data: MovesetData
  ranked: TypeRank[] // the types this Pokémon has a ranking for
  openNonce: number
  preset?: string
}) {
  const ref = useRef<HTMLDetailsElement>(null)
  const [opened, setOpened] = useState(false)

  useEffect(() => {
    if (!openNonce || !ref.current) return
    ref.current.open = true
    setOpened(true)
    ref.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [openNonce])

  const known = !!data.pokemon[slug]
  const fits = hasTierView(data, slug)
  return (
    <details className="ivsec" ref={ref} onToggle={(e) => e.currentTarget.open && setOpened(true)}>
      <summary>
        <Sprite dex={slug} />
        {name}
      </summary>
      <div className="ivbody">
        {opened &&
          (!known ? (
            <p className="hint">No raid moveset data for this form.</p>
          ) : !fits ? (
            <p className="hint">
              The calculator can't reproduce GO Hub's numbers for this Pokémon (error above {MAX_FIT_ERROR}%; usually one that faints
              before it can use a charged move), so there's no moveset view for it.
            </p>
          ) : (
            <Tiers key={preset ?? 'default'} data={data} slug={slug} ranked={ranked} preset={preset} />
          ))}
      </div>
    </details>
  )
}
