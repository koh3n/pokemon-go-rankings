// Sprites come from the PokeAPI sprite repo by Pokédex number. They are lazy loaded and have
// fixed dimensions, so they never delay the search or shift the layout.
const SPRITE_URL = 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/'

export function Sprite({ dex, big = false }: { dex: string | number; big?: boolean }) {
  const n = parseInt(String(dex), 10)
  if (!n) return null
  const size = big ? 48 : 40
  return (
    <img
      className={`spr${big ? ' big' : ''}`}
      src={`${SPRITE_URL}${n}.png`}
      width={size}
      height={size}
      alt=""
      loading="lazy"
      decoding="async"
      onError={(e) => (e.currentTarget.style.visibility = 'hidden')}
    />
  )
}
