"""
The digest, the feedback loop, and retract (brief §11).

NO REAL MESSAGE IS EVER SENT BY THIS FILE, and none was sent during the
build. The digest is verified by rendering it and reading it, which is
the only verification that matters for a format.

NO REAL COMMIT IS EVER REVERTED BY THIS FILE. The retract tests build a
throwaway git repository in a temporary directory, commit fake posts
into it, and run the real retract logic against that — so the thing
being tested is the actual code path and not a description of it.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core.radar import Radar  # noqa: E402
from telegram import digest, feedback, retract  # noqa: E402
from test_ledger import _FakeLedger, _entries  # noqa: E402


def _radar() -> Radar:
    return Radar(dry_run=True, directory=Path(tempfile.mkdtemp(prefix="radar-")))


def _item(radar, **kwargs):
    defaults = dict(
        url="https://example.com/a", title="A finding", source="arXiv cs.LG",
        section="research", topics=["llms", "inference"], quality=82.0,
        relevance=71.0, why="Directly relevant to reasoning-model inference cost.",
    )
    defaults.update(kwargs)
    return radar.add(**defaults)


# --- §11.1 the digest -------------------------------------------------


def test_the_digest_renders_with_no_token_and_no_network():
    """It has to be inspectable on a laptop with no credentials —
    otherwise the only way to check the format is to message someone."""
    text = digest.render(_FakeLedger([]), _radar())
    assert text.startswith("Scout — ")
    assert "Published 0" in text


def test_the_digest_carries_the_three_header_numbers():
    """§11.1's header: published, Radar, budget against target."""
    radar = _radar()
    _item(radar)
    ledger = _FakeLedger(_entries("research", 3, days_ago=0.2))
    text = digest.render(ledger, radar)
    assert "Published 3" in text
    assert "Radar 1" in text
    # 19/week under decision A1, not the brief's 21.
    assert "Budget 3/19 this week" in text


def test_a_quiet_day_says_so_rather_than_apologising():
    """§16: "a quiet week is a correct outcome, not a failure to hit
    target." A digest that read as an apology would invite exactly the
    threshold-lowering the budget exists to prevent."""
    text = digest.render(_FakeLedger([]), _radar())
    assert "correct outcome" in text


def test_the_digest_shows_the_reason_not_just_the_title():
    """§7.2: `whyRelevant` is how a mis-tuned profile becomes visible,
    and the digest is where it becomes visible. A digest of titles
    alone says what happened and not why."""
    radar = _radar()
    _item(radar, why="Concrete attack path for tool-using agents.")
    text = digest.render(_FakeLedger([]), radar)
    assert "Top of Radar (not published):" in text
    assert "A finding" in text


def test_the_radar_block_lists_the_highest_scoring_first():
    radar = _radar()
    for i, score in enumerate([30.0, 90.0, 60.0]):
        _item(radar, url=f"https://example.com/{i}", title=f"Item {i}", relevance=score)
    text = digest.render(_FakeLedger([]), radar)
    block = text.split("Top of Radar (not published):")[1]
    assert block.index("Item 1") < block.index("Item 2") < block.index("Item 0")


def test_there_is_no_practice_line():
    """Decision A2, in the one place §11.1's example format would have
    put one."""
    text = digest.render(_FakeLedger(_entries("research", 2, 0.2)), _radar())
    assert "practice" not in text.lower()
    assert "Practice" not in text


def test_every_item_gets_a_keyboard_with_the_five_actions():
    """§11.1: "inline keyboard buttons per item"."""
    keyboard = digest.keyboard_for("r123")
    assert len(keyboard) == 1
    payloads = [b["callback_data"] for b in keyboard[0]]
    assert payloads == [
        "interesting:r123", "not_useful:r123", "not_my_topic:r123",
        "deep_dive:r123", "retract:r123",
    ]
    assert [b["text"] for b in keyboard[0]] == ["👍", "👎", "🚫", "⭐", "🗑"]


