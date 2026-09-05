---
title: "Abliteration: how one direction holds a model's refusals"
description: "Open-weight models ship with guardrails. A technique borrowed from interpretability research removes them in minutes, with no retraining and no prompt trickery. What it actually does, how far it goes, and whether anything can be done about it."
pubDate: 2026-09-05
tags: ["safety-alignment"]
author: "sebastiaan"
section: "fundamentals"
---

![Two clusters of points, harmless prompts and refused prompts, with a single arrow marking the direction between them](/images/abliteration-how-one-direction-holds-a-model-s-refusals/abl_hero.png)

Download an open-weight chat model, ask it something it was trained to decline, and it declines. Spend twenty minutes editing its weights, ask again, and it answers. No jailbreak prompt, no clever roleplay, no fine-tuning run — and on most benchmarks it is still the same model.

The technique is called **abliteration**, a portmanteau of *ablation* and *obliterated*, published by Maxime Labonne in June 2024 and built on a paper by Arditi and colleagues. It is worth understanding for two reasons. It is the clearest demonstration of what safety training actually is inside a model, which is not what most people assume. And if you are responsible for anything that runs local models, it tells you exactly how much weight a vendor’s guardrails can carry in your threat model. Spoiler: less than the marketing suggests.

This post stays at the level of mechanism rather than implementation. What the finding is, how the removal works geometrically, what it does and does not achieve, which models it applies to, and what the defences look like.

## The finding underneath it

Every token, once looked up in the model’s vocabulary, stops being text and becomes a vector: a list of a few thousand numbers, learned during training, that carries its meaning. That vector then travels through the network, and at every layer something gets added to it. Nothing is overwritten — each layer’s contribution joins a running total. That running total is the **residual stream**: the sum of everything every layer has written so far, for this one token, at this one point in the text.

A list of a few thousand numbers is also a point in a few-thousand-dimensional space, the same way `[4, 2]` is a point on a two-dimensional page. And just as you can ask how far a point on a page lies along some chosen direction — a plain multiply-and-add, nothing fancier — you can ask the identical question of a point in four thousand dimensions. That one measurement is the only piece of maths this entire technique rests on. Models use it to represent features: a direction for ‘this is a question’, another for ‘this is code’, another for ‘this is French’.

In 2024 Arditi et al. asked whether refusal has a direction of its own, and found something sharper than anyone expected. Across thirteen open chat models, up to 72 billion parameters, refusal is mediated by a **single direction**.

The evidence is not a correlation, it is a pair of interventions that work in both directions:

- Erase that one direction from the stream, and the model stops refusing — including on the requests it was specifically trained to decline.
- Add that direction artificially, and the model starts refusing **harmless** requests. Ask it for a cake recipe and it will explain that it cannot help with that.

That second half is what makes the result convincing. The direction is not a statistical shadow of refusal, it is the mechanism.

Which tells you something specific about what a guardrail actually is, mechanically. It has no special status inside the model. It sits on exactly the same footing as ‘this is French’ or ‘this is sarcasm’ — one axis among thousands, stored the same way, with no separate lock and no part of the network whose job is to protect it. Safety training does not teach a model to understand why a request is dangerous; the cheapest way for training to satisfy ‘refuse this, answer that’ turns out to be a single straight line through the space, with the model reacting to which side of it a prompt lands on. It is a learned correlation, not a judgement — closer to a reflex than a decision. And a correlation with no protected status is exactly the kind of thing you can measure and subtract. Safety training did not build a wall around the model’s knowledge. It installed a switch, and abliteration is the discovery of where that switch sits.

## How the removal works

Two steps, and neither one is training. That is the part that surprises people: there is no gradient descent, no dataset of thousands of examples, no GPU cluster.

**Step one is to locate the direction.** Assemble two sets of prompts, a few hundred each: one set the model refuses, one set it happily answers. Run both through the model and record the residual stream at the final token. You now have two clouds of points. Take the average of each cloud and draw the line between those two averages — the difference of the means. That line is your candidate refusal direction. You get one candidate per layer, so the last piece is picking the one that works best, which is a matter of trying them.

**Step two is to stop the model expressing it.** Any vector can be split into a component along a chosen direction and everything else — the same way a diagonal push splits into ‘forwards’ and ‘sideways’. With toy numbers: say a layer wants to write `v = [4, 2]`, and the refusal direction is `d = [0.6, -0.8]`. The amount of `v` that points along `d` is one multiply-and-add, `v·d = 4×0.6 + 2×(-0.8) = 0.8`. Subtract that back out along `d`, and `v` becomes `[3.52, 2.64]` — a vector with exactly zero left along the refusal direction, and everything else untouched.

That ‘exactly zero’ is worth sitting with, because it is easy to misread this as pushing the model toward safe instead. It is not. The result is not a vector that now points toward ‘harmless’ — it is a vector with the refusal signal deleted and nothing put in its place. A polygraph needle taped to the centre of the dial does not prove the person is telling the truth; it just stops swinging, whatever they say next.

