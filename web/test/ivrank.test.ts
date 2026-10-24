import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { IvRanker, type IvData, type LeagueKey, type LeagueRank, type SpreadRow } from '../src/lib/ivrank'

const root = new URL('../../', import.meta.url)
const ivData = JSON.parse(readFileSync(new URL('data/cache/iv_data.json', root), 'utf8')) as IvData
const fx = JSON.parse(readFileSync(new URL('web/test/fixtures.json', root), 'utf8'))
const ranker = new IvRanker(ivData)

const digest = (rows: SpreadRow[]) =>
  createHash('sha256')
    .update(
      rows
        .map(
          (r) =>
            `${r[0]},${r[1]},${r[2]},${r[3]},${r[4].toFixed(1)},${r[5]},${r[6].toFixed(2)},${r[7].toFixed(2)},${r[8].toFixed(2)},${r[9]}`,
        )
        .join('\n'),
    )
    .digest('hex')

describe('allSpreads matches Python', () => {
  for (const s of fx.spreads) {
    it(`${s.name} ${s.league} cap ${s.cap}`, () => {
      const mon = ranker.findExact(s.name)!
      const rows = ranker.allSpreads(mon, s.league as LeagueKey, s.cap)
      expect(rows.length).toBe(s.count)
      expect(rows.slice(0, 40)).toEqual(s.head)
      expect(digest(rows)).toBe(s.sha256)
    })
  }
})

describe('rankIvs matches Python', () => {
  for (const r of fx.ranks) {
    it(`${r.name} ${r.ivs.join('/')} cap ${r.cap}`, () => {
      const got = ranker.rankIvs(ranker.findExact(r.name)!, ...(r.ivs as [number, number, number]), r.cap)
      const want = Object.values(r.result) as LeagueRank[]
      expect(got).toEqual(want)
    })
  }
})

describe('name lookup matches Python', () => {
  for (const [name, want] of Object.entries(fx.names) as [string, { id: number; name: string } | null][]) {
    it(name, () => {
      const m = ranker.findExact(name)
      expect(m ? { id: m.id, name: m.name } : null).toEqual(want)
    })
  }
  for (const [q, want] of Object.entries(fx.find_mons) as [string, string[]][]) {
    it(`findMons ${q}`, () => expect(ranker.findMons(q).map((m) => m.name)).toEqual(want))
  }
  for (const [name, want] of Object.entries(fx.lines) as [string, string[]][]) {
    it(`lineOf ${name}`, () => expect(ranker.lineOf(ranker.findExact(name)!).map((m) => m.name)).toEqual(want))
  }
})

describe('every Pokémon, every league, cap 50 matches Python', () => {
  it('has identical digests', () => {
    const bad: string[] = []
    for (const [key, want] of Object.entries(fx.all_digests as Record<string, string>)) {
      const [name, league] = key.split('|')
      const mon = ivData.mons.find((m) => m.name === name)!
      if (digest(ranker.allSpreads(mon, league as LeagueKey, 50)) !== want) bad.push(key)
    }
    expect(Object.keys(fx.all_digests).length).toBe(ivData.mons.length * 3)
    expect(bad).toEqual([])
  }, 120_000)
})
