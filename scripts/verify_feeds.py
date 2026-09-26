#!/usr/bin/env python3
"""
Check which entries in feeds-releases.json / feeds-benchmarks.json are actually
reachable and parseable. Run this before wiring any feed into the pipeline.

    pip install feedparser requests
    python verify_feeds.py feeds-releases.json feeds-benchmarks.json

Writes feed-verification-report.md and exits non-zero if any entry marked
verified:true fails, so it can run in CI as a drift check.
"""

import json
import sys
from datetime import datetime, timezone

import requests

try:
    import feedparser
except ImportError:
    print("pip install feedparser requests")
    sys.exit(2)

UA = "SecureseinFeedVerifier/1.0 (+https://securesein.github.io/)"
TIMEOUT = 20

# Types that are fetched and parsed as feeds; others are checked for
# reachability only, since they need a bespoke adapter anyway.
#
# html is no longer probe-only: core/feeds.py grew an adapter for it on
# 2026-09-26, so the report should say whether the page actually yields
# items rather than just that it answers.
FEED_TYPES = {"rss", "atom"}
JSON_TYPES = {"json", "hf_api"}
PROBE_ONLY = {"git", "api", "python_client"}
ADAPTED = {"html"}


def check(entry):
    url = entry.get("url", "")
    kind = entry.get("type", "rss")
    name = entry.get("naam", "(unnamed)")

    if not url or url == "-":
        return name, kind, "SKIP", "no url in entry"

    try:
        if kind in FEED_TYPES:
            r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
            if r.status_code != 200:
                return name, kind, "FAIL", f"HTTP {r.status_code}"
            parsed = feedparser.parse(r.content)
            n = len(parsed.entries)
            if n == 0:
                return name, kind, "FAIL", "0 entries parsed"
            latest = ""
            if getattr(parsed.entries[0], "published", None):
                latest = f", latest {parsed.entries[0].published}"
            return name, kind, "OK", f"{n} entries{latest}"

        if kind in JSON_TYPES:
            r = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
            if r.status_code != 200:
                return name, kind, "FAIL", f"HTTP {r.status_code}"
            data = r.json()
            n = len(data) if isinstance(data, list) else 1
            return name, kind, "OK", f"json ok, {n} records"

        if kind in ADAPTED:
            # Run the real adapter, so the report answers the question
            # that matters — does this page yield items? — instead of
            # only whether it answers an HTTP request.
            import sys as _sys, pathlib as _pl
            _sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
            from core.feeds import Source, _fetch_html

            items = _fetch_html(
                Source(name=name, url=url, type="html", tier="primary", vendor="-"),
                limit=30,
            )
            if not items:
                return name, kind, "FAIL", "adapter parsed no items from the page"
            dated = sum(1 for i in items if i.published)
            return name, kind, "OK", f"{len(items)} items via html adapter, {dated} dated"

        if kind in PROBE_ONLY:
            r = requests.get(
                url, timeout=TIMEOUT, headers={"User-Agent": UA}, allow_redirects=True
            )
            if r.status_code >= 400:
                return name, kind, "FAIL", f"HTTP {r.status_code}"
            return name, kind, "PROBE", f"HTTP {r.status_code}, needs custom adapter"

        return name, kind, "SKIP", f"unknown type '{kind}'"

    except Exception as exc:  # noqa: BLE001 - report, never crash the sweep
        return name, kind, "FAIL", f"{type(exc).__name__}: {exc}"


def main(paths):
    rows = []
    regressions = []

    for path in paths:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
        entries = doc.get("feeds") or doc.get("sources") or []
        for entry in entries:
            name, kind, status, detail = check(entry)
            claimed = entry.get("verified", False)
            rows.append((path, name, kind, status, detail, claimed))
            if claimed and status == "FAIL":
                regressions.append(name)
            print(f"{status:6} {name}  —  {detail}")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    with open("feed-verification-report.md", "w", encoding="utf-8") as fh:
        fh.write(f"# Feed verification — {stamp}\n\n")
        fh.write("| File | Feed | Type | Status | Detail | Claimed verified |\n")
        fh.write("|---|---|---|---|---|---|\n")
        for path, name, kind, status, detail, claimed in rows:
            safe = detail.replace("|", "\\|")
            fh.write(
                f"| {path} | {name} | {kind} | {status} | {safe} | {claimed} |\n"
            )

    ok = sum(1 for r in rows if r[3] == "OK")
    print(f"\n{ok}/{len(rows)} parsed cleanly. Report: feed-verification-report.md")

    if regressions:
        print(f"\nRegression — entries marked verified:true that now fail:")
        for name in regressions:
            print(f"  - {name}")
        return 1
    return 0


if __name__ == "__main__":
    args = sys.argv[1:] or ["feeds-releases.json", "feeds-benchmarks.json"]
    sys.exit(main(args))
