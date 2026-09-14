"""
Retract (brief §11.2) — the action the preceding draft was missing.

Because publication is automatic, a 👎 cannot undo anything. Retract
performs a git revert of the post's commit and redeploys, moving the
item to the Radar with `status: "dismissed"`. Cheap with git, and the
only way "not relevant" has real consequences without reintroducing an
approval step.

Four steps, in this order and for these reasons:

  1. FIND the commit that introduced the post file. Not the most recent
     commit touching it — a post can be amended by an entity-dedup
     update — but the one that ADDED it, which is the one whose revert
     removes it.
  2. CHECK that reverting it removes only that post. A Scout commit can
     carry several posts plus state files, and reverting the lot would
     silently unpublish work nobody objected to. If the commit touches
     another post, the file is removed directly instead.
  3. REVERT (or remove), commit, push.
  4. MOVE the item to the Radar with status "dismissed", and trigger a
     redeploy. The Radar record is the point: a retraction that left no
     trace would be indistinguishable from never having published.

    ############################################################
    #  NOTHING HERE RUNS FOR REAL IN THIS BRANCH.              #
    #                                                          #
    #  Every git command goes through _run(), which in a dry   #
    #  run PRINTS the command and returns success without      #
    #  executing it. Dry run is the default, `plan()` never    #
    #  touches git at all beyond reading history, and no       #
    #  workflow reaches this module. During this build no      #
    #  revert was performed and nothing was pushed anywhere.   #
    #  The tests exercise it against a throwaway repository    #
    #  created in a temporary directory.                       #
    ############################################################
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from core.constants import BLOG_DIR, REPO_ROOT
from core.radar import Radar


@dataclass
class Plan:
    """What a retraction WOULD do. Computed without changing anything,
    so it can be inspected, tested and printed."""

    slug: str
    path: str
    commit: str = ""
    strategy: str = ""          # "revert" | "remove" | "none"
    also_touches: list[str] = field(default_factory=list)
    commands: list[list[str]] = field(default_factory=list)
    ok: bool = False
    detail: str = ""


@dataclass
class Result:
    ok: bool
    detail: str
    slug: str | None = None
    plan: Plan | None = None


def _git(args: list[str], *, repo_root: Path) -> str:
    """Read-only git. Used for history questions, never for changes."""
    result = subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def introducing_commit(slug: str, *, repo_root: Path) -> str:
    """The commit that ADDED the post, not the last one to touch it.

    `git log --diff-filter=A` answers exactly this. Taking the most
    recent commit instead would revert an amendment — the dated line an
    entity-dedup update appends — and leave the post itself in place,
    which is the failure mode that makes a retract feature look like it
    worked when it did not.
    """
    relative = f"src/content/blog/{slug}.md"
    return _git(
        ["log", "--diff-filter=A", "--format=%H", "-1", "--", relative],
        repo_root=repo_root,
    )


def commit_touches(commit: str, *, repo_root: Path) -> list[str]:
    output = _git(
        ["show", "--pretty=", "--name-only", commit], repo_root=repo_root
    )
    return [line for line in output.split("\n") if line.strip()]


def plan(slug: str, *, repo_root: Path | None = None) -> Plan:
    """Work out what to do, touching nothing."""
    root = Path(repo_root or REPO_ROOT)
    relative = f"src/content/blog/{slug}.md"
    result = Plan(slug=slug, path=relative)

    if not (root / relative).exists():
        result.detail = (
            f"{relative} is not in the working tree — already retracted, or "
            f"never published."
        )
        result.strategy = "none"
        return result

    commit = introducing_commit(slug, repo_root=root)
    if not commit:
        # The post exists but git has never seen it: an uncommitted
        # draft. Removing the file is the whole retraction.
        result.commit = ""
        result.strategy = "remove"
        result.commands = [
            ["git", "rm", "--", relative],
            ["git", "commit", "-m", f"Retract {slug}"],
            ["git", "push"],
        ]
        result.ok = True
        result.detail = "not committed yet — the file is removed directly."
        return result

    result.commit = commit
    touched = commit_touches(commit, repo_root=root)
    other_posts = [
        p for p in touched
        if p.startswith("src/content/blog/") and p != relative
    ]
    result.also_touches = other_posts

    if other_posts:
        # THE CASE A NAIVE REVERT GETS WRONG. Reverting a commit that
        # carried three posts to retract one would silently unpublish
        # the other two. Remove just this file instead.
        result.strategy = "remove"
        result.commands = [
            ["git", "rm", "--", relative],
            ["git", "commit", "-m",
             f"Retract {slug} (commit {commit[:8]} also carried "
             f"{len(other_posts)} other post(s), so it is not reverted)"],
            ["git", "push"],
        ]
    else:
        result.strategy = "revert"
        result.commands = [
            ["git", "revert", "--no-edit", commit],
            ["git", "push"],
        ]
    result.ok = True
    result.detail = (
        f"{result.strategy} {commit[:8]}"
        + (f" (it also carried {len(other_posts)} other post(s))" if other_posts else "")
    )
    return result


def _run(command: list[str], *, repo_root: Path, dry_run: bool) -> bool:
    if dry_run:
        print(f"    [dry-run] would run: {' '.join(command)}")
        return True
    result = subprocess.run(command, cwd=repo_root, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"    FAILED: {' '.join(command)}\n    {result.stderr.strip()}")
        return False
    return True


def retract(
    item: dict,
    *,
    radar: Radar,
    dry_run: bool = True,
    repo_root: Path | None = None,
) -> Result:
    """Unpublish the post an item was promoted to, and dismiss the item.

    Dry run is the default and prints every git command instead of
    running it, so the whole sequence is inspectable without a single
    change to the repository.
    """
    root = Path(repo_root or REPO_ROOT)
    slug = item.get("promotedTo")
    if not slug:
        # An item that was never published has nothing to revert; the
        # dismissal is the whole effect, which is correct — a 🗑 on a
        # Radar item means "not this, ever", not "undo".
        radar.set_status(item["id"], "dismissed")
        return Result(True, "not published, so nothing to revert — dismissed "
                            "on the Radar.")

    steps = plan(slug, repo_root=root)
    print(f"    retract {slug}: {steps.detail}")
    if not steps.ok:
        # The post is already gone. Still dismiss the item, so the Radar
        # agrees with reality.
        radar.set_status(item["id"], "dismissed", promoted_to=slug)
        return Result(True, steps.detail, slug=slug, plan=steps)

    for command in steps.commands:
        if not _run(command, repo_root=root, dry_run=dry_run):
            return Result(False, f"git failed on: {' '.join(command)}",
                          slug=slug, plan=steps)

    # §6.1: the item moves to the Radar with status "dismissed". It is
    # not deleted — a retraction that left no trace would be
    # indistinguishable from never having published.
    radar.set_status(item["id"], "dismissed", promoted_to=slug)
    radar.save()

    _redeploy(root, dry_run=dry_run)
    return Result(
        True,
        f"retracted /blog/{slug}/ ({steps.strategy} {steps.commit[:8]}), "
        f"moved to Radar as dismissed, redeploy triggered.",
        slug=slug,
        plan=steps,
    )


def _redeploy(repo_root: Path, *, dry_run: bool) -> None:
    """A GITHUB_TOKEN push does not cascade into other workflows, so
    deploy.yml has to be kicked off explicitly — the same thing every
    other workflow in this repo does after it pushes. Without it the
    post stays live on Pages even though it is gone from main, which is
    the one outcome a retraction must not produce."""
    _run(["gh", "workflow", "run", "deploy.yml"], repo_root=repo_root, dry_run=dry_run)
