# mlsnextscores.com

An unofficial, mobile-first record of MLS NEXT — every fixture, result and
table across the Allstate Homegrown Division, the Academy Division and Flex,
U13 through U19.

MLS publishes all of this already. It publishes it as a wide desktop table
inside an iframe, which is not much use standing on the touchline holding a
phone, and that is the entire reason this exists.

## Where the data comes from

The schedule page on mlssoccer.com is a shell around a viewer hosted at
`mls-assist.theintelligenceplatform.com`. That viewer reads six plain static
JSON files off S3/CloudFront:

    /data/schedule/<key>.json      every fixture in the competition
    /data/standings/<key>.json     every table, by conference and age group

for the keys `mls-next-league-26-27`, `mls-next-2-academy-division-26-27` and
`mls-next-flex-26-27`. No authentication, no cookie, no token, no signature.
The host's robots.txt disallows nothing. They carry ETags and a four-minute
CDN cache, so a refresh that finds nothing new costs six conditional requests
rather than 24MB.

This is somebody else's data, served under MLS's terms. Open to fetch is not
the same as licensed to redistribute, and if this ever grows past a tool for
one parent and his kids' teams that is a conversation to have with MLS rather
than an assumption to keep making.

## The pipeline

    tools/fetch.py       six URLs -> raw/, skipping anything unchanged
    tools/transform.py   raw/ -> data/, cut three ways
    tools/crests.py      data/crests.json -> img/clubs/<id>.png
    build.py             app.template.html + data -> index.html

Every step runs in GitHub Actions, because the feed host refuses both the
laptop and the sandbox this was written in by egress policy. `raw/` is not
committed: it is an input, not a record.

## Why the data is cut three ways

The feeds are shaped for a desktop table — each match carries both clubs in
full, crest URL and all — which is how they reach 24MB. A phone asks three
questions, so there are three answers:

    data/d/<YYYY-MM-DD>.json   every match that day, all divisions (~38KB worst case)
    data/c/<club-id>.json      one club's whole season, every age group (2-16KB)
    data/t/<div>__<age>.json   the standings tables for that slice

The date files and the club files hold the same matches twice. That is the
point: the scores page is answered in one request and a club page in one more,
where a single season file would mean shipping the lot to read one Saturday.
Clubs, venues and competitions are interned into their own small files.

## Two things the feed gets wrong

A scatter of fixtures months in the future arrive flagged `completed` — the
furthest is dated June 2027. A match is treated as finished here only when it
has kicked off *and* carries a score, never on the flag.

About one in seven matches that have kicked off has no score yet; results
trickle in over the following day. That is the league's data entry, not a
fetching problem, which is why the refresh runs often rather than hard.

## What is not here

No players. The feed names none — no rosters, no goalscorers, no squad
numbers — and for a league of minors that is the right absence rather than a
gap to fill.
