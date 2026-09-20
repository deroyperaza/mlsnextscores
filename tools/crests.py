#!/usr/bin/env python3
"""Mirror the club crests into the repo.

Every crest in the feed is an imgix URL on kitman.imgix.net. Pointing the app
at those means a request per club to a third party on every page view, a layout
that breaks the day they move a file, and a club's logo vanishing from an
archive page years later. They are small; keep them.

Only new or changed ones are fetched, so an ordinary refresh downloads nothing.
"""
import json, os, sys, hashlib, urllib.request, urllib.error

OUT = os.environ.get("MLSNEXT_OUT", "data")
IMG = os.environ.get("MLSNEXT_IMG", "img/clubs")
SIZE = 128          # twice the largest the app draws, for a retina screen
UA = "Mozilla/5.0 (compatible; mlsnextscores/1.0; +https://mlsnextscores.com/about)"


def sized(url):
    """imgix takes the dimensions in the query string, so ask for the size the
    app needs rather than shrinking a bigger file in the browser."""
    base = url.split("?")[0]
    return base + "?ixlib=rails-4.2.0&fit=fill&trim=off&bg=00FFFFFF&w=%d&h=%d&auto=format" % (SIZE, SIZE)


def main():
    crests = json.load(open(os.path.join(OUT, "crests.json"), encoding="utf-8"))
    os.makedirs(IMG, exist_ok=True)
    state_path = os.path.join(IMG, "sources.json")
    try:
        state = json.load(open(state_path, encoding="utf-8"))
    except Exception:
        state = {}

    got = skipped = failed = 0
    for cid, url in sorted(crests.items()):
        if not url:
            continue
        want = sized(url)
        dest = os.path.join(IMG, "%s.png" % cid)
        if state.get(cid) == want and os.path.exists(dest):
            skipped += 1
            continue
        try:
            req = urllib.request.Request(want, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45) as r:
                body = r.read()
            if len(body) < 100:
                raise ValueError("suspiciously small")
            with open(dest, "wb") as f:
                f.write(body)
            state[cid] = want
            got += 1
        except Exception as e:
            # a missing crest is a missing picture, never a failed refresh
            failed += 1
            print("  crest %s: %s" % (cid, str(e)[:70]))

    json.dump(state, open(state_path, "w"), indent=1, sort_keys=True)
    print("  crests: %d new, %d unchanged, %d unavailable" % (got, skipped, failed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
