#!/usr/bin/env python3
"""
Local web UI for pogo_tiers.py  ->  http://127.0.0.1:8000

    python pogo_ui.py                 # start and open the browser
    python pogo_ui.py --port 9000     # different port
    python pogo_ui.py --no-browser    # don't auto-open a tab

Runs only on your own machine (bound to 127.0.0.1). Type a Pokemon name or
Pokedex number, pick which forms you want, and it shows the tier rankings for
the whole evolution line, one tab per form group, plus the evolution tree.

Searches read all_rankings.json, so they are instant and need no network. Make
or update that file with `python src/refresh_data.py` (the hosted/--nightly mode does
it automatically every night). The UI itself never scrapes anything.
"""
import argparse
import json
import os
import sys
import threading
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))   # find pogo_tiers.py next to this file
import pogo_tiers as pt  # noqa: E402
import ivrank  # noqa: E402

LOCK = threading.Lock()      # one scrape at a time -> stays polite to the site
CONFIG = {}


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
def asof_text():
    snap = get_snapshot()
    when = (snap or {}).get("scraped_at", "")
    return f"· Rankings as of {when[:10]}" if when else ""


def get_snapshot():
    """all_rankings.json parsed once, and re-read if the file changes."""
    path = Path(CONFIG["snapshot"])
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    if CONFIG.get("snapshot_mtime") != mtime:
        CONFIG["snapshot_data"] = pt.load_snapshot(path)
        CONFIG["snapshot_mtime"] = mtime
    return CONFIG.get("snapshot_data")


def run_search(q, forms, ivs=None, cap=ivrank.DEFAULT_CAP):
    if forms == "all":
        wanted = set(pt.FORM_GROUPS)
    elif forms == "none":
        wanted = set()
    else:
        wanted = {g.strip().lower() for g in forms.split(",") if g.strip()}
        bad = wanted - set(pt.FORM_GROUPS)
        if bad:
            raise ValueError(f"unknown form group(s): {', '.join(sorted(bad))}")

    snap = get_snapshot()
    if snap is None:
        sys.exit("No rankings data yet. Run `python src/refresh_data.py` once, then reload.")
    with LOCK:
        result = pt.build_from_snapshot(snap, q, wanted)
    result["query"] = q
    if ivs:
        add_ivs(result, q, ivs, cap)
    return result


LEAGUE_MODES = {"Great League": "great", "Ultra League": "ultra", "Master League": "master"}


def add_ivs(result, q, ivs, cap):
    """Attach IV ranks: result['iv'] (the searched line) and an 'iv' entry on league rows."""
    atk, dfn, sta = ivs
    result["ivs"] = {"values": [atk, dfn, sta], "cap": cap}
    try:
        result["iv"] = run_iv(q, atk, dfn, sta, cap)["results"]
    except ValueError as e:
        result["iv"] = []
        result["ivs"]["error"] = str(e)
    cache = {}

    def ranks_for(name):
        if name not in cache:
            # shadow Pokémon rank like their normal form (CP ignores the shadow multipliers)
            base = name[7:] if name.startswith("Shadow ") else name
            hit = [m for m in ivrank.find_mons(base) if m["name"].lower() == base.lower()]
            cache[name] = ivrank.rank_ivs(hit[0], atk, dfn, sta, cap) if hit else None
        return cache[name]

    for rows in result["rankings"].values():
        for r in rows:
            key = LEAGUE_MODES.get(r["mode"])
            ranks = ranks_for(r["pokemon"]) if key else None
            if ranks:
                x = ranks[key]
                r["iv"] = {"rank": x["rank"], "level": x["level"], "cp": x["cp"],
                           "percent": x["percent"], "capped": x["capped"]}


def run_iv(q, atk, dfn, sta, cap):
    """PvP IV ranks for a Pokémon (and every stage of its line)."""
    mons = ivrank.find_mons(q)
    if not mons:
        raise ValueError(f"No Pokémon matches '{q}' in the IV data.")
    if len(mons) > 6:
        raise ValueError(f"'{q}' matches {len(mons)} Pokémon; be more specific.")
    seen, out = set(), []
    for base in mons:
        for m in ivrank.line_of(base):
            if m["id"] in seen:
                continue
            seen.add(m["id"])
            out.append({"name": m["name"], "id": m["id"] % 10000,
                        "base": [m["atk"], m["def"], m["sta"]],
                        "leagues": list(ivrank.rank_ivs(m, atk, dfn, sta, cap).values()),
                        "selected": m["id"] == base["id"]})
    return {"query": q, "ivs": [atk, dfn, sta], "cap": cap, "results": out}


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def parse_ivs(qs):
    """(atk, def, hp) and level cap from the query string, or (None, cap) if no IVs given."""
    get = lambda k, d="": (qs.get(k) or [d])[0].strip()
    raw = [get("a"), get("d"), get("s")]
    if not any(raw):
        return None, ivrank.DEFAULT_CAP
    try:
        ivs = tuple(int(v) for v in raw)
        cap = int(get("cap", str(ivrank.DEFAULT_CAP)))
    except ValueError:
        raise ValueError("Fill in all three IVs (Atk, Def, HP) as whole numbers from 0 to 15.")
    if not all(0 <= v <= 15 for v in ivs):
        raise ValueError("IVs must be between 0 and 15.")
    if cap not in ivrank.LEVEL_CAPS:
        raise ValueError(f"Level cap must be one of {', '.join(map(str, ivrank.LEVEL_CAPS))}.")
    return ivs, cap