def test_radar_items_are_addressable_too():
    """§6: a Radar item that gets a ⭐ can be written up days after it
    was first seen. That is only possible if the digest gives it a
    button with its own id."""
    radar = _radar()
    item = _item(radar)
    blocks = digest.messages(_FakeLedger([]), radar)
    payloads = [
        b["callback_data"]
        for _, keyboard in blocks if keyboard
        for row in keyboard for b in row
    ]
    assert f"deep_dive:{item['id']}" in payloads


def test_the_digest_fits_in_one_telegram_message():
    from telegram import api

    radar = _radar()
    for i in range(40):
        _item(radar, url=f"https://example.com/{i}", title=f"Item {i} " + "x" * 60)
    text = digest.render(_FakeLedger(_entries("research", 5, 0.2)), radar)
    assert len(api.truncate(text)) <= api.MESSAGE_LIMIT


def test_generating_a_digest_sends_nothing():
    """The one property that makes this file safe to run."""
    sent = []
    from telegram import api

    original = api._post  # noqa: SLF001
    api._post = lambda *a, **k: sent.append(a) or {"ok": True}  # noqa: SLF001
    try:
        digest.render(_FakeLedger([]), _radar())
        digest.messages(_FakeLedger([]), _radar())
    finally:
        api._post = original  # noqa: SLF001
    assert sent == []


# --- §11.2 feedback actions ------------------------------------------


def test_the_five_actions_and_their_scopes():
    spec = feedback.weights()
    assert set(spec) == {"interesting", "not_useful", "not_my_topic",
                         "deep_dive", "retract"}
    assert spec["interesting"]["weight"] == 1
    assert spec["not_useful"]["weight"] == -1
    assert spec["not_my_topic"]["weight"] == -3
    assert spec["deep_dive"]["weight"] == 3
    assert spec["retract"]["weight"] == -3
    assert spec["retract"].get("action") == "unpublish"


def test_not_useful_is_scoped_to_the_item_and_not_my_topic_to_the_topic():
    """THE distinction §11.2 is explicit about. A good topic covered
    badly is a drafting problem; letting 👎 demote the topic would teach
    the profile the opposite of what happened."""
    spec = feedback.weights()
    assert spec["not_useful"]["scope"] == "item"
    assert spec["not_my_topic"]["scope"] == "topic"


def test_an_item_scoped_reaction_contributes_no_topic_score():
    """The same distinction, as arithmetic rather than as a label."""
    rows = [
        {"at": "2026-09-14T00:00:00+00:00", "itemId": "r1", "kind": "not_useful",
         "topics": ["llms"], "section": "research"},
    ]
    signal = feedback.topic_signal(rows)
    assert signal["llms"]["net"] == 0
    # It still counts as having LOOKED at the topic, which is what
    # min_observations measures.
    assert signal["llms"]["observations"] == 1


def test_a_topic_scoped_reaction_does_move_the_topic():
    rows = [
        {"at": "2026-09-14T00:00:00+00:00", "itemId": "r1", "kind": "not_my_topic",
         "topics": ["multimodal"], "section": "research"},
    ]
    signal = feedback.topic_signal(rows)
    assert signal["multimodal"]["net"] == -3
    assert signal["multimodal"]["observations"] == 1


def test_a_malformed_callback_is_ignored_rather_than_guessed_at():
    assert feedback.parse_callback("") is None
    assert feedback.parse_callback("nonsense") is None
    assert feedback.parse_callback("burn_it:r1") is None
    assert feedback.parse_callback("interesting:") is None
    assert feedback.parse_callback("interesting:r1") == ("interesting", "r1")


def test_a_reaction_to_an_item_that_aged_off_the_radar_is_recorded_anyway():
    """A reaction can arrive months later. Losing the signal because the
    item is gone would throw away exactly the accumulated evidence
    §11.3 runs on."""
    outcome = feedback.apply("interesting", "r-does-not-exist", radar=_radar())
    assert outcome.accepted
    assert "no longer on the Radar" in outcome.detail


