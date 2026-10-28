import { PVPOKE_CP, pvpokeId } from '../lib/pvpoke'

// Per-Pokémon links after the name (which links to the GO Hub page itself): the raid movesets and IV
// spreads sections and, for league rows, the PvPoke ranking page. slug may be a plain dex number or a form slug.
export function ExtraLinks({
  slug,
  name,
  mode,
  onIv,
  onMoves,
}: {
  slug: string | number
  name: string
  mode?: string
  onIv: (name: string) => void
  onMoves?: () => void
}) {
  if (!parseInt(String(slug), 10)) return null
  const cp = mode ? PVPOKE_CP[mode] : undefined
  return (
    <span className="xlinks">
      {onMoves && (
        <a
          href="#movesets-card"
          title="Best raid moveset against bosses weak to a type"
          onClick={(e) => {
            e.preventDefault()
            onMoves()
          }}
        >
          Movesets
        </a>
      )}
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