class Handler(BaseHTTPRequestHandler):
    server_version = "PogoTiers/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[ui] " + (fmt % args) + "\n")

    def _send(self, code, body, ctype):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False),
                   "application/json; charset=utf-8")

    def _host_ok(self):
        # Refuse requests whose Host isn't localhost (DNS-rebinding guard).
        # Not applicable when deliberately hosted on a public domain.
        if CONFIG.get("hosted"):
            return True
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in ("127.0.0.1", "localhost", "::1")

    def do_GET(self):
        if not self._host_ok():
            return self._json(403, {"error": "forbidden host"})
        url = urlparse(self.path)
        if url.path == "/":
            page = (INDEX_HTML.replace("__GROUPS__", json.dumps(pt.FORM_GROUPS))
                    .replace("__ASOF__", asof_text()))
            return self._send(200, page, "text/html; charset=utf-8")
        if url.path == "/api/search":
            qs = parse_qs(url.query)
            q = (qs.get("q") or [""])[0].strip()
            forms = (qs.get("forms") or ["all"])[0]
            if not q:
                return self._json(400, {"error": "Type a Pokémon name or number."})
            try:
                ivs, cap = parse_ivs(qs)
                return self._json(200, run_search(q, forms, ivs, cap))
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            except SystemExit as e:             # the scraper reports errors this way
                return self._json(502, {"error": str(e.code)})
            except requests.RequestException as e:
                return self._json(502, {"error": f"Network error: {e}"})
            except Exception as e:              # keep the server alive
                return self._json(500, {"error": f"{type(e).__name__}: {e}"})
        if url.path == "/api/ivnames":
            try:
                names = sorted({m["name"] for m in ivrank.load_data()["mons"]})
                return self._json(200, names)
            except Exception as e:
                return self._json(502, {"error": f"Couldn't load IV data: {e}"})
        if url.path == "/api/ivspreads":
            qs = parse_qs(url.query)
            get = lambda k, d="": (qs.get(k) or [d])[0].strip()
            try:
                mon = ivrank.find_exact(get("p"))
                if not mon:
                    raise ValueError(f"No Pokémon named '{get('p')}'.")
                league = get("league", "great")
                cap = int(get("cap", str(ivrank.DEFAULT_CAP)))
                rows = ivrank.all_spreads(mon, league, cap)
                line = [{"name": m["name"], "id": m["id"] % 10000}
                        for m in ivrank.line_of(mon)]
                return self._json(200, {
                    "name": mon["name"], "id": mon["id"] % 10000,
                    "base": [mon["atk"], mon["def"], mon["sta"]],
                    "league": league, "cap": cap, "line": line, "rows": rows,
                    "cp_cap": {k: c for k, _l, c in ivrank.LEAGUES}[league]})
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            except Exception as e:
                return self._json(500, {"error": f"{type(e).__name__}: {e}"})
        self._json(404, {"error": "not found"})


