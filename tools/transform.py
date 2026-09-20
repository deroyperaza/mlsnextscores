#!/usr/bin/env python3
"""Turn the six raw feeds into what the app actually asks for.

The feeds are built for a desktop table: every match carries its two clubs in
full, crest URL and all, which is why they run to 24MB. A phone wants three
things -- what happened today, where a club stands, and what my club is doing
next -- so the data is cut three ways and everything repeated is interned.

  data/meta.json           divisions, age groups, dates that exist, counts
  data/clubs.json          id -> [name, short, division bitmask]
  data/venues.json         id -> name
  data/d/<YYYY-MM-DD>.json every match that day, all divisions
  data/c/<clubid>.json     one club's whole season, every age group
  data/t/<div>__<age>.json the standings tables for that slice

The two cuts overlap on purpose. A date file answers the scores page in one
request and a club file answers a club page and the followed list in one more;
holding a single season file instead would mean shipping 24MB to read one
Saturday.
"""
import json, os, re, sys, collections, datetime

RAW = os.environ.get("MLSNEXT_RAW", "raw")
OUT = os.environ.get("MLSNEXT_OUT", "data")

DIVISIONS = [
    ("league",  "Allstate Homegrown", "HG"),
    ("academy", "Academy Division",   "AD"),
    ("flex",    "Flex",               "FX"),
]
DIV_ORDER = {d[0]: i for i, d in enumerate(DIVISIONS)}

AGE_RE = re.compile(r"\bU(\d{2})([A-Z]?)\b")


def age_of(squad_name):
    """'U13 AD' and 'U17B' both name an age group; the division is recorded
    separately, so the suffix is kept only when it is a real split (U17B) and
    dropped when it is just the division saying its own name again."""
    m = AGE_RE.search(squad_name or "")
    if not m:
        return None
    return "U" + m.group(1) + (m.group(2) or "")


def short_name(name):
    """Club names run long ('South Florida Football Academy'). The list needs
    something that fits a phone row without becoming a riddle."""
    n = re.sub(r"\s+", " ", (name or "").strip())
    for suffix in (" Soccer Club", " Football Academy", " Soccer Academy",
                   " Academy FC", " Football Club"):
        if n.endswith(suffix):
            n = n[: -len(suffix)]
            break
    n = re.sub(r"\s+(FC|SC|CF|AFC)$", "", n) if len(n) > 18 else n
    return n.strip() or (name or "")


