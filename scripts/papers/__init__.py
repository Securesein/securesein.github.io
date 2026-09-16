"""
Reader (build brief §9) — a personal reading digest, deliberately separate
from Scout's publishing pipeline.

Scout asks "is this worth publishing to the world?" (quality gate 65,
19/week budget, a bad answer is a public mistake). Reader asks "is this
worth my ten minutes?" (whatever survives to a 6-item daily cap, a bad
answer costs 30 seconds). One ranker cannot serve both without being
wrong for one of them, so this package imports only two things from the
rest of scripts/ — telegram/api.py and core/llm.py — and reimplements
everything else (feeds, dedup, scoring) rather than reusing Scout's, so a
Scout refactor can never silently change what Reader does.
"""