# --------------------------------------------------------------------------
# front end (single page, no external assets)
# --------------------------------------------------------------------------
INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GO Tier Lookup</title>
<style>
:root{
  --bg:#f6f7f9; --card:#ffffff; --text:#1b1f24; --muted:#667085; --line:#e4e7ec;
  --accent:#2563eb; --accent-text:#ffffff; --chip:#eef2f7;
  --t-s:#b45309; --t-a:#7c3aed; --t-b:#2563eb; --t-c:#0f766e; --t-d:#64748b; --t-f:#b91c1c;
}
@media (prefers-color-scheme: dark){
  :root{
    --bg:#0f1216; --card:#171b21; --text:#e8eaed; --muted:#9aa3af; --line:#2a313a;
    --accent:#60a5fa; --accent-text:#0b1220; --chip:#222932;
    --t-s:#f59e0b; --t-a:#a78bfa; --t-b:#60a5fa; --t-c:#2dd4bf; --t-d:#94a3b8; --t-f:#f87171;
  }
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:960px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:16px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
input[type=text]{flex:1;min-width:200px;padding:10px 12px;border:1px solid var(--line);
  border-radius:8px;background:var(--bg);color:var(--text);font:inherit}
button{padding:10px 16px;border-radius:8px;border:1px solid var(--line);background:var(--card);
  color:var(--text);font:inherit;cursor:pointer}
button.primary{background:var(--accent);color:var(--accent-text);border-color:var(--accent);font-weight:600}
button:disabled{opacity:.55;cursor:wait}
.ivrow{margin-top:12px}
.forms{margin-top:12px;display:flex;gap:6px 14px;flex-wrap:wrap;color:var(--muted);font-size:13px}
.forms label{display:flex;gap:5px;align-items:center;cursor:pointer}
#status{margin:0 0 16px;color:var(--muted)}
#status.error{color:var(--t-f)}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.tab{padding:6px 12px;border-radius:999px;border:1px solid var(--line);background:var(--card);
  font-size:13px;cursor:pointer}
.tab[aria-selected=true]{background:var(--accent);color:var(--accent-text);border-color:var(--accent);font-weight:600}
.tab small{opacity:.75;margin-left:4px}
.toolbar{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px}
select{padding:6px 8px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--text);font:inherit}
table{width:100%;border-collapse:collapse}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line)}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:600}
td.num{color:var(--muted);width:44px}
td.rank{font-variant-numeric:tabular-nums;color:var(--muted)}
.badge{display:inline-block;min-width:34px;text-align:center;padding:1px 8px;border-radius:6px;
  border:1.5px solid var(--tc,var(--t-d));color:var(--tc,var(--t-d));font-weight:700;font-size:13px}
.tier-s{--tc:var(--t-s)} .tier-a{--tc:var(--t-a)} .tier-b{--tc:var(--t-b)}
.tier-c{--tc:var(--t-c)} .tier-d{--tc:var(--t-d)} .tier-f{--tc:var(--t-f)}
.empty{color:var(--muted);padding:12px 0}
input.ivtext{width:190px;flex:none;min-width:0;padding:10px 12px;border:1px solid var(--line);
  border-radius:8px;background:var(--bg);color:var(--text);font:inherit}
.foot{color:var(--muted);font-size:12px;margin:24px 0 8px;text-align:center}
.foot a{color:inherit}
.hint{color:var(--muted);font-size:13px;margin:8px 0 0}
.hint.error{color:var(--t-f)}
.ivmon{margin:14px 0 0}
.ivmon h3{font-size:14px;margin:0 0 4px}
.ivmon h3 small{color:var(--muted);font-weight:400;margin-left:6px}
.ivmon.sel h3::after{content:"searched";margin-left:8px;font-size:11px;color:var(--accent);font-weight:600}
td.r1 b{font-size:15px}
.pct-hi{color:var(--t-c)} .pct-mid{color:var(--text)} .pct-lo{color:var(--t-f)}
td.dim{color:var(--muted)}
h2{font-size:16px;margin:0 0 10px}
.xlinks{font-size:12px;margin-left:8px;white-space:nowrap}
.xlinks a{color:var(--muted);text-decoration:none;margin-right:6px}
.xlinks a:hover{color:var(--accent);text-decoration:underline}
.spr{width:40px;height:40px;vertical-align:middle;margin-right:6px;flex:none}
.spr.big{width:48px;height:48px}
ul.tree,ul.tree ul{list-style:none;margin:0;padding-left:22px;border-left:2px solid var(--line)}
ul.tree{padding-left:0;border-left:0}
ul.tree li{margin:6px 0}
.chip{display:inline-block;background:var(--chip);border-radius:999px;padding:1px 9px;margin:2px 4px 2px 0;
  font-size:12px;color:var(--muted)}
.chip a{color:inherit;text-decoration:none}
.chip a:hover,.name a:hover{text-decoration:underline}
.name a{color:var(--text);font-weight:600;text-decoration:none}
details{margin-top:10px;color:var(--muted);font-size:13px}
details.ivsec{margin:0;border-top:1px solid var(--line);color:var(--text);font-size:15px}
details.ivsec:first-of-type{border-top:0}
details.ivsec>summary{cursor:pointer;padding:10px 0;font-weight:600}
details.ivsec>summary small{color:var(--muted);font-weight:400;margin-left:6px}
.ivbody{padding:0 0 12px}
.ivbody td.n{font-variant-numeric:tabular-nums}
.ivbody td.iv{font-variant-numeric:tabular-nums;font-weight:600}
.ivbody .more{margin-top:12px;display:flex;gap:8px;flex-wrap:wrap}
input.flt{flex:none;width:190px;min-width:0;padding:8px 10px;border:1px solid var(--line);
  border-radius:8px;background:var(--bg);color:var(--text);font:inherit}
