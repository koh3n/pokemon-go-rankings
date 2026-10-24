"""Tests for the tier-ranking parser and the refresh safeguard.   python -m unittest discover tests"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import pogo_tiers as pt  # noqa: E402


def parse(html):
    return pt.parse_rankings(BeautifulSoup(html, "html.parser"))


class ParseRankings(unittest.TestCase):
    def test_split_tier_hash_number(self):
        # 2026 markup: the tier, "#" and the number are separate pieces of text
        html = ('<h3>Corsola\'s Tier Ranking</h3><div class="PokemonPageRenderers_tierRankingsContainer_x">'
                '<div><span>Raid Attacker</span><small>Not ranked<br/></small></div>'
                '<div><span>Water-type</span><div>F</div><div>#</div><div><!-- -->218</div></div>'
                '<div><span>Great League</span><div>A+</div><div>#</div><div>8</div></div></div>')
        self.assertEqual(parse(html), ([{"mode": "Water-type", "tier": "F", "rank": 218},
                                        {"mode": "Great League", "tier": "A+", "rank": 8}], ["Raid Attacker"]))

    def test_tiles_after_a_meta_analysis_blurb(self):
        # the tiles are in their own container, past headings inside the blurb's dialog
        html = ('<h3 id="tier-ranking">X\'s Tier Ranking &amp; Meta Analysis</h3><section><dialog><h2>PvE Analysis</h2>'
                '</dialog></section><div class="PokemonPageRenderers_tierRankingsContainer_y">'
                '<div><span>Great League</span><div>S</div><div>#</div><div>3</div></div></div>')
        self.assertEqual(parse(html)[0], [{"mode": "Great League", "tier": "S", "rank": 3}])

    def test_older_formats_still_work(self):
        html = ('<h3>X Tier Ranking</h3><div>Great League</div><div>A Tier</div><div>#259</div>'
                '<div>Fire-type</div><div>B+ Tier #12</div><div>Raid Attacker</div><div>Not ranked</div>')
        self.assertEqual(parse(html), ([{"mode": "Great League", "tier": "A", "rank": 259},
                                        {"mode": "Fire-type", "tier": "B+", "rank": 12}], ["Raid Attacker"]))

    def test_tier_without_a_rank(self):
        html = '<h3>X Tier Ranking</h3><div>Fire-type</div><div>C</div><div>Ice-type</div><div>D</div>'
        self.assertEqual(parse(html)[0], [{"mode": "Fire-type", "tier": "C", "rank": None},
                                          {"mode": "Ice-type", "tier": "D", "rank": None}])

    def test_no_section(self):
        self.assertEqual(parse("<h3>Something else</h3>"), (None, None))


class RefreshSafeguard(unittest.TestCase):
    def snapshot(self, rankings_per_page, pages=100):
        return {"pages_scraped": pages, "pages_failed": {}, "per_pokemon": [
            {"slug": str(i), "rankings": [{"mode": "m", "tier": "A", "rank": 1}] * rankings_per_page}
            for i in range(pages)]}

    def refresh(self, old, new):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "all_rankings.json"
            path.write_text(json.dumps(old))
            with mock.patch.object(pt, "build_all", return_value=new):
                ok, msg = pt.refresh_snapshot(path, d)
            return ok, msg, json.loads(path.read_text())

    def test_keeps_old_data_when_no_rankings_were_found(self):
        old = self.snapshot(3)
        ok, msg, saved = self.refresh(old, self.snapshot(0))   # right page count, nothing parsed
        self.assertFalse(ok)
        self.assertIn("rankings", msg)
        self.assertEqual(saved, old)

    def test_saves_a_good_scrape(self):
        new = self.snapshot(3)
        ok, _, saved = self.refresh(self.snapshot(3), new)
        self.assertTrue(ok)
        self.assertEqual(saved, new)


if __name__ == "__main__":
    unittest.main()
