"""Identify Wikibooks recipe-origin categories and their ancestors."""

import re

ORIGIN_ROOT = "recipes by origin"
CATEGORY_LINK = re.compile(r"\[\[\s*category\s*:\s*([^\]|#]+)(?:\|[^\]]*)?\]\]", re.I)
IGNORED_MARKUP = re.compile(r"<!--.*?-->|<nowiki\b[^>]*>.*?</nowiki\s*>", re.I | re.S)


def normalize_category(name):
    name = re.sub(r"^\s*category\s*:\s*", "", name, flags=re.I)
    return re.sub(r"\s+", " ", name.replace("_", " ")).strip()


def category_key(name):
    return normalize_category(name).casefold()


def is_recipe_category(name):
    key = category_key(name)
    return key == ORIGIN_ROOT or key.endswith(" recipes")


def category_links(wikitext):
    text = IGNORED_MARKUP.sub("", wikitext)
    return {normalize_category(match.group(1)) for match in CATEGORY_LINK.finditer(text)}


def origin_category_map(category_parents):
    """Map origin category keys to their cuisine labels, including origin ancestors."""
    names, parents = {}, {}
    for name, parent_names in category_parents.items():
        key = category_key(name)
        names[key] = normalize_category(name)
        parents.setdefault(key, set()).update(category_key(parent) for parent in parent_names)
        for parent in parent_names:
            names.setdefault(category_key(parent), normalize_category(parent))

    origin = {ORIGIN_ROOT}
    while True:
        found = {name for name, links in parents.items() if links & origin}
        new = found - origin
        if not new:
            break
        origin.update(new)

    result = {}
    for key in origin - {ORIGIN_ROOT}:
        seen, pending = set(), [key]
        while pending:
            current = pending.pop()
            if current in seen or current not in origin:
                continue
            seen.add(current)
            pending.extend(parents.get(current, ()))
        result[key] = sorted(
            names[name][:-len(" recipes")]
            for name in seen if name != ORIGIN_ROOT and name.endswith(" recipes")
        )
    return result