@media (max-width:560px){ th:nth-child(1),td.num{display:none} }
</style>
</head>
<body>
<main>
  <h1>GO Tier Lookup</h1>
  <p class="sub">Tier rankings for a Pokémon, its whole evolution line and its forms — from db.pokemongohub.net, running only on your computer.</p>

  <div class="card">
    <form id="form" class="row">
      <input id="q" type="text" list="ivnames" placeholder="Pokémon name or Pokédex number (e.g. charmander, 4)" autocomplete="off" autofocus>
      <button id="go" class="primary" type="submit">Search</button>
    </form>
    <div class="row ivrow">
      <span class="hint" style="margin:0">Your IVs (optional):</span>
      <input id="ivs" class="ivtext" type="text" inputmode="text" placeholder="e.g. 11/2/3 or 11 2 3"
        aria-label="IVs: attack, defense, HP" autocomplete="off" form="form">
      <select id="ivcap" aria-label="Level cap" title="Highest level you'd power it to" form="form">
        <option value="40">Lv 40</option><option value="41">Lv 41</option>
        <option value="50" selected>Lv 50</option><option value="51">Lv 51</option>
      </select>
      <datalist id="ivnames"></datalist>
    </div>
    <div class="forms" id="forms"><span>Include forms:</span></div>
  </div>

  <p id="status" role="status"></p>
  <div id="results" hidden>
    <div class="card">
      <div class="toolbar">
        <h2 id="title" style="margin:0"></h2>
      </div>
      <div class="tabs" id="tabs" role="tablist"></div>
      <div class="toolbar">
        <label>Mode: <select id="mode"></select></label>
        <span id="count" style="color:var(--muted);font-size:13px"></span>
      </div>
      <div id="table"></div>
      <div id="unranked"></div>
    </div>
    <div class="card" id="ivpanel" hidden>
      <h2>PvP IV rank</h2>
      <p id="ivnote" class="hint"></p>
      <div id="ivout"></div>
    </div>
    <div class="card">
      <h2>Evolution tree</h2>
      <div id="tree"></div>
    </div>
    <div class="card" id="ivspreads-card">
      <h2>IV spreads</h2>
      <p class="hint" style="margin:0 0 6px">Every IV combination for each Pokémon in the line, best first. Expand one to see Great, Ultra and Master League.</p>
      <div id="ivspreads"></div>
    </div>
  </div>
</main>
<footer class="foot">Data: <a href="https://db.pokemongohub.net" target="_blank" rel="noopener">Pokémon GO Hub</a>
  · Sprites: <a href="https://github.com/PokeAPI/sprites" target="_blank" rel="noopener">PokeAPI</a>
  <span>__ASOF__</span></footer>

<script>
const GROUPS = __GROUPS__;
const LABELS = {normal:"Normal", shadow:"Shadow", regional:"Regional", "regional-shadow":"Regional Shadow",
  mega:"Mega", primal:"Primal", dynamax:"Dynamax", gigantamax:"Gigantamax", other:"Other forms"};
const $ = id => document.getElementById(id);
let RESULT = null, activeGroup = "normal", modeFilter = "";

const esc = s => String(s).replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const label = g => LABELS[g] || g;

// form-group checkboxes
for (const g of GROUPS) {
  const l = document.createElement("label");
  l.innerHTML = `<input type="checkbox" id="f-${esc(g)}" checked> ${esc(label(g))}`;
  $("forms").appendChild(l);
}

function setStatus(msg, cls) { $("status").textContent = msg; $("status").className = cls || ""; }

async function search() {
  const q = $("q").value.trim();
  if (!q) { setStatus("Type a Pokémon name or number.", "error"); return; }
  const checked = GROUPS.filter(g => $("f-" + g).checked);
  const forms = checked.length === GROUPS.length ? "all" : (checked.length ? checked.join(",") : "none");
  $("go").disabled = true;
  setStatus("Looking it up…");
  try {
    const params = {q, forms};
    const raw = $("ivs").value.trim();
    if (raw) {
      // "11/2/3", "11 2 3", "11,2,3" and "11-2-3" all work
      const parts = raw.split(/[\s/,\-.]+/).filter(Boolean);
      if (parts.length !== 3 || !parts.every(p => /^\d{1,2}$/.test(p) && +p <= 15)) {
        setStatus("IVs should be three numbers from 0 to 15, like 11/2/3 or 11 2 3.", "error");
        return;
      }
      Object.assign(params, {a: parts[0], d: parts[1], s: parts[2], cap: $("ivcap").value});
    }
    const res = await fetch("/api/search?" + new URLSearchParams(params));
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || res.statusText);
    RESULT = data; activeGroup = "normal"; modeFilter = "";
    setStatus("");
    render();
  } catch (e) {
    setStatus(e.message, "error");
  } finally {
    $("go").disabled = false;
  }
}