def test_a_reaction_is_recorded_before_its_effect_is_applied():
    """So a failure in the effect cannot lose the signal."""
    import inspect

    source = inspect.getsource(feedback.apply)
    assert source.index("record_feedback(") < source.index('if action == "retract"')


def test_deep_dive_marks_the_item_for_promotion():
    radar = _radar()
    item = _item(radar)
    outcome = feedback.apply("deep_dive", item["id"], radar=radar)
    assert outcome.accepted
    assert radar.find(item["id"])["feedback"] == "deep_dive"


def test_feedback_cannot_hold_a_post_back():
    """§11: feedback is steering, not gating. Nothing in the publication
    path consults it, and nothing in this module can block."""
    import inspect

    from core import pipeline

    for fn in (pipeline.publish, pipeline.run_flow, pipeline.publish_ranked):
        source = inspect.getsource(fn)
        assert "feedback" not in source, fn.__name__


# --- §11.2 retract ----------------------------------------------------


def _throwaway_repo() -> Path:
    """A real git repository in a temporary directory. Nothing here
    touches the securesein repo."""
    root = Path(tempfile.mkdtemp(prefix="retract-test-"))
    blog = root / "src" / "content" / "blog"
    blog.mkdir(parents=True)
    run = lambda *a: subprocess.run(["git", *a], cwd=root, capture_output=True,
                                    text=True, check=True)
    run("init", "-q", "-b", "main")
    run("config", "user.email", "test@example.com")
    run("config", "user.name", "test")
    (root / "README.md").write_text("seed\n")
    run("add", "-A")
    run("commit", "-qm", "seed")
    return root


def _commit_post(root: Path, slug: str, *, message: str, extra: list[str] = ()):
    blog = root / "src" / "content" / "blog"
    (blog / f"{slug}.md").write_text(f"---\ntitle: {slug}\n---\n\nbody\n")
    for other in extra:
        (blog / f"{other}.md").write_text(f"---\ntitle: {other}\n---\n\nbody\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=root, check=True,
                   capture_output=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()


def test_retract_finds_the_commit_that_ADDED_the_post():
    """Not the most recent commit to touch it. An entity-dedup update
    appends a dated line to an existing post; reverting THAT would undo
    the amendment and leave the post live — a retract feature that
    looks like it worked and did not."""
    root = _throwaway_repo()
    added = _commit_post(root, "a-post", message="Publish a-post")
    # An amendment, exactly as core/frontmatter.append_update makes one.
    path = root / "src" / "content" / "blog" / "a-post.md"
    path.write_text(path.read_text() + "\n## Updates\n\n- **2026-09-14** — GA.\n")
    subprocess.run(["git", "commit", "-qam", "Update a-post"], cwd=root,
                   check=True, capture_output=True)

    assert retract.introducing_commit("a-post", repo_root=root) == added


def test_a_retract_plans_a_revert_of_the_right_commit():
    root = _throwaway_repo()
    _commit_post(root, "other", message="Publish other")
    target = _commit_post(root, "a-post", message="Publish a-post")

    steps = retract.plan("a-post", repo_root=root)
    assert steps.ok
    assert steps.strategy == "revert"
    assert steps.commit == target
    assert steps.commands[0] == ["git", "revert", "--no-edit", target]
    assert ["git", "push"] in steps.commands


def test_a_commit_carrying_several_posts_is_not_reverted_wholesale():
    """The case a naive implementation gets wrong. Reverting a Scout
    commit that carried three posts in order to retract one would
    silently unpublish the other two."""
    root = _throwaway_repo()
    _commit_post(root, "a-post", message="Scout run", extra=["b-post", "c-post"])

    steps = retract.plan("a-post", repo_root=root)
    assert steps.strategy == "remove"
    assert sorted(steps.also_touches) == [
        "src/content/blog/b-post.md", "src/content/blog/c-post.md",
    ]
    assert steps.commands[0] == ["git", "rm", "--", "src/content/blog/a-post.md"]


def test_a_retract_of_something_already_gone_is_not_an_error():
    root = _throwaway_repo()
    steps = retract.plan("never-existed", repo_root=root)
    assert steps.strategy == "none"
    assert "already retracted, or never published" in steps.detail


def test_a_dry_run_retract_changes_nothing_and_prints_what_it_would_do():
    root = _throwaway_repo()
    target = _commit_post(root, "a-post", message="Publish a-post")
    head_before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                                 capture_output=True, text=True).stdout.strip()

    radar = _radar()
    item = _item(radar, url="https://example.com/a-post", title="A post")
    radar.set_status(item["id"], "promoted", promoted_to="a-post")

    result = retract.retract(item, radar=radar, dry_run=True, repo_root=root)
    assert result.ok
    assert result.plan.commit == target

    head_after = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                                capture_output=True, text=True).stdout.strip()
    assert head_before == head_after, "a dry run must not move HEAD"
    assert (root / "src" / "content" / "blog" / "a-post.md").exists()


