"""
Paths and tunables shared by every channel.

Anything here that is a *policy* decision rather than a fact about the
repo is named, commented and given a single definition, so widening or
narrowing it later is a one-line edit rather than a hunt through the
pipeline for a magic number.

Section, format and topic vocabularies are deliberately NOT here: they
live in /taxonomy.json and are read through core/taxonomy.py, because
the Astro site reads the same file and a second copy would drift.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# --- repo layout ----------------------------------------------------

SCRIPTS_DIR = REPO_ROOT / "scripts"
CONFIG_DIR = REPO_ROOT / "config"
# Overridable so the test suite can point every state write at a
# throwaway directory. Running the tests must not append to the repo's
# own audit logs — those lines are noise in a commit, and a test that
# dirties the working tree is a test people stop running.
STATE_DIR = Path(os.environ.get("SECURESEIN_STATE_DIR") or (REPO_ROOT / "state"))
DATA_DIR = REPO_ROOT / "data"
BLOG_DIR = REPO_ROOT / "src" / "content" / "blog"
BENCHMARK_COLLECTION_DIR = REPO_ROOT / "src" / "content" / "benchmarks"
# Decision A3: the Radar is INTERNAL ONLY. It is a content collection so
# the same Zod validation that guards posts guards it, but there is no
# /radar/ route, no nav entry, no RSS and no sitemap presence.
#
# Overridable for the same reason STATE_DIR is: a test run must not put
# rows in the committed collection, and a test that dirties the working
# tree is a test people stop running.
RADAR_COLLECTION_DIR = Path(
    os.environ.get("SECURESEIN_RADAR_DIR")
    or (REPO_ROOT / "src" / "content" / "radar")
)

TAXONOMY_FILE = REPO_ROOT / "taxonomy.json"
MODELS_REGISTRY_FILE = REPO_ROOT / "models.json"
BENCHMARKS_REGISTRY_FILE = REPO_ROOT / "benchmarks.json"
INTEREST_PROFILE_FILE = REPO_ROOT / "interest_profile.yaml"

FEEDS_NEWS_FILE = REPO_ROOT / "feeds.json"
FEEDS_RELEASES_FILE = REPO_ROOT / "feeds-releases.json"
FEEDS_BENCHMARKS_FILE = REPO_ROOT / "feeds-benchmarks.json"
FEEDS_RESEARCH_SECURITY_FILE = REPO_ROOT / "feeds-research-security.json"

LEDGER_FILE = STATE_DIR / "ledger.json"
ENTITIES_FILE = STATE_DIR / "entities.json"
QUEUE_FILE = STATE_DIR / "queue.json"
TOPIC_ACTIVITY_FILE = STATE_DIR / "topic_activity.json"
REJECTED_FILE = STATE_DIR / "rejected.jsonl"
FEEDBACK_FILE = STATE_DIR / "feedback.jsonl"
UNRESOLVED_MODELS_FILE = STATE_DIR / "unresolved_models.jsonl"
SEEN_RELEASES_FILE = STATE_DIR / "seen_releases.json"
ADAPTER_FAILURES_FILE = STATE_DIR / "adapter_failures.jsonl"
DIGEST_STATE_FILE = STATE_DIR / "digest.json"
PROFILE_PROPOSALS_FILE = STATE_DIR / "profile_proposals.jsonl"

# The four automated channels. Decision A2 removed Practice, so there is
# no practice.py and no `practice` anywhere in this pipeline.
#
# A channel is not the same thing as a section: `research` and
# `security` both read feeds-research-security.json and differ in which
# section they publish into and which §8 rules apply, and `benchmarks`
# mostly writes measurements rather than posts. Each channel declares
# its section in its own module.
CHANNELS = ("releases", "research", "security", "benchmarks")

# --- ingestion policy -----------------------------------------------

# How far back Epoch AI measurements are ingested. Their data reaches
# back to 2023; everything before this date is skipped, which keeps the
# `benchmarks` collection (one JSON file per measurement) and therefore
# the Astro build to a sane size.
#
# DEFAULT APPLIED, NOT CONFIRMED WITH THE SITE OWNER — brief §14.2. To
# widen the window, change this one date and re-run the benchmarks
# channel; nothing else in the pipeline encodes a cutoff.
EPOCH_BACKFILL_START = "2025-01-01"

EPOCH_BULK_ZIP_URL = "https://epoch.ai/data/benchmark_data.zip"
EPOCH_ATTRIBUTION = "Epoch AI, 'Capabilities & Benchmarking', https://epoch.ai/benchmarks"
EPOCH_LICENSE = "CC-BY-4.0 (Epoch AI) — attribution required wherever the numbers are shown"

# Network manners, applied to every fetch this pipeline makes.
USER_AGENT = "Mozilla/5.0 (compatible; securesein-pipeline/1.0; +https://securesein.github.io/)"
FETCH_TIMEOUT = 20
