#!/usr/bin/env python3
"""
Pokemon GO Hub tier scraper (https://db.pokemongohub.net)

Given a Pokemon (name or Pokedex number), this finds its whole evolution line,
scrapes the "Tier Ranking" section of every member's page (every mode shown:
Raid Attacker, Gym Defender, per-type lists, Great/Ultra/Master League, Little
Cup, ...), and writes a JSON file containing:

  * evolution_tree : nested evolution tree (with each node's forms attached)
  * rankings       : one list per form group (normal, shadow, regional, mega,
                     ...), each sorted from best to worst tier
  * per_pokemon    : raw rankings for every page that was scraped

Forms (Shadow, regional, Mega, Dynamax, ...) are ranked separately from the
normal forms, because the site gives each its own page and its own ranking.

Usage:
    python pogo_tiers.py charmander
    python pogo_tiers.py 4 --forms shadow,regional
    python pogo_tiers.py charmander --forms none -o charmander.json
    python pogo_tiers.py --all            # every page -> all_rankings.json

Needs:  pip install requests beautifulsoup4

Speed: all of a line's pages are downloaded in parallel with no pause between
requests (--delay SECONDS adds one back), and cached on disk in data/cache/ next
to this script, so repeat searches are instant. --all scrapes the whole site
once (~3 minutes) and keeps only the rankings (~1 MB, no HTML), which the web
UI then reads. If the site ever answers 429
(too many requests) the script backs off and retries. robots.txt on the site
allows crawling.
"""
import argparse
import json
import os
import re
import sys
import threading
import time
import unicodedata
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests
import movesets
from bs4 import BeautifulSoup, Comment

BASE = "https://db.pokemongohub.net"
DEFAULT_SNAPSHOT = str(Path(__file__).resolve().parent.parent / "data" / "all_rankings.json")
USER_AGENT = "pogo-tier-script/1.0 (personal use, low volume)"
WORKERS = 32         # max pages downloaded at the same time (a whole line fits in one burst)
DEFAULT_DELAY = 0.0  # no pause between requests; use --delay 0.5 etc. to slow down

# Best -> worst. Anything not listed sorts after F (and is reported).
TIER_ORDER = ["SS", "S+", "S", "A+", "A", "A-", "B+", "B", "B-",
              "C+", "C", "C-", "D+", "D", "D-", "E", "F"]
TIER_INDEX = {t: i for i, t in enumerate(TIER_ORDER)}

# "A", "A+", "A Tier", "A Tier #259" (the site now writes the tier, "#" and the number as
# separate pieces of text; older pages wrote "A Tier" and "#259")
TIER_RE = re.compile(r"^([A-Z]{1,2}[+\-]?)(?:\s*Tier)?\s*(?:#\s*(\d+))?$")
RANK_RE = re.compile(r"^#\s*(\d+)$")
HEADING_RE = re.compile(r"^h[1-6]$")
FAMILY_TITLE_RE = re.compile(
    r"^Check (.+?) stats, moves, counters, and typing in Pok[eé]mon GO$")

REGIONAL_TAGS = {"alola", "alolan", "galar", "galarian",
                 "hisui", "hisuian", "paldea", "paldean"}
FORM_GROUPS = ["shadow", "regional", "regional-shadow", "mega", "primal",
               "dynamax", "gigantamax", "other"]


# --------------------------------------------------------------------------
# slugs / forms
# --------------------------------------------------------------------------
def slug_from_href(href):
    """'/pokemon/6-Mega_X/pvp' or full URL -> '6-Mega_X'."""
    path = urlparse(href or "").path
    m = re.match(r"^/(?:[a-z]{2}/)?pokemon/([^/]+)(?:/.*)?$", path)
    return m.group(1) if m else None


def split_slug(slug):
    m = re.match(r"^(\d+)(?:-(.+))?$", slug)
    if not m:
        return None, None
    return int(m.group(1)), m.group(2)


def form_group(slug):
    """normal | shadow | regional | regional-shadow | mega | primal | dynamax
    | gigantamax | other"""
    _, tag = split_slug(slug)
    if not tag:
        return "normal"
    parts = [p.lower() for p in tag.split("_")]
    if parts[0] in REGIONAL_TAGS:
        return "regional-shadow" if "shadow" in parts else "regional"
    if parts[0] in ("shadow", "mega", "primal", "dynamax", "gigantamax"):
        return parts[0]
    return "other"


