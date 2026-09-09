---
title: "LLMs Model a Harsher World Than the One We Live In"
description: "A new benchmark shows language models know what's wrong but not how people actually react to it — and the bias may come from alignment itself."
pubDate: 2026-09-09
tags: ["safety-alignment", "research"]
author: "sebastiaan"
section: "fundamentals"
---

![A chart contrasting how harshly language models predict social reactions to a wrongdoing versus how humans actually react](/images/llms-model-a-harsher-world/hero.svg)

Ask a language model whether taking credit for a colleague's work is wrong, and it will tell you yes. Ask it what the colleague sitting two desks away would *do* about it, and the answer starts drifting away from reality. That gap is the subject of [Beyond Right and Wrong](https://arxiv.org/abs/2609.05437), a paper from the University of Pennsylvania and the World Bank, and it turns out to be a more interesting gap than it first sounds.

## Two layers of a social norm

The first layer is the rule itself: don't steal, don't lie, don't take credit for someone else's work. This is where AI alignment has spent nearly all its effort — teaching models what is acceptable and what isn't. Benchmarks like ETHICS and Social-Chem-101 live here.

The second layer is everything that happens *after* a violation. Who is entitled to say something? How forcefully? Is saying anything at all appropriate? Social scientists call these **metanorms**, and they are arguably where social intelligence actually lives. You know instinctively that confronting your brother about something is a different act than confronting a stranger about the same thing, even though the underlying rule is identical. Nobody has been testing whether models know that.

The authors built a framework that decomposes it into three measurable pieces:

| Dimension | What it captures |
|---|---|
| **Self-regulation** | Does the violator feel shame, guilt, embarrassment? (internal sanctions) |
| **Other-regulation** | Does the observer feel anger, contempt, disgust? (external sanctions) |
| **Norm enforcement** | Does the observer actually act — and would they, versus should they? |

Each of these is then crossed with **social distance**: strong ties (family, close friends), weak ties (coworkers, acquaintances), and strangers. That third axis is the whole point, because the right to sanction is not distributed evenly across a social network.

## The human baseline is the surprise

They ran 450 norm-violation scenarios past 871 human raters, then past six models — GPT-5.2, Gemini-3-Pro and Claude-4.5-Opus on the closed side, GPT-OSS-20B, Llama-4-Scout-17B and Gemma-3-12B on the open side. Deliberately with no persona and no prompt engineering, the way people actually use these things.

The human results alone are worth the read:

| Human response | Strong tie | Weak tie | Stranger |
|---|---|---|---|
| Confrontation (verbal or physical) | 35% | 12.5% | 8% |
| Do nothing | 22% | 38% | **60%** |
| Observer feels shame/guilt | 19% | — | 9% |
| Observer feels anger/contempt/disgust | 47% | — | 65% |

Read the "do nothing" row again. For a stranger, inaction is the majority response — and not because people don't care. It's because they recognise they lack *standing*. Intervening in a stranger's business is itself a minor social violation. What emerges is a properly calibrated system: direct confrontation for people close to you, gossip and avoidance for the middle ring, silence for strangers. Restraint is the norm working correctly, not the norm failing.

There's a second detail I find delightful. Gossip shows a clean split between what people say *would* happen and what they say *should* happen: they acknowledge it as the realistic response while rejecting it as the right one. Everyone knows gossip does useful work in maintaining norms, and everyone also thinks it's a bit shabby. You only see that ambivalence if you ask both questions, which is exactly why the framework asks both.

## Where the models go wrong

Consistently, and in one direction. Models predict more emotion, more intervention, more punishment.

| Failure mode | Magnitude |
|---|---|
| Open models over-predict observer anger | up to **+27%** |
| Open models over-predict observer disgust | up to +16% |
| Closed models over-predict contempt (weak ties, strangers) | up to +18% |
| Open models over-predict gossip for weak ties | up to **+66%** |
| Observer shame/guilt for strong ties (humans ~19%) | models: 4–11%, ~0% beyond |

The gossip number is the eye-catcher, but the interesting behaviour shows up when you switch from descriptive to injunctive framing. Asked what people *should* do, the models don't retreat — they escalate, shifting from gossip to direct verbal confrontation. Humans stay restrained under both framings. So models don't merely over-predict intervention; they normatively endorse the more confrontational version of it.

