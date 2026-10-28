"""Tests for GO Hub's per-type lists and the off-type rankings built from them.   python -m unittest discover tests"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import movesets  # noqa: E402
import pogo_tiers as pt  # noqa: E402


def list_page(rows):
    """A best-per-type page: the list is embedded in the page's payload."""
    attackers = [{"order": rank, "attacker": {"id": dex, "name": name, "form": form, "type1": "psychic"},
                  "qm": "$4c:props:initialData:attackers:0:qm", "score": 20.0, "tier": tier}
                 for rank, dex, form, name, tier in rows]
    payload = 'ee:["$","$Lf0",null,{"initialData":{"attackers":' + json.dumps(attackers) + "}}]"
    return f"<html><script>self.__next_f.push([1,{json.dumps(payload)}])</script></html>"


class FakeFetch:
    def __init__(self, pages):
        self.pages = pages

    def get(self, path):
        return self.pages.get(path.rsplit("/", 1)[1], "<html>no list</html>")


def snapshot():
    def p(slug, name, *modes):
        return {"slug": slug, "name": name, "group": "normal", "dex": int(slug.split("-")[0]), "url": "",
                "rankings": [{"mode": m, "tier": "A", "rank": 9} for m in modes], "unranked_modes": []}
    return {"per_pokemon": [p("150-Mega_Y", "Mega Mewtwo Y", "Psychic-type"), p("464", "Rhyperior", "Rock-type"),
                            p("94", "Gengar", "Ghost-type")], "rankings": {}}


class ParseTypeList(unittest.TestCase):
    def test_rows_and_slugs(self):
        rows = movesets.parse_type_list(list_page([(1, 94, None, "Gengar", "S"), (2, 150, "Mega Y", "Mega Mewtwo Y", "SS"),
                                                   (3, 76, "Alola Shadow", "Shadow Alolan Golem", "A")]))
        self.assertEqual([(r["rank"], r["slug"], r["tier"]) for r in rows],
                         [(1, "94", "S"), (2, "150-Mega_Y", "SS"), (3, "76-Alola_Shadow", "A")])

    def test_page_without_a_list(self):
        self.assertIsNone(movesets.parse_type_list("<html>nothing</html>"))


class OffTypeRankings(unittest.TestCase):
    def merge(self, snap, pages):
        return pt.add_off_type_rankings(snap, FakeFetch(pages))

    def ghost_modes(self, snap, slug):
        return [r for p in snap["per_pokemon"] if p["slug"] == slug for r in p["rankings"] if r["mode"] == "Ghost-type"]

    def test_adds_a_top_ranked_off_type_attacker(self):
        snap = snapshot()
        added, failed = self.merge(snap, {t: list_page([(2, 150, "Mega Y", "Mega Mewtwo Y", "SS")]) for t in pt.TYPES})
        self.assertEqual(failed, [])
        row = self.ghost_modes(snap, "150-Mega_Y")[0]
        self.assertEqual((row["tier"], row["rank"], row["off_type"]), ("SS", 2, True))

    def test_keeps_only_the_top_50(self):
        snap = snapshot()
        self.merge(snap, {t: list_page([(50, 150, "Mega Y", "Mega Mewtwo Y", "B"), (51, 464, None, "Rhyperior", "C")])
                          for t in pt.TYPES})
        self.assertTrue(self.ghost_modes(snap, "150-Mega_Y"))          # #50 stays
        self.assertFalse(self.ghost_modes(snap, "464"))                # #51 doesn't

    def test_own_type_tile_from_the_page_is_not_replaced(self):
        snap = snapshot()
        self.merge(snap, {t: list_page([(1, 94, None, "Gengar", "S")]) for t in pt.TYPES})
        ghost = self.ghost_modes(snap, "94")
        self.assertEqual(len(ghost), 1)
        self.assertNotIn("off_type", ghost[0])

    def test_unknown_pokemon_is_skipped(self):
        snap = snapshot()
        added, _ = self.merge(snap, {t: list_page([(1, 999, None, "Nobody", "S")]) for t in pt.TYPES})
        self.assertEqual(added, 0)

    def test_can_be_re_run(self):
        snap = snapshot()
        pages = {t: list_page([(2, 150, "Mega Y", "Mega Mewtwo Y", "SS")]) for t in pt.TYPES}
        self.merge(snap, pages)
        self.merge(snap, pages)
        self.assertEqual(len(self.ghost_modes(snap, "150-Mega_Y")), 1)

    def test_a_list_that_cannot_be_read_is_reported(self):
        snap = snapshot()
        pages = {t: list_page([(2, 150, "Mega Y", "Mega Mewtwo Y", "SS")]) for t in pt.TYPES if t != "ghost"}
        _, failed = self.merge(snap, pages)
        self.assertEqual(failed, ["ghost"])

    def test_group_rankings_are_rebuilt(self):
        snap = snapshot()
        self.merge(snap, {t: list_page([(2, 150, "Mega Y", "Mega Mewtwo Y", "SS")]) for t in pt.TYPES})
        self.assertTrue(any(r["mode"] == "Ghost-type" for rows in snap["rankings"].values() for r in rows))


if __name__ == "__main__":
    unittest.main()