def base_slug(slug):
    """The slug of the 'plain' Pokemon this form belongs to
    (regional forms count as their own base: 38-Alola_Shadow -> 38-Alola)."""
    dex, tag = split_slug(slug)
    if tag and tag.split("_")[0].lower() in REGIONAL_TAGS:
        return f"{dex}-{tag.split('_')[0]}"
    return str(dex)


def norm(text):
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", text.lower())


# --------------------------------------------------------------------------
# fetching (polite + cached)
# --------------------------------------------------------------------------
class Fetcher:
    def __init__(self, cache_dir, delay, offline=False, refresh=False, store=True):
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self.offline = offline
        self.refresh = refresh
        self.store = store                 # False: don't write pages to disk
        self.last = 0.0
        self._pace = threading.Lock()      # spaces out request *starts*
        self._local = threading.local()    # one HTTP session per worker thread

    @property
    def session(self):
        if not hasattr(self._local, "s"):
            self._local.s = requests.Session()
            self._local.s.headers["User-Agent"] = USER_AGENT
        return self._local.s

    def _file(self, path):
        key = re.sub(r"[^A-Za-z0-9_.\-]+", "_", path.strip("/"))
        return self.cache / f"{key}.html"

    def get(self, path):
        f = self._file(path)
        if f.exists() and not self.refresh:
            return f.read_text(encoding="utf-8")
        if self.offline:
            sys.exit(f"--offline set and {path} is not cached ({f})")
        for attempt in range(4):
            # Requests may overlap, but never start closer together than --delay.
            with self._pace:
                wait = self.delay - (time.time() - self.last)
                if wait > 0:
                    time.sleep(wait)
                self.last = time.time()
            r = self.session.get(BASE + path, timeout=30)
            if r.status_code == 200:
                if self.store:
                    f.write_text(r.text, encoding="utf-8")
                return r.text
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(5 * (attempt + 1))
                continue
            sys.exit(f"GET {BASE}{path} -> HTTP {r.status_code}")
        sys.exit(f"GET {BASE}{path} kept failing; try again later")


# --------------------------------------------------------------------------
# name -> Pokedex slug
# --------------------------------------------------------------------------
def anchor_name(a):
    title = a.get("title") or ""
    m = re.match(r"^(?:Check\s+)?(.+?)\s+(?:stats|Pok[eé]mon GO)", title)
    if m:
        return m.group(1).strip()
    return a.get_text(" ", strip=True)


def load_name_index(fetch):
    idx_file = fetch.cache / "name_index.json"
    if idx_file.exists() and not fetch.refresh:
        return json.loads(idx_file.read_text(encoding="utf-8"))
    idx = {}
    with ThreadPoolExecutor(max_workers=9) as ex:      # all 9 generation pages at once
        pages = list(ex.map(lambda g: fetch.get(f"/pokemon-list/gen-{g}"), range(1, 10)))
    for html in pages:
        # the page is paginated in the browser, but the full list is embedded
        # in the Next.js payload as {"id":856,"name":"Hatenna",...,"form":null}
        for pid, name in re.findall(
                r'\{\\?"id\\?":(\d+),\\?"name\\?":\\?"([^"\\]+)\\?",'
                r'\\?"originalName\\?":\\?"[^"\\]*\\?",\\?"form\\?":null', html):
            idx.setdefault(norm(name), str(int(pid)))
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            slug = slug_from_href(a["href"])
            if slug and slug.isdigit():          # plain forms only
                name = anchor_name(a)
                if name:
                    idx.setdefault(norm(name), slug)
    # Some species have no plain page, only forms (422-East_Sea, 422-West_Sea):
    # index them by their base name so they can be searched and scraped.
    plain = {split_slug(v)[0] for v in idx.values() if v.isdigit()}
    for html in pages:
        for a in BeautifulSoup(html, "html.parser").find_all("a", href=True):
            slug = slug_from_href(a["href"])
            dex, tag = split_slug(slug) if slug else (None, None)
            if dex and tag and dex not in plain and form_group(slug) == "other":
                name = re.sub(r"\s*\(.*\)\s*$", "", anchor_name(a))
                if name:
                    idx.setdefault(norm(name), slug)
    idx_file.write_text(json.dumps(idx), encoding="utf-8")
    return idx


