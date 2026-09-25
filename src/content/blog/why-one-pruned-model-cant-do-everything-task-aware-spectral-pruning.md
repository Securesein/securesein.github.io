---
title: "Why One Pruned Model Can't Do Everything: Task-Aware Spectral Pruning"
description: "Classic LLM pruning commits to one compressed structure before it knows what question a user will ask. TASP calibrates five task-specific masks instead, and a cheap router picks one per turn."
pubDate: 2026-09-25
kind: "explainer"
format: "deepdive"
topics: ["inference", "llms"]
credit: "directed"
model: "Claude"
contributions:
  chose: true
  checked: true
source:
  url: "https://arxiv.org/abs/2609.29499"
  publisher: "arXiv cs.LG"
---

Large language models are expensive to run. That is not news. To make them faster and cheaper, researchers have spent years pruning away the parts that seem to contribute little — a process called pruning. A recent paper (Shihab, Afrin, Akter and Sharma, 2026, from Iowa State University and the Kalinga Institute of Industrial Technology) shows the classic approach has a blind spot, and proposes an alternative: **Task-Aware Spectral Pruning (TASP)**.

## The problem: one model, every task

Picture a language model as a collection of thousands of small parts — attention heads, feedforward blocks — that together decide how it processes text. Classic pruning methods (SparseGPT, Wanda, ShortGPT among them) work like this: run some general text through the model, measure which parts seem to contribute little, and remove those permanently. The result is one fixed, smaller model, deployed for everything from that point on.

That is where the problem sits. A part that is crucial for mathematical reasoning is not necessarily the same part that matters for fluent writing or translation. Because the pruning decision is made once, before anyone knows what question a user will ever ask, that single selection is forced to be a compromise. The authors call this the **versatility tax**: you pay in quality for the fact that one fixed structure has to do everything.

## The fix: several masks, one shared model

TASP takes a different route. Instead of building one final version, it builds **five different masks** — one per task family (reasoning, generation, retrieval, code, translation) — that all share the same underlying weights. For each incoming prompt, a small routing model picks which mask gets used.

How does TASP work out what matters per task? By computing a kind of fingerprint for every part of the model, from three signals:

- **Effective rank** — how concentrated or spread out the information in that part is. A part that reacts to only one "thing" has low effective rank and is easier to lose; a part that processes many different patterns at once has high rank and is riskier to remove.
- **Tail exponent** — a statistical property from research on well-trained networks. A "heavy tail" in a weight distribution's spectrum often points to strongly learned, meaningful structure.
- **Salience** — how strongly a part responds to specific kinds of tokens, such as digits, arithmetic symbols or logical connectives. A head that attends heavily to "if... then..." and numbers is probably important for reasoning.

These signals are combined with measured data — the authors actually cut parts out and measure, per task, how much damage that does — to train a predictor that says: "this part matters for task X, but is redundant for task Y."

Importantly, before running this whole process, TASP first checks whether this kind of prediction works well enough at all for the given model. On Llama-3-8B and Llama-3-70B it did; on the smaller Qwen2.5-1.5B it did not — the system simply stopped there, rather than proceeding with an approach it could not trust.

## The router: the conductor behind the scenes

Once the five masks are ready, one question remains: for each incoming prompt, who decides which mask to use? That is the job of a small neural network — three layers, negligible in size next to the main model.

This router looks purely at the prompt's text (not at internal model activations) and watches for simple signals: text patterns, length, the presence of digits or code punctuation, and hand-built cues such as "does this contain a code block?" or "does the word 'translate' appear here?" From that it computes a probability distribution over the five tasks.

If the router is confident enough (above a set threshold), the matching sparse mask is used. If it is unsure, the system falls back to the full, unpruned model — better slightly slower than fast and wrong. This routing decision costs only 0.16 milliseconds and is made once per user turn; once chosen, the same mask stays fixed for the entire length of the reply.

The router is trained on the same labeled prompts already used to measure task sensitivity — thousands of examples from standard benchmarks, each tagged with a task label, with a held-out validation set to honestly test whether it also works on prompts the router has never seen.

## Does it work?

On the large Llama-3-70B model, at a 43% cut in active compute:

- TASP retains **97.7%** of the full model's quality, against 93.3% for a single global mask and 94.0% for the strongest competing method.
- Decode speed goes from 45.2 to 31.3 milliseconds per token — a **1.44×** speedup.
- Compared with the most closely related competitor, ShadowLLM (which picks a fresh pattern per individual prompt rather than per task family), TASP scores somewhat better on quality (97.7% versus 93.9%) while being slightly less fast (1.44× versus 1.52×).

The authors are upfront that this is not a universal win. Some competing methods are faster; TASP retains more quality — a classic Pareto trade-off, in the paper's own words. And the approach is not free: calibrating TASP costs around 136 GPU-hours for the 70B model, far more than simpler methods. That only pays off under large-scale, sustained use with stable task categories.

## Bottom line

TASP reframes pruning from "what can I best leave out on average" to "what does this specific question need." By keeping several ready-made selections instead of committing to one, and letting a cheap router make the choice, the result is a model that runs faster without giving up as much quality as traditional, task-blind pruning does.
