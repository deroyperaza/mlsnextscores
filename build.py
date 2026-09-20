#!/usr/bin/env python3
"""app.template.html + data/meta.json -> index.html.

The page boots knowing three things: when the data was last pulled, which
divisions and age groups exist, and which dates have matches. Everything else
is fetched on demand, so the page itself stays small however big the season
gets.
"""
import json, os, sys

TPL = os.environ.get("MLSNEXT_TPL", "app.template.html")
OUT = os.environ.get("MLSNEXT_OUT", "data")
PAGE = os.environ.get("MLSNEXT_PAGE", "index.html")


def main():
    meta = json.load(open(os.path.join(OUT, "meta.json"), encoding="utf-8"))
    # The app never needs the per-table counts or the raw competition list at
    # boot; they are in the files that use them.
    boot = {
        "path": "/data/",
        "updated": meta["updated"],
        "synced": meta.get("synced"),
        "divisions": meta["divisions"],
        "ages": meta["ages"],
        "dates": meta["dates"],
        "tiebreakers": meta.get("tiebreakers", {}),
        "clubs": meta.get("clubs"),
        "matches": meta.get("matches"),
    }
    tpl = open(TPL, encoding="utf-8").read()
    if "__META__" not in tpl:
        raise SystemExit("template has no __META__ slot")
    page = tpl.replace("__META__", json.dumps(boot, separators=(",", ":")))
    with open(PAGE, "w", encoding="utf-8") as f:
        f.write(page)
    print("  index.html %.0fKB, %d dates, %d age groups, %d divisions"
          % (os.path.getsize(PAGE) / 1024.0, len(boot["dates"]),
             len(boot["ages"]), len(boot["divisions"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