def resolve(query, fetch):
    q = query.strip()
    if re.fullmatch(r"\d+", q):
        return str(int(q))
    if re.fullmatch(r"\d+-[A-Za-z0-9_]+", q):     # explicit form slug
        return q
    idx = load_name_index(fetch)
    key = norm(q)
    if key in idx:
        return idx[key]
    close = sorted(n for n in idx if key and key in n)[:8]
    hint = f" Did you mean one of: {', '.join(close)}?" if close else ""
    sys.exit(f"Couldn't find '{query}' on the generation lists.{hint} "
             "You can also pass the Pokedex number (e.g. 4).")


# --------------------------------------------------------------------------
# page parsing
# --------------------------------------------------------------------------
def parse_rankings(soup):
    """Return (rankings, unranked) from the '<Name>'s Tier Ranking' section.

    Works from the section's text tokens rather than exact tags, so it copes
    with table / list / div layouts:
        <mode label>  <'Not ranked' | 'A' '#' '259' | 'A Tier' '#259' | 'A Tier #259'>
    The tiles live in a container of their own (class "...tierRankingsContainer");
    older pages put them straight after the "Tier Ranking" heading, which is the
    fallback.
    """
    tokens = None
    box = soup.find(class_=re.compile(r"tierRankingsContainer"))
    if box is not None:
        tokens = [" ".join(s.split()) for s in box.find_all(string=True)
                  if not isinstance(s, Comment) and not s.find_parent(["script", "style"])]
        tokens = [t for t in tokens if t]
    if not tokens:
        head = None
        for h in soup.find_all(HEADING_RE):
            if re.search(r"tier ranking", h.get_text(" ", strip=True), re.I):
                head = h
                break
        if head is None:
            return None, None
        tokens = []
        for s in head.find_all_next(string=True):
            if isinstance(s, Comment) or s.find_parent(["script", "style"]):
                continue
            owner = s.find_parent(HEADING_RE)
            if owner is head:
                continue
            if owner is not None:           # reached the next heading -> section over
                break
            t = " ".join(s.split())
            if t:
                tokens.append(t)
            if len(tokens) > 150:
                break

    rankings, unranked = [], []
    mode, pending, hash_seen = None, None, False
    for t in tokens:
        if pending is not None:                       # waiting for '#123', or '#' then '123'
            m = RANK_RE.match(t)
            if m:
                rankings.append({"mode": mode, "tier": pending,
                                 "rank": int(m.group(1))})
                pending = None
                continue
            if t == "#" and not hash_seen:
                hash_seen = True
                continue
            if hash_seen and t.isdigit():
                rankings.append({"mode": mode, "tier": pending, "rank": int(t)})
                pending, hash_seen = None, False
                continue
            rankings.append({"mode": mode, "tier": pending, "rank": None})
            pending, hash_seen = None, False
        if t.lower().rstrip(".") == "not ranked":
            if mode:
                unranked.append(mode)
            continue
        m = TIER_RE.match(t)
        if m and mode:
            if m.group(2):
                rankings.append({"mode": mode, "tier": m.group(1),
                                 "rank": int(m.group(2))})
            else:
                pending = m.group(1)
            continue
        mode = t.rstrip(":").strip()
    if pending is not None:
        rankings.append({"mode": mode, "tier": pending, "rank": None})
    return rankings, unranked


def parse_edges(soup):
    """Rows of the 'Evolution Chart' table -> [{from,to,requires,...}]."""
    head = None
    for h in soup.find_all(HEADING_RE):
        if h.get_text(" ", strip=True).lower().startswith("evolution chart"):
            head = h
            break
    table = head.find_next("table") if head else None
    edges = []
    if table is None:
        return edges
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        a_from = tds[0].find("a", href=True)
        a_to = tds[-1].find("a", href=True)
        if not (a_from and a_to):
            continue
        s_from, s_to = slug_from_href(a_from["href"]), slug_from_href(a_to["href"])
        if not (s_from and s_to):
            continue
        edges.append({
            "from": s_from, "from_name": a_from.get_text(" ", strip=True),
            "to": s_to, "to_name": a_to.get_text(" ", strip=True),
            "requires": " ".join(tds[1].get_text(" ", strip=True).split()),
        })
    return edges


