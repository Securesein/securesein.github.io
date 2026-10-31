---
title: "Why an AI mistakes a Labrador for a cat"
description: "A tiny, invisible change can make an image model see a cat where any person sees a dog. The 2019 MIT paper 'Adversarial Examples Are Not Bugs, They Are Features', explained without the maths: what the researchers found, the experiment that makes the point, and why it matters for anyone who relies on AI."
pubDate: 2026-10-31
kind: "research"
format: "paper"
topics: ["ai-security", "deep-learning"]
credit: "directed"
model: "Claude"
contributions:
  chose: true
source:
  url: "https://arxiv.org/abs/1905.02175"
  publisher: "arXiv (NeurIPS 2019)"
  publishedAt: 2019-05-06
---
A tiny, invisible change can make an image model see a cat where any person sees a dog. A 2019 MIT paper argued this is not a glitch: the model is reacting to real patterns in the data that we simply cannot see.

I ran into this idea on episode #503 of the Lex Fridman Podcast, published on 26 October 2026. Mathematician Ankur Moitra brought it up while discussing how AI solves problems differently from humans. The video showed a striking example of an attack on ResNet-50, a well-known image classifier.

The model first labels a photo of a Labrador as a Labrador retriever, with 54% confidence. Then a faint pattern is added, changing each colour value by at most 2 of 255 levels. The photo looks identical, yet the model now says "tabby cat" with 99.9% confidence.

This post explains, without the maths, what the researchers found and why it matters for anyone who relies on AI.

## What an adversarial example is

To a computer, a photo is a grid of numbers. Each pixel has a value for red, green and blue, from 0 to 255. An image classifier learns which patterns in those numbers go with which label.

An adversarial example is a photo that has been nudged on purpose. The attacker asks the model, in effect, "which tiny change would push your answer furthest towards *cat*?" and then applies exactly that change. Each pixel moves by an amount far too small for the eye to notice.

Researchers have known about this since around 2013. For years the common view was that it was a bug: a strange side effect of working with millions of numbers at once, or of models memorising their training data too closely. If it was a bug, the thinking went, better engineering should be able to fix it.

## The finding: not a bug, a feature

