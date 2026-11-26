import json
import sys
import tempfile
import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import data_pipeline as dp  # noqa: E402
import fetch_wikibooks as fw  # noqa: E402
from cuisine_categories import category_links, origin_category_map  # noqa: E402

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


class CuisineTests(unittest.TestCase):
    def test_origin_categories_include_ancestors_and_ignore_unrelated_categories(self):
        parents = {
            "Thai recipes": {"Southeast Asian recipes"},
            "Southeast Asian recipes": {"Asian recipes"},
            "Asian recipes": {"Recipes by origin"},
            "Main course recipes": {"Recipes by course"},
            "Cycle A recipes": {"Cycle B recipes"},
            "Cycle B recipes": {"Cycle A recipes"},
        }
        categories = origin_category_map(parents)
        self.assertEqual(categories["thai recipes"], ["Asian", "Southeast Asian", "Thai"])
        self.assertNotIn("main course recipes", categories)
        self.assertNotIn("cycle a recipes", categories)

    def test_fetch_combines_paginated_category_parents(self):
        pages = [{"content": "[[Category:Thai recipes]] [[Category:Main course recipes]]"}]
        responses = [
            {"query": {"pages": [
                {"title": "Category:Thai recipes", "categories": [{"title": "Category:Southeast Asian recipes"}]},
                {"title": "Category:Main course recipes", "categories": [{"title": "Category:Recipes by course"}]},
            ]}, "continue": {"clcontinue": "next", "continue": "||"}},
            {"query": {"pages": [
                {"title": "Category:Thai recipes", "categories": [{"title": "Category:Family heritage recipes"}]},
            ]}},
            {"query": {"pages": [
                {"title": "Category:Southeast Asian recipes", "categories": [{"title": "Category:Recipes by origin"}]},
                {"title": "Category:Family heritage recipes", "categories": [{"title": "Category:Recipes by origin"}]},
            ]}},
        ]
        with patch.object(fw, "api_get", side_effect=responses) as api, patch.object(fw.time, "sleep"):
            categories = fw.fetch_cuisine_categories(pages)
        self.assertEqual(categories["thai recipes"], ["Family heritage", "Southeast Asian", "Thai"])
        self.assertNotIn("main course recipes", categories)
        self.assertEqual(api.call_args_list[1].args[0]["clcontinue"], "next")

    def test_category_fetch_failure_preserves_recipes_and_invalidates_old_categories(self):
        response = {"query": {"pages": [{
            "pageid": 1, "title": "Cookbook:Test",
            "revisions": [{"revid": 2, "timestamp": "2026-01-01", "slots": {"main": {"content": "test"}}}],
        }]}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "cuisine_categories.json").write_text('{"stale": []}', encoding="utf-8")
            with patch.object(fw, "OUT_DIR", root), patch.object(fw, "api_get", return_value=response), \
                    patch.object(fw, "fetch_cuisine_categories", side_effect=RuntimeError("unavailable")):
                with self.assertRaisesRegex(RuntimeError, "unavailable"):
                    fw.fetch_all()
            self.assertTrue((root / "wikibooks_recipes.jsonl").is_file())
            self.assertTrue((root / "retrieval.json").is_file())
            self.assertFalse((root / "cuisine_categories.json").exists())

    def test_recipe_cuisines_use_real_category_links_not_comments_or_page_text(self):
        text = (
            "==Ingredients==\n* cumin\n* basil\n"
            "[[Category:Thai_recipes|{{PAGENAME}}]]\n"
            "[[:Category:Italian recipes]]\n"
            "<!-- [[Category:Italian recipes]] -->\n"
            "<nowiki>[[Category:Italian recipes]]</nowiki>\n"
            "Thai and Italian food"
        )
        self.assertEqual(category_links(text), {"Thai recipes"})
        page = {"pageid": 1, "title": "Cookbook:Example", "revid": 2, "content": text}
        recipe = dp.parse_recipe(page, ALIASES, {"thai recipes": ["Asian", "Thai"], "italian recipes": ["Italian"]})
        self.assertEqual(set(recipe["cuisine_sources"]), {"Asian", "Thai"})

    def test_cuisine_counts_lift_and_examples_are_computed_from_eligible_members(self):
        recipes = [
            {"pageid": 1, "ingredients": {"basil", "cumin"},
             "cuisine_sources": {"Thai": 5, "Asian": 1}, "blends": dp.Counter({"curry powder": 2})},
            {"pageid": 2, "ingredients": {"basil"},
             "cuisine_sources": {"Thai": 2}, "blends": dp.Counter()},
            {"pageid": 3, "ingredients": set(),
             "cuisine_sources": {"Thai": 3}, "blends": dp.Counter()},
            {"pageid": 4, "ingredients": {"basil", "cumin"},
             "cuisine_sources": {"Italian": 4}, "blends": dp.Counter()},
        ]
        sources = {r["pageid"]: r for r in recipes}
        sources[5] = {**recipes[0], "pageid": 5}
        result = dp.cuisine_statistics(recipes, {1: 0, 2: 1, 4: 2, 5: 3}, sources)
        thai = result["Thai"]
        self.assertEqual(thai["eligible_recipes"], 3)
        self.assertEqual(thai["recipes_with_tracked_ingredients"], 2)
        self.assertEqual(thai["counts"], {"basil": 2, "cumin": 1})
        self.assertEqual(thai["pairs"][0]["shared"], 1)
        self.assertEqual(thai["pairs"][0]["lift"], 1.5)
        self.assertEqual(thai["pairs"][0]["examples"], [3])
        self.assertEqual(thai["excluded_blends"], {"curry powder": 1})
        self.assertEqual(result["Italian"]["pairs"][0]["examples"], [2])
        self.assertEqual(result["Asian"]["eligible_recipes"], 1)

    def test_duplicate_recipes_keep_all_source_cuisines(self):
        recipes = [
            {"pageid": 1, "title": "Stew", "ingredients": {"basil"}, "section_hash": "same",
             "cuisine_sources": {"Asian": 1}},
            {"pageid": 2, "title": "Other", "ingredients": {"basil"}, "section_hash": "same",
             "cuisine_sources": {"Thai": 2}},
            {"pageid": 3, "title": "Stew (Easy)", "ingredients": {"basil"}, "section_hash": "different",
             "cuisine_sources": {"Indian": 3}},
        ]
        kept, removed = dp.deduplicate(recipes)
        self.assertEqual(len(removed), 2)
        self.assertEqual(kept[0]["cuisine_sources"], {"Asian": 1, "Thai": 2, "Indian": 3})

    def test_build_keeps_cuisine_examples_linked_to_tagged_duplicates(self):
        def page(pageid, title, ingredients, category):
            return {"pageid": pageid, "title": "Cookbook:" + title, "revid": pageid,
                    "content": "==Ingredients==\n" + ingredients + "\n[[Category:" + category + " recipes]]"}

        pages = [
            page(1, "Stew", "* basil\n* cumin\n* garlic", "Asian"),
            page(2, "Stew (Thai)", "* basil\n* cumin\n* garlic", "Thai"),
            page(3, "Thai soup", "* basil\n* sugar", "Thai"),
            page(4, "Thai noodles", "* tofu\n* oil", "Thai"),
            page(5, "Italian stew", "* 2 tsp basil\n* 2 tsp cumin", "Italian"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw, retrieval, categories = root / "recipes.jsonl", root / "retrieval.json", root / "categories.json"
            raw.write_text("\n".join(json.dumps(p) for p in pages), encoding="utf-8")
            retrieval.write_text("{}", encoding="utf-8")
            categories.write_text(json.dumps({
                "asian recipes": ["Asian"], "thai recipes": ["Asian", "Thai"], "italian recipes": ["Italian"],
            }), encoding="utf-8")
            with patch.multiple(dp, RAW=raw, RETRIEVAL=retrieval, CUISINE_CATEGORIES=categories,
                                OUT_JSON=root / "pairings.json", OUT_JS=root / "pairings.js", AUDIT=root / "audit.json"):
                output = dp.build()
            thai = output["cuisines"]["Thai"]
            self.assertEqual(output["meta"]["eligible_recipes"], 4)
            self.assertEqual(thai["eligible_recipes"], 3)
            self.assertEqual(thai["pairs"][0]["lift"], 1.5)
            self.assertEqual(thai["counts"]["garlic"], 1)
            self.assertTrue(any({p["a"], p["b"]} == {"cumin", "garlic"} for p in thai["pairs"]))
            self.assertEqual(output["recipes"][thai["pairs"][0]["examples"][0]]["t"], "Stew (Thai)")
            self.assertEqual(json.loads((root / "pairings.json").read_text(encoding="utf-8")), output)

    def test_cuisine_uses_the_tagged_duplicate_ingredient_matches(self):
        first = {"pageid": 1, "title": "Cookbook:Dish", "revid": 1,
                 "content": "==Ingredients==\n* [[Cookbook:Coriander|coriander]]\n* cumin\n"
                            "[[Category:Asian recipes]]"}
        second = {"pageid": 2, "title": "Cookbook:Thai Dish", "revid": 2,
                  "content": "==Ingredients==\n* [[Cookbook:Cilantro|coriander]]\n* cumin\n"
                             "[[Category:Thai recipes]]"}
        categories = {"asian recipes": ["Asian"], "thai recipes": ["Thai"]}
        parsed = [dp.parse_recipe(page, ALIASES, categories) for page in (first, second)]
        kept, _ = dp.deduplicate(parsed)
        self.assertEqual(len(kept), 1)
        result = dp.cuisine_statistics(kept, {1: 0, 2: 1}, {r["pageid"]: r for r in parsed})
        self.assertEqual(result["Thai"]["counts"], {"cilantro": 1, "cumin": 1})
        self.assertEqual(result["Thai"]["pairs"][0]["examples"], [1])
        self.assertEqual(result["Asian"]["counts"], {"cumin": 1})


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
            raw, retrieval, categories = root / "recipes.jsonl", root / "retrieval.json", root / "categories.json"
            raw.write_text("\n".join(dp.json.dumps(p) for p in pages), encoding="utf-8")
            retrieval.write_text("{}", encoding="utf-8")
            categories.write_text("{}", encoding="utf-8")
            out_json, out_js, audit = root / "pairings.json", root / "pairings.js", root / "audit.json"
            with patch.multiple(dp, RAW=raw, RETRIEVAL=retrieval, CUISINE_CATEGORIES=categories,
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
                             "content": f"==Ingredients==\n* thyme\n* {allium}"}, ALIASES, {})
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
