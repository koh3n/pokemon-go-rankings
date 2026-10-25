import { useId, useMemo, useState } from 'react'
import { normName } from '../lib/ivrank'

const MAX = 8

/**
 * The name box with a short suggestion list. This replaces a native <datalist> of every name:
 * more than a thousand options is a lot for a phone's browser, so only the top few matches
 * are ever in the page.
 */
export function NameInput({
  value,
  onChange,
  names,
  onSubmit,
}: {
  value: string
  onChange: (v: string) => void
  names: string[]
  onSubmit: () => void
}) {
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const listId = useId()

  const index = useMemo(() => names.map((n) => [n, normName(n)] as const), [names])
  const matches = useMemo(() => {
    const q = normName(value)
    if (!q || /^\d+$/.test(value.trim())) return []
    const starts = index.filter(([, k]) => k.startsWith(q))
    const has = index.filter(([, k]) => !k.startsWith(q) && k.includes(q))
    return [...starts, ...has].slice(0, MAX).map(([n]) => n)
  }, [index, value])

  const shown = open && matches.length > 0 && !(matches.length === 1 && matches[0] === value)
  const pick = (n: string) => {
    onChange(n)
    setOpen(false)
    setActive(-1)
  }

  return (
    <div className="suggest">
      <input
        type="text"
        role="combobox"
        aria-expanded={shown}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={shown && active >= 0 ? `${listId}-${active}` : undefined}
        placeholder="Pokémon name or Pokédex number (e.g. charmander, 4)"
        autoComplete="off"
        autoCapitalize="none"
        spellCheck={false}
        value={value}
        onChange={(e) => {
          onChange(e.target.value)
          setOpen(true)
          setActive(-1)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown' && matches.length) {
            e.preventDefault()
            setOpen(true)
            setActive((a) => (a + 1) % matches.length)
          } else if (e.key === 'ArrowUp' && matches.length) {
            e.preventDefault()
            setActive((a) => (a <= 0 ? matches.length - 1 : a - 1))
          } else if (e.key === 'Escape') {
            setOpen(false)
          } else if (e.key === 'Enter' && shown && active >= 0) {
            e.preventDefault()
            pick(matches[active])
            onSubmit()
          }
        }}
      />
      {shown && (
        <ul className="suggestions" id={listId} role="listbox">
          {matches.map((n, i) => (
            <li
              key={n}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'on' : undefined}
              // pointerdown, not click: the input's blur would close the list before a click lands
              onPointerDown={(e) => {
                e.preventDefault()
                pick(n)
              }}
            >
              {n}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