The flattened observer emotions matter more than they look. In real life, a family member's transgression produces vicarious shame in the people around them, and guilt over not having prevented it. Those feelings are what drive the *repairing* behaviours — mediating, smoothing things over, having a quiet word. Strip them out and you get a social world where observers only ever condemn and are never themselves implicated. Every prosocial response disappears from the model's picture.

Performance also degrades exactly where you'd predict:

| Task | Strong tie | Weak tie | Stranger |
|---|---|---|---|
| Average F1, descriptive ("would do") | .80 | .70 | **.48** |
| Average F1, injunctive ("should do") | .69 | .56 | .46 |

Two patterns here. Accuracy collapses as social distance grows, because distant-tie norms are dominated by inaction and models won't predict inaction. And injunctive is consistently harder than descriptive — which makes sense: predicting what people *do* is frequency estimation over training data, while predicting what people think *ought* to be done requires a second-order belief, a belief about others' beliefs. The authors' conclusion is blunt: LLMs may serve as rough descriptive models of behaviour, but they're unreliable as models of the normative structure that explains it.

One methodological note worth stealing for your own evals: aggregate F1 hid genuinely opposite behaviour. On strangers, Claude posted the highest precision (0.80) with low recall (0.73) — reluctant to grant strangers standing. Llama inverted it: 0.96 recall, 0.69 precision — licensing stranger intervention far too freely. Similar F1, incompatible social policies. One risks passivity where intervention is warranted, the other risks over-enforcement. If your metric can't distinguish those, it isn't measuring what you care about.

## The uncomfortable part

The authors identify three missing concepts: models lack *conditional preferences* (sanctioning depends on what you believe others expect, it isn't a reflex triggered by detection), they lack *reference-network sensitivity* (legitimacy is relationally distributed), and they lack the distinction between empirical and normative expectations.

Where does the bias come from? Their candidates are training corpora that over-represent moral outrage relative to everyday restraint, post-training that rewards decisive and normatively legible answers, and safety policies that push toward overt condemnation. Which is to say: some of this may be alignment doing its job. Everything that makes a model sound responsible — taking a clear position, naming the wrong, not shrugging — pushes it away from how people actually behave. That's an alignment objective with a measurable cost in social realism, and it's not obvious how you'd optimise for both.

The consequence they're most worried about isn't a broken benchmark. Humans already overestimate how punitive their surroundings are — false consensus and egocentric bias are well-documented. Models don't introduce that distortion; they *amplify* it, and they amplify it toward the more severe end of the scale. Ask an LLM how people will react to something you did and you'll get back more anger and less tolerance than your actual social circle would produce. At scale, with these systems embedded as moderators, recommenders and confidants, that becomes a mechanism the authors call **AI-mediated pluralistic ignorance**: people coming to believe their community is harsher than it is. Norm theorists have spent decades documenting that exact dynamic as the reason harmful practices survive despite near-universal private disapproval.

## What to take from it

Two things, if you're building anything that touches social judgement.

First, "does the model know this is wrong" is the easy half of the question and we've been treating it as the whole one. The harder half — who gets to react, how much, and whether reacting is appropriate at all — is where models are weakest and where nobody has been looking. If your system moderates content, mediates conflict, or simulates social behaviour for research or policy work, it is running on the half that hasn't been tested.

Second, the failure has a direction, which makes it tractable. Models are systematically too punitive and too interventionist, and predictably worse the more distant the relationship. That's a bias you can correct for once you know it's there. The scenarios and human annotations are released as **NormReact**, so you can measure it on your own stack.

The caveats are real: American norms only, instruction-tuned models only, and no prompt variation, so whether the bias sits in pretraining or post-training is still open. But the core finding is hard to argue with. Knowing right from wrong is not the same as knowing who is entitled to react — and right now our models only know the first one.

---

*Paper: Rai, Kuang et al., [Beyond Right and Wrong: Evaluating Second-order Social Reasoning in Large Language Models](https://arxiv.org/abs/2609.05437), arXiv:2609.05437. Dataset: [NormReact](https://github.com/sunnyraiphd/NormReact).*