![Left panel: two clusters of activations with an arrow between their averages, labelled the refusal direction. Right panel: a layer’s output vector split into a kept perpendicular part and a removed part along the refusal direction](/images/abliteration-how-one-direction-holds-a-model-s-refusals/abl_direction.png)

*Find the direction from the averages, then subtract it out of everything the model writes.*

Do this to every contribution before it joins the running sum, at every layer, for every token, and the refusal component can never accumulate — there is nothing left to add up. Not persuasion. Structural absence.

![A chain of boxes showing embedding plus layer 1 plus layer 2 and so on, each layer contribution labelled minus refusal part removed first, running into a final vector used to predict the next token](/images/abliteration-how-one-direction-holds-a-model-s-refusals/abl_stream.png)

*The residual stream is just this running sum. Strip the same component out of every addition, and it can never reappear.*

There are two ways to apply it, and the difference matters more than it looks. You can do the subtraction **at inference time**, as a hook that intercepts the model while it runs: reversible, but it needs a modified runtime. Or you can bake it into the **weights** by adjusting the matrices that write to the stream so that they cannot produce that component in the first place — mathematically the same result, applied once, permanently.

That second option is why this is a security topic rather than a research curiosity. The output is not a patched runtime or a jailbreak string. It is an ordinary model file. It loads in any standard inference stack, it quantises to GGUF like anything else, and nothing about it announces what was done. Hundreds of abliterated models sit on Hugging Face today, usually with nothing but the word “abliterated” or “uncensored” in the name to tell you.

## What it does, and what it does not

This is where most coverage of abliteration goes wrong in both directions, so it is worth being precise.

- **It removes the refusal, not the ignorance.** Abliteration adds no knowledge and no capability. If the model never learned something, an abliterated version still does not know it — it will simply attempt an answer instead of declining. The exposure is whatever was already in the weights, no longer gated.
- **It costs one specific kind of quality, not quality in general.** A benchmark is a standard test with known right answers, used to score and compare models. The original paper ran a broad sweep of them — general knowledge, reasoning, arithmetic, and TruthfulQA, which is built from questions people commonly get wrong — across five model families up to 72B, and found almost every score essentially unchanged after ablation, within normal run-to-run noise. The one score that reliably drops is TruthfulQA, for a reason that makes sense once you see it: answering those questions well means rejecting a popular but false claim, which is itself a small act of refusal. Take away the axis that handles refusal, and the model gets slightly worse at refusing bad information too. Labonne’s own experiment saw a broader drop and healed it afterwards with light preference tuning (DPO) — a reminder that the exact damage varies by model and by how carefully the direction was chosen, not a fixed side effect.
- **It is not specific to safety.** The same procedure works on any behaviour you can separate with two prompt sets. The best demonstration is FailSpy’s MopeyMule, a model abliterated into permanent melancholy. Read abliteration as *behaviour editing without retraining*; refusal is just its most famous target.
- **It is not a jailbreak.** There is no adversarial prompt to detect, no suspicious phrasing to filter, no unusual request pattern. The model is simply a model that does not refuse. Every defence built around recognising attacks at the input is looking in the wrong place.

One honest caveat on the headline claim. The ‘harmful’ and ‘harmless’ labels you start with are a human, binary call — but what you actually measure, the dot product against the direction, is an ordinary number on a continuous scale: some prompts score high, some low, some sit right on the boundary. The model’s eventual behaviour looks binary, refuse or don’t, only because a threshold somewhere later in the network turns that continuous score into a yes-or-no. Ablation and addition work by shoving nearly everything to one side of that threshold, which is why they work so well on average — and why prompts that sat close to the boundary to begin with are exactly where you see the leftover hedging or partial refusals in practice. The mechanism is real; the surgical precision is somewhat overstated.

## Does this work on every model?

The requirement is not a model family, it is **access**. To find the direction you must observe the internal state while the model runs, and to remove it permanently you must edit weights. That draws a hard line:

| What you have | Can it be abliterated? |
| --- | --- |
| Open weights you can download and run | Yes. Any transformer with a residual stream, which in practice means all of them — across families, sizes and tokenizers. |
| An API endpoint from a vendor | No. You cannot read the internal state or touch the weights. Not a sign of stronger alignment, just a different deployment model. |
| A hosted open model on someone else’s platform | Not by you — but by whoever holds the weights. Provenance is the question, not the licence. |

Some practical texture on the ‘yes’ row. Model size is barely a barrier: the paper covered up to 72B, and the work is a handful of forward passes plus a matrix edit, not a training run. Newer architectures need care about which matrices actually write to the shared workspace — mixture-of-experts models have more of them, and multimodal models have more entry points — but the principle is unchanged. Reasoning models add an interesting wrinkle, because refusal can sit in the thinking phase as well as the answer, giving you more than one place to look.

