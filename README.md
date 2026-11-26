# Spice & herb pairing network

An interactive network of how often spices and culinary herbs appear together in recipes, scored by how much **more** often they co-occur than their individual popularity would predict.

![Nodes are spices (orange) and herbs (green); edges are supported positive pairings.](docs/screenshot.png)

## Quick start

```powershell
python fetch_wikibooks.py      # download the Wikibooks Cookbook recipes (cached in data/raw/, git-ignored)
python data_pipeline.py        # parse, normalize, score -> web/data/pairings.json + .js, data/audit.json
start web\index.html           # open in a browser (works from file://, no server needed)
```

Only the Python standard library is required. Cytoscape.js is vendored in `web/vendor/`. The generated data is committed, so you can open `web/index.html` without re-running the pipeline.

Tests:

```powershell
python -m unittest discover -s tests
node --test tests/
```

## How the score works

For every pair of tracked ingredients, over **N** deduplicated recipes:

```
lift = (recipes with both × N) / (recipes with A × recipes with B)
```

- **lift > 1**: used together more often than chance given how common each one is.
- **lift ≈ 1**: no association beyond popularity.
- **lift < 1**: used together less than expected *in this corpus* — not proof they clash.

Raw co-occurrence counts would mostly show that black pepper and parsley are common. Lift corrects for that, but it can overrate rare pairs, so every pair also shows the number of shared recipes.

### What the network shows

- **Nodes**: one per spice or herb; size reflects the number of recipes containing it.
- **Edges**: pairs with at least *k* shared recipes **and** lift > 1. Width is scaled log-lift. *k* defaults to **10** and can be changed in the header. Pairs with fewer than 10 shared recipes are drawn dashed (sparse evidence) when you lower *k*.
- **Click an ingredient** to see its strongest supported partners, observed pairs that aren't drawn (below threshold or no positive association), and ingredients never seen with it.
- **Click an edge or row** to see lift, counts, expected co-occurrence and links to example recipes.

Network positions are produced by a force layout and are not a taste distance.

## Data pipeline

1. `fetch_wikibooks.py` uses the official MediaWiki API to download every page in `Category:Recipes` (the Cookbook namespace), with revision IDs and retrieval time. It backs off on rate limits.
2. `data_pipeline.py`:
   - extracts bullet lines under `Ingredients` headings (including subsections); pages with fewer than 2 such lines are skipped;
   - strips wiki markup and matches the rules in `ingredient_aliases.json` in order;
   - keeps cilantro (leaf) separate from coriander seed, and black, white, Sichuan pepper, cayenne and red pepper flakes separate; ambiguous bare "coriander" or "pepper" (e.g. "1 pepper, sliced") is excluded and logged;
   - ignores garlic "cloves", ginger ale, Dijon/prepared mustard, dill pickles, etc.;
   - does **not** split blends (curry powder, garam masala, chili powder, Italian seasoning, …) into components — they are counted and reported separately;
   - excludes lines that offer alternatives ("thyme or oregano") from pair evidence;
   - counts each ingredient once per recipe;
   - removes duplicate recipes (identical ingredient sections, or same base title with the same spice set);
   - keeps recipes without any tracked spice in the denominator N.
3. `data/audit.json` lists ambiguous lines, excluded alternatives, removed duplicates and a random sample of 200 parsed lines for manual review.

## Current results (retrieved 2026-11-26)

- 3,802 recipe pages downloaded; 112 without a usable ingredient list and 20 duplicates removed → **N = 3,670** recipes, 2,355 containing at least one of the 48 tracked spices/herbs.
- 596 pairs observed together at least once; **145** meet the default filter (≥ 10 shared recipes, lift > 1).
- Strong clusters: Indian tempering (asafoetida, curry leaf, mustard seed, turmeric, fenugreek), warm baking/sweet spices (cloves, mace, allspice, cardamom, saffron, cinnamon, star anise) and Mediterranean herbs (rosemary + thyme 11.1×, basil + oregano 9.8×).
- Black pepper is in 32% of recipes, so its raw counts are the largest, but its lift is moderate (~1.6–2.3×).
- Stability: across 100 bootstrap resamples, 94–100% (mean 98%) of the 145 default edges kept lift > 1. Edges with lift close to 1 are the ones that flip, so treat them as weak.
- Thin coverage (< 10 recipes): anise seed, makrut lime leaf, nigella, juniper, Sichuan pepper, savory, chervil, epazote, sumac. They appear faded until you lower the threshold.
- Blends were counted but not scored: chili powder (139), curry powder (58), garam masala (34), berbere (24), …

## Limitations

- One community-written corpus of a few thousand recipes; coverage skews toward cuisines Wikibooks contributors wrote about, and rare spices have little evidence.
- Co-occurrence reflects culinary convention, not chemistry or taste tests. Quantities, cooking method, dish type and three-way combinations are ignored.
- Rule-based matching makes mistakes; see `data/audit.json`.
- Missing edges mean insufficient evidence or no positive association in this corpus, not incompatibility.

## License and attribution

Recipe text is from the [English Wikibooks Cookbook](https://en.wikibooks.org/wiki/Cookbook:Table_of_Contents), © Wikibooks contributors, licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) ([policy](https://en.wikibooks.org/wiki/Wikibooks:Copyrights)). The derived data in `web/data/` and `data/audit.json` (which quotes ingredient lines) is shared under CC BY-SA 4.0. Every example link points at its source page.

Cytoscape.js is MIT-licensed (`web/vendor/cytoscape-LICENSE.txt`).
