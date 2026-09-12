---
title: "Curiosity at the Edge of Chaos: What a New RL Paper Actually Shows"
description: "A new reinforcement learning paper claims curiosity should emerge from an agent's own internal dynamics rather than a hand-tuned bonus term — a skeptical read of what the experiments actually support."
pubDate: 2026-09-12
kind: "deepdive"
format: "paper"
topics: ["models"]
credit: "directed"
contributions:
  chose: true
  checked: true
model: "Claude"
heroAlt: "Curiosity at the edge of chaos — a spectrum from rigid to chaotic, with a feedback loop between incoherence and exploration"
hero: "/images/curiosity-edge-of-chaos/hero.svg"
---

Reinforcement learning has a well-known weak spot: it needs a reward signal to learn from, and in a lot of real environments that signal is sparse, delayed, or missing entirely. An agent that only acts when it's told "good job" doesn't do much in a world that rarely says so.

The usual fix is to give the agent an extra, self-generated reason to act — "curiosity" — on top of whatever the environment provides. A recent paper, *[Endogenous Exploration in Reinforcement Learning with Intrinsic Curiosity](https://arxiv.org/abs/2609.05650)* (Vieira, 2026), takes a specific angle on this that's worth unpacking, without dressing it up as more than it is.

## The setup: two layers, not one

The system has two parts:

1. A **Liquid State Machine (LSM)** — a type of reservoir computing model built from spiking neurons — that turns the agent's stream of experience into a rich, high-dimensional representation with a kind of built-in short-term memory (a "fading memory" of recent events).
2. A **coherence-regulating layer** sitting on top, which tracks how organised or disorganised the reservoir's internal state is, and uses that to steer exploration.

An important detail: the reservoir itself isn't "the agent" making decisions. It's just the medium the coherence layer operates over — a rich soup of dynamics that gets read out and interpreted, not a decision-maker in its own right.

## The actual idea: a closed loop, not a bonus signal

Most curiosity methods (like the well-known Intrinsic Curiosity Module, ICM) work by adding a reward bonus for surprising outcomes — the agent gets extra reward when its internal prediction of what will happen turns out wrong. It's an open loop: surprise goes in, a bonus reward comes out, done.

This paper does something more circular. The system's own **incoherence** — how unsettled or disorganised its internal state is — determines how much it explores. That exploration then changes the internal state, which changes the coherence, which changes how much it explores next. Incoherence drives exploration, exploration reshapes coherence, coherence reshapes incoherence — round and round.

None of the ingredients are new on their own: reservoir computing, intrinsic motivation, coherence dynamics (borrowed from Friston's active inference / free-energy framework), and noise-based exploration (à la simulated annealing) all exist separately. The claimed contribution is specifically wiring them into this self-referential loop, rather than any one piece being novel by itself.

## The "sweet spot," and why it's not mystical

The paper's central empirical claim is that useful exploration shows up in a **middle band** between two failure modes:

- Too coherent → the system is too rigid, barely explores, gets stuck.
- Too incoherent → the system is too chaotic, exploration becomes noise, and it stops making progress.

This is a fairly familiar story from reservoir computing more broadly: these systems tend to work best at an "edge of chaos" — not fully ordered, not fully chaotic. What's specific here is applying that same idea to *exploration behaviour* in RL, and coupling it to the agent's own dynamics rather than setting it as a fixed external hyperparameter (like a temperature or epsilon schedule you'd tune by hand).

The paper does reach for a bigger framing at one point, linking this middle regime to theories connecting consciousness and criticality (Tononi's Integrated Information Theory). That's worth flagging as narrative colour rather than something the experiments actually demonstrate — nothing in a LunarLander or BipedalWalker benchmark run tells you anything about consciousness. Worth noting, not worth building conclusions on.

## What was actually tested

The method was evaluated on two standard RL benchmarks:

- **LunarLander-v2** (discrete actions)
- **BipedalWalker-v3** (continuous control)

against PPO and ICM as baselines, and came out competitive — not obviously dominant, but holding its own. That's a reasonable result for a first paper introducing a new mechanism, but it's a small benchmark suite, from a single author, without (as far as the paper shows) ablations that isolate exactly which part of the loop is doing the work.

## The genuinely interesting bit

Strip away the framing, and here's what's actually worth taking from this: **exploration doesn't have to be an external knob.** Most curiosity mechanisms are still, at bottom, an engineered bonus term someone tuned. This paper's contribution is a mechanism where the *drive* to explore emerges from the system's own internal state, and adjusts itself as that state changes — closer to how a self-regulating dynamical system behaves than to a hand-crafted reward shaping trick.

Whether "coherence" is really tracking something meaningful about the agent's understanding of its environment, or whether it's a cleverly reframed noise-scheduling mechanism, isn't fully settled by two benchmarks and one paper. But the framing — closing the loop between an internal state and the drive it produces — is a genuinely different way to think about the exploration problem, independent of whether the LSM/coherence specifics turn out to be the right implementation.

## What's still needed

To know whether this holds up:

- **More benchmarks.** Two environments, both fairly standard and low-dimensional, is a starting point, not evidence of general applicability.
- **Ablations.** Does the *closed loop* matter, or would a simpler open-loop coherence-based bonus do just as well? The paper's own framing claims the loop is the contribution — that needs to be isolated and tested directly, not just asserted.
- **Independent replication.** Single-author papers introducing a new named mechanism ("curiosity window") are exactly the kind of result that benefits from someone else trying to reproduce it.
- **A sharper line between mechanism and metaphor.** The active-inference and criticality/consciousness references are useful for motivation, but the paper would be stronger if the empirical claims stood on their own without leaning on that framing.

The underlying idea — self-referential exploration instead of an externally imposed bonus — is worth watching. Whether *this specific* implementation is the one that sticks is a separate question, and one two benchmarks can't answer yet.
