// Type badges come from the PokeAPI sprite repo (Scarlet/Violet set, ids follow the games' type order).
// Each image is a pill with the type's icon on its left; the CSS crops it to just the icon.
const TYPE_ICON_URL = 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/types/generation-ix/scarlet-violet/'
const TYPE_IDS: Record<string, number> = {
  normal: 1,
  fighting: 2,
  flying: 3,
  poison: 4,
  ground: 5,
  rock: 6,
  bug: 7,
  ghost: 8,
  steel: 9,
  fire: 10,
  water: 11,
  grass: 12,
  electric: 13,
  psychic: 14,
  ice: 15,
  dragon: 16,
  dark: 17,
  fairy: 18,
}

export function TypeIcon({ type }: { type: string }) {
  const id = TYPE_IDS[type.toLowerCase()]
  if (!id) return null
  return (
    <img
      className="tico"
      src={`${TYPE_ICON_URL}${id}.png`}
      width={20}
      height={20}
      alt=""
      title={type.charAt(0).toUpperCase() + type.slice(1)}
      loading="lazy"
      decoding="async"
      onError={(e) => (e.currentTarget.style.display = 'none')}
    />
  )
}
