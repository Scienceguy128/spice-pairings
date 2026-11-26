"""Download Wikibooks Cookbook recipes and cuisine categories via the MediaWiki API.

Writes one JSON object per page to data/raw/wikibooks_recipes.jsonl and
retrieval and cuisine-category metadata to data/raw/. Text is CC BY-SA 4.0.
"""
import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from cuisine_categories import (
    ORIGIN_ROOT, category_key, category_links, is_recipe_category, normalize_category, origin_category_map,
)

API = "https://en.wikibooks.org/w/api.php"
CATEGORY = "Category:Recipes"
USER_AGENT = "spice-pairings-prototype/0.1 (local, non-commercial research; python-urllib)"
OUT_DIR = Path(__file__).parent / "data" / "raw"


def api_get(params):
    query = urllib.parse.urlencode({**params, "format": "json", "formatversion": "2", "maxlag": "5"})
    req = urllib.request.Request(f"{API}?{query}", headers={"User-Agent": USER_AGENT})
    for attempt in range(8):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as err:
            if err.code not in (429, 503):
                raise
            wait = int(err.headers.get("Retry-After") or 0) or 15 * (attempt + 1)
            print(f"HTTP {err.code}; waiting {wait}s", flush=True)
            time.sleep(wait)
            continue
        if data.get("error", {}).get("code") == "maxlag":
            time.sleep(5 * (attempt + 1))
            continue
        if "error" in data:
            raise RuntimeError(data["error"])
        return data
    raise RuntimeError("API request kept failing (maxlag/rate limit)")


def fetch_cuisine_categories(pages):
    names = {
        category_key(name): name
        for page in pages for name in category_links(page["content"])
        if is_recipe_category(name)
    }
    parents, queried = {}, {ORIGIN_ROOT}
    while True:
        pending = sorted(set(names) - queried)
        if not pending:
            break
        for start in range(0, len(pending), 50):
            batch = pending[start:start + 50]
            cont = {}
            while True:
                data = api_get({
                    "action": "query",
                    "titles": "|".join("Category:" + names[key] for key in batch),
                    "prop": "categories",
                    "cllimit": "max",
                    **cont,
                })
                for page in data.get("query", {}).get("pages", []):
                    name = normalize_category(page["title"])
                    key = category_key(name)
                    names[key] = name
                    parents.setdefault(key, set())
                    for category in page.get("categories", []):
                        parent = normalize_category(category["title"])
                        if is_recipe_category(parent):
                            parent_key = category_key(parent)
                            names.setdefault(parent_key, parent)
                            parents[key].add(parent_key)
                if "continue" not in data:
                    break
                cont = data["continue"]
                time.sleep(3)
            queried.update(batch)
            print(f"checked {len(queried)} recipe categories", flush=True)
            time.sleep(3)
    graph = {names[key]: [names[parent] for parent in links] for key, links in parents.items()}
    categories = origin_category_map(graph)
    if not categories:
        raise RuntimeError("No recipe-origin categories found in Wikibooks category metadata.")
    return categories


def save_cuisine_categories(pages):
    categories = fetch_cuisine_categories(pages)
    (OUT_DIR / "cuisine_categories.json").write_text(
        json.dumps(categories, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    print(f"saved {len(categories)} recipe-origin categories")


def fetch_all():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    params = {
        "action": "query",
        "generator": "categorymembers",
        "gcmtitle": CATEGORY,
        "gcmnamespace": "102",
        "gcmtype": "page",
        "gcmlimit": "50",
        "prop": "revisions",
        "rvprop": "ids|timestamp|content",
        "rvslots": "main",
    }
    pages = {}
    cont = {}
    while True:
        data = api_get({**params, **cont})
        for page in data.get("query", {}).get("pages", []):
            revs = page.get("revisions")
            if not revs:
                continue
            rev = revs[0]
            pages[page["pageid"]] = {
                "pageid": page["pageid"],
                "title": page["title"],
                "revid": rev["revid"],
                "timestamp": rev["timestamp"],
                "content": rev["slots"]["main"].get("content", ""),
            }
        print(f"fetched {len(pages)} pages", flush=True)
        if "continue" not in data:
            break
        cont = data["continue"]
        time.sleep(3)

    category_cache = OUT_DIR / "cuisine_categories.json"
    if category_cache.exists():
        category_cache.unlink()
    with open(OUT_DIR / "wikibooks_recipes.jsonl", "w", encoding="utf-8") as f:
        for page in sorted(pages.values(), key=lambda p: p["title"]):
            f.write(json.dumps(page, ensure_ascii=False) + "\n")
    meta = {
        "source": "English Wikibooks Cookbook",
        "category": CATEGORY,
        "api": API,
        "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "page_count": len(pages),
        "license": "CC BY-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "copyright_policy": "https://en.wikibooks.org/wiki/Wikibooks:Copyrights",
    }
    (OUT_DIR / "retrieval.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"saved {len(pages)} pages")
    save_cuisine_categories(pages.values())


def refresh_cuisine_categories():
    raw = OUT_DIR / "wikibooks_recipes.jsonl"
    if not raw.is_file():
        raise FileNotFoundError("Recipe cache is missing; run python fetch_wikibooks.py first.")
    pages = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines() if line.strip()]
    save_cuisine_categories(pages)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--categories-only", action="store_true", help="refresh cuisine categories for cached recipes")
    args = parser.parse_args()
    if args.categories_only:
        refresh_cuisine_categories()
    else:
        fetch_all()
