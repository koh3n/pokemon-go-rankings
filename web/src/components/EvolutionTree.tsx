import type { EvoNode } from '../lib/tiers'
import { ExtraLinks } from './ExtraLinks'
import { Sprite } from './Sprite'

function Node({ n, labelOf, onIv }: { n: EvoNode; labelOf: (g: string) => string; onIv: (name: string) => void }) {
  return (
    <li>
      <span className="name">
        <span className="who">
          <Sprite dex={n.slug} />
          <a href={n.url} target="_blank" rel="noopener">
            {n.name}
          </a>
        </span>
        <ExtraLinks slug={n.slug} name={n.name} onIv={onIv} />
      </span>{' '}
      {n.requires && <span className="chip">{n.requires}</span>}
      {n.forms.length > 0 && (
        <div>
          {n.forms.map((f) => (
            <span className="chip" key={f.slug}>
              <a href={f.url} target="_blank" rel="noopener" title={labelOf(f.group)}>
                {f.name}
              </a>
            </span>
          ))}
        </div>
      )}
      {n.evolves_to.length > 0 && (
        <ul>
          {n.evolves_to.map((c) => (
            <Node key={c.slug} n={c} labelOf={labelOf} onIv={onIv} />
          ))}
        </ul>
      )}
    </li>
  )
}

export function EvolutionTree({
  roots,
  labelOf,
  onIv,
}: {
  roots: EvoNode[]
  labelOf: (g: string) => string
  onIv: (name: string) => void
}) {
  return (
    <ul className="tree">
      {roots.map((n) => (
        <Node key={n.slug} n={n} labelOf={labelOf} onIv={onIv} />
      ))}
    </ul>
  )
}
