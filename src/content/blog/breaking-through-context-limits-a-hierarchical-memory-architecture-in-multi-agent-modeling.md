---
title: "Breaking Through Context Limits: A Hierarchical Memory Architecture in Multi-Agent Modeling"
description: "A three-layer memory architecture keeps a team of AI agents working on the same pharmacology project for weeks, by capping and evicting state instead of remembering everything."
pubDate: 2026-09-21
updatedDate: 2026-09-21
kind: "research"
format: "paper"
topics: ["agents", "evaluation"]
credit: "directed"
model: "Claude"
contributions:
  chose: true
  checked: true
  rewrote: true
source:
  url: "https://arxiv.org/abs/2607.07666"
  publisher: "arXiv cs.MA"
---

*This post replaces an earlier, auto-published draft that talked around the paper's actual mechanism and — worse — illustrated it with two invented scenarios (a smart-grid example, a financial-modeling failure mode) that don't appear in the source at all. This version is checked directly against the paper and its full text; see the disclosure box below for what changed and why it won't recur.*

Give a language model a long-running project — one that spans weeks and dozens of separate conversations — and it forgets everything the moment the session ends. The usual patch is to paste the entire prior transcript back in at the start of the next one. That works for a session or two. By session twenty it doesn't: the model is re-reading tens of thousands of tokens about a solver setting that got fixed in week one, and burying the one detail that still matters under everything that doesn't.

A paper by Shivendra G. Tewari and Holly Kimko, posted to arXiv in July 2026, builds a system called Ensemble QSP that avoids this entirely — not by summarizing the transcript better, but by refusing to carry the transcript forward at all. Instead of one memory that grows with the conversation, it uses three, each with a hard size limit, and each thrown out or refreshed on its own schedule.

## The problem with just pasting the conversation back in

The naive approach — concatenate the full history and hand it to the model each time — has a name in the paper: it grows as O(N×T), the context size scaling with both the number of sessions (N) and the length of each one (T). Session 1 might run 8,000 tokens. Session 5 is 40,000. By session 20 you're well past 150,000, and long before you get there the model's actual reasoning has degraded — not because it ran out of room, but because the signal is diluted across acres of resolved, irrelevant history.

Ensemble QSP's answer is to make the injected context **constant** with respect to project duration — session 20 starts with roughly the same amount of context as session 2 — by never letting any single layer of memory grow unboundedly in the first place.

## Three layers, each capped differently

**Short-term** is what's live *right now*, rebuilt every turn: a rolling window of the 4 to 20 most recent conversation turns (the exact number depends on the underlying model's own context size), a scratchpad capped at 20,000 characters for a specialist agent and 8,000 for the project lead, and a buffer of the five most recent results from other agents. This is where an agent parks a fact it needs to survive the next truncation — an exact file path, a parameter index, a data column name — because once the conversation window slides past it, it's gone from short-term memory whether or not it still matters.

Picture a session where an agent is fitting a stiff system of differential equations and the solver keeps failing to converge. Rather than let that struggle sprawl across the conversation transcript, the scratchpad holds only what's still actionable: which solver is currently selected, which tolerance was last tried, what the residual looks like now. When the session ends, this entire layer is discarded. Nobody needs to know in session 17 which solver tolerance got tried and rejected in session 12 — that fact did its job and is allowed to disappear.