def parse_family(soup):
    """'<Name> family' links (evolutions + every form) -> {slug: display name}."""
    out = {}
    for a in soup.find_all("a", href=True):
        m = FAMILY_TITLE_RE.match(a.get("title") or "")
        slug = slug_from_href(a["href"])
        if m and slug:
            out.setdefault(slug, m.group(1))
    return out


def page_name(soup):
    """The Pokemon's name. GO Hub puts a site-wide <h1>Pokémon</h1> before the page's own, so skip
    that one; the <title> ("Fuecoco: Best Moveset, ...") is the fallback."""
    for h1 in soup.find_all("h1"):
        text = h1.get_text(" ", strip=True)
        if text and norm(text) != "pokemon":
            return text
    if soup.title and soup.title.string and ":" in soup.title.string:
        return soup.title.string.split(":")[0].strip() or None
    return None


def parse_page(html):
    soup = BeautifulSoup(html, "html.parser")
    name = page_name(soup)
    rankings, unranked = parse_rankings(soup)
    return {"name": name, "rankings": rankings, "unranked": unranked,
            "edges": parse_edges(soup), "family": parse_family(soup)}


# --------------------------------------------------------------------------
# build the result
# --------------------------------------------------------------------------
def sort_key(entry):
    tier_i = TIER_INDEX.get(entry["tier"], len(TIER_ORDER))
    rank = entry["rank"] if entry["rank"] is not None else 10 ** 9
    return (tier_i, rank, entry["dex"], entry["mode"])


def group_rankings(per_pokemon):
    """One list per form group, sorted best -> worst, with a 'position' field."""
    by_group = {}
    for p in per_pokemon:
        for r in p["rankings"]:
            by_group.setdefault(p["group"], []).append({
                "pokemon": p["name"], "slug": p["slug"], "dex": p["dex"],
                "mode": r["mode"], "tier": r["tier"], "rank": r["rank"],
            })
    for items in by_group.values():
        items.sort(key=sort_key)
        for i, item in enumerate(items, 1):
            item["position"] = i
            del item["dex"]
    return by_group


def build_all(fetch, workers=8):
    """Every Pokemon page on the site -> rankings only (no HTML is kept).

    Discovery: fetch /pokemon/<dex> for every Pokedex number, then follow each
    page's family links (forms + evolutions) until no new pages turn up.
    """
    idx = load_name_index(fetch)
    seeds = sorted(set(idx.values()), key=lambda v: (split_slug(v)[0], v))
    pages, names, failed = {}, {}, {}

    def grab(slug):
        try:
            return slug, parse_page(fetch.get(f"/pokemon/{slug}")), None
        except (SystemExit, requests.RequestException) as e:
            return slug, None, str(e)

    def run(slugs):
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for i, (slug, page, err) in enumerate(ex.map(grab, slugs), 1):
                if err or page is None:
                    failed[slug] = err
                else:
                    pages[slug] = page
                    names.setdefault(slug, page["name"] or slug)
                    for fs, fn in page["family"].items():
                        if split_slug(fs)[0] is not None:
                            names.setdefault(fs, fn)
                if i % 50 == 0 or i == len(slugs):
                    print(f"  {i}/{len(slugs)} pages", file=sys.stderr)

    print(f"Pass 1: {len(seeds)} Pokedex entries", file=sys.stderr)
    run(seeds)
    round_ = 2
    while True:
        todo = sorted(s for s in names if s not in pages and s not in failed)
        if not todo:
            break
        print(f"Pass {round_}: {len(todo)} forms/evolutions found", file=sys.stderr)
        run(todo)
        round_ += 1

    per_pokemon = []
    edges = {}
    plain = {split_slug(s)[0] for s in pages if s.isdigit()}

    def group_of(slug):
        g = form_group(slug)
        return "normal" if g == "other" and split_slug(slug)[0] not in plain else g

    for slug in sorted(pages, key=lambda s: (split_slug(s)[0], group_of(s) != "normal", s)):
        page = pages[slug]
        per_pokemon.append({
            "slug": slug, "name": names.get(slug) or slug, "group": group_of(slug),
            "dex": split_slug(slug)[0], "url": f"{BASE}/pokemon/{slug}",
            "rankings": page["rankings"] or [],
            "unranked_modes": page["unranked"] or [],
        })
        for e in page["edges"]:
            edges[(e["from"], e["to"])] = {"from": e["from"], "to": e["to"],
                                           "requires": e["requires"]}
    return {
        "source": BASE, "tier_order_best_to_worst": TIER_ORDER,
        "scraped_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pages_scraped": len(pages), "pages_failed": failed,
        "rankings": group_rankings(per_pokemon),
        "per_pokemon": per_pokemon,
        "evolutions": list(edges.values()),
    }


