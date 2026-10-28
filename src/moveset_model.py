"""
Raid moveset calculator: which fast + charged move is best when the boss takes a given
effectiveness multiplier from each move type?

Damage per hit      0.5 * power * K * same-type bonus * effectiveness + 0.5
Cycle               a charged move needs charged_energy / fast_energy fast moves first (a 100-energy
                    move needs whole fast moves, since a full bar is capped)
DPS                 (n * fast_damage + charged_damage) / (n * fast_time + charged_time)

K is the attacker's Attack divided by the boss's Defense. It differs per Pokémon (level,
Shadow and Mega boosts) so it is fitted to GO Hub's own neutral-boss numbers for that Pokémon
(fit_k). eDPS is DPS reduced by a fixed time penalty per faint; because the Pokémon's survival
time doesn't depend on its own damage, eDPS = DPS * f with one constant f per Pokémon.

This is an independent implementation of the public Dialgadex-style formulas, checked against
GO Hub's published numbers (see validate_model.py), not a copy of their code.
"""
import math

STAB = 1.2
SUPER, RESIST, IMMUNE = 1.6, 0.625, 0.625 * 0.625   # Pokémon GO's effectiveness steps

TYPES = ["normal", "fire", "water", "electric", "grass", "ice", "fighting", "poison", "ground",
         "flying", "psychic", "bug", "rock", "ghost", "dragon", "dark", "steel", "fairy"]
# attacker -> {defender: step}; 2 = super effective, 0.5 = resisted, 0 = no effect (GO: double resist)
_CHART = {
    "normal": {"rock": .5, "ghost": 0, "steel": .5},
    "fire": {"fire": .5, "water": .5, "grass": 2, "ice": 2, "bug": 2, "rock": .5, "dragon": .5, "steel": 2},
    "water": {"fire": 2, "water": .5, "grass": .5, "ground": 2, "rock": 2, "dragon": .5},
    "electric": {"water": 2, "electric": .5, "grass": .5, "ground": 0, "flying": 2, "dragon": .5},
    "grass": {"fire": .5, "water": 2, "grass": .5, "poison": .5, "ground": 2, "flying": .5, "bug": .5,
              "rock": 2, "dragon": .5, "steel": .5},
    "ice": {"fire": .5, "water": .5, "grass": 2, "ice": .5, "ground": 2, "flying": 2, "dragon": 2, "steel": .5},
    "fighting": {"normal": 2, "ice": 2, "poison": .5, "flying": .5, "psychic": .5, "bug": .5, "rock": 2,
                 "ghost": 0, "dark": 2, "steel": 2, "fairy": .5},
    "poison": {"grass": 2, "poison": .5, "ground": .5, "rock": .5, "ghost": .5, "steel": 0, "fairy": 2},
    "ground": {"fire": 2, "electric": 2, "grass": .5, "poison": 2, "flying": 0, "bug": .5, "rock": 2, "steel": 2},
    "flying": {"electric": .5, "grass": 2, "fighting": 2, "bug": 2, "rock": .5, "steel": .5},
    "psychic": {"fighting": 2, "poison": 2, "psychic": .5, "dark": 0, "steel": .5},
    "bug": {"fire": .5, "grass": 2, "fighting": .5, "poison": .5, "flying": .5, "psychic": 2, "ghost": .5,
            "dark": 2, "steel": .5, "fairy": .5},
    "rock": {"fire": 2, "ice": 2, "fighting": .5, "ground": .5, "flying": 2, "bug": 2, "steel": .5},
    "ghost": {"normal": 0, "psychic": 2, "ghost": 2, "dark": .5},
    "dragon": {"dragon": 2, "steel": .5, "fairy": 0},
    "dark": {"fighting": .5, "psychic": 2, "ghost": 2, "dark": .5, "fairy": .5},
    "steel": {"fire": .5, "water": .5, "electric": .5, "ice": 2, "rock": 2, "steel": .5, "fairy": 2},
    "fairy": {"fire": .5, "fighting": 2, "poison": .5, "dragon": 2, "dark": 2, "steel": .5},
}


def effectiveness(attack_type, defender_types):
    """GO's multiplier for one move type against a (possibly dual-typed) defender."""
    mult = 1.0
    for d in defender_types:
        step = _CHART.get(attack_type, {}).get(d, 1)
        mult *= SUPER if step == 2 else RESIST if step == .5 else IMMUNE if step == 0 else 1.0
    return mult


def multipliers_for_boss(*boss_types):
    return {t: effectiveness(t, boss_types) for t in TYPES}


def tier_multipliers(featured_type, step):
    """The tier view: the featured type hits at `step` (1, 1.6 or 2.56), every other type at 1."""
    return {t: (step if t == featured_type else 1.0) for t in TYPES}


def _secs(ms):
    """Move durations are whole half-seconds in raids."""
    return max(0.5, round(ms / 1000 * 2) / 2)


def hit(move, k, mult):
    return 0.5 * move["power"] * k * (STAB if move.get("hasStab") else 1.0) * mult + 0.5


# Calibrated against GO Hub's published numbers (validate_model.py): the model above is slightly
# high for 100-energy charged moves and slightly low for 33-energy ones.
BAR_CORRECTION = {1: 0.9585, 2: 1.0062, 3: 1.0217}      # keyed by charged-move size: 100 / 50 / 33 energy


def _bars(charged):
    e = charged["energy"]
    return 1 if e >= 100 else 2 if e >= 50 else 3