The blunt version: **if you can run it locally, its refusals are optional.** Any risk assessment that treats a downloaded model’s built-in safety as a control is assessing something the model’s owner can switch off in an afternoon.

## So can anything be done about it?

Partly, and understanding *why* only partly is the most useful thing in this post. It comes down to which of three layers a guardrail is sitting in.

![Three stacked layers: pretraining data, refusal training in the weights, and the system boundary around the model, with abliteration marked as reaching only the middle layer](/images/abliteration-how-one-direction-holds-a-model-s-refusals/abl_layers.png)

*Abliteration reaches the middle layer. Everything above and below it is untouched.*

**In the weights, the honest answer is that you are raising cost, not building a wall.** Whoever holds the weights can compute anything they like about them — there is no lock you can put on a list of numbers that still lets it be used for maths. Two research directions are genuinely trying to raise that cost, though, and they attack the problem from different ends. *Circuit breakers* (representation rerouting) target the refusal mechanism itself: instead of giving the model a clean switch that flips to ‘refuse’ — exactly the kind of switch abliteration finds and removes — they train it so that the internal representation of harmful content collapses into something incoherent the moment it appears. Not a lock on the door; the door itself gives way when someone leans on it, so there is no lock left to pick. *Tamper-resistant safeguards* such as TAR attack a different moment: not the refusal itself, but any later attempt to edit it back out. The model is trained so that further weight edits or fine-tuning aimed at recovering the removed capability actively break that capability instead of restoring it — closer to a self-destruct triggered by tampering than a stronger lock. Both raise the bar meaningfully. Neither is a guarantee, and the published record in this area is a cycle of defences being broken by the next paper.

**In the training data, the defence is real but brutal.** You cannot ablate what was never learned. Filtering dangerous content out of the pretraining corpus is the only measure on this list that an attacker with full weight access cannot undo, which is why it has become a serious research direction for open releases. The price is that it is expensive, imprecise, decided once before training, and it removes the knowledge for legitimate users too.

**Around the model, you are back on familiar ground — and this is where your leverage actually is.** An edit to the weights changes exactly one thing: the model file. It cannot reach anything running alongside it, which is precisely why everything outside that file still holds: classifiers that screen input and output as a separate process the model cannot touch; scoping, so a model with no tool or network access cannot act on a request no matter how willing it has become; rate limiting, which caps damage regardless of how compliant the model is; logging and retention, so misuse is visible after the fact; egress control on the host, so even a fully unlocked model cannot ship data out if the network path is closed. None of it lives in the file, so none of it can be edited away by anyone editing the file.

Abliteration also turns a vague supply-chain worry into a concrete requirement. Before this, ‘which model is actually running’ was a soft question for open weights — a file that looked right, mostly was right. After this, a file with the same architecture, the same size, the same name, can have had its refusals quietly removed with nothing about it visibly different. So it earns the same discipline you’d already apply to a software dependency: pin the exact file by hash rather than trusting a filename, know which source it came from, know who reviewed it before it went anywhere near production. “Someone pulled a model from a public hub” is a change you should be able to see, the same way you’d want to see an unreviewed package show up in a build.

Which reframes the whole thing. Model-level refusal is a **product behaviour**: valuable, worth having, the right default. It is not a security boundary, because it lives in a file the operator controls, and an operator can always edit their own file. Treat it the way you would treat client-side validation in a browser — genuinely useful, catches the honest majority of cases, pleasant for everyone using the model as intended — but never the thing an attacker with control of the client cannot get past. The real control has to sit somewhere the model’s own weights cannot reach.

## So

Abliteration is a small, elegant result with an uncomfortable implication. Safety training does not make a model unable to do things; it teaches it to decline, and that decision turns out to be stored in one direction out of thousands. Find the direction with a few hundred prompts, subtract it from everything the model writes, and the refusals are gone — without touching the knowledge underneath, and without leaving a trace in the file.

For open weights, that is simply the deal, and it is worth being clear-eyed rather than alarmed about it: the same access that makes local models auditable, private and cheap to run also makes their guardrails the operator’s choice. Which is fine, as long as your controls live somewhere the operator does not decide on your behalf.

There is plenty more depth here — how the direction is selected per layer, what the healing step does, how circuit breakers differ from refusal training — and it deserves its own follow-up.

### Further reading

- A. Arditi, O. Obeso, A. Syed, D. Paleka, N. Panickssery, W. Gurnee & N. Nanda, *Refusal in Language Models Is Mediated by a Single Direction* (2024), arXiv:2406.11717 — the source result
- M. Labonne, *Uncensor any LLM with abliteration*, Hugging Face blog (2024) — the practical write-up this post follows
- A. Zou et al., *Improving Alignment and Robustness with Circuit Breakers* (2024), arXiv:2406.04313
- R. Tamirisa et al., *Tamper-Resistant Safeguards for Open-Weight LLMs* (2024), arXiv:2408.00761 — the TAR method