def build(query, fetch, wanted_groups):
    start = resolve(query, fetch)
    start_page = parse_page(fetch.get(f"/pokemon/{start}"))

    edges = start_page["edges"]
    dexes = {split_slug(start)[0]}
    for e in edges:
        dexes |= {split_slug(e["from"])[0], split_slug(e["to"])[0]}

    # every member of the family (evolutions + forms) -> display name
    members = {}
    for e in edges:
        members[e["from"]] = e["from_name"]
        members[e["to"]] = e["to_name"]
    for slug, name in start_page["family"].items():
        if split_slug(slug)[0] in dexes:          # drops unrelated links
            members[slug] = name
    members.setdefault(start, start_page["name"] or start)

    keep = {s: n for s, n in members.items()
            if form_group(s) == "normal" or form_group(s) in wanted_groups}

    # Download every member's page up front, a few at a time (cache hits are free).
    todo = [s for s in keep if s != start]
    if todo:
        with ThreadPoolExecutor(max_workers=min(WORKERS, len(todo))) as ex:
            list(ex.map(lambda s: fetch.get(f"/pokemon/{s}"), todo))

    return assemble(query, start, keep, edges,
                    lambda slug: start_page if slug == start
                    else parse_page(fetch.get(f"/pokemon/{slug}")))


def assemble(query, start, keep, edges, page_of):
    """Rankings + evolution tree for one line.

    keep: {slug: name}; edges: [{from, to, requires}]; page_of(slug) ->
    {"rankings": [...] | None, "unranked": [...]}.
    """
    # species the site only lists as forms (Shellos) count as "normal"
    plain = {split_slug(s)[0] for s in keep if s.isdigit()}

    def grp(slug):
        g = form_group(slug)
        return "normal" if g == "other" and split_slug(slug)[0] not in plain else g

    per_pokemon = []
    warned = set()
    for slug in sorted(keep, key=lambda s: (split_slug(s)[0], grp(s) != "normal", s)):
        page = page_of(slug)
        rankings = page["rankings"]
        if rankings is None:
            print(f"warning: no 'Tier Ranking' section found on /pokemon/{slug}",
                  file=sys.stderr)
            rankings, page["unranked"] = [], []
        for r in rankings:
            if r["tier"] not in TIER_INDEX and r["tier"] not in warned:
                warned.add(r["tier"])
                print(f"warning: unknown tier '{r['tier']}' sorts last; add it "
                      "to TIER_ORDER", file=sys.stderr)
        per_pokemon.append({
            "slug": slug, "name": keep[slug], "group": grp(slug),
            "dex": split_slug(slug)[0], "url": f"{BASE}/pokemon/{slug}",
            "rankings": rankings, "unranked_modes": page["unranked"] or [],
        })

    rankings_by_group = group_rankings(per_pokemon)

    # --- evolution tree ------------------------------------------------------
    # Mega/Primal rows in the chart are forms, not evolutions -> excluded here.
    nodes = {}
    for slug, name in keep.items():
        if grp(slug) in ("normal", "regional"):
            nodes[slug] = {"slug": slug, "name": name,
                           "url": f"{BASE}/pokemon/{slug}",
                           "requires": None, "evolves_to": [], "forms": []}
    has_parent = set()
    for e in edges:
        if e["from"] in nodes and e["to"] in nodes:
            nodes[e["to"]]["requires"] = e["requires"]
            if e["to"] not in {c["slug"] for c in nodes[e["from"]]["evolves_to"]}:
                nodes[e["from"]]["evolves_to"].append(nodes[e["to"]])
            has_parent.add(e["to"])
    for slug, name in keep.items():
        g = grp(slug)
        if g in ("normal", "regional"):
            continue
        owner = nodes.get(base_slug(slug)) or nodes.get(str(split_slug(slug)[0]))
        if owner:
            owner["forms"].append({"slug": slug, "name": name, "group": g,
                                   "url": f"{BASE}/pokemon/{slug}"})
    # regional nodes are also forms of their plain Pokemon
    for slug, node in nodes.items():
        if grp(slug) == "regional" and slug not in has_parent:
            owner = nodes.get(str(split_slug(slug)[0]))
            if owner:
                owner["forms"].append({"slug": slug, "name": node["name"],
                                       "group": "regional", "url": node["url"]})
    roots = [n for s, n in nodes.items() if s not in has_parent
             and grp(s) == "normal"]
    roots += [n for s, n in nodes.items() if s not in has_parent
              and grp(s) == "regional"]

    return {
        "query": query, "resolved_slug": start, "source": BASE,
        "tier_order_best_to_worst": TIER_ORDER,
        "evolution_tree": roots,
        "rankings": rankings_by_group,
        "per_pokemon": per_pokemon,
    }


