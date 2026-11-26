"""Build spice/herb/aromatic pairing statistics from the cached Wikibooks corpus.

Usage:
    python fetch_wikibooks.py   # once, downloads data/raw/*.jsonl
    python data_pipeline.py     # writes web/data/pairings.json(.js) and data/audit.json
"""
import hashlib
import json
import math
import random
import re
import unicodedata
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw" / "wikibooks_recipes.jsonl"
RETRIEVAL = ROOT / "data" / "raw" / "retrieval.json"
ALIASES = ROOT / "ingredient_aliases.json"
OUT_JSON = ROOT / "web" / "data" / "pairings.json"
OUT_JS = ROOT / "web" / "data" / "pairings.js"
AUDIT = ROOT / "data" / "audit.json"

DEFAULT_MIN_SHARED = 10
MAX_EXAMPLES = 5
MIN_INGREDIENT_LINES = 2

HEADING = re.compile(r"^(=+)\s*(.*?)\s*\1\s*$")
INGREDIENT_HEADING = re.compile(r"^ingredients?\b", re.I)
LINK = re.compile(r"\[\[([^\]|]*)(?:\|([^\]]*))?\]\]")
TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
ALTERNATIVE = re.compile(r"(?<![a-z])(?:or|and/or)(?![a-z])")

NON_BLACK_PEPPER = re.compile(
    r"(?<![a-z])(?:bell|sweet|green|red|yellow|orange|hot|chil(?:l?i|e)|jalape\w*|habanero|serrano|poblano|"
    r"banana|scotch bonnet|roasted|pimi?ento|lemon|chipotle|ancho|piquillo|cubanelle|anaheim|thai|"
    r"bird'?s?[- ]eye|long|fresno|cherry|wax|large|medium|small|seeded|stuffed|capsicum)\b[\w -]{0,12}?peppers?(?![a-z])"
)
BARE_PEPPER = re.compile(r"(?<![a-z])pepper(?![a-z])")
PEPPER_SPICE_CONTEXT = re.compile(
    r"(?<![a-z])(?:salt|ground|taste|cracked|freshly|season\w*|dash|pinch|teaspoons?|tsp|tablespoons?|tbsp|white|black)(?![a-z])"
)
BARE_CORIANDER = re.compile(r"(?<![a-z])coriander(?![a-z])")
CILANTRO_CONTEXT = re.compile(r"(?<![a-z])(?:fresh|chopped|handful|bunch|sprigs?|garnish|leaves|leaf|minced)(?![a-z])")
SEED_CONTEXT = re.compile(r"(?<![a-z])(?:ground|seeds?|powder|teaspoons?|tsp|dried|whole|roasted)(?![a-z])")
BARE_CLOVES = re.compile(r"(?<![a-z])cloves?(?![a-z])")
GARLIC_CLOVES = re.compile(
    r"(?<![a-z])(?:(?:whole\s+)?cloves?\s+(?:of\s+)?"
    r"(?:(?:fresh|peeled|crushed|minced|chopped|black)\s+)*garlic|garlic\s+cloves?)(?![a-z])"
)


def bounded(pattern):
    return re.compile(r"(?<![a-z])(?:" + pattern + r")(?![a-z])", re.I)


def load_aliases(path=ALIASES):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rules = [(rule["id"], [bounded(p) for p in rule["patterns"]]) for rule in data["rules"]]
    excludes = [bounded(p) for p in data["exclude_phrases"]]
    unknown = {rid for rid, _ in rules if not rid.startswith("blend:")} - set(data["ingredients"])
    if unknown:
        raise ValueError(f"rules reference unknown ingredients: {sorted(unknown)}")
    return {"ingredients": data["ingredients"], "rules": rules, "excludes": excludes}


