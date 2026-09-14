"""
The daily digest (brief §11.1).

One message a day, listing what was published, with scores and reasons,
then the top of the Radar that was not. Each item carries an inline
keyboard so a reaction addresses that item specifically.

    python scripts/run.py --digest [--dry-run]

The format is §11.1's, adapted only where decision A2 changed the
sections: there is no Practice line, because there is no Practice.

WHY THE SCORES AND THE REASON ARE IN THE MESSAGE. §7.2: `whyRelevant` is
not decoration. It is how a mis-tuned profile becomes visible, and it is
the first thing to read when the wrong things start getting published. A
digest listing titles alone would tell the owner what happened and not
why, which is the half that can be acted on.

**This is not an approval queue.** It is sent after publication, nothing
waits for a reply, and the next run happens whether it is read or not
(§11, and §2's "do not add a manual approval step anywhere").

NOTHING HERE SENDS BY ITSELF. render() builds a string. send() is a
separate call, gated by --send AND by not being a dry run AND by a
token being present — see telegram/api.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core import taxonomy as tax
from core.constants import BLOG_DIR
from core.frontmatter import read_frontmatter
from core.ledger import Ledger
from core.radar import Radar
from telegram import api

# How many Radar items to list under the published ones. Enough to show
# what was close, short enough that the message stays scannable on a
# phone — which is the only place it is ever read.
RADAR_PREVIEW = 5
# A published item scoring at or above this gets the flame. §11.1 shows
# one on 93 and none on 81, so the line is somewhere between.
HOT_SCORE = 85


def _published_today(ledger: Ledger, hours: int = 24) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    return ledger._rows_since(cutoff)  # noqa: SLF001


def _post_facts(slug: str) -> dict:
    """Section, topics and title, read off the post itself rather than
    carried in the ledger. The ledger records a decision; the post is
    the fact, and if the two disagree the post is right."""
    path = BLOG_DIR / f"{slug}.md"
    if not path.exists():
        return {}
    data = read_frontmatter(path)
    import re

    text = path.read_text(encoding="utf-8")
    match = re.search(r"^topics:\s*\[(.*?)\]\s*$", text, re.M)
    topics = (
        [t.strip().strip('"') for t in match.group(1).split(",") if t.strip()]
        if match else []
    )
    scout = data.get("scout") or {}
    return {
        "title": data.get("title", slug),
        "section": data.get("kind", ""),
        "topics": topics,
        "why": scout.get("whyRelevant", ""),
    }


def _item_block(entry: dict) -> list[str]:
    facts = _post_facts(entry["slug"])
    score = entry.get("relevanceScore") or 0
    flame = "🔥" if score >= HOT_SCORE else "  "
    section = tax.section_label(facts.get("section") or entry.get("section", ""))
    topics = ", ".join(facts.get("topics") or [])
    why = facts.get("why") or entry.get("whyRelevant") or ""

    lines = [f"{flame} {score:>3.0f}  {facts.get('title', entry['slug'])}"]
    lines.append(f"      {section}" + (f" · {topics}" if topics else ""))
    if why:
        lines.append(f'      "{why}"')
    lines.append(f"      /blog/{entry['slug']}/")
    return lines


def render(ledger: Ledger, radar: Radar, *, hours: int = 24) -> str:
    """The message, as text. Always renderable — no token, no network,
    no side effects — because that is how it is inspected."""
    published = _published_today(ledger, hours)
    seen = radar.since(hours=hours)
    stamp = datetime.now(timezone.utc).strftime("%-d %B")

    target = sum(ledger.config["targets_7d"].values())
    lines = [f"Scout — {stamp}"]
    lines.append(
        f"Published {len(published)} · Radar {len(seen)} · "
        f"Budget {ledger.used()}/{target} this week"
    )
    lines.append("")

    if published:
        for entry in sorted(
            published, key=lambda e: e.get("relevanceScore") or 0, reverse=True
        ):
            lines.extend(_item_block(entry))
            lines.append("")
    else:
        # §16: "a quiet week is a correct outcome, not a failure to hit
        # target." The digest says so plainly rather than apologising.
        lines.append("Nothing published today. A quiet day is a correct outcome.")
        lines.append("")

    top = radar.top(limit=RADAR_PREVIEW)
    if top:
        lines.append("Top of Radar (not published):")
        for item in top:
            lines.append(
                f"   {item['relevanceScore']:>3.0f}  {item['title'][:58]}"
            )
            lines.append(f"        {item['url']}")
    return "\n".join(lines).rstrip() + "\n"


# --- the inline keyboard ---------------------------------------------

# §11.2's five actions. The callback payload is "<action>:<id>", and the
# id is the stable candidate id from core/radar.py — a hash of the
# item's URL — so a tap hours after the digest was sent still addresses
# the thing it was shown under.
ACTIONS = [
    ("👍", "interesting"),
    ("👎", "not_useful"),
    ("🚫", "not_my_topic"),
    ("⭐", "deep_dive"),
    ("🗑", "retract"),
]


def keyboard_for(candidate_id: str) -> list[list[dict]]:
    return [[
        {"text": emoji, "callback_data": f"{action}:{candidate_id}"}
        for emoji, action in ACTIONS
    ]]


def messages(ledger: Ledger, radar: Radar, *, hours: int = 24) -> list[tuple]:
    """(text, keyboard) pairs.

    One message per published post, each with its own keyboard, plus a
    header and a Radar footer. Telegram attaches a keyboard to a
    MESSAGE, not to a line inside one, so §11.1's "inline keyboard
    buttons per item" means one message per item — there is no way to
    put five reaction rows under five lines of a single message.
    """
    published = _published_today(ledger, hours)
    seen = radar.since(hours=hours)
    stamp = datetime.now(timezone.utc).strftime("%-d %B")
    target = sum(ledger.config["targets_7d"].values())

    out: list[tuple] = [(
        f"Scout — {stamp}\n"
        f"Published {len(published)} · Radar {len(seen)} · "
        f"Budget {ledger.used()}/{target} this week",
        None,
    )]

    for entry in sorted(
        published, key=lambda e: e.get("relevanceScore") or 0, reverse=True
    ):
        facts = _post_facts(entry["slug"])
        candidate_id = (
            (facts.get("candidateId") if isinstance(facts, dict) else None)
            or entry.get("slug")
        )
        out.append(("\n".join(_item_block(entry)), keyboard_for(candidate_id)))

    top = radar.top(limit=RADAR_PREVIEW)
    if top:
        block = ["Top of Radar (not published):"]
        for item in top:
            block.append(f"   {item['relevanceScore']:>3.0f}  {item['title'][:58]}")
            block.append(f"        {item['url']}")
        out.append(("\n".join(block), None))
        # The Radar items are addressable too: a ⭐ on one is how §6's
        # "promotion later" actually happens.
        for item in top:
            out.append((f"   {item['title'][:70]}", keyboard_for(item["id"])))
    return out


def send(text: str) -> bool:
    """One plain message, no keyboard. Used by run.py --digest --send,
    which is itself refused in a dry run and passed by nothing in this
    repository."""
    result = api.send(text)
    return bool(result and result.get("ok"))


def send_interactive(ledger: Ledger, radar: Radar) -> bool:
    """The full digest, one message per item, with keyboards.

    NOT CALLED BY ANYTHING IN THIS REPOSITORY. It exists so that turning
    the digest on is wiring rather than writing, and so the format above
    is the format that would actually be sent.
    """
    ok = True
    for text, keyboard in messages(ledger, radar):
        result = api.send(text, keyboard=keyboard)
        ok = ok and bool(result and result.get("ok"))
    return ok