def load_snapshot(path):
    """all_rankings.json (written by --all) -> dict, or None if absent/unreadable."""
    try:
        snap = json.loads(Path(path).read_text(encoding="utf-8"))
        return snap if snap.get("per_pokemon") else None
    except (OSError, ValueError):
        return None


TYPES = ["normal", "fighting", "flying", "poison", "ground", "rock", "bug", "ghost", "steel", "fire", "water",
         "grass", "electric", "psychic", "ice", "dragon", "dark", "fairy"]
OFF_TYPE_TOP = 50     # only off-type attackers this high in a type's list are kept


def add_off_type_rankings(snap, fetch, top=OFF_TYPE_TOP):
    """Add the per-type list rankings that a Pokémon's own page doesn't show.

    A page only has tiles for the Pokémon's own types, but GO Hub's best-per-type lists also include
    "off-type attackers": Mega Mewtwo Y (Psychic) is #2 in Ghost because it has Shadow Ball. Those rows
    are added, marked "off_type", when they are in the top `top` of that list; lower ones (Rhyperior is
    #62 in Water) would only be noise. Rows added earlier are replaced, so this can be re-run.
    Returns (rows added, types whose list could not be read).
    """
    by_slug = {p["slug"]: p for p in snap["per_pokemon"]}
    for p in snap["per_pokemon"]:
        p["rankings"] = [r for r in p["rankings"] if not r.get("off_type")]
    added, failed = 0, []
    for t in TYPES:
        try:
            rows = movesets.parse_type_list(fetch.get(f"/pokemon-list/best-per-type/{t}"))
        except (SystemExit, requests.RequestException):
            rows = None
        if not rows:
            failed.append(t)
            continue
        mode = f"{t.capitalize()}-type"
        for r in rows:
            p = by_slug.get(r["slug"])
            if r["rank"] > top or p is None or any(x["mode"] == mode for x in p["rankings"]):
                continue
            p["rankings"].append({"mode": mode, "tier": r["tier"], "rank": r["rank"], "off_type": True})
            added += 1
    snap["rankings"] = group_rankings(snap["per_pokemon"])
    return added, failed


