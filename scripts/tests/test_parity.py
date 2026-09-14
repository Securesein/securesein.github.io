"""
Differential test: the refactored pipeline against the script it
replaced.

Phase 2's acceptance criterion is that `run.py --channel research
--dry-run` reproduces today's Scout decision logic. A prose claim that
the behaviour is unchanged is worth very little; this runs both
implementations over the real archive and compares them.

scripts/generate_blog_post.py is still in the tree and is loaded here
directly, with its imports and module-level side effects (an OpenAI
client, a required API key) stripped, so only the pure functions
survive — which is exactly the part of the pipeline where a silent
behaviour change would be invisible until it published something wrong:
title tokenising, story similarity, duplicate detection, the
publisher-self-reference heuristic, slugs, frontmatter parsing.

WHAT IS DELIBERATELY *NOT* ASSERTED IDENTICAL, and why:

  - `build_system_prompt`. The editorial identity changed under
    decision A2 (practitioner blog with an AI pillar -> AI research
    radar), the closed topic list changed with it, and every post now
    declares its section. Asserting byte equality would be asserting
    that the brief was not implemented. What IS asserted is that every
    carried-over block survives verbatim — AUDIENCE, VOICE, STRUCTURE,
    LENGTH & EXAMPLES — because those are the parts that produce the
    site's voice and none of them were meant to change.

  - `render`. Frontmatter gained `format` and `scout`, both required by
    the new schema. Asserted instead: the old field order is preserved
    with `format` inserted after `kind`, and nothing the old writer
    emitted has moved or changed spelling.

Everything that talks to a model or the network is deliberately not
exercised here; the control flow around it is covered by the dry-run
tests.

    python3 scripts/tests/run_tests.py
"""

from __future__ import annotations

import ast
import re
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from core import dedup, draft, frontmatter, profile  # noqa: E402

PRE_MOVE_PATH = REPO_ROOT / "scripts" / "generate_blog_post.py"


def _load_pre_move() -> types.ModuleType:
    """The old script, loaded with its imports and module-level side
    effects stripped out. Only the pure functions survive."""
    source = PRE_MOVE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    keep: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.Assign):
            # Drop the module-level client / env reads; keep literals.
            try:
                ast.literal_eval(node.value)
            except (ValueError, SyntaxError):
                continue
        keep.append(node)
    tree.body = keep

    module = types.ModuleType("pre_move_generate_blog_post")
    from datetime import date, timedelta
    from difflib import SequenceMatcher

    module.__dict__.update({
        "re": re, "json": __import__("json"), "sys": sys,
        "time": __import__("time"), "date": date, "timedelta": timedelta,
        "SequenceMatcher": SequenceMatcher, "Path": Path,
        "BLOG_DIR": REPO_ROOT / "src" / "content" / "blog",
        "TAXONOMY_FILE": REPO_ROOT / "taxonomy.json",
    })
    exec(compile(tree, "<pre-move>", "exec"), module.__dict__)
    return module


OLD = _load_pre_move()

# Real headlines out of the archive, including the three GPT-6 Astra
# posts the entity-dedup work exists because of, plus adversarial pairs
# that must NOT match.
TITLES = [
    "GPT-6 Astra: A New Era for Developers",
    "GPT-6 Astra: Redefining Intelligence and Efficiency for Developers",
    "Understanding the Impact of OpenAI's GPT-6 Astra on Enterprise Operations",
    "Gemini 3.7 Flash: The New Frontier in AI Workhorse Models",
    "Google's August AI Announcements: A Closer Look at Gemini and Pixel 11",
    "Understanding VentureBeat's Role in the AI Industry",
    "Understanding Tokens in AI Language Models",
    "Tokens: the one idea that explains most of AI's odd behaviour",
    "Intune compliance in hybrid work",
    "When AI Agents Go Rogue: The Wiki Communication Incident",
    "NVIDIA's Acquisition of Hugging Face: What's at Stake for AI Development",
    "Claude Code v2.1.267: Enhancements and Fixes You Need to Know",
    "",
    "A",
]

PUBLISHERS = [
    "VentureBeat AI",
    "Google AI Blog",
    "OpenAI News",
    "TechCrunch AI",
    "Ars Technica AI",
    "Anthropic News",
]


def test_title_tokens_identical():
    for title in TITLES:
        assert OLD._title_tokens(title) == dedup.title_tokens(title), title


