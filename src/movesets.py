"""
Moveset data from a GO Hub Pokémon page.

Each page embeds, for its Pokémon: the types and base stats, every move it can
learn (power, energy, duration, legacy flag, same-type flag) and GO Hub's own
neutral-boss ranking of every fast x charged combination (DPS, TDO, eDPS). This
module pulls that block out of the page's Next.js payload. The calculator that
re-ranks movesets for other effectiveness multipliers is in moveset_model.py.
"""
import json
import re

_FLIGHT_RE = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', re.S)
_REF_RE = re.compile(r"^\$[0-9a-f]+:0:props:initialResults:(\d+):(qm|cm)$")


def _payload(html):
    """The page's React Server Components payload as one string."""
    out = []
    for chunk in _FLIGHT_RE.findall(html):
        try:
            out.append(json.loads('"' + chunk + '"'))     # the chunks are JSON string literals
        except ValueError:
            pass
    return "".join(out)


def parse_moveset_props(html):
    """-> {"pokemon": {...}, "moves": [...], "results": [...]} or None if the page has no table.

    results are GO Hub's neutral (25,000 HP dummy boss, level 40) rankings: one entry per
    fast/charged pair with qm / cm (move id, name, type, isLegacy), dps, tdo and score (eDPS).
    """
    blob = _payload(html)
    first = blob.find('"isQuickMove"')
    if first < 0:
        return None
    start = blob.rfind('[{"id":', 0, first)
    dec = json.JSONDecoder()
    try:
        moves, end = dec.raw_decode(blob[start:])
        rest = blob[start + end:]
        pk_at = rest.index('"pokemon":') + len('"pokemon":')
        pokemon, _ = dec.raw_decode(rest[pk_at:])
        res_at = rest.index('"initialResults":') + len('"initialResults":')
        results, _ = dec.raw_decode(rest[res_at:])
    except (ValueError, json.JSONDecodeError):
        return None

    # the payload de-duplicates repeated move objects: "$ee:0:props:initialResults:0:cm"
    def resolve(value):
        for _ in range(5):
            m = _REF_RE.match(value) if isinstance(value, str) else None
            if not m:
                break
            value = results[int(m.group(1))][m.group(2)]
        return value

    for r in results:
        r["qm"], r["cm"] = resolve(r["qm"]), resolve(r["cm"])
    return {"pokemon": pokemon, "moves": moves, "results": results}
