#!/usr/bin/env python3
"""
The entrypoint for every automated channel.

    python scripts/run.py --channel releases   [--dry-run]
    python scripts/run.py --channel research   [--dry-run]
    python scripts/run.py --channel security   [--dry-run]
    python scripts/run.py --channel benchmarks [--dry-run]
    python scripts/run.py --report             [--dry-run]
    python scripts/run.py --digest             [--dry-run]
    python scripts/run.py --feedback           [--dry-run]
    python scripts/run.py --propose            [--dry-run]

There is no `--channel practice`. Decision A2 removed the Practice
section, and nothing in this pipeline knows the word.

--dry-run is the switch that decides whether anything reaches the repo.
In a dry run every channel does its full job — fetch, classify, resolve,
dedup, gate, rank, draft, verify — and then writes nothing consequential:
no post files, no ledger entries, no entity records, no measurement
files, no Telegram messages, no git operations. What it *does* write is
the observability: state/queue.json, state/rejected.jsonl,
state/unresolved_models.jsonl, state/topic_activity.json and the radar
collection — which is exactly what makes a threshold tunable without
publishing anything to tune it against.

    ############################################################
    #  DRY RUN IS THE DEFAULT.                                 #
    #                                                          #
    #  Publishing for real requires --publish (or PUBLISH=true #
    #  in the environment) AND a schedule that does not exist.  #
    #  NOTHING in this repository passes --publish to any       #
    #  channel, no workflow carries a `schedule:` trigger, and  #
    #  no cron-job.org job has been created for any of these.   #
    #  See the build report for the exact list of steps that    #
    #  would be required to change that.                       #
    ############################################################
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.constants import CHANNELS  # noqa: E402
from core.ledger import Ledger, Queue  # noqa: E402
from core.llm import LLM, LIVE, OFFLINE  # noqa: E402
from core.radar import Radar  # noqa: E402
from core.constants import TELEGRAM_FEEDBACK_OFFSET_FILE  # noqa: E402
from core.state import ensure_state_dir, read_json, write_json  # noqa: E402


@dataclass
class Context:
    """Everything a channel needs and nothing it does not. Passing this
    rather than reaching for module-level globals is what lets a test
    run a channel against a fixture with a fake clock and no network."""

    channel: str
    dry_run: bool
    llm: LLM
    ledger: Ledger
    queue: Queue
    radar: Radar
    limit: int | None = None
    fixtures: Path | None = None
    # Legacy path only: the Telegram marked-item flow, no feed sweep.
    marked_only: bool = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one automated publishing channel.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--channel", choices=CHANNELS, help="which channel to run")
    parser.add_argument(
        "--report",
        action="store_true",
        help="generate the weekly observability report instead of running a channel",
    )
    parser.add_argument(
        "--digest",
        action="store_true",
        help="generate the daily Telegram digest instead of running a channel",
    )
    parser.add_argument(
        "--feedback",
        action="store_true",
        help="poll Telegram for button taps (§11.2) and apply them: record the "
             "reaction, adjust the Radar/profile signal, and — for a 🗑 — "
             "retract the post. Fetching updates always hits Telegram for "
             "real (it is a read, not a send); in a dry run the local "
             "offset is deliberately NOT advanced, so the same pending taps "
             "are peeked at again next time instead of being consumed — "
             "every actual EFFECT stays gated by --dry-run/--publish exactly "
             "like every other channel.",
    )
    parser.add_argument(
        "--propose",
        action="store_true",
        help="generate proposed interest_profile.yaml changes from accumulated "
             "feedback and PRINT them. There is deliberately no --apply: §11.3 "
             "says Scout proposes and the owner approves, so a proposal is "
             "something a human applies by hand or not at all.",
    )
    publish = parser.add_mutually_exclusive_group()
    publish.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=None,
        help="decide everything, write nothing (the default)",
    )
    publish.add_argument(
        "--publish",
        dest="dry_run",
        action="store_false",
        help="actually write posts, measurements and state. Requires an "
             "explicit flag; never the default; passed by nothing in this repo.",
    )
    parser.add_argument(
        "--offline-llm",
        action="store_true",
        help="use the deterministic stand-ins instead of calling a model at "
             "all. Implied when OPENAI_API_KEY is unset.",
    )
    parser.add_argument("--limit", type=int, default=None, help="cap items examined")
    parser.add_argument(
        "--marked-only",
        action="store_true",
        help="research only: run ONLY the legacy Telegram marked-item path and "
             "skip the feed sweep entirely. This is what the existing live "
             "workflow calls. It publishes only what the owner has replied to "
             "by hand, so it activates no autonomous publishing.",
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=None,
        help="directory of recorded source data to run against instead of the network",
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="--report/--digest only: also send it to Telegram. Opt-in, and "
             "nothing in this repo passes it — generating a message is free, "
             "sending one is a side effect. Refused outright in a dry run.",
    )
    return parser


def resolve_dry_run(flag: bool | None) -> bool:
    """Precedence: an explicit flag, then PUBLISH in the environment,
    then dry-run. The environment can only ever be consulted when no
    flag was given, so a --dry-run on the command line can never be
    overridden by a stray env var."""
    if flag is not None:
        return flag
    return os.environ.get("PUBLISH", "false").strip().lower() not in ("1", "true", "yes")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.channel and not args.report and not args.digest and not args.feedback and not args.propose:
        build_parser().print_help()
        return 2

    ensure_state_dir()
    dry_run = resolve_dry_run(args.dry_run)
    llm = LLM(OFFLINE if args.offline_llm else None)
    ledger = Ledger(dry_run=dry_run)
    radar = Radar(dry_run=dry_run)

    mode = "DRY RUN — nothing will be written" if dry_run else "PUBLISHING FOR REAL"
    print(f"securesein pipeline — {mode}")
    print(f"  llm: {llm.mode}{' (no OPENAI_API_KEY)' if llm.mode == OFFLINE else ''}")
    print(f"  budget: {ledger.summary()}")

    if args.report:
        from channels import report

        text = report.render(ledger)
        print(text)
        _maybe_send(report.send, text, args.send, dry_run, "report")
        return 0

    if args.propose:
        from core import learning

        proposal = learning.propose()
        text = learning.render(proposal)
        print(text)
        learning.record(proposal, dry_run=dry_run)
        _maybe_send(
            lambda body: bool(_send_plain(body)), text, args.send, dry_run, "proposal"
        )
        return 0

    if args.digest:
        from telegram import digest

        text = digest.render(ledger, radar)
        print(text)
        # The interactive form (one message per item, each with its own
        # reaction keyboard) is what §11.1/§11.2 actually describe —
        # digest.send() alone has nowhere to attach a button. send_interactive
        # is what --publish --send calls; a dry run never reaches either.
        if args.send:
            if dry_run:
                print("\n[dry-run] --send ignored: a dry run never sends a real "
                      "digest. Re-run with --publish --send to send for real.")
            else:
                print("\nSending digest to Telegram (one message per item, "
                      "with reaction buttons)...")
                ok = digest.send_interactive(ledger, radar)
                print("sent." if ok else "send FAILED — see above.")
        return 0

    if args.feedback:
        from telegram import api, feedback
        from papers import rate as raw_feed_rate

        offset_state = read_json(TELEGRAM_FEEDBACK_OFFSET_FILE, {"offset": None})
        updates = api.get_updates(offset_state.get("offset"))
        print(f"  telegram: {len(updates)} update(s) fetched")

        outcomes = feedback.handle_updates(updates, radar=radar, dry_run=dry_run)
        for outcome in outcomes:
            tag = "ok" if outcome.accepted else "skipped"
            print(f"    [{tag}] {outcome.action} -> {outcome.item_id}: {outcome.detail}")

        # Same poll, a second module: raw_feed.py's rating buttons carry
        # callback_data feedback.py's own parse_callback doesn't recognise
        # (see papers/rate.py's docstring for why the two don't share one
        # code path), so every update is offered to both rather than
        # running a second, independent getUpdates poller for them.
        rating_outcomes = raw_feed_rate.handle_updates(updates, dry_run=dry_run)
        for outcome in rating_outcomes:
            print(f"    [ok] rating {outcome['rating']}/5 -> {outcome['id']}")
        if updates and not outcomes and not rating_outcomes:
            print("    (no recognised callback_query among the fetched updates)")

        # Reading is always real (see the --feedback help text above); only
        # the offset commit and the Radar/state effects are dry-run-gated,
        # matching every other channel's write discipline.
        if updates and not dry_run:
            next_offset = max(u.get("update_id", -1) for u in updates) + 1
            write_json(TELEGRAM_FEEDBACK_OFFSET_FILE, {"offset": next_offset})
        elif updates:
            print(f"    [dry-run] would advance the offset past "
                  f"{max(u.get('update_id', -1) for u in updates)}")

        radar.save()
        return 0

    ctx = Context(
        channel=args.channel,
        dry_run=dry_run,
        llm=llm,
        ledger=ledger,
        queue=Queue(ledger),
        radar=radar,
        limit=args.limit,
        fixtures=args.fixtures,
        marked_only=args.marked_only,
    )

    if args.channel == "releases":
        from channels import releases

        releases.run(ctx)
    elif args.channel == "research":
        from channels import research

        research.run(ctx)
    elif args.channel == "security":
        from channels import security

        security.run(ctx)
    elif args.channel == "benchmarks":
        from channels import benchmarks

        benchmarks.run(ctx)

    ctx.queue.save()
    ctx.radar.save()
    ledger.save()
    if llm.mode == LIVE:
        print(f"  {llm.calls} model call(s) made.")
    return 0


def _send_plain(text: str):
    from telegram import api

    return api.send(text)


def _maybe_send(sender, text: str, send: bool, dry_run: bool, what: str) -> None:
    """One place where a real Telegram message could ever leave this
    process, and it is guarded twice: an explicit --send AND not being
    in a dry run. A dry run refuses loudly rather than sending quietly,
    because "I thought it was a dry run" is not a recoverable mistake
    once a message has arrived on someone's phone."""
    if not send:
        return
    if dry_run:
        print(f"\n[dry-run] --send ignored: a dry run never sends a real "
              f"{what}. Re-run with --publish --send to send for real.")
        return
    print(f"\nSending {what} to Telegram...")
    print("sent." if sender(text) else "send FAILED — see above.")


if __name__ == "__main__":
    raise SystemExit(main())