def cycle_dps(fast, charged, k, mults=None):
    """DPS of one fast + charged moveset; mults maps move type -> effectiveness (default 1)."""
    mults = mults or {}
    if fast["energy"] <= 0:
        return 0.0
    n = charged["energy"] / fast["energy"]
    if charged["energy"] >= 100:
        n = math.ceil(n - 1e-9)           # a full bar is capped at 100, so overflow energy is wasted
    t_fast, t_charged = _secs(fast["duration"]), _secs(charged["duration"])
    damage = n * hit(fast, k, mults.get(fast["type"], 1.0)) + hit(charged, k, mults.get(charged["type"], 1.0))
    return BAR_CORRECTION[_bars(charged)] * damage / (n * t_fast + t_charged)


UNUSABLE = {"Frustration"}      # Shadow-only; GO Hub scores it as zero damage


def split_moves(props):
    moves = [m for m in props["moves"] if m["name"] not in UNUSABLE]
    return [m for m in moves if m["isQuickMove"]], [m for m in moves if not m["isQuickMove"]]


def fit_k(props):
    """Scale K that best reproduces GO Hub's neutral DPS for every one of this Pokémon's movesets."""
    by_id = {m["id"]: m for m in props["moves"]}
    rows = [(by_id[r["qm"]["id"]], by_id[r["cm"]["id"]], r["dps"]) for r in props["results"]
            if r["qm"]["id"] in by_id and r["cm"]["id"] in by_id and r["dps"] > 0.5
            and r["cm"]["name"] not in UNUSABLE]
    if not rows:
        return None

    def err(k):
        return sum(math.log(cycle_dps(f, c, k) / d) ** 2 for f, c, d in rows)

    lo, hi = 0.05, 20.0
    for _ in range(70):                       # golden-section search on a unimodal error
        a, b = lo + (hi - lo) * 0.382, lo + (hi - lo) * 0.618
        lo, hi = (lo, b) if err(a) < err(b) else (a, hi)
    return (lo + hi) / 2


def edps_factor(props):
    """eDPS / DPS for this Pokémon (median across its movesets)."""
    ratios = sorted(r["score"] / r["dps"] for r in props["results"]
                    if r["dps"] > 0.5 and r["cm"]["name"] not in UNUSABLE)
    return ratios[len(ratios) // 2] if ratios else None


def rank_movesets(props, k, f, mults=None, allow_legacy=True):
    """[(fast, charged, dps, edps)] best first for the given effectiveness map."""
    fast, charged = split_moves(props)
    out = []
    for fm in fast:
        for cm in charged:
            if not allow_legacy and (fm["isLegacy"] or cm["isLegacy"]):
                continue
            d = cycle_dps(fm, cm, k, mults)
            out.append((fm, cm, d, d * f))
    out.sort(key=lambda r: -r[2])
    return out


# ---------------------------------------------------------------------------------------------
# compact dataset (data/movesets.json) and the three-tier view
# ---------------------------------------------------------------------------------------------
STEPS = (1.0, 1.6, 2.56)                  # neutral, super effective, double super effective
MAX_FIT_ERROR = 8.0                       # % mean DPS error above which the tier view is hidden


def build_dataset(props_by_slug, fit_error):
    """Compact data for the web app. Move stats are the same for every Pokémon, so they are stored once;
    the same-type bonus is recomputed from the Pokémon's types, so only legacy flags are per Pokémon."""
    moves, pokemon = {}, {}
    for slug, props in sorted(props_by_slug.items()):
        k, f = fit_k(props), edps_factor(props)
        if k is None or f is None:
            continue
        pk = props["pokemon"]
        types = [t for t in (pk["type1"], pk.get("type2")) if t]
        entry = []
        for m in props["moves"]:
            if m["name"] in UNUSABLE:
                continue
            moves[str(m["id"])] = [m["name"], m["type"], m["power"], m["energy"], m["duration"], int(m["isQuickMove"])]
            entry.append([m["id"], int(bool(m["isLegacy"]))])
        pokemon[slug] = {"t": types, "k": round(k, 4), "f": round(f, 4),
                         "e": round(fit_error.get(slug, 99.0), 1), "m": sorted(entry)}
    return {"moves": dict(sorted(moves.items(), key=lambda kv: int(kv[0]))), "pokemon": pokemon}


def entry_props(dataset, slug):
    """The dataset entry as the move dicts that cycle_dps / rank_movesets expect."""
    e = dataset["pokemon"][slug]
    out = []
    for move_id, legacy in e["m"]:
        name, mtype, power, energy, duration, fast = dataset["moves"][str(move_id)]
        out.append({"id": move_id, "name": name, "type": mtype, "power": power, "energy": energy,
                    "duration": duration, "isQuickMove": fast, "isLegacy": legacy,
                    "hasStab": mtype in e["t"] and name != "Hidden Power"})
    return {"moves": out}, e["k"], e["f"]


def move_types(dataset, slug):
    """The types of the Pokémon's usable moves, i.e. the choices for the 'boss is weak to ...' view."""
    props, _, _ = entry_props(dataset, slug)
    return sorted({m["type"] for m in props["moves"]})


def tier_view(dataset, slug, featured_type, allow_legacy=True):
    """Best movesets at 1x / 1.6x / 2.56x for `featured_type`; other types hit at 1x.
    -> {step: [(fast, charged, edps), ...top 2]}"""
    props, k, f = entry_props(dataset, slug)
    out = {}
    for step in STEPS:
        ranked = rank_movesets(props, k, f, tier_multipliers(featured_type, step), allow_legacy)
        out[step] = [(fm["name"], cm["name"], round(e, 2)) for fm, cm, _, e in ranked[:2]]
    return out
