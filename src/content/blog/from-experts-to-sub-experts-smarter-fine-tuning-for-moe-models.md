---
title: "From Experts to Sub-Experts: Smarter Fine-Tuning for MoE Models"
description: "NSFT cuts each expert in a Mixture-of-Experts model into channel groups and trains only the ones that matter — beating LoRA and ESFT on accuracy per trained parameter, and forgetting less along the way."
pubDate: 2026-09-25
kind: "explainer"
format: "deepdive"
topics: ["training", "llms"]
credit: "directed"
model: "Claude"
contributions:
  chose: true
  checked: true
source:
  url: "https://arxiv.org/abs/2609.25655"
  publisher: "arXiv cs.LG"
---

## Why this paper matters

Fine-tuning a Mixture-of-Experts (MoE) model can be done with a fraction of the usual trainable parameters, if you zoom in far enough. That is the core claim of NSFT (Neural Sub-expert Fine-Tuning), a recent paper from Alibaba Group and Southeast University.

Full fine-tuning of today's large models is expensive in GPU memory and compute. Parameter-efficient fine-tuning (PEFT) methods such as LoRA exist to cut that cost. NSFT asks a sharper question: at what granularity should you pick the parameters you train?

Their answer: not whole weight matrices, not whole experts, but small groups of channels inside experts. In this post I walk through how that works, what it gains you, and why it also helps against catastrophic forgetting.

## A quick refresher on Mixture-of-Experts

An MoE layer replaces one big feed-forward block with many smaller ones, called experts. A router decides, per token, which few experts do the work.

Say a layer has 64 experts and the router picks the top 8 for each token. The other 56 sit idle for that token. That is routing sparsity, and it is built into every MoE model, before any fine-tuning happens.

Each expert is itself a small gated MLP. Inside it sit hundreds or thousands of intermediate channels: think of them as individual neurons. This inner level is where NSFT does its work.

## The problem: experts are too coarse a unit

Existing efficient fine-tuning methods for MoE models work at two levels:

- **LoRA** adds small low-rank corrections to whole weight matrices. It is generic: it does not target the parts of the network that actually matter for the task.
- **ESFT** (Expert-Specialized Fine-Tuning) picks the experts that respond most to your training data and trains those experts in full.

The NSFT authors measured what happens inside an activated expert. Most channel activations sit close to zero; only a small share respond strongly to the target task.

So when ESFT trains a whole expert, it spends much of its update budget on channels that barely contribute. Selecting the right experts is a good first step, but it leaves a lot of waste inside them.

## How NSFT picks sub-experts

NSFT cuts each expert into groups of consecutive channels, called sub-experts, and trains only the groups that matter. Before training, it runs the task data through the model and collects two statistics:

1. **Routing importance (R)**: how often the router picks this expert, as a share of all picks in the layer.
2. **Channel saliency**: within the expert, how much of the total activation each channel carries, summed over all tokens routed to it.

A channel's score is the product of the two. A group's score is the sum of its channels' scores.

### A toy example

Take a layer with two experts, each split into four groups. Expert A gets 60% of the routing, Expert B 40%.

| Group | Routing importance R | Share of activation inside the expert | Score (R × share) |
| --- | --- | --- | --- |
| A-g1 | 0.6 | 0.50 | 0.30 |
| B-g1 | 0.4 | 0.70 | 0.28 |
| A-g2 | 0.6 | 0.30 | 0.18 |
| A-g3 | 0.6 | 0.15 | 0.09 |
| B-g2 | 0.4 | 0.20 | 0.08 |
| A-g4 | 0.6 | 0.05 | 0.03 |
| B-g3 | 0.4 | 0.05 | 0.02 |
| B-g4 | 0.4 | 0.05 | 0.02 |

NSFT ranks all groups in the layer and keeps the smallest set whose scores add up to a threshold τ. With τ = 0.6 for this toy, it keeps A-g1, B-g1 and A-g2 (0.30 + 0.28 + 0.18 = 0.76). Five of eight groups stay frozen.

Note that B-g1 beats most of Expert A's groups, even though B is the less popular expert. The score rewards a group that is strongly active inside a moderately used expert.

### The general form

For layer `l`, expert `e` and channel `m`, the channel score is:

```
S(l, e, m) = R(l, e) × M̂(l, e, m)
```

Here R is the expert's routing share and M̂ (M-hat) the channel's normalized activation within the expert. In the real models, the paper found a group size of 16 channels works best and uses τ = 0.2 in its main experiments. Groups of 1 channel fragment the update too much; very large groups pull in weak channels again.

## Two training tricks that make sparse updates work

Training only a sliver of each expert creates a new problem: the total update is too small. NSFT fixes that with two adjustments.

### Learning-rate scaling

If you train 20% of an expert's channels, the expert as a whole moves far less per step than under full-expert tuning. NSFT therefore raises the learning rate by the inverse of the active share, with a ceiling for stability.