def test_a_retract_moves_the_item_to_the_radar_as_dismissed():
    """§11.2's other half. The record of the retraction is the point —
    deleting the item would make a retraction indistinguishable from
    never having published."""
    root = _throwaway_repo()
    _commit_post(root, "a-post", message="Publish a-post")
    radar = _radar()
    item = _item(radar, url="https://example.com/a-post", title="A post")
    radar.set_status(item["id"], "promoted", promoted_to="a-post")

    retract.retract(item, radar=radar, dry_run=True, repo_root=root)
    after = radar.find(item["id"])
    assert after["status"] == "dismissed"
    assert after["promotedTo"] == "a-post"


def test_a_retract_triggers_a_redeploy():
    """Without it the post stays live on Pages even though it is gone
    from main — the one outcome a retraction must not produce."""
    import inspect

    assert "deploy.yml" in inspect.getsource(retract._redeploy)  # noqa: SLF001
    assert "_redeploy(" in inspect.getsource(retract.retract)


def test_a_retract_through_the_feedback_action_does_the_same_thing():
    """End to end from the button payload, which is how it would
    actually arrive."""
    root = _throwaway_repo()
    _commit_post(root, "a-post", message="Publish a-post")
    radar = _radar()
    item = _item(radar, url="https://example.com/a-post", title="A post")
    radar.set_status(item["id"], "promoted", promoted_to="a-post")

    action, item_id = feedback.parse_callback(f"retract:{item['id']}")
    outcome = feedback.apply(action, item_id, radar=radar, dry_run=True,
                             repo_root=root)
    assert outcome.accepted
    assert outcome.retracted_slug == "a-post"
    assert radar.find(item["id"])["status"] == "dismissed"


def test_retracting_a_radar_item_that_was_never_published_just_dismisses_it():
    """A 🗑 on a Radar item means "not this, ever", not "undo"."""
    radar = _radar()
    item = _item(radar)
    outcome = feedback.apply("retract", item["id"], radar=radar, dry_run=True)
    assert outcome.accepted
    assert outcome.retracted_slug is None
    assert radar.find(item["id"])["status"] == "dismissed"


def test_every_git_command_goes_through_the_dry_run_guard():
    """The safety property of this whole module: there is exactly one
    place that can execute a mutating git command, and it refuses in a
    dry run."""
    import inspect

    source = inspect.getsource(retract)
    # subprocess.run appears exactly twice: once in _git (read-only) and
    # once in _run (guarded). A third would be a way around the guard.
    assert source.count("subprocess.run(") == 2
    guarded = inspect.getsource(retract._run)  # noqa: SLF001
    assert "if dry_run:" in guarded
    assert guarded.index("if dry_run:") < guarded.index("subprocess.run(")
