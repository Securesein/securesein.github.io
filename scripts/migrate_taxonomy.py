#!/usr/bin/env python3
"""
ONE-SHOT migration of the existing archive onto the three-axis model
(brief §3.4). Run once, commit the result, delete this file.

    python3 scripts/migrate_taxonomy.py --apply
    python3 scripts/migrate_taxonomy.py            # dry run, prints the report

WHAT IT CHANGES, AND ONLY THIS
------------------------------
Frontmatter `kind`, `format` and `topics`. Nothing else: not the body,
not the title, not the date, not `credit`, not `source`, not `hero`, not
`threads`, not `betterCoveredBy`, not the filename, and therefore not
the /blog/<slug>/ URL. Brief §2 is explicit that section remapping is a
frontmatter-only operation.

WHY IT IS A TABLE AND NOT A RULE ENGINE
---------------------------------------
Brief §3.4 asks for a deterministic, auditable script rather than an LLM
pass. The old `kind` -> new `format` half of the mapping genuinely is
mechanical and is expressed as one. The section and topic halves are
not: decision A2 (PURE AI RESEARCH RADAR) retired `mobility`,
`enterprise` and `selfhosted`, and the new vocabulary has no successor
at all for `industry` (Money & industry — funding, acquisitions, pricing,
market structure). A static old-slug -> new-slug table would therefore
either drop those posts' only topic or map a funding story onto a
research topic it is not about.

So each post carries an explicit, hand-derived decision with a written
rationale, encoded here. That is still deterministic (no model runs, the
output is a pure function of this file) and it is *more* auditable than
a rule engine, because the reasoning sits next to the result and shows
up in the diff.

Posts whose real subject does not fit any of the thirteen new topics are
marked EXCEPTION. They are not deleted, not unpublished, not hidden and
not given an invented slug — they get the closest defensible placement
and are printed loudly at the end of the report for the owner to
overrule by hand.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BLOG_DIR = REPO_ROOT / "src" / "content" / "blog"

# --- the mechanical half: old kind + old format -> new format --------
#
# §3.4's table says `deepdive -> format: deepdive`. One refinement: the
# new format vocabulary contains `paper`, and four of the seven deep
# dives already carried `format: paper` under the old vocabulary. Those
# keep it — mapping a post that is a reading of one paper onto the
# generic `deepdive` shape would throw away information the archive
# already had. Every other deep dive (teardown, postmortem, notebook)
# becomes `deepdive`.
FORMAT_FROM_OLD = {
    ("news", None): "news",
    ("explainer", None): "explainer",
    ("deepdive", "paper"): "paper",
    ("deepdive", "teardown"): "deepdive",
    ("deepdive", "postmortem"): "deepdive",
    ("deepdive", "notebook"): "deepdive",
}

# Topics that do not survive decision A2, listed so the report can say
# which posts were touched because of it rather than because of a
# routine reclassification.
RETIRED_TOPICS = {
    "mobility": "A2 — dropped from the closed vocabulary",
    "enterprise": "A2 — dropped from the closed vocabulary",
    "selfhosted": "A2 — dropped from the closed vocabulary",
    "industry": "no successor in the new vocabulary (gap predates A2)",
    "models": "split across llms / reasoning / multimodal / inference by subject",
    "agents": "carried over unchanged",
    "safety": "split across ai-safety / ai-security by whether it is a failure mode",
}

# --- the editorial half ---------------------------------------------
#
# slug -> (section, topics, rationale, flag)
#   flag: "" plain, "JUDGEMENT" non-obvious but defensible,
#         "EXCEPTION" no honest fit — needs an owner decision.
DECISIONS: dict[str, tuple[str, list[str], str, str]] = {
    # ---- clean reclassifications -----------------------------------
    "abliteration-how-one-direction-holds-a-model-s-refusals": (
        "security",
        ["interpretability", "ai-security", "llms"],
        "Guardrail removal is named in §8.4 as Security, not Research — it is a "
        "failure mode of a deployed model, not a result. The technique is "
        "interpretability, hence the second topic. Old topic `safety` -> "
        "`ai-security` (an attack), not `ai-safety`.",
        "",
    ),
    "anthropic-faster-reasoning-model": (
        "release",
        ["llms", "reasoning", "inference"],
        "A vendor shipping a model — the definition of Model Updates. Old "
        "`models` -> llms + reasoning + inference, which is what the post is "
        "actually about (a faster, cheaper reasoning model).",
        "",
    ),
    "building-an-ai-that-learns-from-experts-creating-an-organizational-second-brain": (
        "research",
        ["agents", "llms"],
        "A lab-blog systems piece about how an agent captures expert knowledge: "
        "mechanism, not an event. Old topic `industry` dropped — the post "
        "contains no funding, pricing or market-structure content; the tag was "
        "loose under the old vocabulary.",
        "JUDGEMENT",
    ),
    "catching-ai-liars": (
        "research",
        ["ai-safety", "evaluation", "llms"],
        "Nineteen teams building lie detectors is an evaluation-methodology "
        "result, and §8.4 reserves Security for attacks and incidents. Old "
        "`safety` -> `ai-safety` (model behaviour), not `ai-security`.",
        "",
    ),
    "claude-code-v2-1-267-enhancements-and-fixes-you-need-to-know": (
        "research",
        ["agents", "llms"],
        "A coding-agent CLI point release. §8.1 is explicit that runtime and "
        "tooling releases are NOT model releases, so Model Updates is closed to "
        "it, and there is no Practice section under A2. Filed under Research "
        "per §3.4's own fallback for unmappable posts. Under the new rules this "
        "item would not have been published at all — the Model Updates channel "
        "suppresses exactly this.",
        "EXCEPTION",
    ),
    "curiosity-edge-of-chaos": (
        "research",
        ["reinforcement-learning", "deep-learning"],
        "A sceptical read of an RL paper. Old `models` -> the subject matter "
        "(curiosity from internal dynamics) rather than the generic bucket.",
        "",
    ),
    "empowering-enterprises-with-chatgpt-s-new-data-agent": (
        "release",
        ["agents", "llms"],
        "OpenAI announcing a shipped capability on its own news feed — a "
        "primary-source vendor announcement, which is what Model Updates is "
        "for, even though the thing shipped is a product feature rather than a "
        "model. Old `enterprise` has no successor; the post's actual subject is "
        "an agent, so `agents` + `llms`.",
        "JUDGEMENT",
    ),
    "exploring-nvidia-s-personal-ai-router-a-new-era-of-distributed-ai-computing": (
        "research",
        ["inference", "llms"],
        "Old `selfhosted` -> `inference`: the post is about distributing local "
        "inference across RTX/DGX/Mac nodes, which is an inference-serving "
        "subject in the new vocabulary. Not Model Updates — PAIR is a router, "
        "and §8.1 puts runtime software outside that section.",
        "JUDGEMENT",
    ),
    "frontier-reasoning-on-the-edge-deploying-and-optimizing-models-with-nvidia-jetson": (
        "research",
        ["inference", "reasoning"],
        "Old `selfhosted` -> `inference`. Running reasoning models at the edge "
        "is an inference-efficiency subject; the deployment angle has no "
        "Practice section to go to under A2.",
        "JUDGEMENT",
    ),
    "gemini-3-7-flash-the-new-frontier-in-ai-workhorse-models": (
        "release",
        ["llms", "reasoning"],
        "Google DeepMind announcing a model on its own blog. Old `enterprise` "
        "dropped (A2); the post is about coding and agent-workflow capability, "
        "so llms + reasoning.",
        "",
    ),
    "google-s-august-ai-announcements-a-closer-look-at-gemini-and-pixel-11": (
        "release",
        ["llms", "multimodal"],
        "A vendor's own announcement roundup of model releases. Old `industry` "
        "dropped — this is product news, not market structure.",
        "JUDGEMENT",
    ),
    "gpt-6-astra-a-new-era-for-developers": (
        "release",
        ["llms", "agents"],
        "One of the three GPT-6 Astra posts the entity-dedup rule (§8.1) exists "
        "to collapse. All three are migrated as-is — the archive is not "
        "rewritten — but they are the proof point for the dedup test.",
        "",
    ),
    "gpt-6-astra-redefining-intelligence-and-efficiency-for-developers": (
        "release",
        ["llms", "reasoning"],
        "Second of the three GPT-6 Astra posts. Old `enterprise` dropped (A2).",
        "",
    ),
    "inside-microsoft-s-project-zenith-a-new-era-for-developer-focused-windows": (
        "research",
        ["agents", "llms"],
        "A Windows developer-experience feature. Old topics were `enterprise` "
        "(no successor under A2) and `agents`. This is not AI research and has "
        "no honest section in a pure AI research radar; filed under Research "
        "per §3.4's fallback, with `agents` as the only defensible topic.",
        "EXCEPTION",
    ),
    "intune-compliance-hybrid-work": (
        "security",
        ["ai-security"],
        "The hardest case in the archive. An Intune device-compliance post with "
        "old topics `enterprise` + `mobility`, both retired by A2, and it is "
        "not an AI piece at all. No new topic honestly describes it. Placed in "
        "Security with `ai-security` as the least-misleading pair available "
        "(it is a security-posture piece, and section and topic at least agree "
        "with each other), rather than forcing an AI-research topic onto it or "
        "hiding the post. THE OWNER SHOULD DECIDE whether this stays, gets a "
        "`betterCoveredBy`, or is retracted by hand.",
        "EXCEPTION",
    ),
    "llms-model-a-harsher-world": (
        "research",
        ["llms", "ai-safety", "evaluation"],
        "A benchmark paper about alignment-induced bias. Old `safety` -> "
        "`ai-safety` (behaviour under training pressure, not an attack).",
        "",
    ),
    "navigating-the-0-155-0-alpha-3-8-release-what-s-new-in-openai-codex": (
        "research",
        ["agents", "llms"],
        "An alpha point release of a coding CLI — same class as the Claude Code "
        "post above, and the same reasoning: §8.1 closes Model Updates to "
        "tooling releases, A2 removed Practice, so Research is the fallback. "
        "Would not be published under the new rules.",
        "EXCEPTION",
    ),
    "navigating-the-pricing-maze-with-anthropic-s-claude-commerce-agents": (
        "release",
        ["agents", "llms"],
        "Anthropic shipping an Apache-2.0 agent blueprint. Old `industry` "
        "dropped — the post is about what shipped, not about market structure, "
        "despite the pricing framing in the headline.",
        "JUDGEMENT",
    ),
    "navigating-the-unknown-preparing-for-a-world-with-reasoning-ais": (
        "research",
        ["reasoning", "ai-safety"],
        "OpenAI's own essay on reasoning models and what follows from them. Old "
        "`safety` -> `ai-safety`; old `models` -> `reasoning`.",
        "",
    ),
    "neomme-a-breakthrough-in-multimodal-and-multilingual-encoding": (
        "release",
        ["multimodal", "llms"],
        "A model released on the Hugging Face blog by the org that built it — a "
        "primary-source release. Old `models` -> `multimodal`, which is what "
        "NeoMME actually is.",
        "",
    ),
    "nvidia-s-acquisition-of-hugging-face-what-s-at-stake-for-ai-development": (
        "research",
        ["llms"],
        "A pure M&A story: NVIDIA buying Hugging Face for $12.9bn. Its only old "
        "topic was `industry`, which has NO successor in the new vocabulary — "
        "and `funding rounds, valuations, IPOs, acquisitions` is the first line "
        "of interest_profile.yaml's `exclude[]`, so the new pipeline would hard-"
        "drop this item before it was ever scored. Kept and placed in Research "
        "with `llms`, on the grounds that what is at stake is the main "
        "open-weights distribution platform. THE OWNER SHOULD DECIDE whether to "
        "retract it; nothing here hides it.",
        "EXCEPTION",
    ),
    "proactive-cyber-defense-for-governments-and-enterprises-google-s-fairwind-program-unpacked": (
        "security",
        ["ai-security"],
        "An AI-assisted cyber-defence programme. Old `safety` -> `ai-security`; "
        "old `enterprise` dropped (A2).",
        "",
    ),
    "rethinking-communication-when-reasoning-meets-information-theory": (
        "research",
        ["reasoning", "deep-learning"],
        "IBM Research on integrating reasoning into communication systems — "
        "mechanism over event, the Research section's own test. Old `enterprise` "
        "and `industry` both dropped; neither described the post.",
        "JUDGEMENT",
    ),
    "skills-or-subagents": (
        "research",
        ["agents", "llms"],
        "A paper comparing two agent-skill execution models. Clean fit.",
        "",
    ),
    "the-swarm-in-the-sandbox": (
        "security",
        ["agents", "ai-security"],
        "Agents escaping their sandbox and attacking Hugging Face is an "
        "incident, which §8.4 places in Security. Old `safety` -> `ai-security`.",
        "",
    ),
    "tokens-the-one-idea-that-explains-most-of-ai-s-odd-behaviour": (
        "explainer",
        ["llms", "training"],
        "The site's one Fundamentals piece, unchanged in section. Old `models` "
        "-> llms + training (BPE, vocabulary construction, embeddings). Its "
        "`order: 1` reading-path position is preserved.",
        "",
    ),
    "understanding-the-impact-of-openai-s-gpt-6-astra-on-enterprise-operations": (
        "release",
        ["llms", "inference"],
        "Third of the three GPT-6 Astra posts. Old `enterprise` dropped (A2); "
        "the post's substance is context window and cost, so `inference`.",
        "",
    ),
    "understanding-tokens-in-ai-language-models": (
        "explainer",
        ["llms"],
        "A concept explainer with no news hook, previously filed as news "
        "because the old vocabulary had nowhere else for a Scout-drafted "
        "explainer to go. Fundamentals is where it belongs. Its "
        "`betterCoveredBy` cross-link to the stronger piece is preserved.",
        "JUDGEMENT",
    ),
    "understanding-venturebeat-s-role-in-the-ai-industry": (
        "research",
        ["llms"],
        "A publisher-about-itself story — the sixth line of "
        "interest_profile.yaml's `exclude[]`, so the new pipeline would hard-"
        "drop it before scoring. Its only old topic was `industry`, which has "
        "no successor. Kept, placed in Research with `llms` as the least-wrong "
        "topic, and flagged: of the whole archive this is the strongest "
        "candidate for a manual retraction. Nothing here removes it.",
        "EXCEPTION",
    ),
    "unpacking-abliteration-ai-the-business-of-removing-ai-guardrails": (
        "security",
        ["ai-security", "llms"],
        "Commercial guardrail removal — §8.4 Security. Old `industry` dropped: "
        "the business angle is the frame, the guardrail removal is the subject. "
        "Part of the abliteration thread, which is preserved.",
        "JUDGEMENT",
    ),
    "when-ai-agents-go-rogue-the-wiki-communication-incident": (
        "security",
        ["agents", "ai-security"],
        "An agent incident. Old `safety` -> `ai-security`.",
        "",
    ),
    "when-ai-solves-math-the-ethics-and-implications-of-openai-s-latest-breakthrough": (
        "research",
        ["reasoning", "ai-safety"],
        "A result plus its ethics. Old `safety` -> `ai-safety`.",
        "",
    ),
    "why-dont-ml-research-agents-overfit": (
        "research",
        ["agents", "training", "deep-learning"],
        "An Amazon Science paper explaining a decade-old puzzle — mechanism "
        "first. Old `models` -> training + deep-learning.",
        "",
    ),
    "world-time-compute-lifting-ai-generalization-with-verified-code-world-models": (
        "research",
        ["reasoning", "training"],
        "An arXiv paper on verified code world models. Old `models` -> the "
        "actual subject.",
        "",
    ),
}


# --- frontmatter surgery ---------------------------------------------


def read_block(text: str) -> str:
    match = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not match:
        raise ValueError("no frontmatter block")
    return match.group(1)


def scalar(block: str, key: str) -> str | None:
    match = re.search(rf"^{key}:\s*(.+)$", block, re.M)
    if not match:
        return None
    return match.group(1).strip().strip('"')


def topic_list(block: str) -> list[str]:
    match = re.search(r"^topics:\s*\[(.*?)\]\s*$", block, re.M)
    if not match:
        return []
    return [t.strip().strip('"') for t in match.group(1).split(",") if t.strip()]


def rewrite(text: str, kind: str, fmt: str, topics: list[str]) -> str:
    """Replace exactly three lines. `format` may be absent (it was
    deep-dive-only) — in that case it is inserted directly after `kind`,
    which is where it already sits on the posts that have one, so the
    archive stays visually uniform."""
    rendered_topics = "[" + ", ".join(f'"{t}"' for t in topics) + "]"

    new = re.sub(r"^kind:\s*.+$", f'kind: "{kind}"', text, count=1, flags=re.M)
    if re.search(r"^format:\s*.+$", new, re.M):
        new = re.sub(r"^format:\s*.+$", f'format: "{fmt}"', new, count=1, flags=re.M)
    else:
        new = re.sub(
            r"^(kind:\s*.+)$", rf'\1\nformat: "{fmt}"', new, count=1, flags=re.M
        )
    new = re.sub(
        r"^topics:\s*\[.*?\]\s*$", f"topics: {rendered_topics}", new, count=1, flags=re.M
    )
    return new


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="write the changes (default: dry run)"
    )
    args = parser.parse_args()

    paths = sorted(BLOG_DIR.glob("*.md"))
    print(f"Migrating {len(paths)} posts in {BLOG_DIR}\n")

    unmapped: list[str] = []
    judgements: list[str] = []
    exceptions: list[str] = []
    touched_by_a2: list[str] = []
    rows: list[tuple] = []

    for path in paths:
        text = path.read_text(encoding="utf-8")
        block = read_block(text)
        slug = path.stem

        old_kind = scalar(block, "kind") or ""
        old_format = scalar(block, "format")
        old_topics = topic_list(block)

        key = (old_kind, old_format)
        new_format = FORMAT_FROM_OLD.get(key)
        if new_format is None:
            print(f"  !! {slug}: no format mapping for kind={old_kind!r} "
                  f"format={old_format!r} — SKIPPED", file=sys.stderr)
            unmapped.append(slug)
            continue

        decision = DECISIONS.get(slug)
        if decision is None:
            # §3.4: anything unmappable goes to research and is listed
            # for manual correction. Reached only if a post landed in
            # the archive after this table was written.
            new_kind, new_topics = "research", ["llms"]
            rationale = ("NOT IN THE DECISION TABLE — fell through to the §3.4 "
                         "default (research / llms). Needs manual correction.")
            flag = "EXCEPTION"
        else:
            new_kind, new_topics, rationale, flag = decision

        retired = [t for t in old_topics if t in ("mobility", "enterprise", "selfhosted")]
        if retired:
            touched_by_a2.append(f"{slug} (had {', '.join(retired)})")

        rows.append((slug, old_kind, old_format, old_topics, new_kind, new_format,
                     new_topics, rationale, flag))

        if flag == "JUDGEMENT":
            judgements.append(slug)
        elif flag == "EXCEPTION":
            exceptions.append(slug)

        if args.apply:
            path.write_text(rewrite(text, new_kind, new_format, new_topics),
                            encoding="utf-8")

    # --- the report --------------------------------------------------
    for (slug, ok, of, ot, nk, nf, nt, why, flag) in rows:
        marker = {"": "  ", "JUDGEMENT": "~ ", "EXCEPTION": "! "}[flag]
        print(f"{marker}{slug}")
        print(f"    kind    {ok}{'/' + of if of else ''}  ->  {nk}  (format: {nf})")
        print(f"    topics  {', '.join(ot) or '-'}  ->  {', '.join(nt)}")
        if flag:
            print(f"    [{flag}] {' '.join(why.split())}")
        print()

    print("=" * 72)
    print(f"{len(rows)} posts migrated, {len(unmapped)} skipped.")
    print(f"  plain reclassifications : {len(rows) - len(judgements) - len(exceptions)}")
    print(f"  judgement calls         : {len(judgements)}")
    print(f"  EXCEPTIONS (need owner) : {len(exceptions)}")
    print()
    print("Posts touched because decision A2 retired a topic they carried:")
    for line in touched_by_a2:
        print(f"  - {line}")
    print()
    print("EXCEPTIONS — no honest fit in the new vocabulary. Not deleted, not")
    print("hidden; placed as close as is defensible and listed here so the")
    print("owner can overrule any of them by hand:")
    for slug in exceptions:
        print(f"  - {slug}")
    if unmapped:
        print("\nUNMAPPED (left untouched, fix by hand):")
        for slug in unmapped:
            print(f"  - {slug}")

    if not args.apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
