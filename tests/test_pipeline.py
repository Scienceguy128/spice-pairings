import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import data_pipeline as dp  # noqa: E402

ALIASES = dp.load_aliases()


def found(line):
    return set(dp.match_line(line, ALIASES)["found"])


class MatchingTests(unittest.TestCase):
    def test_wikilinks_and_templates_are_cleaned(self):
        line = "* 1 [[Cookbook:Teaspoon|teaspoon]] {{convert|5|g|oz}} ground [[Cookbook:Cumin|cumin]]"
        self.assertEqual(found(line), {"cumin"})

    def test_cilantro_and_coriander_seed_stay_separate(self):
        self.assertEqual(found("* 2 tbsp chopped fresh coriander"), {"cilantro"})
        self.assertEqual(found("* 1 tsp ground coriander"), {"coriander_seed"})
        self.assertEqual(found("* 1 bunch cilantro"), {"cilantro"})
        self.assertEqual(dp.match_line("* coriander", ALIASES)["ambiguous"], ["coriander"])

    def test_pepper_types(self):
        self.assertEqual(found("* Salt and pepper to taste"), {"black_pepper"})
        self.assertEqual(found("* 1 green bell pepper, diced"), set())
        self.assertEqual(found("* 1/2 tsp white pepper"), {"white_pepper"})
        self.assertEqual(found("* 1 tsp crushed red pepper flakes"), {"red_pepper_flakes"})
        self.assertEqual(dp.match_line("* 1 pepper, sliced", ALIASES)["ambiguous"], ["pepper"])

    def test_garlic_cloves_are_not_the_spice(self):
        self.assertEqual(found("* 3 cloves garlic, minced"), set())
        self.assertEqual(found("* 4 whole cloves"), {"cloves"})

    def test_blends_are_not_expanded(self):
        result = dp.match_line("* 2 tsp curry powder", ALIASES)
        self.assertEqual(result["found"], [])
        self.assertEqual(result["blends"], ["curry powder"])
        self.assertEqual(found("* 10 curry leaves"), {"curry_leaf"})

    def test_alternatives_are_not_counted_as_both(self):
        result = dp.match_line("* 1 tsp dried thyme or oregano", ALIASES)
        self.assertEqual(result["found"], [])
        self.assertEqual(set(result["alternatives"]), {"thyme", "oregano"})

    def test_non_spice_phrases_excluded(self):
        self.assertEqual(found("* 1 can ginger ale"), set())
        self.assertEqual(found("* 2 tbsp Dijon mustard"), set())
        self.assertEqual(found("* 1 tsp dry mustard"), {"mustard_seed"})
        self.assertEqual(found("* 1 cup sausage"), set())
        self.assertEqual(found("* 4 slices pepper jack cheese"), set())
        self.assertEqual(found("* 2 tbsp mustard seed oil"), set())

    def test_ingredient_section_includes_subsections_only(self):
        text = "==Ingredients==\n===Sauce===\n* thyme\n==Procedure==\n* add sage"
        self.assertEqual(dp.ingredient_lines(text), ["* thyme"])


class StatisticsTests(unittest.TestCase):
    def test_lift_corrects_for_popularity_and_is_symmetric(self):
        # 'pop' is in every recipe, so it cannot show association with anything.
        sets = [(i, {"pop", "a", "b"}) for i in range(5)] + [(i, {"pop"}) for i in range(5, 10)]
        counts, pairs, total = dp.compute_pairs(sets)
        by_pair = {(p["a"], p["b"]): p for p in pairs}
        self.assertEqual(total, 10)
        self.assertAlmostEqual(by_pair[("a", "pop")]["lift"], 1.0)
        self.assertAlmostEqual(by_pair[("a", "b")]["lift"], 2.0)
        self.assertEqual(dp.lift(5, 5, 10, 10), dp.lift(5, 10, 5, 10))

    def test_denominator_includes_recipes_without_tracked_ingredients(self):
        sets = [(0, {"a", "b"}), (None, set()), (None, set()), (None, set())]
        _, pairs, total = dp.compute_pairs(sets)
        self.assertEqual(total, 4)
        self.assertAlmostEqual(pairs[0]["lift"], 4.0)

    def test_duplicate_ingredients_counted_once_per_recipe(self):
        counts, pairs, _ = dp.compute_pairs([(0, ["a", "a", "b"])])
        self.assertEqual(counts["a"], 1)
        self.assertEqual(pairs[0]["shared"], 1)

    def test_zero_evidence_is_undefined_not_zero(self):
        self.assertIsNone(dp.lift(0, 0, 5, 10))
        self.assertIsNone(dp.lift(0, 1, 1, 0))
        self.assertEqual(dp.compute_pairs([]), (dp.Counter(), [], 0))

    def test_threshold_boundary(self):
        pairs = [{"a": "x", "b": "y", "shared": n, "lift": 1.5} for n in (9, 10, 11)]
        self.assertEqual([p["shared"] for p in dp.supported_edges(pairs, 10)], [10, 11])
        self.assertEqual(dp.supported_edges([{"shared": 50, "lift": 0.8}], 10), [])

    def test_deduplication(self):
        base = {"ingredients": {"thyme"}, "section_hash": "h1"}
        recipes = [
            {**base, "pageid": 1, "title": "Stew"},
            {**base, "pageid": 2, "title": "Other"},
            {"pageid": 3, "title": "Stew (Easy)", "ingredients": {"thyme"}, "section_hash": "h2"},
            {"pageid": 4, "title": "Stew II", "ingredients": {"sage"}, "section_hash": "h3"},
        ]
        kept, removed = dp.deduplicate(recipes)
        self.assertEqual([r["pageid"] for r in kept], [1, 4])
        self.assertEqual(len(removed), 2)


if __name__ == "__main__":
    unittest.main()