def load(kind, slug):
    path = os.path.join(RAW, "%s__%s.json" % (kind, slug))
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    clubs, venues, comps = {}, {}, {}
    by_date = collections.defaultdict(list)
    by_club = collections.defaultdict(list)
    ages, synced, counts = set(), None, {}
    now = datetime.datetime.now(datetime.timezone.utc)
    missing = []

    for slug, label, abbr in DIVISIONS:
        sched = load("schedule", slug)
        if sched is None:
            missing.append(slug)
            continue
        synced = max(synced or "", sched.get("synced_at") or "")
        kept = 0
        for e in sched.get("events", []):
            ho, ao = e.get("home_organisation") or {}, e.get("away_organisation") or {}
            if not ho.get("id") or not ao.get("id"):
                continue
            age = age_of(e.get("home_squad_name")) or age_of(e.get("away_squad_name"))
            if not age:
                continue
            ages.add(age)
            for o in (ho, ao):
                c = clubs.setdefault(o["id"], {"name": o.get("name") or "",
                                               "logo": o.get("logo_full_path") or "",
                                               "divs": set()})
                c["divs"].add(slug)
            loc = e.get("event_location") or {}
            if loc.get("id"):
                venues[loc["id"]] = loc.get("name") or ""
            comp = e.get("competition") or {}
            if comp.get("id"):
                comps[comp["id"]] = comp.get("name") or ""

            ts = e.get("start_time") or ""
            kicked = bool(ts) and ts < now.isoformat()
            # The feed flags a scatter of future fixtures as completed -- the
            # latest "completed" match in it is dated eight months out. A match
            # is finished when it has kicked off AND carries a score, never on
            # the flag alone.
            hs, as_ = e.get("home_score"), e.get("away_score")
            done = bool(e.get("completed")) and kicked and hs is not None and as_ is not None

            row = [
                e.get("id"),                       # 0 stable id
                ts,                                # 1 kickoff, UTC
                e.get("local_timezone") or "",     # 2 so a phone in NY can show a CA kickoff right
                ho["id"], ao["id"],                # 3,4 clubs
                age,                               # 5 age group
                slug,                              # 6 division
                (hs if done else None),            # 7 scores, only once they mean something
                (as_ if done else None),           # 8
                1 if done else 0,                  # 9
                loc.get("id") or 0,                # 10 venue
                comp.get("id") or 0,               # 11 competition
                e.get("round_number") or 0,        # 12
                e.get("home_penalty_shootout_score") or 0,
                e.get("away_penalty_shootout_score") or 0,
                str(e.get("game_key") or ""),      # 15 the number printed on MLS's own page
            ]
            day = ts[:10]
            if day:
                by_date[day].append(row)
            by_club[ho["id"]].append(row)
            by_club[ao["id"]].append(row)
            kept += 1
        counts[slug] = kept

    if missing:
        print("  no raw file yet for: %s" % ", ".join(missing))
    if not by_date:
        raise SystemExit("REFUSING to write: not one usable match in any feed")

    # ---- standings -------------------------------------------------------
    tables = collections.defaultdict(list)
    tiebreak = {}
    for slug, label, abbr in DIVISIONS:
        st = load("standings", slug)
        if st is None:
            continue
        cs = st.get("competition_season") or {}
        tiebreak[slug] = [[t.get("abbr"), t.get("key"), t.get("name")]
                          for t in (cs.get("tiebreakers") or [])]
        for br in cs.get("competition_brackets") or []:
            age = (br.get("age_group") or {}).get("name") or ""
            if not age:
                continue
            ages.add(age)
            rows = []
            for r in br.get("standings") or []:
                t = r.get("team") or {}
                if not t.get("organisation_id"):
                    continue
                c = clubs.setdefault(t["organisation_id"],
                                     {"name": t.get("name") or "",
                                      "logo": t.get("logo_url") or "", "divs": set()})
                c["divs"].add(slug)
                if not c["logo"]:
                    c["logo"] = t.get("logo_url") or ""
                vals = r.get("tiebreaker_values") or {}
                rows.append([r.get("position"), t["organisation_id"]] +
                            [(vals.get(k[1]) or {}).get("value") for k in tiebreak[slug]])
            if rows:
                tables["%s__%s" % (slug, age)].append(
                    {"id": br.get("id"), "name": br.get("name"),
                     "gender": br.get("gender") or "", "rows": rows})

    # ---- write -----------------------------------------------------------
    for sub in ("d", "c", "t"):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)

    def dump(path, obj):
        full = os.path.join(OUT, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            json.dump(obj, f, separators=(",", ":"), ensure_ascii=False)
        return os.path.getsize(full)

    dbytes = sum(dump("d/%s.json" % d, sorted(rows, key=lambda r: (r[1], r[5])))
                 for d, rows in by_date.items())
    cbytes = sum(dump("c/%d.json" % cid, sorted(rows, key=lambda r: r[1]))
                 for cid, rows in by_club.items())
    tbytes = sum(dump("t/%s.json" % k, v) for k, v in tables.items())

    dump("clubs.json", {str(cid): [c["name"], short_name(c["name"]),
                                   sorted(c["divs"], key=lambda s: DIV_ORDER[s])]
                        for cid, c in sorted(clubs.items())})

    # A club's URL should read like the club, not like a row id. Collisions get
    # the id appended rather than a guessed disambiguation -- two clubs really
    # are called Inter Miami CF at different levels.
    slugs, taken = {}, {}
    for cid, c in sorted(clubs.items()):
        base = re.sub(r"[^a-z0-9]+", "-", short_name(c["name"]).lower()).strip("-") or str(cid)
        slug = base if base not in taken else "%s-%d" % (base, cid)
        taken[base] = True
        slugs[slug] = cid
    dump("slugs.json", slugs)
    dump("venues.json", {str(k): v for k, v in sorted(venues.items())})
    # kept out of clubs.json so the app never has to carry a third-party URL:
    # the mirror step reads this and nothing else does
    dump("crests.json", {str(cid): c["logo"] for cid, c in sorted(clubs.items()) if c["logo"]})

    age_sort = lambda a: (int(re.sub(r"\D", "", a) or 0), a)
    meta = {
        "updated": datetime.datetime.now(datetime.timezone.utc)
                   .strftime("%Y-%m-%dT%H:%M:%SZ"),
        "synced": synced,
        "divisions": [{"key": k, "name": n, "abbr": a, "matches": counts.get(k, 0)}
                      for k, n, a in DIVISIONS if k in counts],
        "ages": sorted(ages, key=age_sort),
        "dates": sorted(by_date),
        "clubs": len(clubs),
        "matches": sum(counts.values()),
        "tables": {k: len(v) for k, v in sorted(tables.items())},
        "tiebreakers": tiebreak,
        "competitions": {str(k): v for k, v in sorted(comps.items())},
    }
    dump("meta.json", meta)

    print("  %d matches, %d clubs, %d dates, %d tables"
          % (meta["matches"], len(clubs), len(by_date), sum(len(v) for v in tables.values())))
    print("  dates %.1fMB, clubs %.1fMB, tables %.1fMB"
          % (dbytes / 1048576.0, cbytes / 1048576.0, tbytes / 1048576.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
