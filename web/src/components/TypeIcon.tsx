// Type icons: partywhale/pokemon-type-icons (MIT, see public/types/LICENSE.txt), bundled in public/types.
const KNOWN = new Set([
  'normal', 'fighting', 'flying', 'poison', 'ground', 'rock', 'bug', 'ghost', 'steel',
  'fire', 'water', 'grass', 'electric', 'psychic', 'ice', 'dragon', 'dark', 'fairy',
])

export function TypeIcon({ type }: { type: string }) {
  const t = type.toLowerCase()
  if (!KNOWN.has(t)) return null
  return (
    <img
      className="tico"
      src={`${import.meta.env.BASE_URL}types/${t}.svg`}
      width={20}
      height={20}
      alt=""
      title={t.charAt(0).toUpperCase() + t.slice(1)}
      decoding="async"
      onError={(e) => (e.currentTarget.style.display = 'none')}
    />
  )
}
