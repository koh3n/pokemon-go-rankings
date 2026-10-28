import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { IvRanker, type IvData } from '../src/lib/ivrank'
import { runSearch } from '../src/lib/search'
import type { Snapshot } from '../src/lib/tiers'

const root = new URL('../../', import.meta.url)
const read = (p: string) => JSON.parse(readFileSync(new URL(p, root), 'utf8'))
const snap = read('web/test/data/all_rankings.json') as Snapshot
const ranker = new IvRanker(read('web/test/data/iv_data.json') as IvData)
const fx = read('web/test/fixtures.json')

describe('search matches Python', () => {
  for (const s of fx.searches) {
    it(`${s.q}${s.ivs ? ' with IVs' : ''}`, () => {
      const run = () => runSearch(snap, ranker, s.q, 'all', s.ivs, 50)
      if (s.error) {
        expect(run).toThrow()
        try {
          run()
        } catch (e) {
          expect((e as Error).message).toBe(s.error)
        }
      } else {
        // the list of tier names is metadata that grows when GO Hub adds a tier (SS), so it isn't compared
        const strip = (r: Record<string, unknown>) => ({ ...r, tier_order_best_to_worst: undefined })
        expect(strip(JSON.parse(JSON.stringify(run())))).toEqual(strip(s.result))
      }
    })
  }
})