With 1,024 channels in an expert and 205 selected, the factor is 1,024 / 205 ≈ 5. The selected channels get a learning rate roughly five times the base, unless that exceeds the cap.

```
η(l, e) = η_base × min( d_expert / K(l, e),  α_max )
```

### Gradient scaling

Not every selected group is equally relevant. NSFT multiplies each group's gradient by a factor based on its activation energy compared with the average selected group. A group twice as active as average gets a boost; weaker groups keep a factor of at least 1.0, and a clip prevents extreme values.

An entropy-based exponent softens the contrast when a few groups dominate, which keeps training stable.

### Why the scaling has to be dynamic

A fixed gradient multiplier mostly disappears under the Adam optimizer. Adam divides each update by a running estimate of the gradient's size, so a constant factor cancels out.

NSFT therefore recomputes the scaling factors during training, every 1 or 5 steps, smoothed with an exponential moving average. The ablations show learning-rate scaling gives the largest and most consistent gain; gradient scaling adds a smaller, less stable one.

## Results: more score per trained parameter

NSFT beats LoRA and ESFT on in-domain tasks while training fewer parameters, and keeps nearly all general capability. The authors tested two MoE models, OLMoE-7B and Ling-mini-2.0-16B, on medicine, scientific extraction, RAG, math, code and table QA.

### OLMoE-7B, averaged over six domains

| Method | Trainable parameters (avg.) | In-domain avg. | General benchmark avg. |
| --- | --- | --- | --- |
| Base model (no tuning) | 0% | 36.39 | 47.49 |
| Full fine-tuning | 100% | 49.91 | 35.98 |
| LoRA r32 | 4.49% | 41.41 | 44.13 |
| LoRA r64 | 8.97% | 43.38 | 43.41 |
| ESFT | 6.50% | 43.42 | 46.24 |
| **NSFT** | **5.67%** | **46.62** | **45.96** |

NSFT scores about 3 points higher in-domain than ESFT with fewer trainable parameters. Full fine-tuning wins in-domain, but loses more than 11 points on general benchmarks.

### Ling-mini-2.0-16B, table question answering

| Method | Trainable parameters | TableQA avg. | General benchmark avg. |
| --- | --- | --- | --- |
| Base model (no tuning) | 0% | 19.79 | 66.45 |
| Full fine-tuning | 100% | 39.34 | 62.59 |
| LoRA r32 | 7.45% | 28.71 | 64.09 |
| LoRA r64 | 14.84% | 32.00 | 63.90 |
| ESFT | 3.35% | 17.68 | 67.03 |
| **NSFT** | **2.86%** | **34.44** | **66.18** |

Here the gap is starker: NSFT nearly doubles ESFT's TableQA score with slightly fewer parameters, and beats LoRA r64 with a fifth of its parameters. Compared with the heaviest LoRA setup (attention plus MLP), the paper reports up to 66.9% fewer trainable parameters at similar or better accuracy.

Fewer trainable parameters also means less GPU memory for gradients and optimizer state, since Adam keeps two extra values per trained parameter.

## Catastrophic forgetting, and why touching less helps

The biggest practical win of NSFT may be what it does not break. Catastrophic forgetting is a long-known weakness of neural networks, not something this paper discovered.

A model stores what it learned in shared weights, spread across billions of parameters. Train it further on a new task, and the optimizer adjusts those same weights to fit the new data. Patterns that supported older skills get partly overwritten. The model does not lose a memory the way a person does; its new weights simply no longer compute the old functions well.

It is called catastrophic because it can be abrupt. A short burst of training on new data can drop performance on old tasks far more than the size of the change suggests.

Full fine-tuning is most exposed, because every parameter receives an update, including ones that matter only for general skills. The OLMoE numbers above show it: general benchmarks fall from 47.49 to 35.98.

NSFT trains only the channel groups that respond to the new task and freezes everything else. Most of the original weights, and the general knowledge in them, stay untouched: the general average ends at 45.96.

This is a trade-off, not a free lunch. The fewer parameters you train, the less you forget, but also the less capacity you have for the new task. That is why full fine-tuning still wins in-domain. NSFT is an attempt to find a better point on that curve.

## What to take away

For MoE models, the expert is too big a unit to fine-tune; the channel group is a better one. If you plan to adapt an MoE model to a domain, a few points are worth keeping in mind:

- **It is MoE-only.** The method relies on router statistics and expert structure, so it does not transfer to dense models.
- **It needs a profiling pass.** You run your task data through the model once to collect routing and activation statistics before training starts.
- **The evidence is still narrow.** Two models were tested, at 7B and 16B parameters. Results on much larger MoE models remain to be shown.
- **Tuning still matters.** The best dynamic-scaling interval differed per task, and ESFT kept slightly better general scores in some setups.

The bigger idea is worth watching: as models get more modular, the unit you fine-tune can follow that structure down to a finer level. [The code is public](https://github.com/aheadformore/NSFT), so you can try it on your own data.