def test_same_story_identical():
    for a in TITLES:
        for b in TITLES:
            assert OLD._same_story(a, b) == dedup.same_story(a, b), (a, b)


def test_publication_self_reference_identical():
    """The exclusion that catches "Understanding VentureBeat's Role in
    the AI Industry" — already in the archive, and now a standing entry
    in interest_profile.yaml's exclude[]."""
    for title in TITLES:
        for publisher in PUBLISHERS:
            assert OLD._publication_self_reference(
                title, publisher
            ) == profile.publication_self_reference(title, publisher), (title, publisher)


def test_slugify_identical():
    for title in TITLES + ["...", "Ünïcödé — em dash", "trailing   spaces   "]:
        assert OLD.slugify(title) == frontmatter.slugify(title), title


def test_frontmatter_reader_identical():
    blog = REPO_ROOT / "src" / "content" / "blog"
    files = sorted(blog.glob("*.md"))
    assert files, "no posts to compare against"
    for path in files:
        assert OLD._frontmatter(path) == frontmatter.read_frontmatter(path), path.name


def test_existing_posts_index_matches_on_the_shared_fields():
    """The archive index the duplicate check reads. The new one carries
    two extra fields (`format`, `topics`) that the starvation bonus
    needs; every field the old one had must still be identical."""
    old_rows = OLD.load_existing_posts()
    new_rows = frontmatter.existing_posts()
    assert len(old_rows) == len(new_rows)
    for old, new in zip(old_rows, new_rows):
        for field in old:
            assert old[field] == new[field], (new["slug"], field)


def test_is_duplicate_identical():
    """The real decision, over every archive post crossed with every
    test headline — both the URL branch and the title branch."""
    existing = frontmatter.existing_posts()
    urls = [None, "", "https://example.com/nothing"] + [
        p["source_url"] for p in existing if p["source_url"]
    ][:6]
    for title in TITLES:
        for url in urls:
            assert OLD.is_duplicate(title, url, existing) == dedup.is_duplicate(
                title, url, existing
            ), (title, url)


def test_task_prompts_identical():
    """The two user-message builders are unchanged, byte for byte."""
    for instructions in (None, "focus on pricing"):
        assert OLD.build_article_task(
            "T", "S", "body text", instructions
        ) == draft.build_article_task("T", "S", "body text", instructions)
    assert OLD.build_custom_task("write about tokens") == draft.build_custom_task(
        "write about tokens"
    )


def test_drafting_constants_unchanged():
    """The numbers that decide how long a post is and when the second
    pass fires. A silent change here would alter every post on the site
    and show up nowhere in a diff of the prose."""
    assert OLD.MIN_WORDS == draft.MIN_WORDS == 850
    assert OLD.TARGET_WORDS == draft.TARGET_WORDS == 1200
    assert OLD.ARTICLE_MAX_CHARS == draft.ARTICLE_MAX_CHARS == 8000
    assert OLD.STYLE_EXAMPLE_COUNT == draft.STYLE_EXAMPLE_COUNT == 2


def _blocks(text: str) -> dict[str, str]:
    """The system prompt's named blocks, split on their all-caps
    headings so each can be compared independently of the others."""
    headings = ["AUDIENCE:", "VOICE:", "STRUCTURE:", "LENGTH & EXAMPLES"]
    out = {}
    for i, heading in enumerate(headings):
        start = text.find(heading)
        if start == -1:
            continue
        end = len(text)
        for later in headings[i + 1:]:
            position = text.find(later, start + 1)
            if position != -1:
                end = min(end, position)
        # Stop at the style-examples block, which differs by construction.
        marker = text.find("The example posts below", start)
        if marker != -1:
            end = min(end, marker)
        out[heading] = text[start:end].strip()
    return out


