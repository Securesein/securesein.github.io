---
title: "Why Don't Machine Learning Research Agents Overfit?"
description: "New research from Amazon Science offers a surprisingly elegant explanation for a decade-old puzzle: good solutions are simply too short to cheat with."
pubDate: 2026-09-12
kind: "deepdive"
format: "paper"
topics: ["models", "agents"]
credit: "directed"
contributions:
  chose: true
  checked: true
model: "Claude"
heroAlt: "Hundreds of experiments compressed into a prompt of a few tokens, from which a fresh model reconstructs the full approach"
hero: "/images/why-dont-ml-research-agents-overfit/hero.png"
---

There's a gap that's existed for years between what theory predicts and what actually happens in machine learning. New research from Amazon Science, with Aaron Roth among the authors, offers a surprisingly elegant explanation: good solutions are simply too short to cheat with.

## First, what actually is a benchmark?

You probably know the word "benchmark" mostly from speed tests — how many frames per second a GPU can push, how fast an app loads. In machine learning it means something different: a **fixed dataset with the correct answers attached**.

Think of ImageNet: thousands of photos, each labelled with what's in it. Or MMLU for language models: a collection of questions with the correct answer. You turn your model loose on it, and the score is simply: how much did it get right?

Both kinds of benchmark share the same purpose — a standardised yardstick everyone can measure their results against. One just measures speed, the other accuracy.

## The problem: the yardstick wears out

The entire point of a test set is that your model has never seen it. Only then does a good score actually tell you something about how the model performs on new, unseen data.

But that isn't how research works in practice. What actually happens is this:

1. Train a model, test it on the benchmark.
2. The score disappoints. Adjust something.
3. Test again. Repeat — hundreds of times.

And that's where the leak is. By staring at the same test set over and over and steering your approach based on it, that test set quietly becomes part of your training process. Do it often enough, and you'll eventually land on a model that happens to score well on those exact examples — without having learned anything useful.

Picture coin flips. Have one person guess 20 in a row and the odds of getting them all right are negligible. Have a thousand people guess, and there's almost certainly someone who gets them all right — purely from the number of attempts, not from any skill.

## So why does everyone keep using the same benchmarks anyway?

Because the alternative is worse. A shared benchmark makes results comparable across research groups, makes progress measurable over years, and saves the enormous cost of building well-validated datasets from scratch every time. On top of that, conferences and reviewers expect you to measure your work against existing research on the same yardstick.

The result: the entire ML community has spent years running one giant, distributed optimisation loop against a handful of fixed benchmarks. By the textbook, the leaderboards should by now be full of models that ace the benchmark and are useless everywhere else.

## But that isn't what happens

Researchers have tested this directly, by building entirely new test sets for old, widely-used benchmarks. The outcome: the improvements hold up. Models that scored better on the old benchmark also score better on fresh data. The progress is real.

That's the puzzle. And until now it's been hard to study, because the "test subject" is the entire research community. You can't reset a field and redo the last decade under controlled conditions.

## The experiment: agents as lab rats

This is where AI research agents come in. They run the same optimisation loops as humans do — except you actually can reset them, wipe their memory, and control exactly what they get to see.

The setup uses three roles:

**The explorer** gets an ML problem and is allowed to freely experiment on a validation set for hundreds of rounds. Different architectures, optimizers, learning rates — testing, adjusting, testing again. This is exactly the loop that, according to theory, should overfit.

**The compressor** then reads the full log of all those experiments and tries to compress the winning strategy down to a handful of tokens.

**The reproducer** is a completely fresh model. It has never seen the validation set, never read the log. All it gets is that tiny prompt, and it has to rebuild the model from scratch using only that.

The question is simple: does the reproducer match the original performance?

## The result

Across eight varied datasets — from tabular classification to image recognition, language models and diffusion models — prompts of 16 to 32 tokens turned out to be enough. One language-model strategy survived compression down to 16 tokens, roughly like this:

```
QKn 12L768 Mu .1 R² b2M 4x
```

Cryptic to a human, but for an LLM with enough background knowledge, perfectly legible: QK-normalization, 12 layers of 768 dimensions, the Muon optimizer with a learning rate of 0.1, squared ReLU, batches of two million tokens, a four-times feed-forward block.

Cut the budget down to eight tokens and it breaks. The reproducer no longer matches the original performance. That matters: it shows those few extra tokens carry real, data-derived information — the reproducer isn't just guessing from prior knowledge.

## Why this says something about overfitting

This is the core of it, and it cuts two ways.

**Too small to memorize.** Suppose the explorer had overfit by memorizing the answers to a thousand validation examples. Passing that along would take far more than 16 tokens — a thousand individual data points simply don't fit through a channel that narrow. If it still works, nothing was memorized.

**Too few short candidates to win by accident.** There are only so many different 16-token descriptions that exist. That search space is too small to stumble onto one that scores well purely by luck. This is Occam's razor in mathematical form: among the few short hypotheses that exist, it's rare for one to mislead you by chance.

The image that sticks: a burglar escaping the bank through a narrow hatch. If he makes it out the other side and the loot checks out, he can't possibly have dragged the entire vault through with him — the hatch is too small for that. Same story here. If the strategy fits through the 16-token hatch and still works, it isn't memorization and it isn't luck. Real, transferable knowledge must have made it through.

## The test that confirms it

A good theory has to be falsifiable, and this one is. The researchers deliberately forced agents to overfit by giving them direct access to the validation set with instructions to maximize that score at any cost. In 38 of 102 runs, the validation score ended up more than 10 percentage points ahead of real performance.

And that exact gain didn't survive compression. As soon as the strategy had to pass through the narrow channel, the advantage disappeared. The method distinguished legitimate strategies from overfitting ones with high accuracy.

## Conclusion

Why doesn't benchmark-driven machine learning overfit, when the textbook says it should? Because the things that end up working are short.

A researcher stares at thousands of scores for months, but what comes out the other end is a handful of choices: an architecture family, an optimizer, a learning rate, a regularization trick. The process was long and messy, but the outcome is compact. And being compact is exactly what makes overfitting impossible — there's no room to memorize, and no room to get lucky.

Two things to take from this. First, as reassurance: the progress we see on benchmarks is probably mostly real, even though the process violates every rule of statistical hygiene. Second, as a tool: compression isn't just an explanation, it's a measuring instrument. If you can't reproduce a result from a short description, that's a red flag.

The researchers sum it up themselves in a line worth remembering: what fits into few tokens doesn't overfit.

---

*Source: [Why don't machine learning research agents overfit?](https://www.amazon.science/blog/why-dont-machine-learning-research-agents-overfit) — Martin Bertran Lopez and Aaron Roth, Amazon Science, September 2026. Underlying paper: "What fits (into few tokens) doesn't overfit: Compression and generalization in ML research agents" ([arXiv](https://arxiv.org/abs/2606.11045)).*
