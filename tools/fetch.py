#!/usr/bin/env python3
"""Pull the MLS NEXT feeds.

The schedule on mlssoccer.com is an iframe around a viewer at
mls-assist.theintelligenceplatform.com, and that viewer reads plain static
JSON off S3/CloudFront -- no auth, no cookie, nothing to sign. Its robots.txt
disallows nothing. So this is a straight GET of six files.

Each file carries an ETag and a Last-Modified, and the CDN holds them for four
minutes, so a refresh that has nothing new to say costs one conditional request
per feed rather than 24MB. The etags are kept in raw/etags.json.

Run it anywhere with open egress; the sandbox this was written in cannot reach
the host at all, which is why the refresh lives in CI.
"""
import json, os, sys, time, urllib.request, urllib.error

BASE = "https://mls-assist.theintelligenceplatform.com/data"

# Adding a competition -- a Cup or FEST key, when MLS publishes a viewer for
# one -- is one line here and nothing anywhere else.
SEASONS = [
    ("league",   "mls-next-league-26-27",              "Allstate Homegrown"),
    ("academy",  "mls-next-2-academy-division-26-27",  "Academy Division"),
    ("flex",     "mls-next-flex-26-27",                "Flex"),
]
KINDS = ("schedule", "standings")

RAW = os.environ.get("MLSNEXT_RAW", "raw")
UA = ("Mozilla/5.0 (compatible; mlsnextscores/1.0; "
      "+https://mlsnextscores.com/about)")


def load_etags():
    try:
        return json.load(open(os.path.join(RAW, "etags.json")))
    except Exception:
        return {}


def get(url, etag=None, tries=4):
    """One file. 304 comes back as None, which means 'nothing changed'."""
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept": "application/json"})
        if etag:
            req.add_header("If-None-Match", etag)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read(), r.headers.get("ETag"), r.headers.get("Last-Modified")
        except urllib.error.HTTPError as e:
            if e.code == 304:
                return None, etag, None
            # 403/404 are answers, not hiccups -- only back off on 5xx and 429
            if e.code < 500 and e.code != 429:
                raise
            last = e
        except urllib.error.URLError as e:
            last = e
        time.sleep(2 ** attempt)
    raise SystemExit("giving up on %s: %s" % (url, last))


def main():
    os.makedirs(RAW, exist_ok=True)
    etags = load_etags()
    force = "--force" in sys.argv
    changed, report = [], {}

    for slug, key, _label in SEASONS:
        for kind in KINDS:
            url = "%s/%s/%s.json" % (BASE, kind, key)
            name = "%s__%s" % (kind, slug)
            path = os.path.join(RAW, name + ".json")
            have = None if force else etags.get(name)
            if have and not os.path.exists(path):
                have = None            # etag without the file is not a cache
            body, etag, modified = get(url, have)
            if body is None:
                report[name] = "unchanged"
                continue
            # parse before writing: a truncated transfer must not land on disk
            # as a valid-looking file and quietly empty the site
            doc = json.loads(body)
            n = len(doc.get("events", [])) if kind == "schedule" else \
                len(doc.get("competition_season", {}).get("competition_brackets", []))
            if n == 0:
                report[name] = "REFUSED: empty payload"
                continue
            with open(path, "wb") as f:
                f.write(body)
            etags[name] = etag
            changed.append(name)
            report[name] = "%d %s, %.1fMB%s" % (
                n, "events" if kind == "schedule" else "tables",
                len(body) / 1048576.0, ", modified " + modified if modified else "")

    json.dump(etags, open(os.path.join(RAW, "etags.json"), "w"), indent=1)
    for k in sorted(report):
        print("  %-22s %s" % (k, report[k]))
    print("changed: %s" % (", ".join(changed) if changed else "nothing"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
