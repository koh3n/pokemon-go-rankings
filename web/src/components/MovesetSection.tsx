import { useEffect, useMemo, useRef, useState } from 'react'
import { MAX_FIT_ERROR, defaultType, hasTierView, moveTypes, tierView, type MovesetData, type Pick } from '../lib/movesets'

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
      {p.fast}
      {star(p.fastLegacy)} / {p.charged}
      {star(p.chargedLegacy)}
    </>
  )
}

const TITLES = (type: string) => [
  { title: 'Neutral boss', note: `${cap(type)} hits normally`, mult: '1×' },
  { title: `Weak to ${cap(type)}`, note: 'super effective', mult: '1.6×' },
  { title: `Double weak to ${cap(type)}`, note: 'e.g. Water/Flying vs Electric', mult: '2.56×' },
]

function Tiers({ data, slug, preset }: { data: MovesetData; slug: string; preset?: string }) {
  const types = useMemo(() => moveTypes(data, slug), [data, slug])
  const [picked, setPicked] = useState<string | null>(null) // the user's own choice, if any
  const type = picked ?? (preset && types.includes(preset) ? preset : defaultType(data, slug))
  const [hideLegacy, setHideLegacy] = useState(false)
  const tiers = useMemo(() => tierView(data, slug, type, !hideLegacy), [data, slug, type, hideLegacy])
  const titles = TITLES(type)

  return (
    <>
      <div className="tabs" role="tablist" aria-label="Type the boss is weak to">
        {types.map((t) => (
          <button key={t} type="button" className="tab" role="tab" aria-selected={t === type} onClick={() => setPicked(t)}>
            {cap(t)}
          </button>
        ))}
      </div>
      <label className="legacy">
        <input type="checkbox" checked={hideLegacy} onChange={(e) => setHideLegacy(e.target.checked)} /> Hide legacy moves (no Elite TM)
      </label>
      <div className="tiers">
        {tiers.map((t, i) => {
          const [best, second] = t.picks
          const close = second && best && second.edps >= best.edps * 0.97
          return (
            <div className="tier-card" key={t.step}>
              <div className="tier-head">
                <b>{titles[i].title}</b>
                <span className="tier-mult">{titles[i].mult}</span>
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
                </>
              ) : (
                <div className="hint">No moveset without legacy moves.</div>
              )}
            </div>
          )
        })}
      </div>
      <p className="hint" style={{ margin: '10px 0 0' }}>
        How this reads: only {cap(type)} moves get the boost; this Pokémon's other move types are treated as neutral.
        Against a boss where another of its types is also super effective (Rock against Flying, say) a different moveset can
        win. eDPS is on GO Hub's neutral-boss scale and estimated by a calculator that matches GO Hub's own numbers to about 1%
        (median) per moveset.
      </p>
    </>
  )
}

/** One collapsible per Pokémon. Nothing is calculated until it has been opened. */
export function MovesetSection({
  slug,
  name,
  data,
  openNonce,
  preset,
}: {
  slug: string
  name: string
  data: MovesetData
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
      <summary>{name}</summary>
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
            <Tiers key={preset ?? 'default'} data={data} slug={slug} preset={preset} />
          ))}
      </div>
    </details>
  )
}
