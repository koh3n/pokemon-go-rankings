// Links to PvPoke ranking pages by league. Best-effort GO Hub display name -> PvPoke id,
// e.g. "Shadow Alolan Ninetales" -> "ninetales_alolan_shadow".
export const PVPOKE_CP: Record<string, number> = { 'Great League': 1500, 'Ultra League': 2500, 'Master League': 10000 }

const SPECIAL: Record<string, string> = {
  'black kyurem': 'kyurem_black',
  'white kyurem': 'kyurem_white',
  'dusk mane necrozma': 'necrozma_dusk_mane',
  'dawn wings necrozma': 'necrozma_dawn_wings',
  'crowned sword zacian': 'zacian_crowned_sword',
  'crowned shield zamazenta': 'zamazenta_crowned_shield',
  'zygarde complete form': 'zygarde_complete',
}

const clean = (t: string) =>
  t
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/%/g, '')
    .replace(/['’.]/g, '')
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')

export function pvpokeId(name: string): string {
  let n = name.trim()
  const shadow = /\bShadow\b/.test(n)
  n = n.replace(/\bShadow\b/g, '').replace(/\s+/g, ' ').trim()
  const reg = /\b(Alolan|Galarian|Hisuian|Paldean)\b/.exec(n)
  if (reg) n = n.replace(reg[0], '').replace(/\s+/g, ' ').trim()
  const strip = (f: string) => f.replace(/\s+(Forme?|Mode|size|Breed|Style|Cloak)$/i, '')
  let base = n
  let form = ''
  let m: RegExpExecArray | null
  if (SPECIAL[n.toLowerCase()]) base = SPECIAL[n.toLowerCase()]
  else if ((m = /^(.+?)\s*\((.+)\)$/.exec(n))) {
    base = m[1]
    form = m[2].replace(/^Hero of Many Battles$/i, 'Hero').replace(/^(East|West) Sea$/i, '')
  } else if ((m = /^(.+?) (?:Forme|Mode) (.+)$/.exec(n))) {
    form = m[1]
    base = m[2]
  } else if ((m = /^(\S+) (.+?) Forme$/.exec(n))) {
    base = m[1]
    form = m[2]
  }
  return [clean(base), reg ? reg[1].toLowerCase() : '', clean(strip(form)), shadow ? 'shadow' : ''].filter(Boolean).join('_')
}
