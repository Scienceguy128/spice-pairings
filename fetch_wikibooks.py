"""Download Wikibooks Cookbook recipe pages via the official MediaWiki API.

Writes one JSON object per page to data/raw/wikibooks_recipes.jsonl and
retrieval metadata to data/raw/retrieval.json. Text is CC BY-SA 4.0.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

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


if __name__ == "__main__":
    fetch_all()
