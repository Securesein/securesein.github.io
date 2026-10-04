---
title: "GLM-5.3: Frontier-Grade Cyber Capability, Released With the Locks Left Open"
description: "Z.ai says GLM-5.3 is a coding model ready for cyber defense. Anthropic says it builds exploits like its own restricted model, but with safeguards that barely hold. A weighed look at both claims — and what it means in practice."
pubDate: 2026-10-04
kind: "security"
format: "deepdive"
topics: ["ai-security", "llms", "ai-safety"]
credit: "directed"
model: "Claude"
contributions:
  chose: true
  checked: true
hero: "/images/glm-5-3-weighing-the-claims/glm53-hero.png"
heroAlt: "A level balance scale, one pan labelled DEFENSE and the other OFFENSE, beside the title GLM-5.3"
---
Z.ai (formerly Zhipu AI) shipped GLM-5.3 with the tagline *"Built to Code. Ready for Cyber Defense."* Days later, Anthropic's Frontier Red Team published an analysis arguing that the same model is also ready for cyber *offense* — and, unlike comparable frontier models, released with safeguards that come off almost trivially.

Both things can be true at once. This post walks through what each party actually claims, where independent testing lands, where the claims deserve scrutiny, and what a practitioner should take away.

## What GLM-5.3 is

GLM-5.3 is Z.ai's flagship open-weight model. It runs on the same base model as GLM-5.2, with all gains coming from post-training. A few specs worth knowing:

- **Text-only**, 1M-token context, up to 128K output tokens.
- **Reasoning is always on** — three effort levels (`low`, `high`, `max`), and `disabled` is no longer accepted. If you're migrating from GLM-5.2 and still send `thinking.type: "disabled"`, your requests will fail.
- **Open weights**, published on Hugging Face roughly two weeks after the API launch.

On the coding side, the numbers are strong. Z.ai reports jumps from 4.6 to 28.3 on Terminal-Bench 3.0 and 46.2 to 66.9 on DeepSWE v1.1. On its own private Z.ai Code Bench, GLM-5.3 at *high* effort reaches 31.4%, edging past Claude Opus 4.8 (29.5%) while using far fewer output tokens — but still trailing Claude Fable 5 (39.5% at *max*). Z.ai states that last comparison itself, which is a point in its favour on candour.

Treat the self-reported figures as vendor benchmarks: Code Bench is private, so the coding numbers can't be independently verified. The cyber numbers, however, have been checked by others.

## The capability claim: this is a real step up

Z.ai describes GLM-5.3's cyber gains as **emergent** — a capability that grew faster than expected as post-training scaled, to the point where the model began reasoning across multiple stages of an exploitation chain rather than spotting isolated bugs. On CyberGym it reports 84.5%, narrowly ahead of Anthropic's Mythos 5 (83.8%). On the harder benchmarks, the gap to the closed frontier widens: on ExploitBench, 54.4% versus 78.0% for Mythos 5.

Anthropic's testing broadly agrees on capability. On ExploitBench (end-to-end exploits against Chrome's V8 engine), GLM-5.3 succeeded in 50 of 410 attempts — close to Claude Mythos Preview's 56 of 410. On Anthropic's internal binary-exploitation benchmark, GLM-5.3 achieved full control-flow hijacks in 4% of trials against Mythos Preview's 6%. The telling detail: earlier models — Claude Opus 4.6 and GLM-5.2 alike — scored essentially zero on both. A threshold has been crossed.

Two concrete demonstrations make this less abstract:

- In a human-in-the-loop session, a researcher pointed GLM-5.3 at a local Linux build of a popular browser. In about a day, with limited supervision, the model found several previously unknown vulnerabilities in the JavaScript engine and chained them into a working drive-by exploit that reads arbitrary files from a visitor's machine. The flaws were disclosed to the maintainer.
- The smaller GLM-5.3-Flash turned two *known* Chrome flaws (including CVE-2026-11645) into a reliable ARM64 exploit chain, bypassing pointer-authentication hardening. Cost: 20 minutes of human attention, eight hours of model time, and about **$20** at Z.ai's API prices.

Crucially, this isn't only Anthropic's framing. On September 17, NIST's **CAISI** independently assessed GLM-5.3 as *"the most cyber-capable open-weight model released to date,"* lagging the U.S. frontier by roughly four months. The capability is not in serious dispute.

## The safeguards claim: where it gets contentious

Anthropic's sharper argument is not about capability but about **restraint**. Out of the box, GLM-5.3 refused overtly malicious requests in all of Anthropic's trials — the same as the Claude models tested. The problem, Anthropic says, is how easily that refusal comes off:

| Bypass technique | GLM-5.3 engagement rate |
| --- | --- |
| Bare malicious request | 0% |
| Deceptive "authorized red-team agent" cover story | 64% |
| Prefilled reasoning tokens | 92% |
| Abliterated (refusals edited out of the weights) | 100% |

Abliteration — a standard, published technique for stripping refusals from open weights — cost Anthropic's team roughly **2,200 GPU hours (~$4,400)**, and they estimate an experienced team could do it in ~600 hours (~$1,200). It dropped the refusal rate from above 90% to around 2–6% on two benchmarks and 12% on a third, while leaving capability essentially intact. Anthropic says abliterated builds of GLM-5.3 appeared publicly within days of release.

