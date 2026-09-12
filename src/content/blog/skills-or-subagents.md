---
title: "Skills or subagents? How you run reusable knowledge matters as much as what's in it"
description: "A new paper compares two ways of executing agent skill packages, and finds that subagents only win when a skill declares what it needs and what it returns."
pubDate: 2026-09-10
kind: "deepdive"
format: "paper"
topics: ["agents"]
credit: "directed"
contributions:
  chose: true
  checked: true
model: "Claude"
heroAlt: "Agent-skill execution keeps everything in one growing context window; subagent execution spreads the same skill packages across separate windows and returns only results"
hero: "/images/skills-or-subagents/hero.svg"
---

Agent skills have become the standard way to hand domain knowledge to an LLM agent: a folder with a description, a `SKILL.md` full of instructions, and whatever scripts or reference files come with it. Most of the attention so far has gone to writing better skills. A paper from Cornell and Microsoft Research Cambridge asks a different question — not what goes into a skill, but how it should be executed.

## Two ways to run the same skill

A skill package is formally just three parts: a short description the agent sees when deciding whether to use the skill, an instruction file describing the procedure, and a bag of supporting resources. Nothing about that package dictates how it runs. There are two options.

**Agent-skill execution** is what most harnesses do today. The agent invokes the skill, the instruction file gets pasted into its context, and the agent carries out the steps itself as ordinary turns in the same conversation.

**Subagent execution** uses the same package differently. Instead of loading the instructions inline, the harness spins up a fresh context window seeded with the instruction file and the specific task input. That subagent does the work in isolation and returns only its final answer. The main agent never sees the intermediate steps.

![Agent-skill execution keeps everything in one growing context window; subagent execution spreads the same skill packages across separate windows and returns only results.](/images/skills-or-subagents/skill-vs-subagent-execution.svg)

## Why this matters: peak context, not total tokens

The motivation is a well-documented failure mode: LLM reasoning degrades as context grows, even when retrieval is perfect. Long-horizon agentic tasks are exactly where this bites — verbose tool outputs, intermediate reasoning, and retries pile up turn after turn. Loading more skill instructions into that same window makes it worse.

The authors point out that what hurts is not the total number of tokens spent on a task, but the **peak** context length any single window has to reason over. Split a task across several windows and each one stays smaller. They frame this as information encapsulation: a subagent's messy internal trajectory is hidden, and the main agent gets a cleaner, shorter picture to reason about.

The cost is communication overhead. A subagent can't see the main context, so anything it needs has to be handed to it explicitly — which means duplicating information across windows. Subagent execution buys lower peak context by spending more tokens overall.

## The catch: skills need input-output contracts

Here's the part worth internalising if you write skills yourself. Subagents introduce a delegation problem that agent skills don't have. The main agent has to pick the right subagent *and* supply everything it needs, blind. Get either wrong and the subagent fails.

So the skill description has to carry more than a summary of purpose. It needs to state explicitly what information the skill expects, and what it hands back. The paper structures the description as three parts — expected input, a short summary, and expected output — and requires the instructions to actually deliver on that promise. One of their examples, a vulnerability-scanning skill, declares that it expects the lockfile path and desired report path from the audit plan, and that it returns a JSON report on disk plus counts by severity. The next skill in the chain declares that it expects that report path plus the severity filter, and returns normalised records with specific fields.

They tie this to the options framework from reinforcement learning: the input contract behaves like an initiation condition (when may this run), the instructions like the policy (how it runs), and the output contract like a termination condition (what counts as done). That's what makes a skill self-contained enough to delegate.

## What the experiments show

The evaluation runs on SkillsBench, a benchmark of long-horizon agentic tasks with human-authored skill packages, using OpenHands as the harness across a range of open and closed models.

Inspecting the benchmark's own curated skills, the authors found that very few declare their inputs and outputs — they describe useful knowledge without defining an interface. On those packages, plain agent-skill execution matched or beat subagents on every model tested. The trend reversed once they synthesised contract-driven procedural packages (generated from successful task trajectories, covering 64 of the 87 tasks): there, subagents came out ahead, with the biggest gains on smaller models, which are more bandwidth-limited to begin with.

Two supporting results back up the mechanism. Padding the context with irrelevant tool descriptions degraded agent-skill execution faster than subagent execution — the fuller the main context, the more it pays to keep skill instructions out of it. And on the stronger models, subagents lowered peak context on more than 80% of tasks, while total token consumption went up, exactly the trade the authors predicted. On weak models the peak-context comparison breaks down, because agent-skill runs simply give up early and never grow a long context in the first place.

An appendix experiment adds a practical wrinkle: organising skills into a hierarchy and exposing only part of the library at a time helped further, and the best configuration was hybrid — routing nodes run inline as agent skills, leaf skills run as subagents. That fits the theory neatly, since a routing node has no procedure and no contract to encapsulate.

## What to take from it

If you're authoring skills for an agent system, the design advice is concrete: don't just dump relevant knowledge into a `SKILL.md`. Write the description as an interface — this is what I need, this is what you get back — and make sure the instructions genuinely transform the one into the other. Skills written that way can be delegated to an isolated context; skills written as loose reference material are better off loaded inline.

And the broader point holds regardless of harness: as agent systems scale, controlling how much any single context window has to hold becomes a first-order design concern. Modularity behind clear interfaces is the same lever software engineering has used for decades, applied to context instead of code.

---

*Piriyakulkij, Lawrence, Curth, Karmalkar & Prasad, "Subagents vs Agent Skills: Executing Reusable Knowledge for Long-Horizon Agentic Tasks" — [arXiv:2609.09233](https://arxiv.org/abs/2609.09233), September 2026.*
