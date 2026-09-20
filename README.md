# securesein

[securesein.com](https://securesein.com) — a personal AI blog, and the pipeline that partly writes it.

This repo is two things in one: an [Astro](https://astro.build) static site, and a set of Python
scripts that read AI news/research feeds, score what's worth covering, and — for some sections —
draft and publish posts with no human review at all. What ships without review, what's directed by
a human with a model drafting, and what's fully hand-written is disclosed on every post; the full
story is on the site's [About](https://securesein.com/about/) and
[Colophon](https://securesein.com/colophon/) pages.

## Layout

```
src/                  Astro site: pages, components, the content-collection schema
src/content/blog/     Every post, as markdown with frontmatter
config/                Budgets, the reading-interest profile, and the pipeline's other tunables
scripts/
  core/               Feed fetching, dedup, scoring, the ledger, LLM calls, draft writing
  channels/           One module per publishing lane (releases, research, security, benchmarks)
  telegram/           The review/digest/feedback flow over Telegram
  papers/             Reader — a separate, read-only arXiv digest (see scripts/papers/__init__.py)
.github/workflows/    CI: one workflow per channel, plus digest/feedback/deploy
```

`src/content.config.ts` is the single source of truth for what a post is allowed to look like
(section, format, up to three topics, an authorship record); `scripts/core/frontmatter.py` is what
writes to that shape from the Python side. The two have to stay in sync by hand — there's no
generated client between them.

## Running it yourself

This is a personal, opinionated setup, not a generic templated product — forking it means adapting
the config to your own taste, not flipping a switch. A few things to know going in:

- **The Python pipeline and the Astro schema are tightly coupled.** The taxonomy (which sections,
  formats and topics exist) lives in `taxonomy.json` and is read by both the site and the scripts.
  Change one without the other and posts stop validating.
- **Scheduling is external.** GitHub Actions' own `schedule` trigger isn't reliable enough for the
  timing some of these channels need, so every scheduled channel is `workflow_dispatch`-only and
  triggered by an outside cron service hitting
  `https://api.github.com/repos/<you>/<repo>/actions/workflows/<name>.yml/dispatches` with a GitHub
  token. This repo was built against [cron-job.org](https://cron-job.org); any scheduler that can
  make an authenticated POST works.
- **Secrets.** Set these as repository secrets:
  - `OPENAI_API_KEY` — drafting and scoring
  - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — the review digest and feedback loop
  - `TELEGRAM_PAPERS_CHAT_ID` — optional, only for the separate Reader digest (`scripts/papers/`)
- **Tune before you turn it loose.** `config/interest_profile.yaml` (what's worth writing about),
  `config/budgets.json` (how much it's allowed to publish and spend), and `taxonomy.json` (the
  vocabulary) are the levers. The defaults reflect one person's interests, not a neutral baseline.
- **Local dev:** `npm install && npm run dev` for the site; `pip install -r scripts/requirements.txt`
  for the pipeline. `npm run build` runs the content-collection schema as a validation gate —
  a malformed post fails the build, on purpose.

None of the content under `src/content/blog/` is covered by any implied invitation to reuse it as
your own writing — see [About](https://securesein.com/about/) for what's actually true about how
each piece was made.

## License

MIT — see [LICENSE](LICENSE). The code is yours to fork and adapt; the posts are still just posts.
