"""
The Security channel — "What can go wrong?" (brief §8.4).

Covers the security and safety of AI SYSTEMS: prompt injection,
jailbreaks and guardrail removal, agent hijacking, tool abuse, data
exfiltration and memorisation, adversarial robustness, model supply
chain (weights, MCP servers), and AI security incidents.

Two placement rules, both enforced in code:

  1. **Reward hacking and specification gaming belong here, not in
     Research.** They are failure modes, not results. The classifier's
     section patterns put them here, and `interest_profile.yaml` says
     the same thing in its note on reinforcement learning.

  2. **A defensive tooling release is rarely post-worthy on its own;
     the ATTACK CLASS it responds to is.** A new garak probe family is
     a Security post; garak v0.x.y is not. This is a hard reject rather
     than a score penalty, because the defensive-tool repos in
     feeds-research-security.json (garak, llm-guard, Guardrails AI,
     Inspect, mcp-scan, MCP servers) ship constantly and a penalty is
     something a quiet week overcomes.

Where a finding has a concrete enterprise consequence — an agent that
can be hijacked through a document, an MCP server that leaks credentials
— the section rules handed to the drafter require saying what a
practitioner should actually do about it. Under decision A2 there is no
Practice section for that to bridge to, so the advice lives inside the
Security post rather than being split out.

    python scripts/run.py --channel security [--dry-run]
"""

from __future__ import annotations

import re

from core import pipeline
from core.constants import FEEDS_NEWS_FILE, FEEDS_RESEARCH_SECURITY_FILE
from core.profile import ROUNDUP_SOURCES, profile as load_profile_object

CHANNEL = "security"
SECTION = "security"
SOURCE_FILES = (FEEDS_RESEARCH_SECURITY_FILE, FEEDS_NEWS_FILE)

# Repos whose releases are defensive TOOLING. Their feed rows are all
# tier `corroborating` or `community` already, but tiering alone would
# still let a quiet week publish a scanner's point release, so the rule
# is stated here as well.
DEFENSIVE_TOOLS = {
    "garak (NVIDIA) — LLM vulnerability scanner",
    "llm-guard (Protect AI)",
    "Guardrails AI",
    "Inspect (UK AI Security Institute)",
    "mcp-scan (Invariant Labs)",
    "Model Context Protocol — servers",
    "OWASP Top 10 for LLM Applications",
    "MITRE ATLAS — navigator data",
}

# What makes a defensive-tool item worth looking at anyway: it is about
# the attack, not the release. A new probe family, a newly covered
# technique, a documented bypass.
ATTACK_CLASS = re.compile(
    r"\b(probe|new (?:attack|technique|vector|class)|bypass|"
    r"injection|jailbreak|exfiltrat|hijack|poison|backdoor|"
    r"vulnerab|advisory|\bcve\b|exploit|threat)\b",
    re.I,
)
# A version-shaped title with nothing else in it is a point release.
VERSION_ONLY = re.compile(r"^\s*v?\d+(\.\d+)+[\w.\-]*\s*$")

SECTION_RULES = """SECTION RULES — Security:
- The subject is the ATTACK CLASS or the FAILURE MODE, never the tool
  that responds to it. If the post could be retitled as a release
  announcement, it is the wrong post.
- Say concretely what an attacker does and what they get. A threat
  described only in the abstract cannot be defended against.
- Where the finding has a practitioner consequence — an agent that can
  be hijacked through a document it reads, an MCP server that leaks
  credentials — say what someone responsible for a system should
  actually do about it, specifically enough to act on.
- Reward hacking and specification gaming are failure modes and belong
  in this section. Write them as such, not as results.
- Do not overstate severity and do not understate it. If the attack
  needs conditions that rarely hold, say which."""


def _not_post_worthy(item) -> str | None:
    """The two §8.4 hard rejects, plus §8.3's roundup rule which applies
    here for the same reason."""
    if item.source.name in ROUNDUP_SOURCES:
        return "roundup_only_source"
    if item.source.name in DEFENSIVE_TOOLS:
        text = f"{item.title}\n{item.summary}"
        if VERSION_ONLY.match(item.title or "") or not ATTACK_CLASS.search(text):
            # garak v0.x.y is not a Security post; a new garak probe
            # family is.
            return "no_product_angle"
    return None


def run(ctx) -> int:
    outcome = pipeline.run_flow(
        ctx,
        channel=CHANNEL,
        sections=(SECTION,),
        source_files=SOURCE_FILES,
        extra_reject=_not_post_worthy,
    )

    prof = load_profile_object()
    stats = pipeline.gate_stats(outcome.scores, prof)
    if stats.get("n"):
        print(f"  quality gate: {stats['passed']}/{stats['n']} passed "
              f"({stats['pass_rate']:.0%}), median {stats['median']}, "
              f"p75 {stats['p75']}, p90 {stats['p90']}, threshold {stats['threshold']}")

    return pipeline.publish_ranked(
        ctx, outcome, channel=CHANNEL, section=SECTION, section_rules=SECTION_RULES
    )