function groupsPresent() {
  const order = ["normal", ...GROUPS];
  return order.filter(g => RESULT.rankings[g] && RESULT.rankings[g].length);
}

function render() {
  $("results").hidden = false;
  const root = RESULT.evolution_tree[0];
  $("title").textContent = (root ? root.name + " line" : RESULT.query);

  const groups = groupsPresent();
  if (!groups.includes(activeGroup)) activeGroup = groups[0] || "normal";
  $("tabs").innerHTML = "";
  for (const g of (groups.length ? groups : ["normal"])) {
    const n = (RESULT.rankings[g] || []).length;
    const b = document.createElement("button");
    b.className = "tab"; b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", g === activeGroup);
    b.innerHTML = `${esc(label(g))}<small>${n}</small>`;
    b.onclick = () => { activeGroup = g; modeFilter = ""; render(); };
    $("tabs").appendChild(b);
  }
  renderIv();
  renderTable();
  $("tree").innerHTML = `<ul class="tree">${RESULT.evolution_tree.map(treeNode).join("")}</ul>`;
  renderIvSections();
}

function renderIv() {
  const info = RESULT.ivs;
  $("ivpanel").hidden = !info;
  if (!info) return;
  const v = info.values.join("/");
  $("ivnote").textContent = info.error ? info.error
    : `IVs ${v} at level cap ${info.cap}. Rank 1 is the best of 4096 spreads; ties share a rank.`;
  $("ivnote").className = "hint" + (info.error ? " error" : "");
  $("ivout").innerHTML = (RESULT.iv || []).map(ivMon).join("");
}

function ivCell(iv) {
  if (!iv) return `<td class="dim"></td>`;
  const cls = iv.percent >= 98 ? "pct-hi" : iv.percent >= 90 ? "pct-mid" : "pct-lo";
  return `<td class="rank"><b class="${cls}">#${iv.rank}</b> <small>${iv.percent}% · L${iv.level} · ${iv.cp} CP</small></td>`;
}

function renderTable() {
  const all = RESULT.rankings[activeGroup] || [];
  const modes = [...new Set(all.map(r => r.mode))];
  if (!modes.includes(modeFilter)) modeFilter = "";
  $("mode").innerHTML = `<option value="">All modes</option>` +
    modes.map(m => `<option ${m === modeFilter ? "selected" : ""} value="${esc(m)}">${esc(m)}</option>`).join("");
  const rows = modeFilter ? all.filter(r => r.mode === modeFilter) : all;
  $("count").textContent = rows.length ? `${rows.length} ranking${rows.length === 1 ? "" : "s"}, best first` : "";
  if (!rows.length) {
    $("table").innerHTML = `<div class="empty">No rankings for this group — these Pokémon aren't ranked in any mode on the site.</div>`;
  } else {
    const hasIv = !!RESULT.ivs && rows.some(r => r.iv);
    $("table").innerHTML = `<table><thead><tr><th>#</th><th>Pokémon</th><th>Mode</th><th>Tier</th><th>Rank</th>${hasIv ? "<th>Your IV rank</th>" : ""}</tr></thead><tbody>` +
      rows.map((r, i) => `<tr><td class="num">${i + 1}</td>
        <td>${sprite(r.slug)}<a href="https://db.pokemongohub.net/pokemon/${encodeURIComponent(r.slug)}" target="_blank" rel="noopener" style="color:inherit">${esc(r.pokemon)}</a>${xlinks(r.slug, r.pokemon, r.mode)}</td>
        <td>${esc(r.mode)}</td>
        <td><span class="badge tier-${esc(r.tier[0].toLowerCase())}">${esc(r.tier)}</span></td>
        <td class="rank">${r.rank == null ? "" : "#" + r.rank}</td>${hasIv ? ivCell(r.iv) : ""}</tr>`).join("") +
      `</tbody></table>`;
  }
  const un = RESULT.per_pokemon.filter(p => p.group === activeGroup && p.unranked_modes.length);
  $("unranked").innerHTML = un.length
    ? `<details><summary>Not ranked in</summary>` +
      un.map(p => `<div><b>${esc(p.name)}</b>: ${p.unranked_modes.map(esc).join(", ")}</div>`).join("") + `</details>`
    : "";
}

