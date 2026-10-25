import { PVPOKE_CP, pvpokeId } from '../lib/pvpoke'

// Per-Pokémon links after the name (which links to the GO Hub page itself): the IV spreads
// section and, for league rows, the PvPoke ranking page. slug may be a plain dex number or a form slug.
export function ExtraLinks({
  slug,
  name,
  mode,
  onIv,
}: {
  slug: string | number
  name: string
  mode?: string
  onIv: (name: string) => void
}) {
  if (!parseInt(String(slug), 10)) return null
  const cp = mode ? PVPOKE_CP[mode] : undefined
  return (
    <span className="xlinks">
      <a
        href="#ivspreads-card"
        title="All IV spreads for every league"
        onClick={(e) => {
          e.preventDefault()
          onIv(name)
        }}
      >
        IV spreads
      </a>
      {cp && (
        <a
          href={`https://pvpoke.com/rankings/all/${cp}/overall/${pvpokeId(name)}/`}
          target="_blank"
          rel="noopener"
          title={`${mode} ranking on PvPoke`}
        >
          PvPoke
        </a>
      )}
    </span>
  )
}
