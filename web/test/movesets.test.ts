import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { defaultType, hasTierView, moveTypes, neutralView, tierView, type MovesetData } from '../src/lib/movesets'

const root = new URL('../../', import.meta.url)
const data = JSON.parse(readFileSync(new URL('web/test/data/movesets.json', root), 'utf8')) as MovesetData
const fx = JSON.parse(readFileSync(new URL('web/test/moveset_fixtures.json', root), 'utf8'))

const stepKey = (s: number) => (s === 1 ? '1.0' : String(s))

describe('tier view matches the Python calculator', () => {
  it('has identical results for every Pokémon, every type, with and without legacy moves', () => {
    const bad: string[] = []
    for (const [slug, want] of Object.entries(fx.digests as Record<string, string>)) {
      const lines: string[] = []
      for (const t of moveTypes(data, slug))
        for (const legacy of [true, false])
          for (const r of tierView(data, slug, t, legacy))
            lines.push(
              `${slug}|${t}|${legacy ? 1 : 0}|${stepKey(r.step)}|` +
                r.picks.map((p) => `${p.fast}/${p.charged}/${p.edps.toFixed(2)}`).join(','),
            )
      if (createHash('sha256').update(lines.join('\n')).digest('hex') !== want) bad.push(slug)
    }
    expect(Object.keys(fx.digests).length).toBe(Object.keys(data.pokemon).length)
    expect(bad).toEqual([])
  }, 120_000)

  for (const [key, want] of Object.entries(fx.samples as Record<string, Record<string, [string, string, number][]>>)) {
    it(`sample ${key}`, () => {
      const [slug, type] = key.split('|')
      for (const r of tierView(data, slug, type)) {
        const got = r.picks.map((p) => [p.fast, p.charged, Number(p.edps.toFixed(2))])
        expect(got).toEqual(want[stepKey(r.step)])
      }
    })
  }
})

describe('behaviour', () => {
  it('Shadow Alolan Golem: Electric fast move wins once Electric is super effective', () => {
    const [neutral, weak, double] = tierView(data, '76-Alola_Shadow', 'electric')
    expect(neutral.picks[0].fast).toBe('Rollout')
    expect(weak.picks[0]).toMatchObject({ fast: 'Volt Switch', charged: 'Wild Charge' })
    expect(double.picks[0]).toMatchObject({ fast: 'Volt Switch', charged: 'Wild Charge' })
  })
  it('hiding legacy moves never returns a legacy move', () => {
    for (const r of tierView(data, '76-Alola_Shadow', 'electric', false))
      for (const p of r.picks) expect(p.fastLegacy || p.chargedLegacy).toBe(false)
  })
  it('eDPS grows with the multiplier', () => {
    const [a, b, c] = tierView(data, '94', 'poison')
    expect(b.picks[0].edps).toBeGreaterThan(a.picks[0].edps)
    expect(c.picks[0].edps).toBeGreaterThan(b.picks[0].edps)
  })
  it('knows which Pokémon fit well enough to show', () => {
    expect(hasTierView(data, '94')).toBe(true)
    expect(hasTierView(data, 'not-a-pokemon')).toBe(false)
  })
  it('picks a default type from the Pokémon\'s own moves', () => {
    expect(moveTypes(data, '94')).toContain(defaultType(data, '94'))
  })
  it('only considers the types it is given for the default', () => {
    expect(defaultType(data, '94', ['ghost', 'poison'])).toMatch(/^(ghost|poison)$/)
  })
  it('the neutral result does not depend on which type is featured', () => {
    for (const slug of ['94', '6', '76-Alola_Shadow', '464'])
      for (const legacy of [true, false]) {
        const n = neutralView(data, slug, legacy)
        for (const t of moveTypes(data, slug)) expect(tierView(data, slug, t, legacy)[0]).toEqual(n)
      }
  })
})
