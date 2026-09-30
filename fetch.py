#!/usr/bin/env python3
"""WikiPull: download freely licensed photos from Wikimedia Commons.

Usage:
    python fetch.py "Renato Moicano"             # top 5 images
    python fetch.py "Renato Moicano" --count 3
    python fetch.py --queue queue.txt            # one search per line

For each search, images land in images/<slug>/ along with credits.md and
credits.json, which record the author, license and source page for every file.
Only openly licensed files (CC0, CC BY, CC BY-SA, public domain) are kept.

No third-party packages needed: standard library only.
"""

import argparse
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
# Wikimedia asks every client to send a descriptive User-Agent.
USER_AGENT = "WikiPull/1.0 (https://github.com/jlopresti02/WikiPull) python-urllib"

IMAGES_DIR = Path(__file__).resolve().parent / "images"
TARGET_WIDTH = 1600   # download size; big enough for a post, small enough for git
MIN_WIDTH = 500       # skip tiny files
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
FREE_LICENSE = re.compile(r"(cc0|cc[ -]by|public domain|^pd\b|pd-)", re.I)


# ---------------------------------------------------------------- helpers

def api_get(base, params, retries=3):
    params = {**params, "format": "json", "formatversion": "2"}
    url = base + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except Exception as exc:  # network hiccup or rate limit: back off and retry
            if attempt == retries - 1:
                raise
            print(f"  retrying after error: {exc}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        dest.write_bytes(resp.read())


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "search"


def strip_html(text):
    text = re.sub(r"<[^>]+>", "", text or "")
    return " ".join(html.unescape(text).split())


def meta(info, key):
    return strip_html(info.get("extmetadata", {}).get(key, {}).get("value", ""))


# ---------------------------------------------------------------- lookups

def wikidata_main_image(query):
    """The photo Wikipedia uses for this person/thing (Wikidata property P18)."""
    found = api_get(WIKIDATA_API, {
        "action": "wbsearchentities", "search": query,
        "language": "en", "type": "item", "limit": 1,
    }).get("search", [])
    if not found:
        return []
    entity = api_get(WIKIDATA_API, {
        "action": "wbgetentities", "ids": found[0]["id"], "props": "claims",
    })["entities"][found[0]["id"]]
    claims = entity.get("claims", {}).get("P18", [])
    return ["File:" + c["mainsnak"]["datavalue"]["value"]
            for c in claims if "datavalue" in c.get("mainsnak", {})]


IMAGEINFO = {
    "prop": "imageinfo",
    "iiprop": "url|size|mime|extmetadata",
    "iiurlwidth": TARGET_WIDTH,
    "iiextmetadatafilter": "Artist|Credit|LicenseShortName|LicenseUrl|UsageTerms|ImageDescription",
}


def file_info(titles):
    if not titles:
        return []
    data = api_get(COMMONS_API, {"action": "query", "titles": "|".join(titles), **IMAGEINFO})
    return [p for p in data.get("query", {}).get("pages", []) if p.get("imageinfo")]


def commons_search(query, limit=40):
    data = api_get(COMMONS_API, {
        "action": "query", "generator": "search",
        "gsrsearch": f'"{query}" filetype:bitmap', "gsrnamespace": 6,
        "gsrlimit": limit, **IMAGEINFO,
    })
    pages = data.get("query", {}).get("pages", [])
    return sorted(pages, key=lambda p: p.get("index", 999))  # keep relevance order


# ---------------------------------------------------------------- main flow

def usable(page):
    info = page["imageinfo"][0]
    if info.get("mime") not in ALLOWED_MIME:
        return False
    if info.get("width", 0) < MIN_WIDTH:
        return False
    return bool(FREE_LICENSE.search(meta(info, "LicenseShortName")))


def fetch(query, count):
    print(f"Searching Wikimedia Commons for: {query}")
    candidates = []
    try:
        candidates += file_info(wikidata_main_image(query))
    except Exception as exc:
        print(f"  Wikidata lookup skipped: {exc}", file=sys.stderr)
    candidates += commons_search(query)

    picked, seen = [], set()
    for page in candidates:
        if page["title"] in seen or not usable(page):
            continue
        seen.add(page["title"])
        picked.append(page)
        if len(picked) == count:
            break

    if not picked:
        print("  No openly licensed images found.")
        return 0

    folder = IMAGES_DIR / slugify(query)
    folder.mkdir(parents=True, exist_ok=True)
    credits = []
    for n, page in enumerate(picked, 1):
        info = page["imageinfo"][0]
        url = info.get("thumburl") or info["url"]
        ext = Path(urllib.parse.urlparse(url).path).suffix.lower() or ".jpg"
        name = f"{n:02d}-{slugify(page['title'].removeprefix('File:').rsplit('.', 1)[0])[:60]}{ext}"
        dest = folder / name
        if not dest.exists():
            download(url, dest)
            time.sleep(0.5)  # be polite to Wikimedia's servers
        credits.append({
            "file": name,
            "title": page["title"],
            "author": meta(info, "Artist") or "Unknown",
            "license": meta(info, "LicenseShortName"),
            "license_url": meta(info, "LicenseUrl"),
            "source": info.get("descriptionurl", ""),
        })
        print(f"  saved {dest.relative_to(IMAGES_DIR.parent)}  [{credits[-1]['license']}]")

    (folder / "credits.json").write_text(json.dumps(credits, indent=2) + "\n")
    lines = [f"# Image credits: {query}", ""]
    for c in credits:
        lines.append(f"- **{c['file']}**: {c['author']}, {c['license']}, {c['source']}")
    (folder / "credits.md").write_text("\n".join(lines) + "\n")
    return len(credits)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="?", help="what to search for, e.g. a fighter's name")
    ap.add_argument("--count", type=int, default=5, help="images per search (default 5)")
    ap.add_argument("--queue", help="text file with one search per line")
    args = ap.parse_args()

    queries = []
    if args.query:
        queries.append(args.query.strip())
    if args.queue and Path(args.queue).exists():
        queries += [l.strip() for l in Path(args.queue).read_text().splitlines()
                    if l.strip() and not l.lstrip().startswith("#")]
    if not queries:
        ap.error("give a search term or a --queue file with at least one line")

    total = sum(fetch(q, args.count) for q in queries)
    print(f"Done: {total} image(s) saved.")


if __name__ == "__main__":
    main()
