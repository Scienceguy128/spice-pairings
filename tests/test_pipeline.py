import sys
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

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
        for line in ("* 3 cloves garlic, minced", "* 2 whole cloves of garlic",
                     "* 3 garlic cloves", "* garlic, 2 cloves",
                     "* 2 whole cloves of fresh garlic", "* 1 clove crushed garlic",
                     "* 3 cloves [[Cookbook:Garlic|garlic]], minced"):
            with self.subTest(line=line):
                self.assertEqual(found(line), {"garlic"})
        self.assertEqual(found("* 4 whole cloves"), {"cloves"})
        self.assertEqual(found("* 1 tsp ground cloves"), {"cloves"})
        self.assertEqual(found("* 2 whole cloves and 1 garlic clove"), {"cloves", "garlic"})

    def test_allium_aliases_and_forms(self):
        cases = {
            "* 2 red onions, diced": {"onion"},
            "* 1 tsp onion powder": {"onion"},
            "* 1 tsp garlic powder": {"garlic"},
            "* 2 scallions": {"scallion"},
            "* 2 spring onions": {"scallion"},
            "* 2 green onions": {"scallion"},
            "* 2 green-onions": {"scallion"},
            "* 3 shallots": {"shallot"},
            "* 2 eschalots": {"shallot"},
            "* 1 leek": {"leek"},
            "* 1 tbsp garlic chives": {"chives"},
        }
        for line, ids in cases.items():
            with self.subTest(line=line):
                self.assertEqual(found(line), ids)

    def test_aromatics_do_not_absorb_seeds_or_blends(self):
        cases = {
            "* 2 celery stalks": {"celery"},
            "* 1 fennel bulb": {"fennel"},
            "* 1 inch galangal": {"galangal"},
            "* 1 tsp celery seeds": {"celery_seed"},
            "* 1 tsp fennel seeds": {"fennel_seed"},
            "* 1 tsp ground fennel": {"fennel_seed"},
            "* 1 tsp black onion seeds": {"nigella"},
            "* 1 tsp celery salt": set(),
            "* 1 tsp garlic salt": set(),
            "* 1 tsp onion salt": set(),
            "* 2 slices garlic bread": set(),
            "* 1 packet onion soup mix": set(),
        }
        for line, ids in cases.items():
            with self.subTest(line=line):
                self.assertEqual(found(line), ids)

    def test_aromatic_alternatives_are_excluded(self):
        result = dp.match_line("* 1 onion or 2 shallots", ALIASES)
        self.assertEqual(result["found"], [])
        self.assertEqual(set(result["alternatives"]), {"onion", "shallot"})

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
    def test_build_includes_aromatics_and_valid_recipe_examples(self):
        pages = [
            {"pageid": 1, "revid": 1, "title": "Cookbook:Stew",
             "content": "==Ingredients==\n* 2 garlic cloves\n* garlic powder\n* thyme\n* onion"},
            {"pageid": 2, "revid": 2, "title": "Cookbook:Soup",
             "content": "==Ingredients==\n* green onions\n* celery"},
            {"pageid": 3, "revid": 3, "title": "Cookbook:Rice",
             "content": "==Ingredients==\n* rice\n* water"},
        ]
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw, retrieval = root / "recipes.jsonl", root / "retrieval.json"
            raw.write_text("\n".join(dp.json.dumps(p) for p in pages), encoding="utf-8")
            retrieval.write_text("{}", encoding="utf-8")
            out_json, out_js, audit = root / "pairings.json", root / "pairings.js", root / "audit.json"
            with patch.multiple(dp, RAW=raw, RETRIEVAL=retrieval,
                                OUT_JSON=out_json, OUT_JS=out_js, AUDIT=audit):
                output = dp.build()
            self.assertEqual(dp.json.loads(out_json.read_text(encoding="utf-8")), output)
            self.assertEqual(out_js.read_text(encoding="utf-8"), "window.PAIRINGS_DATA = " +
                             out_json.read_text(encoding="utf-8") + ";\n")
            nodes = {n["id"]: n for n in output["nodes"]}
            self.assertEqual(nodes["garlic"]["type"], "aromatic")
            self.assertEqual(nodes["garlic"]["count"], 1)
            self.assertEqual(nodes["onion"]["count"], 1)
            self.assertEqual(nodes["scallion"]["count"], 1)
            self.assertEqual(nodes["cloves"]["count"], 0)
            self.assertEqual(output["meta"]["eligible_recipes"], 3)
            self.assertEqual(output["meta"]["recipes_with_tracked_ingredients"], 2)
            pairs = {(p["a"], p["b"]): p for p in output["pairs"]}
            pair = pairs[("garlic", "thyme")]
            self.assertEqual(pair["shared"], 1)
            self.assertEqual(pair["lift"], 3.0)
            self.assertEqual(output["recipes"][pair["examples"][0]]["t"], "Stew")
            self.assertEqual(pairs[("celery", "scallion")]["shared"], 1)

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

    def test_deduplication_retains_different_aromatics(self):
        recipes = [
            dp.parse_recipe({"pageid": i, "revid": i, "title": title,
                             "content": f"==Ingredients==\n* thyme\n* {allium}"}, ALIASES)
            for i, title, allium in (
                (1, "Cookbook:Stew", "onion"),
                (2, "Cookbook:Stew II", "shallots"),
                (3, "Cookbook:Stew III", "red onions"),
            )
        ]
        kept, removed = dp.deduplicate(recipes)
        self.assertEqual([r["pageid"] for r in kept], [1, 2])
        self.assertEqual(len(removed), 1)


if __name__ == "__main__":
    unittest.main()