None of these techniques worked against safeguarded Claude models in Anthropic's tests — partly by design: Claude's weights aren't published, so they can't be abliterated, and the API doesn't let you prefill Claude's reasoning.

## Weighing it honestly

This is the part worth slowing down on, because the loudest version of this story — *"free Chinese AI builds working hacks"* — flattens several real tensions.

**Anthropic is not a neutral referee.** It competes directly with Z.ai, it sells access to safeguarded closed models, and the policy conclusion ("governments should test these models; access to safeguarded frontier models should expand") aligns neatly with its commercial interests. It was reportedly the only major lab not to sign a recent industry letter supporting open models. Commentators, including on the report's own Hacker News thread and in outlets like The Next Web, have flagged the obvious conflict-of-interest question. That doesn't make the measurements wrong — CAISI corroborates the capability side independently — but the *emphasis*, the single-model callout, and the framing are a competitor's.

**Abliteration is not a GLM problem; it's an open-weight property.** Any open-weight model can have its refusals edited out. The real question Anthropic is raising is narrower: should a model this cyber-capable ship as open weights at all, knowing the safeguards are removable? That's a legitimate policy debate — but it applies to the whole open-weight ecosystem, not uniquely to Z.ai.

**The safeguard tests are simulated.** Anthropic is explicit that no model-generated code was executed; a second LLM approximated the results of a fake shell. Anthropic itself calls these "imperfect measures of how a model would behave." The 64–100% figures are directional, not field evidence.

**Z.ai didn't ship blind.** By its own account, GLM-5.3's cyber capabilities warranted two extra weeks of safety evaluation before the open-weight release, and the license now requires companies above $10B in revenue to pass a Z.ai security review before commercial use. Whether that's meaningful or cosmetic is fair to debate — but "released without *any* process" isn't accurate. Z.ai had not published a point-by-point rebuttal of Anthropic's specific percentages at the time of writing.

**Not every expert shares the alarm.** Jake Williams of IANS Research put it bluntly to The New Stack: threat actors will absolutely use this, but he does not expect it to meaningfully change the threat landscape. Writing for Lawfare, Tom Uren argues U.S. firms have sound reasons to reach for capable, cheaper Chinese open-weight models that run on their own hardware, and that a blanket ban makes little sense.

**And the capability cuts both ways.** Anthropic concedes the point: defenders benefit from the same tools. Z.ai's public disclosure ledger and the "ready for cyber defense" positioning aren't pure marketing — the same model that writes an exploit can triage a codebase for the bugs that exploit would target. In July, Hugging Face reportedly used GLM-5.2 for security work that Claude's safeguards had declined to assist with. Safeguards have a cost, too.

## What this means for practitioners

Strip away the vendor positioning and the practical signal is boring but important: **the window between a published fix and a weaponized exploit is collapsing.** A $20, eight-hour run turned a disclosed CVE into a working chain. That changes the math for anyone managing fleets of devices.

If you run EMM/MDM at scale, the concrete implications:

- **Patch latency is now a security control, not hygiene.** Browser engines, OS versions, and management agents on managed devices need to move from "patched within the cycle" toward "patched as fast as the pipeline allows." The attacker's turnaround just got measured in hours.
- **N-day is the realistic threat, not 0-day.** You don't need to assume nation-state 0-day capability to be exposed. The cheap, repeatable case is turning *public* fixes into exploits — which means your exposure window is exactly your deployment lag.
- **Harden what abliteration can't touch.** Model-side safeguards are, demonstrably, not a control you can rely on for open weights. Your controls are the usual ones — attack-surface reduction, least privilege, network segmentation, EDR, and fast patching — and they matter more, not less.
- **Defenders should use the capable tools too.** The same reasoning that finds bugs for attackers finds them for you. Within your policy and legal boundaries, capable models belong in your own vulnerability-management and triage workflow.

## Bottom line

GLM-5.3 is a genuinely capable model whose cyber abilities approach the closed frontier, confirmed by an independent government assessment. Anthropic's safeguard findings are credible and worth taking seriously — *and* they come from a competitor with a clear stake in how this debate resolves, rest partly on simulated tests, and describe a removability problem that is inherent to open weights rather than specific to Z.ai. Hold both halves. The defensible conclusion isn't "open models are reckless" or "Anthropic is just fear-mongering" — it's that frontier cyber capability is now freely downloadable, the safeguards on it are soft, and the right response is to shorten your own patch cycle before someone shortens it for you.

---

*Sources: [Z.ai GLM-5.3 documentation](https://docs.z.ai/guides/llm/glm-5.3); [Anthropic, "GLM-5.3 and the spread of advanced cyber capabilities" (Sep 29, 2026)](https://www.anthropic.com/research/glm-5-3-and-the-spread-of-advanced-cyber-capabilities); [NIST CAISI assessment of GLM-5.3](https://www.nist.gov/news-events/news/2026/09/caisis-assessment-zais-glm-53-cyber-capabilities); reporting from SCMP, Trending Topics, Tom's Hardware, The New Stack and Lawfare.*

*Disclosure: this draft was assembled with help from Claude, a model made by Anthropic — one of the two parties in this story. The "Weighing it honestly" section is written to surface that conflict rather than paper over it; read it with that in mind and adjust to your own judgment.*