def clean_line(raw):
    """Return (lowercase display text, lowercase link targets) for one wikitext line."""
    targets = []

    def link_repl(m):
        target = m.group(1).strip()
        targets.append(re.sub(r"^\s*cookbook\s*:\s*", "", target, flags=re.I).lower())
        return m.group(2) if m.group(2) is not None else target.split(":")[-1]

    text = raw
    text = re.sub(r"<ref[^>]*/>|<ref[^>]*>.*?</ref>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    for _ in range(3):
        text = TEMPLATE.sub(" ", text)
    text = LINK.sub(link_repl, text)
    text = text.replace("'''", "").replace("''", "")
    text = unicodedata.normalize("NFKC", text).replace("\u2019", "'").lower()
    text = re.sub(r"^[*#:;\s]+", "", text)
    return re.sub(r"\s+", " ", text).strip(), targets


def ingredient_lines(wikitext):
    """Bullet lines under any 'Ingredients' heading (including its subsections)."""
    lines, level = [], None
    for line in wikitext.splitlines():
        stripped = line.strip()
        heading = HEADING.match(stripped)
        if heading:
            depth = len(heading.group(1))
            if level is not None and depth <= level:
                level = None
            if level is None and INGREDIENT_HEADING.match(heading.group(2)):
                level = depth
            continue
        if level is not None and stripped.startswith("*"):
            lines.append(stripped)
    return lines


def match_line(raw, aliases):
    """Match one ingredient line.

    Returns dict with 'found' (canonical ids), 'blends', 'ambiguous' (reason strings),
    and 'alternatives' (ids dropped because the line offers them as alternatives).
    """
    text, targets = clean_line(raw)
    found, blends, ambiguous = [], [], []
    work = " " + GARLIC_CLOVES.sub("garlic", text) + " "
    for rx in aliases["excludes"]:
        work = rx.sub(" ", work)
    for rid, patterns in aliases["rules"]:
        for rx in patterns:
            if rx.search(work):
                work = rx.sub(" ", work)
                if rid.startswith("blend:"):
                    blends.append(rid[6:])
                elif rid not in found:
                    found.append(rid)

    if BARE_CORIANDER.search(work):
        if "cilantro" in targets or CILANTRO_CONTEXT.search(work):
            found.append("cilantro")
        elif SEED_CONTEXT.search(work):
            found.append("coriander_seed")
        else:
            ambiguous.append("coriander")
        work = BARE_CORIANDER.sub(" ", work)

    if BARE_CLOVES.search(work):
        if "garlic" in found or "garlic" in work or "garlic" in targets:
            pass  # garlic cloves
        else:
            found.append("cloves")
        work = BARE_CLOVES.sub(" ", work)

    work = NON_BLACK_PEPPER.sub(" ", work)
    if BARE_PEPPER.search(work):
        if PEPPER_SPICE_CONTEXT.search(work) or re.fullmatch(r"\s*pepper\s*", work):
            found.append("black_pepper")
        else:
            ambiguous.append("pepper")

    found = list(dict.fromkeys(found))
    alternatives = []
    if len(found) >= 2 and ALTERNATIVE.search(text):
        alternatives, found = found, []
    return {"text": text, "found": found, "blends": blends, "ambiguous": ambiguous, "alternatives": alternatives}


def parse_recipe(page, aliases):
    lines = ingredient_lines(page["content"])
    found, blends, ambiguous, alternatives, samples = set(), Counter(), [], [], []
    for raw in lines:
        result = match_line(raw, aliases)
        found.update(result["found"])
        blends.update(result["blends"])
        if result["ambiguous"]:
            ambiguous.append((result["ambiguous"], result["text"]))
        if result["alternatives"]:
            alternatives.append((result["alternatives"], result["text"]))
        samples.append((result["text"], result["found"]))
    title = page["title"].split(":", 1)[-1]
    return {
        "pageid": page["pageid"],
        "title": title,
        "revid": page["revid"],
        "url": "https://en.wikibooks.org/wiki/" + quote(page["title"].replace(" ", "_"), safe=":/()',"),
        "line_count": len(lines),
        "ingredients": found,
        "blends": blends,
        "ambiguous": ambiguous,
        "alternatives": alternatives,
        "samples": samples,
        "section_hash": hashlib.sha1(
            "\n".join(re.sub(r"[^a-z0-9]+", "", s[0]) for s in samples).encode()
        ).hexdigest(),
    }


def base_title(title):
    t = re.sub(r"\(.*?\)", " ", title.lower())
    t = re.sub(r"\b(?:recipe|recipes|easy|simple|basic|classic|traditional|homemade|ii|iii|\d+)\b", " ", t)
    return re.sub(r"[^a-z]+", "", t)


def deduplicate(recipes):
    """Drop exact duplicate ingredient sections, and same-base-title recipes with identical tracked sets."""
    kept, removed, seen_hash, seen_title = [], [], {}, {}
    for r in sorted(recipes, key=lambda r: r["pageid"]):
        if r["section_hash"] in seen_hash:
            removed.append({"title": r["title"], "duplicate_of": seen_hash[r["section_hash"]], "reason": "identical ingredients"})
            continue
        key = (base_title(r["title"]), frozenset(r["ingredients"]))
        if r["ingredients"] and key in seen_title:
            removed.append({"title": r["title"], "duplicate_of": seen_title[key], "reason": "same title and tracked ingredient set"})
            continue
        seen_hash[r["section_hash"]] = r["title"]
        seen_title[key] = r["title"]
        kept.append(r)
    return kept, removed


def lift(shared, count_a, count_b, total):
    """Observed co-occurrence divided by expectation under independence; None when undefined."""
    if total <= 0 or count_a <= 0 or count_b <= 0:
        return None
    return shared * total / (count_a * count_b)


def compute_pairs(recipe_sets, max_examples=MAX_EXAMPLES):
    """recipe_sets: list of (recipe_index, set_of_ids). Returns (counts, pairs, total)."""
    total = len(recipe_sets)
    counts = Counter()
    shared = Counter()
    examples = defaultdict(list)
    for idx, ids in recipe_sets:
        ids = sorted(set(ids))
        counts.update(ids)
        for a, b in combinations(ids, 2):
            shared[(a, b)] += 1
            if len(examples[(a, b)]) < max_examples:
                examples[(a, b)].append(idx)
    pairs = []
    for (a, b), n in shared.items():
        value = lift(n, counts[a], counts[b], total)
        pairs.append({
            "a": a, "b": b, "shared": n,
            "expected": round(counts[a] * counts[b] / total, 3),
            "lift": round(value, 4),
            "examples": examples[(a, b)],
        })
    pairs.sort(key=lambda p: (-p["shared"], p["a"], p["b"]))
    return counts, pairs, total


def supported_edges(pairs, min_shared=DEFAULT_MIN_SHARED):
    """Edges shown by default: enough shared recipes and positive association (lift > 1)."""
    return [p for p in pairs if p["shared"] >= min_shared and p["lift"] > 1]


def build():
    aliases = load_aliases()
    pages = [json.loads(line) for line in RAW.read_text(encoding="utf-8").splitlines() if line.strip()]
    retrieval = json.loads(RETRIEVAL.read_text(encoding="utf-8"))
    parsed = [parse_recipe(p, aliases) for p in pages]
    no_section = [r for r in parsed if r["line_count"] < MIN_INGREDIENT_LINES]
    eligible, duplicates = deduplicate([r for r in parsed if r["line_count"] >= MIN_INGREDIENT_LINES])

    used = [r for r in eligible if r["ingredients"]]
    recipe_index = {r["pageid"]: i for i, r in enumerate(used)}
    counts, pairs, total = compute_pairs([(recipe_index[r["pageid"]], r["ingredients"]) for r in eligible if r["ingredients"]] +
                                         [(None, set()) for r in eligible if not r["ingredients"]])
    meta_ing = aliases["ingredients"]
    nodes = [
        {"id": k, "label": v["label"], "type": v["type"], "count": counts.get(k, 0)}
        for k, v in sorted(meta_ing.items(), key=lambda kv: -counts.get(kv[0], 0))
    ]
    blend_counts = Counter()
    for r in eligible:
        blend_counts.update(set(r["blends"]))

    output = {
        "meta": {
            **retrieval,
            "pages_downloaded": len(pages),
            "pages_without_ingredient_list": len(no_section),
            "duplicates_removed": len(duplicates),
            "eligible_recipes": total,
            "recipes_with_tracked_ingredients": len(used),
            "observed_pairs": len(pairs),
            "default_min_shared": DEFAULT_MIN_SHARED,
            "default_supported_positive_pairs": len(supported_edges(pairs)),
            "score": "lift = shared * N / (count_a * count_b); N = eligible_recipes",
            "attribution": "Recipe data derived from English Wikibooks Cookbook contributors, CC BY-SA 4.0. "
                           "Derived pairing statistics are shared under the same license.",
        },
        "nodes": nodes,
        "pairs": pairs,
        "recipes": [{"t": r["title"], "u": r["url"]} for r in used],
        "excluded_blends": dict(blend_counts.most_common()),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(output, ensure_ascii=False, separators=(",", ":"))
    OUT_JSON.write_text(payload, encoding="utf-8")
    OUT_JS.write_text("window.PAIRINGS_DATA = " + payload + ";\n", encoding="utf-8")

    rng = random.Random(42)
    sample_lines = [(r["title"], t, f) for r in eligible for t, f in r["samples"]]
    ambiguous = Counter(reason for r in eligible for reasons, _ in r["ambiguous"] for reason in reasons)
    audit = {
        "ambiguous_counts": dict(ambiguous),
        "ambiguous_examples": [{"title": r["title"], "reasons": a, "line": t}
                               for r in eligible for a, t in r["ambiguous"]][:150],
        "alternative_lines_excluded": sum(len(r["alternatives"]) for r in eligible),
        "alternative_examples": [{"title": r["title"], "ids": a, "line": t}
                                 for r in eligible for a, t in r["alternatives"]][:100],
        "duplicates_removed": duplicates,
        "pages_without_ingredient_list": [r["title"] for r in no_section],
        "review_sample": [{"title": ti, "line": t, "matched": f}
                          for ti, t, f in rng.sample(sample_lines, min(200, len(sample_lines)))],
    }
    AUDIT.write_text(json.dumps(audit, indent=1, ensure_ascii=False), encoding="utf-8")
    return output


if __name__ == "__main__":
    out = build()
    m = out["meta"]
    print(f"pages={m['pages_downloaded']} no_ingredient_list={m['pages_without_ingredient_list']} "
          f"duplicates={m['duplicates_removed']} eligible={m['eligible_recipes']} "
          f"with_tracked_ingredients={m['recipes_with_tracked_ingredients']}")
    print(f"observed pairs={m['observed_pairs']} supported positive pairs (>= {DEFAULT_MIN_SHARED})="
          f"{m['default_supported_positive_pairs']}")
    print("top ingredients:", ", ".join(f"{n['label']}={n['count']}" for n in out["nodes"][:12]))
    print("ingredients with zero coverage:", [n["label"] for n in out["nodes"] if n["count"] == 0])