In 2019, Andrew Ilyas, Shibani Santurkar, Dimitris Tsipras, Logan Engstrom, Brandon Tran and Aleksander Mądry at MIT published [Adversarial Examples Are Not Bugs, They Are Features](https://arxiv.org/abs/1905.02175) at the NeurIPS conference. Their claim turns the old view around. Adversarial examples exist because models are *good* at spotting useful patterns, including ones humans cannot perceive.

A model is trained for one thing only: to get the label right as often as possible. It has no idea that ears, whiskers and a tail are the "proper" clues for a cat. Any pattern that reliably goes with the label is just as welcome, even a faint texture spread across thousands of pixels.

The authors call these patterns non-robust features. They genuinely help with prediction, but they are fragile, because a tiny change can flip them. An attack does not add random noise. It switches those hidden dog-signals to cat-signals that the model already trusts.

The paper puts it this way: whether a feature counts as "real" is a human judgement. From the model's point of view, a faint pixel pattern can be as informative as the shape of an ear.

## The experiment that makes the point

The most convincing part of the paper is an experiment that sounds like it should fail. Moitra retells it in the podcast, and it goes roughly like this:

1. Train a normal model on correctly labelled photos.
2. Take every training photo and nudge it with an adversarial pattern, so the model now sees it as a different class. A dog photo gets a cat-pattern, for example.
3. Give each photo the new, "wrong" label. To a human, the entire dataset now looks mislabelled.
4. Train a brand-new model only on this strange dataset.
5. Test it on ordinary, correctly labelled photos it has never seen.

If adversarial patterns were meaningless noise, the new model should be useless. Instead it learns to classify real photos well. The only way that works is if the faint patterns carry genuine information about cats and dogs.

| Training data | CIFAR-10 (10 classes) | Restricted ImageNet (9 classes) |
| --- | --- | --- |
| Normal photos, correct labels | 95.3% | 96.6% |
| Nudged photos, random new labels | 63.3% | 87.9% |
| Nudged photos, labels systematically swapped | 43.7% | 64.4% |

Accuracy on the normal test set. Guessing would score about 10%. In the last row, everything a human can see points to the wrong class, and the model still learns something useful ([paper, Table 1](https://arxiv.org/abs/1905.02175)).

The researchers also ran the reverse experiment. They rebuilt a dataset so that it kept only the patterns a hardened, attack-resistant model relies on. An ordinary model trained on that cleaned-up data became noticeably harder to fool. So the weakness lives largely in the data, not only in how models are built.

## Why it matters

If the weakness comes from the data itself, it cannot simply be patched away. That has a few practical consequences.

**Attacks travel between models.** A trick crafted against one model often fools a completely different one. The paper offers a simple explanation: models trained on similar data pick up similar hidden patterns, so the same nudge works on both. An attacker does not always need access to your model to fool it.

**Robustness has to be built in on purpose.** You can train models to ignore fragile patterns, a technique called adversarial training. It helps, but it has a price. In the paper's CIFAR-10 tests, the hardened model scored about 91% on normal photos versus about 95% for the standard one, and it costs more compute to train.

**Explanations can mislead.** Many tools that "explain" a model's decision highlight areas that look sensible to us, like the dog's face. But if the model actually leans on invisible patterns, a human-friendly explanation is not a faithful one. The authors conclude that models which are both robust and understandable need human preferences built into training itself.

**High accuracy is not the same as human-like understanding.** This is the point Moitra makes in the podcast. A model can match or beat people on a test and still get there by a very different route. He warns against assuming AI thinks the way we do, and applies the same caution to the AI-generated maths proofs discussed in the episode, which he says do not look like a human wrote them.

One honest caveat: the authors note that non-robust features are not necessarily the *only* cause of adversarial examples. Other researchers have since shown cases that work differently. The paper changed the conversation, but it did not close it.

## Listen for yourself

**[Lex Fridman Podcast #503 – AI Crisis in Math](https://lexfridman.com/math-ai-crisis/)** (26 October 2026, about 3 hours 40 minutes). Lex talks with Ankur Moitra (MIT), Steven Brunton (University of Washington) and Alex Kontorovich (Rutgers) about AI systems claiming solutions to famous maths problems. The adversarial-examples story starts at [30:13](https://youtube.com/watch?v=ZAzWPE9CItg&t=1813), in the chapter "Can AI create new math?". Moitra describes the experiment in plain words and connects it to the risk of treating AI as if it reasons like a person. A [full transcript](https://lexfridman.com/math-ai-crisis-transcript) is available.

**[TWIML AI Podcast with Aleksander Madry](https://twimlai.com/podcast/twimlai/adversarial-examples-are-not-bugs-they-are-features-aleksandar-madry)**. Here one of the paper's authors walks through the work himself. He discusses the gap between what we expect these systems to do and what they actually do.

## The takeaway

The Labrador-turned-cat is not a model breaking down. It is a model doing exactly what it was trained to do, using clues we never intended it to use. That is worth remembering whenever an AI system performs impressively: it may be right for reasons that have little to do with ours.

---

### Sources

- Ilyas, Santurkar, Tsipras, Engstrom, Tran, Mądry: [Adversarial Examples Are Not Bugs, They Are Features](https://arxiv.org/abs/1905.02175), NeurIPS 2019
- [Lex Fridman Podcast #503 transcript](https://lexfridman.com/math-ai-crisis-transcript)
- [TWIML AI Podcast episode with Aleksander Madry](https://twimlai.com/podcast/twimlai/adversarial-examples-are-not-bugs-they-are-features-aleksandar-madry)
- [Distill discussion of the paper](https://distill.pub/2019/advex-bugs-discussion), with responses from other researchers