**Mid-term** is the layer the paper is actually about, and it's not a summary of the conversation — it's a structured JSON record with fixed fields, rewritten at the end of every session rather than appended to. The fields are specific: the five most recently active user requests (with a running total so older ones aren't simply forgotten), the 20 most-recently-modified files, recent computing jobs, milestones reached, and the last three session summaries — paired with a separate, auto-summarized decision log capped at 16,000 characters that records *why* each choice was made.

Three mechanisms keep this layer from becoming the same unbounded pile the naive approach produces:

- **Capping.** Every category has a ceiling — 20 files, five requests, three summaries. There's no "just this once" overflow.
- **Eviction.** Finished work is deleted, not archived. Once a model-fitting task is done, it drops out of the active task list and a single line is added under milestones — the record doesn't accumulate, it turns over.
- **Selective injection.** Even within that cap, not every field goes to every agent. An agent writing a report is handed milestones and files; an agent debugging code is handed the open issues and running jobs. Each gets only the slice relevant to what it's doing.

Measured across 104 real project runs, this layer landed at a median of 301 tokens, with an interquartile range of 215 to 478 and a maximum of 4,050 — bounded and roughly flat, whichever session number you're looking at. That's the paper's own italicized point about session 20 costing the same as session 2: not a smaller number than a raw transcript, an *architecturally different kind of number*, one that doesn't grow just because time has passed.

**Long-term** is domain knowledge that doesn't belong to any one project: a roughly 24,000-character modeling handbook injected into every specialist agent by default, plus per-domain physics checklists and reference material that's retrieved only when it's actually needed — when a code-review step triggers a physics-validation check, for instance, the relevant checklist and the original source paper's text get pulled in for that step and dropped again afterward, rather than sitting in context the whole time on the chance they'll be needed.

## Who's actually doing the work

A principal investigator agent — playing the role of a domain expert — delegates to five specialist sub-agents with non-overlapping jobs: optimization, modeling, reporting, infrastructure, and code review. The PI doesn't write code; it enforces the physics checklists and catches results that are internally consistent but scientifically wrong, which is a different failure mode than a bug.

## Did it actually work better?

On a benchmark of 20 synthetic pharmacokinetic-pharmacodynamic (PKPD) datasets — six model structures built from two pharmacokinetic models crossed with three response-shape models — the system picked the correct model structure for all 20 on the first attempt, with no human stepping in. The comparison baseline, GitHub Copilot used as a single-pass assistant, got 14 of 20 right, and only after nine rounds of a human manually redirecting it — which works out to 180 separate fitting scripts written and discarded along the way, against one batch job that produced all 20 fits at once. The gap was sharpest on the eight datasets requiring an indirect-response model, the kind that needs a stiff ODE solver with correctly chosen initial conditions: the multi-agent system got all eight, with a median parameter error of 14.1%, where Copilot got five of eight with a median error of 68.4%.

The result wasn't tied to using an expensive frontier model. The authors re-ran the hardest 11 of those 20 datasets with open-weight models standing in for the original Claude Opus writer — DeepSeek-V4-Flash, a notably cheaper model, and DeepSeek-V4-Pro — and both, plus the frontier baseline, got all 11 right. Flash's parameter accuracy came within a fraction of a percentage point of the frontier model's (6.8% median error versus 7.0%). The architecture, not the specific model behind it, was doing the load-bearing work.

## What the paper's own ablation study found

The most interesting numbers in the paper aren't the headline comparisons — they're from deliberately breaking one component at a time while reproducing a published four-compartment pharmacokinetic model, and watching what actually failed.

With everything switched on, the system reproduced the target concentration curves with a mean R² of 0.604 in 39.7 minutes. Switching off structured task-tracking produced the *highest* R² of any configuration, 0.768 — and the paper is explicit that this is not a win: without a persistent task record, the agent drifted off the requested forward-simulation task and quietly wrote an entirely different, unrequested parameter-fitting script instead. It fit the data better because it stopped doing the job it was asked to do. Switching off retrieval of the source publication (relying on the model's general domain knowledge instead) produced a 23.7% error on the peak drug concentration — a case where the architecture's other layers couldn't substitute for actually being allowed to look the paper up. Removing the PI's review step didn't stop the system from producing an answer, just a less accurate one (R² 0.631, versus 0.604 with review — interestingly still lower than the full system's baseline scenario mix, since PI oversight also catches and corrects errors mid-run that a bare run doesn't). And in three separate adversarial tests designed to tempt the system into inventing citations for source material it couldn't actually retrieve, it declined every time rather than fabricating an answer.

## Where the paper is honest about its own limits

The authors' own limitations section is worth reading directly rather than paraphrasing away. Validation is confined to pharmacology — the system has since been extended to body-weight modeling and cardiac electrophysiology without changing the orchestration logic, which the authors offer as *structural evidence* the architecture generalizes, not as proof that it does. Adding a genuinely new scientific domain still means an expert has to hand-write that domain's physics checklists, which is a real, recurring cost the architecture doesn't remove. The only baseline compared against is GitHub Copilot; the authors say plainly that broader comparisons against multi-agent frameworks like AutoGen or CrewAI weren't feasible given their setup. And reported wall-clock times reflect real infrastructure — API rate limits, shared compute queues — as much as they reflect the model's own speed, which the paper flags rather than hides.

One correction worth being explicit about: the code, prompts, benchmark datasets, and archived run metadata for every reported result are publicly deposited on Zenodo under a real DOI, not withheld — a detail worth stating plainly because it's easy to assume otherwise of a system this elaborate.

## Why this generalizes past pharmacology

Strip out the PKPD-specific detail and what's left is a fairly general claim: for any agent doing long-horizon work, the fix for context bloat isn't a better summary of the conversation, it's replacing the conversation with a small number of capped, typed fields that get evicted the moment they're no longer relevant. A rolling summary of a transcript still grows, slowly, because there's always more transcript. A capped form with five fields and a hard limit per field doesn't grow at all — its *contents* change, but its size doesn't. That distinction is the entire reason a number like "median 301 tokens, flat across 104 runs" is even a sentence you can write.
