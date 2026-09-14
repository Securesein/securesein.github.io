"""Shared pipeline core: feeds, state, dedup, ledger, llm, verify,
frontmatter and registry resolution. Channel modules (scripts/channels/)
are thin on top of this; nothing here knows about a specific channel."""