// Sprites come from the PokeAPI sprite repo by Pokédex number. They are lazy
// loaded (only fetched when scrolled near) and have fixed dimensions, so they
// never delay the search or shift the layout. Forms reuse the base sprite.
const SPRITE_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/";
function sprite(slugOrDex, cls = "") {
  const dex = parseInt(slugOrDex, 10);
  if (!dex) return "";
  return `<img class="spr ${cls}" src="${SPRITE_URL}${dex}.png" width="40" height="40" alt=""
    loading="lazy" decoding="async" onerror="this.style.visibility='hidden'">`;
}

// PvPoke ranking pages by league. Only rows whose mode is a league get a link.
const PVPOKE_CP = {"Great League": 1500, "Ultra League": 2500, "Master League": 10000};
const PVPOKE_SPECIAL = {
  "black kyurem": "kyurem_black", "white kyurem": "kyurem_white",
  "dusk mane necrozma": "necrozma_dusk_mane", "dawn wings necrozma": "necrozma_dawn_wings",
  "crowned sword zacian": "zacian_crowned_sword", "crowned shield zamazenta": "zamazenta_crowned_shield",
  "zygarde complete form": "zygarde_complete",
};

// Best-effort GO Hub display name -> PvPoke id, e.g. "Shadow Alolan Ninetales" -> "ninetales_alolan_shadow".
function pvpokeId(name) {
  let n = name.trim();
  const shadow = /\bShadow\b/.test(n);
  n = n.replace(/\bShadow\b/g, "").replace(/\s+/g, " ").trim();
  const reg = n.match(/\b(Alolan|Galarian|Hisuian|Paldean)\b/);
  if (reg) n = n.replace(reg[0], "").replace(/\s+/g, " ").trim();
  const clean = t => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()
    .replace(/%/g, "").replace(/['’.]/g, "").replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  const strip = f => f.replace(/\s+(Forme?|Mode|size|Breed|Style|Cloak)$/i, "");
  let base = n, form = "", m;
  if (PVPOKE_SPECIAL[n.toLowerCase()]) { base = PVPOKE_SPECIAL[n.toLowerCase()]; }
  else if ((m = n.match(/^(.+?)\s*\((.+)\)$/))) {
    base = m[1]; form = m[2].replace(/^Hero of Many Battles$/i, "Hero").replace(/^(East|West) Sea$/i, "");
  }
  else if ((m = n.match(/^(.+?) (?:Forme|Mode) (.+)$/))) { form = m[1]; base = m[2]; }
  else if ((m = n.match(/^(\S+) (.+?) Forme$/))) { base = m[1]; form = m[2]; }
  return [clean(base), reg ? reg[1].toLowerCase() : "", clean(strip(form)), shadow ? "shadow" : ""]
    .filter(Boolean).join("_");
}

// Per-Pokémon links: the GO Hub page, the IV spreads subpage (by name) and, for
// league rows, the PvPoke ranking page. slug may be a plain dex number or a form slug.
function xlinks(slug, name, mode) {
  const dex = parseInt(slug, 10);
  if (!dex) return "";
  const hub = "https://db.pokemongohub.net/pokemon/" + encodeURIComponent(slug);
  const cp = PVPOKE_CP[mode];
  const pvpoke = cp && name
    ? `\n    <a href="https://pvpoke.com/rankings/all/${cp}/overall/${pvpokeId(name)}/" target="_blank" rel="noopener" title="${esc(mode)} ranking on PvPoke">PvPoke</a>` : "";
  return `<span class="xlinks">
    <a href="${hub}" target="_blank" rel="noopener" title="Pokémon GO Hub page">DB</a>
    <a href="#ivspreads-card" data-iv="${esc(name || "")}" title="All IV spreads for every league">IV spreads</a>${pvpoke}</span>`;
}

function treeNode(n) {
  const req = n.requires ? `<span class="chip">${esc(n.requires)}</span>` : "";
  const forms = (n.forms || []).map(f =>
    `<span class="chip"><a href="${esc(f.url)}" target="_blank" rel="noopener" title="${esc(label(f.group))}">${esc(f.name)}</a></span>`).join("");
  const kids = n.evolves_to.length ? `<ul>${n.evolves_to.map(treeNode).join("")}</ul>` : "";
  return `<li><span class="name">${sprite(n.slug)}<a href="${esc(n.url)}" target="_blank" rel="noopener">${esc(n.name)}</a>${xlinks(n.slug, n.name)}</span> ${req}
    ${forms ? `<div>${forms}</div>` : ""}${kids}</li>`;
}

// ---- PvP IV rank ----
fetch("/api/ivnames").then(r => r.ok ? r.json() : []).then(names => {
  $("ivnames").innerHTML = names.map(n => `<option value="${esc(n)}">`).join("");
}).catch(() => {});

function ivMon(m) {
  const rows = m.leagues.map(l => {
    const pct = l.percent >= 98 ? "pct-hi" : l.percent >= 90 ? "pct-mid" : "pct-lo";
    const note = l.cp_cap && !l.capped ? `<td class="dim">maxes out under ${l.cp_cap} CP</td>` : `<td></td>`;
    return `<tr><td>${esc(l.league)}</td>
      <td class="r1"><b>#${l.rank}</b> <span style="color:var(--muted)">/ ${l.of}</span></td>
      <td class="${pct}">${l.percent}%</td><td>L${l.level}</td><td>${l.cp} CP</td>${note}</tr>`;
  }).join("");
  return `<div class="ivmon${m.selected ? " sel" : ""}">
    <h3>${sprite(m.id)}${esc(m.name)}<small>#${m.id} · base ${m.base.join("/")}</small>${xlinks(m.id, m.name)}</h3>
    <table><thead><tr><th>League</th><th>Rank</th><th>Stat product</th><th>Level</th><th>CP</th><th></th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

// ---- IV spreads (collapsible, one per Pokémon in the line) ----
const IV_LEAGUES = [["great", "Great League"], ["ultra", "Ultra League"], ["master", "Master League"]];

function treeNames(nodes, out = []) {
  for (const n of nodes) { if (!out.includes(n.name)) out.push(n.name); treeNames(n.evolves_to, out); }
  return out;
}

function renderIvSections() {
  $("ivspreads").innerHTML = "";
  for (const name of treeNames(RESULT.evolution_tree)) $("ivspreads").appendChild(ivSection(name));
}

function ivSection(name) {
  const d = document.createElement("details");
  d.className = "ivsec"; d.dataset.name = name;
  d.innerHTML = `<summary>${esc(name)}</summary><div class="ivbody"></div>`;
  d.addEventListener("toggle", () => { if (d.open && !d._init) { d._init = true; ivInit(d, name); } });
  return d;
}

function openIv(name) {
  const base = name.replace(/^Shadow /i, "").toLowerCase();
  let d = [...document.querySelectorAll("details.ivsec")].find(x => x.dataset.name.toLowerCase() === base);
  if (!d) { d = ivSection(name.replace(/^Shadow /i, "")); $("ivspreads").appendChild(d); }
  d.open = true;
  d.scrollIntoView({behavior: "smooth", block: "start"});
}
document.addEventListener("click", e => {
  const a = e.target.closest("a[data-iv]");
  if (a) { e.preventDefault(); openIv(a.dataset.iv); }
});

function ivInit(root, name) {
  const body = root.querySelector(".ivbody");
  const st = {league: "great", data: null, shown: 100, filtered: []};
  body.innerHTML = `<div class="tabs"></div>
    <div class="toolbar"><div class="row">
      <label>Level cap: <select class="cap"><option>40</option><option>41</option><option selected>50</option><option>51</option></select></label>
      <input class="flt" type="text" placeholder="Find IVs, e.g. 0/15/15 or */14/*" aria-label="Find an IV spread" autocomplete="off">
    </div><span class="count" style="color:var(--muted);font-size:13px"></span></div>
    <p class="hint note" style="margin:0 0 8px"></p>
    <div class="tbl"></div>
    <div class="more"><button class="more1" hidden></button><button class="moreall" hidden></button></div>`;
  const q = sel => body.querySelector(sel);

  function matcher(text) {
    // "0/15/15", "0 15 15", "*/14/*", or a partial like "15/15"; * matches anything.
    const parts = text.split(/[\s/,\-.]+/).filter(Boolean);
    if (!parts.length) return null;
    if (parts.length === 3) return r => parts.every((p, i) => p === "*" || +p === r[1 + i]);
    return r => r.slice(1, 4).join("/").includes(parts.join("/"));
  }

  function draw() {
    const slice = st.filtered.slice(0, st.shown);
    q(".tbl").innerHTML = !slice.length ? `<div class="empty">No spreads match.</div>` :
      `<table><thead><tr><th>Rank</th><th>IVs (Atk/Def/HP)</th><th>%</th><th>Level</th><th>CP</th><th>Atk</th><th>Def</th><th>HP</th></tr></thead><tbody>` +
      slice.map(r => {
        const cls = r[6] >= 98 ? "pct-hi" : r[6] >= 90 ? "pct-mid" : "pct-lo";
        return `<tr><td class="n"><b>#${r[0]}</b></td><td class="iv">${r[1]}/${r[2]}/${r[3]}</td>
          <td class="n ${cls}">${r[6].toFixed(2)}%</td><td class="n">${r[4]}</td><td class="n">${r[5]}</td>
          <td class="n">${r[7].toFixed(2)}</td><td class="n">${r[8].toFixed(2)}</td><td class="n">${r[9]}</td></tr>`;
      }).join("") + `</tbody></table>`;
    const left = st.filtered.length - slice.length;
    q(".more1").hidden = q(".moreall").hidden = left <= 0;
    q(".more1").textContent = `Show ${Math.min(100, left)} more`;
    q(".moreall").textContent = `Show all (${left} left)`;
  }

  function show() {
    const d = st.data, rows = d.rows, best = rows[0], level = q(".cap").value;
    q(".tabs").innerHTML = "";
    for (const [k, lab] of IV_LEAGUES) {
      const b = document.createElement("button");
      b.type = "button"; b.className = "tab"; b.textContent = lab;
      b.setAttribute("aria-selected", k === st.league);
      b.onclick = () => { st.league = k; load(); };
      q(".tabs").appendChild(b);
    }
    q(".note").textContent = (d.cp_cap
      ? `Highest level ≤ ${level} that keeps CP at or under ${d.cp_cap}. `
      : `Powered to the level cap (${level}). `) +
      `Best spread: ${best[1]}/${best[2]}/${best[3]}` + (d.cp_cap ? ` at L${best[4]} (${best[5]} CP).` : ".") +
      ` Base stats ${d.base.join("/")}.`;
    const m = matcher(q(".flt").value);
    st.filtered = m ? rows.filter(m) : rows;
    q(".count").textContent = m ? `${st.filtered.length} of ${rows.length}` : `${rows.length} spreads`;
    draw();
  }

  async function load() {
    q(".note").textContent = "Calculating…";
    try {
      const res = await fetch("/api/ivspreads?" + new URLSearchParams({p: name, league: st.league, cap: q(".cap").value}));
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || res.statusText);
      st.data = data; st.shown = 100; show();
    } catch (e) { q(".note").textContent = e.message; q(".note").className = "hint note error"; }
  }

  q(".cap").onchange = load;
  q(".flt").oninput = () => { if (st.data) { st.shown = 100; show(); } };
  q(".more1").onclick = () => { st.shown += 100; draw(); };
  q(".moreall").onclick = () => { st.shown = st.filtered.length; draw(); };
  load();
}

$("form").addEventListener("submit", e => { e.preventDefault(); search(); });
$("mode").onchange = e => { modeFilter = e.target.value; renderTable(); };
</script>
</body>
</html>
"""


def nightly_refresh(hour_utc):
    """Background loop: re-scrape the site once a day at hour_utc (UTC)."""
    while True:
        now = datetime.now(timezone.utc)
        nxt = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        time.sleep((nxt - now).total_seconds())
        try:
            print(f"[refresh] scraping at {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC",
                  file=sys.stderr)
            ok, msg = pt.refresh_snapshot(CONFIG["snapshot"], CONFIG["cache_dir"])
            print(f"[refresh] {'ok' if ok else 'skipped'}: {msg}", file=sys.stderr)
        except BaseException as e:      # scraper uses sys.exit; never kill the loop
            print(f"[refresh] failed: {e!r}", file=sys.stderr)


def main():
    data = Path(__file__).resolve().parent.parent / "data"
    ap = argparse.ArgumentParser(description="Local web UI for pogo_tiers")
    ap.add_argument("--host", default="127.0.0.1",
                    help="address to bind (0.0.0.0 to accept outside connections)")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    ap.add_argument("--hosted", action="store_true",
                    help="public deployment: accept any Host header and "
                         "refresh the data nightly")
    ap.add_argument("--nightly", action="store_true",
                    help="re-scrape the whole site once a day (implied by --hosted)")
    ap.add_argument("--refresh-hour", type=int, default=3,
                    help="UTC hour for the nightly refresh (default 3)")
    ap.add_argument("--cache-dir", default=str(data / "cache"))
    ap.add_argument("--snapshot", default=str(data / "all_rankings.json"),
                    help="rankings file made by `python src/refresh_data.py`")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    CONFIG.update(cache_dir=args.cache_dir, snapshot=args.snapshot, hosted=args.hosted)
    try:
        httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as e:
        sys.exit(f"Can't use port {args.port}: {e}. Try --port 8001")
    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}"
    print(f"GO Tier Lookup running at {url}  (Ctrl+C to stop)")
    if args.hosted or args.nightly:
        threading.Thread(target=nightly_refresh, args=(args.refresh_hour,),
                         daemon=True).start()
        print(f"Nightly data refresh at {args.refresh_hour:02d}:00 UTC")
    if not args.no_browser and not args.hosted:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