def test_voice_blocks_carried_over_verbatim():
    """The parts of the system prompt that produce the site's voice are
    unchanged. Two blocks gained material and lost none:

      VOICE             one bullet — §8.1's vendor-claim rule
      LENGTH & EXAMPLES one paragraph — §10 G1's numeric-grounding
                        warning, so the model knows the gate exists
                        before it writes a number it half-remembers

    Everything else must be byte-identical. The parts that had to change
    under A2 — the opening identity sentence, the topic list, the
    section declaration — are covered by the next test.
    """
    old_prompt = OLD.build_system_prompt(OLD.load_topics(), [])
    new_prompt = draft.build_system_prompt([], section="research")
    old_blocks, new_blocks = _blocks(old_prompt), _blocks(new_prompt)
    assert set(old_blocks) == set(new_blocks) == {
        "AUDIENCE:", "VOICE:", "STRUCTURE:", "LENGTH & EXAMPLES",
    }

    for name in ("AUDIENCE:", "STRUCTURE:"):
        assert new_blocks[name] == old_blocks[name], name

    # VOICE: the new bullet is inserted before the closing one, so the
    # comparison is "every old line is still there, in order".
    old_lines = [l for l in old_blocks["VOICE:"].splitlines() if l.strip()]
    new_lines = [l for l in new_blocks["VOICE:"].splitlines() if l.strip()]
    assert _is_subsequence(old_lines, new_lines), "a VOICE line was changed or dropped"
    added = [l for l in new_lines if l not in old_lines]
    assert len(added) == 3, added  # one bullet, wrapped over three lines
    assert "VENDOR CLAIM" in " ".join(added)

    # LENGTH & EXAMPLES: the grounding paragraph is appended.
    assert new_blocks["LENGTH & EXAMPLES"].startswith(old_blocks["LENGTH & EXAMPLES"])
    tail = new_blocks["LENGTH & EXAMPLES"][len(old_blocks["LENGTH & EXAMPLES"]):]
    assert "deterministic check compares every number" in tail


def _is_subsequence(needle: list[str], haystack: list[str]) -> bool:
    it = iter(haystack)
    return all(line in it for line in needle)


def test_prompt_changes_are_the_expected_ones():
    """Every intentional difference is asserted present, so an
    unintended change cannot hide among the intended ones."""
    new_prompt = re.sub(r"\s+", " ", draft.build_system_prompt([], section="research"))
    # A2: the identity sentence.
    assert "an AI research radar written by a hands-on engineer" in new_prompt
    assert "enterprise mobility, and the Microsoft ecosystem" not in new_prompt
    # §3.1: the post declares its section.
    assert 'filed in the "research" section' in new_prompt
    # The closed topic list is the new thirteen, not the old seven.
    assert '"ai-security"' in new_prompt
    assert '"mobility"' not in new_prompt
    assert '"enterprise"' not in new_prompt
    assert '"selfhosted"' not in new_prompt


def test_emitted_frontmatter_is_the_old_shape_plus_the_new_fields():
    """The file Scout writes. Every line the old writer emitted is
    still emitted, in the same order and the same spelling; `format`
    slots in after `kind` and `scout` is appended."""
    post = {
        "title": 'A "quoted" headline: with punctuation',
        "description": "One sentence lede.",
        "topics": ["llms", "agents"],
        "body": "## Section\n\nSome body text.",
    }
    import json as _json
    import time as _time

    old_text = "\n".join([
        "---",
        f'title: {_json.dumps(post["title"])}',
        f'description: {_json.dumps(post["description"])}',
        f"pubDate: {_time.strftime('%Y-%m-%d')}",
        'kind: "news"',
        'topics: ["llms", "agents"]',
        'credit: "scout"',
        f"model: {_json.dumps('gpt-4o')}",
        "source:",
        f"  url: {_json.dumps('https://example.com/a')}",
        f"  publisher: {_json.dumps('Example')}",
        "---",
        "",
        post["body"],
        "",
    ])
    new_text = frontmatter.render(
        post,
        kind="research",
        fmt="news",
        model="gpt-4o",
        source_url="https://example.com/a",
        source_name="Example",
        scout={"qualityScore": 71.5, "relevanceScore": 63.0,
               "whyRelevant": "because", "candidateId": "r123"},
    )

    # Normalise the two intended differences away and the rest must
    # match exactly.
    reduced = new_text
    reduced = reduced.replace('kind: "research"\nformat: "news"', 'kind: "news"')
    reduced = re.sub(r"\nscout:\n(?:  .*\n)+", "\n", reduced)
    strip = lambda t: re.sub(r"^pubDate:.*$", "pubDate: X", t, flags=re.M)
    assert strip(reduced) == strip(old_text), (
        f"\n--- old ---\n{old_text}\n--- new (reduced) ---\n{reduced}"
    )