def refresh_lists(path, cache_dir, delay=0.2):
    """Re-read only the 18 per-type lists and update the off-type rankings in an existing snapshot."""
    path = Path(path)
    snap = load_snapshot(path)
    if snap is None:
        return False, f"can't read {path}"
    added, failed = add_off_type_rankings(snap, Fetcher(cache_dir, delay, refresh=True, store=False))
    if failed:
        return False, f"kept old data: couldn't read the list for {', '.join(failed)}"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(snap, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return True, f"{added} off-type rankings (top {OFF_TYPE_TOP} of a list)"


def unnamed(snap):
    """Slugs saved without a real name: empty, the slug itself, or the site's generic "Pokémon" heading."""
    return [p["slug"] for p in snap["per_pokemon"]
            if not p.get("name") or p["name"] == p["slug"] or norm(p["name"]) == "pokemon"]


def refresh_snapshot(path, cache_dir, workers=4, delay=0.2):
    """Re-scrape the whole site and replace the snapshot file atomically.

    Returns (ok, message). The old file is kept if the new scrape looks
    incomplete (fewer than 90% of the old page count, >5% of pages failed, or
    fewer than 90% of the old number of rankings, or more than 1% of the Pokémon
    without a name, which is what a change in the site's markup looks like), so a
    bad night never wipes the data.
    """
    path = Path(path)
    old = load_snapshot(path)
    fetch = Fetcher(cache_dir, delay, refresh=True, store=False)
    new = build_all(fetch, workers)
    added, list_failures = add_off_type_rankings(new, fetch)
    n, failed = new["pages_scraped"], len(new["pages_failed"])
    old_n = old.get("pages_scraped", 0) if old else 0
    if n < 0.9 * old_n or failed > 0.05 * max(n, 1):
        return False, f"kept old data: new scrape has {n} pages ({failed} failed), old had {old_n}"
    if list_failures:
        return False, f"kept old data: couldn't read the per-type list for {', '.join(list_failures)}"
    count = lambda snap: sum(len(p["rankings"]) for p in snap["per_pokemon"])
    new_r, old_r = count(new), count(old) if old else 0
    if new_r < 0.9 * old_r:
        return False, (f"kept old data: new scrape found {new_r} rankings, old had {old_r}; "
                       "the site's markup may have changed (see parse_rankings in pogo_tiers.py)")
    nameless = unnamed(new)
    if len(nameless) > 0.01 * len(new["per_pokemon"]):
        return False, (f"kept old data: {len(nameless)} of {len(new['per_pokemon'])} Pokémon have no name "
                       f"(e.g. {', '.join(nameless[:5])}); the site's markup may have changed (see page_name in pogo_tiers.py)")
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(new, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return True, f"saved {n} pages, {new_r} rankings, {added} of them off-type list rankings ({failed} failed)"


def build_from_snapshot(snap, query, wanted_groups):
    """Same result as build(), but read from an --all snapshot: no network."""
    by_slug = {p["slug"]: p for p in snap["per_pokemon"]}
    q = query.strip()
    if re.fullmatch(r"\d+", q):
        start = str(int(q))
    elif re.fullmatch(r"\d+-[A-Za-z0-9_]+", q):
        start = q
    else:
        names = {}
        for p in snap["per_pokemon"]:
            if p["slug"].isdigit():
                names.setdefault(norm(p["name"]), p["slug"])
            elif p["group"] == "normal":     # species the site only lists as forms
                base = re.sub(r"\s*\(.*\)\s*$", "", p["name"])
                names.setdefault(norm(base), p["slug"])
        key = norm(q)
        if key not in names:
            close = sorted(n for n in names if key and key in n)[:8]
            hint = f" Did you mean one of: {', '.join(close)}?" if close else ""
            sys.exit(f"Couldn't find '{query}'.{hint} "
                     "You can also pass the Pokedex number (e.g. 4).")
        start = names[key]
    if start not in by_slug:
        sys.exit(f"'{query}' isn't in the saved rankings (try 'Refresh data').")

    edges = snap.get("evolutions", [])
    adj = {}
    for e in edges:
        a, b = split_slug(e["from"])[0], split_slug(e["to"])[0]
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    dexes, todo = set(), [split_slug(start)[0]]
    while todo:
        d = todo.pop()
        if d not in dexes:
            dexes.add(d)
            todo.extend(adj.get(d, ()))

    keep = {p["slug"]: p["name"] for p in snap["per_pokemon"]
            if p["dex"] in dexes
            and (p["group"] == "normal" or p["group"] in wanted_groups)}
    keep.setdefault(start, by_slug[start]["name"])
    line_edges = [e for e in edges
                  if split_slug(e["from"])[0] in dexes and split_slug(e["to"])[0] in dexes]
    return assemble(query, start, keep, line_edges,
                    lambda slug: {"rankings": by_slug[slug]["rankings"],
                                  "unranked": by_slug[slug]["unranked_modes"]})


def print_report(result):
    for group in ["normal"] + FORM_GROUPS:
        items = result["rankings"].get(group)
        if not items:
            continue
        print(f"\n=== {group.upper()} (best -> worst) ===")
        name_w = max(len(i["pokemon"]) for i in items)
        mode_w = max(len(i["mode"]) for i in items)
        for i in items:
            rank = f"#{i['rank']}" if i["rank"] is not None else ""
            print(f"{i['position']:>3}. {i['pokemon']:<{name_w}}  "
                  f"{i['mode']:<{mode_w}}  {i['tier']:<2} {rank}")

    def walk(node, depth=0):
        req = f"  [{node['requires']}]" if node["requires"] else ""
        forms = f"  (forms: {', '.join(f['name'] for f in node['forms'])})" if node["forms"] else ""
        print("  " * depth + ("└─ " if depth else "") + node["name"] + req + forms)
        for c in node["evolves_to"]:
            walk(c, depth + 1)

    print("\n=== EVOLUTION TREE ===")
    for root in result["evolution_tree"]:
        walk(root)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pokemon", nargs="?",
                    help="name (e.g. charmander) or Pokedex number")
    ap.add_argument("--all", action="store_true",
                    help="scrape every Pokemon page and save only the rankings "
                         "(default output: all_rankings.json; HTML is not cached)")
    ap.add_argument("--workers", type=int, default=8,
                    help="parallel downloads for --all (default 8)")
    ap.add_argument("--keep-html", action="store_true",
                    help="with --all, also cache the raw pages in data/cache/")
    ap.add_argument("--forms", default="all",
                    help="'all' (default), 'none', or a comma list of: "
                         + ", ".join(FORM_GROUPS))
    ap.add_argument("-o", "--output", help="JSON output path "
                    "(default: <pokemon>_tiers.json)")
    ap.add_argument("--cache-dir",
                    default=str(Path(__file__).resolve().parent.parent / "data" / "cache"),
                    help="where downloaded pages are cached (default: next to this script)")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY,
                    help="seconds to wait between request starts (default 0 = all at once)")
    ap.add_argument("--offline", action="store_true",
                    help="use only cached pages, never touch the network")
    ap.add_argument("--refresh", action="store_true",
                    help="ignore the cache and re-download pages")
    args = ap.parse_args()

    if args.forms == "all":
        wanted = set(FORM_GROUPS)
    elif args.forms == "none":
        wanted = set()
    else:
        wanted = {g.strip().lower() for g in args.forms.split(",") if g.strip()}
        bad = wanted - set(FORM_GROUPS)
        if bad:
            ap.error(f"unknown form group(s): {', '.join(sorted(bad))}")

    if args.all:
        fetch = Fetcher(args.cache_dir, args.delay, args.offline, args.refresh,
                        store=args.keep_html)
        result = build_all(fetch, args.workers)
        out = Path(args.output or DEFAULT_SNAPSHOT)
        out.write_text(json.dumps(result, separators=(",", ":"), ensure_ascii=False),
                       encoding="utf-8")
        ranked = sum(1 for p in result["per_pokemon"] if p["rankings"])
        print(f"Scraped {result['pages_scraped']} pages ({ranked} with rankings), "
              f"{len(result['pages_failed'])} failed")
        for slug, err in result["pages_failed"].items():
            print(f"  failed: {slug}: {err}", file=sys.stderr)
        print(f"Saved {out} ({out.stat().st_size / 1024:.0f} KB)")
        return
    if not args.pokemon:
        ap.error("give a Pokemon name/number, or use --all")

    fetch = Fetcher(args.cache_dir, args.delay, args.offline, args.refresh)
    result = build(args.pokemon, fetch, wanted)

    out = Path(args.output or f"{re.sub(r'[^a-z0-9]+', '_', args.pokemon.lower())}_tiers.json")
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print_report(result)
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
