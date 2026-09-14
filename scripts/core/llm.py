"""
The one place this pipeline talks to a language model.

Three things live here that used to be scattered through
generate_blog_post.py, and one that is new.

**Model selection per task.** A classifier and a blog post are not the
same job and should not cost the same. The env var names and their
defaults are carried over verbatim from the old script, because the
news channel has to behave identically after the move.

**Lazy client construction.** The old module did
`os.environ["OPENAI_API_KEY"]` at import time, so importing it without a
key crashed. That is fine for a single-purpose script and useless for a
shared core: `run.py --channel releases --dry-run` must be runnable on a
laptop with no key at all. The key is now read when a call is actually
made, so the failure mode moved from "cannot import" to "cannot call",
and nothing that does not call is affected.

**An offline mode.** Every call site passes an `offline` callable
producing the same shape the model would. In offline mode that callable
is used instead of the API. This is what makes the scoring rubric,
the entity dedup and the verification gates testable end to end without
spending a cent or waiting a week of hourly runs — and it is not a
stub: the deterministic classifier behind `--offline-llm` is a real
implementation, just a cheaper and dumber one than a model.

Offline mode is the default whenever OPENAI_API_KEY is absent, so the
dangerous direction (accidentally calling a paid API) needs an explicit
key and the safe direction needs nothing.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable

# Same names and same defaults as the pre-refactor pipeline.
BLOG_MODEL = os.environ.get("OPENAI_BLOG_MODEL", "gpt-4o")
SUMMARY_MODEL = os.environ.get("OPENAI_SUMMARY_MODEL", "gpt-4o-mini")
GATE_MODEL = os.environ.get("OPENAI_GATE_MODEL", "gpt-4o-mini")
# New tasks, both cheap classifiers rather than writers.
CLASSIFY_MODEL = os.environ.get("OPENAI_CLASSIFY_MODEL", GATE_MODEL)
VERIFY_MODEL = os.environ.get("OPENAI_VERIFY_MODEL", GATE_MODEL)

LIVE = "live"
OFFLINE = "offline"


class LLM:
    def __init__(self, mode: str | None = None):
        if mode is None:
            mode = LIVE if os.environ.get("OPENAI_API_KEY") else OFFLINE
        self.mode = mode
        self._client = None
        self.calls = 0

    @property
    def offline(self) -> bool:
        return self.mode == OFFLINE

    def _openai(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        return self._client

    # -- the two call shapes ----------------------------------------

    def json(
        self,
        task: str,
        *,
        model: str,
        system: str | None = None,
        temperature: float = 0.0,
        offline: Callable[[], Any] | None = None,
        label: str = "",
    ) -> Any | None:
        """A strict-JSON completion. Returns the parsed object, or None
        if the call or the parse failed — callers decide whether that
        means reject or let through, because the right answer differs
        per gate and burying it here would hide it."""
        if self.offline:
            if offline is None:
                print(
                    f"    [offline] no deterministic stand-in for {label or 'this call'}"
                    f" — treating as unavailable.",
                    file=sys.stderr,
                )
                return None
            return offline()

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": task})
        try:
            self.calls += 1
            response = self._openai().chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=temperature,
            )
            return json.loads(response.choices[0].message.content or "{}")
        except Exception as exc:  # noqa: BLE001 — one bad call, not a dead run
            print(f"    LLM call failed ({label or model}): {exc}", file=sys.stderr)
            return None

    def text(
        self,
        task: str,
        *,
        model: str,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        offline: Callable[[], str] | None = None,
        label: str = "",
    ) -> str | None:
        if self.offline:
            return offline() if offline else None
        try:
            self.calls += 1
            response = self._openai().chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": task}],
                temperature=temperature,
                **({"max_tokens": max_tokens} if max_tokens else {}),
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            print(f"    LLM call failed ({label or model}): {exc}", file=sys.stderr)
            return None
