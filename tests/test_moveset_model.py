"""Tests for the moveset parser and calculator.   python -m unittest discover tests"""
import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import moveset_model as mm  # noqa: E402
import movesets  # noqa: E402


def move(mid, name, mtype, power, energy, duration, fast, legacy=0, stab=False):
    return {"id": mid, "name": name, "type": mtype, "power": power, "energy": energy, "duration": duration,
            "isQuickMove": fast, "isLegacy": legacy, "hasStab": stab}


class TypeChart(unittest.TestCase):
    def test_single_type_steps(self):
        self.assertAlmostEqual(mm.effectiveness("water", ["fire"]), 1.6)
        self.assertAlmostEqual(mm.effectiveness("fire", ["water"]), 0.625)
        self.assertAlmostEqual(mm.effectiveness("normal", ["ghost"]), 0.625 * 0.625)   # GO: double resist
        self.assertAlmostEqual(mm.effectiveness("electric", ["ground"]), 0.625 * 0.625)

    def test_double_weakness_is_2_56(self):
        self.assertAlmostEqual(mm.effectiveness("electric", ["water", "flying"]), 2.56)
        self.assertAlmostEqual(mm.effectiveness("rock", ["fire", "flying"]), 2.56)

    def test_rock_beats_electric_against_fire_flying(self):
        m = mm.multipliers_for_boss("fire", "flying")
        self.assertGreater(m["rock"], m["electric"])        # the Golem / Moltres case

    def test_tier_multipliers(self):
        m = mm.tier_multipliers("electric", 1.6)
        self.assertEqual(m["electric"], 1.6)
        self.assertTrue(all(v == 1.0 for t, v in m.items() if t != "electric"))


class Formula(unittest.TestCase):
    fast = move(1, "Jab", "normal", 5, 6, 500, 1)
    charged = move(2, "Slam", "normal", 100, 50, 3000, 0)

    def test_hand_computed_cycle(self):
        k = 1.0
        n = 50 / 6
        damage = n * (0.5 * 5 * k + 0.5) + (0.5 * 100 * k + 0.5)
        expected = 1.0062 * damage / (n * 0.5 + 3.0)       # 50-energy moves use the 2-bar correction
        self.assertAlmostEqual(mm.cycle_dps(self.fast, self.charged, k), expected, places=9)

    def test_hundred_energy_move_wastes_overflow(self):
        big = move(3, "Blast", "normal", 150, 100, 3500, 0)
        k = 1.0
        n = math.ceil(100 / 6)                              # 17 fast moves, not 16.67
        damage = n * (0.5 * 5 * k + 0.5) + (0.5 * 150 * k + 0.5)
        self.assertAlmostEqual(mm.cycle_dps(self.fast, big, k), 0.9585 * damage / (n * 0.5 + 3.5), places=9)

    def test_stab_and_effectiveness_raise_damage(self):
        plain = mm.cycle_dps(self.fast, self.charged, 1.0)
        stab = dict(self.charged, hasStab=True)
        self.assertGreater(mm.cycle_dps(self.fast, stab, 1.0), plain)
        self.assertGreater(mm.cycle_dps(self.fast, self.charged, 1.0, {"normal": 1.6}), plain)

    def test_frustration_is_never_recommended(self):
        props = {"moves": [self.fast, self.charged, move(4, "Frustration", "normal", 10, 33, 2000, 0)]}
        ranked = mm.rank_movesets(props, 1.0, 0.9)
        self.assertTrue(all(c["name"] != "Frustration" for _, c, _, _ in ranked))


class Parser(unittest.TestCase):
    def page(self):
        moves = [move(10, "Lick", "ghost", 5, 6, 500, 1, legacy=1, stab=True),
                 move(11, "Sludge Bomb", "poison", 85, 50, 2500, 0, stab=True)]
        for m in moves:
            m.update({"damageWindow": 200, "hasStab": int(m["hasStab"])})
        results = [{"order": "1.", "qm": {"id": 10, "name": "Lick", "type": "ghost", "isLegacy": 1},
                    "cm": {"id": 11, "name": "Sludge Bomb", "type": "poison", "isLegacy": 0},
                    "dps": 15.4, "tdo": 225.0, "score": 13.2},
                   # the page de-duplicates repeated objects into references like this one
                   {"order": "2.", "qm": "$ee:0:props:initialResults:0:qm",
                    "cm": "$ee:0:props:initialResults:0:cm", "dps": 14.0, "tdo": 200.0, "score": 12.0}]
        payload = ('ee:[["$","$Lf0","en:94:",{"moves":' + json.dumps(moves) + ',"lang":"en","pokemon":'
                   + json.dumps({"id": 94, "name": "Gengar", "form": None, "type1": "ghost", "type2": "poison",
                                 "atk": 261, "def": 149, "sta": 155})
                   + ',"initialResults":' + json.dumps(results) + "}]]")
        return f"<html><script>self.__next_f.push([1,{json.dumps(payload)}])</script></html>"

    def test_extracts_pokemon_moves_and_results(self):
        p = movesets.parse_moveset_props(self.page())
        self.assertEqual(p["pokemon"]["name"], "Gengar")
        self.assertEqual({m["name"] for m in p["moves"]}, {"Lick", "Sludge Bomb"})
        self.assertEqual(len(p["results"]), 2)

    def test_resolves_references(self):
        p = movesets.parse_moveset_props(self.page())
        self.assertEqual(p["results"][1]["qm"]["name"], "Lick")
        self.assertEqual(p["results"][1]["cm"]["name"], "Sludge Bomb")

    def test_page_without_a_table(self):
        self.assertIsNone(movesets.parse_moveset_props("<html>nothing here</html>"))


class TierView(unittest.TestCase):
    def dataset(self):
        # a Rock/Electric attacker: an Electric fast move (legacy-free) vs a slightly stronger legacy Rock one
        moves = {"1": ["Volt Switch", "electric", 13, 20, 1500, 1], "2": ["Rollout", "rock", 15, 19, 1500, 1],
                 "3": ["Wild Charge", "electric", 90, 50, 2500, 0]}
        return {"moves": moves, "pokemon": {"x": {"t": ["rock", "electric"], "k": 0.45, "f": 0.88, "e": 1.0,
                                                  "m": [[1, 0], [2, 1], [3, 0]]}}}

    def test_move_types(self):
        self.assertEqual(mm.move_types(self.dataset(), "x"), ["electric", "rock"])

    def test_boosted_type_changes_the_best_fast_move(self):
        v = mm.tier_view(self.dataset(), "x", "electric")
        self.assertEqual(v[1.0][0][0], "Rollout")           # neutral: the stronger Rock move wins
        self.assertEqual(v[2.56][0][0], "Volt Switch")      # double weak to Electric: Electric fast move wins

    def test_hiding_legacy_moves(self):
        v = mm.tier_view(self.dataset(), "x", "electric", allow_legacy=False)
        self.assertTrue(all(row[0] != "Rollout" for tier in v.values() for row in tier))

    def test_eight_percent_threshold_exists(self):
        self.assertEqual(mm.MAX_FIT_ERROR, 8.0)


if __name__ == "__main__":
    unittest.main()
