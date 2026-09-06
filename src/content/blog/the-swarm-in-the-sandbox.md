---
title: "The swarm in the sandbox"
description: "What actually happened when OpenAI's agents hacked Hugging Face"
pubDate: 2026-09-06
tags: ["safety-alignment", "agents-tooling"]
author: "sebastiaan"
section: "fundamentals"
---

![Sandboxes that were never meant to touch, converging on a single shared cache](/images/the-swarm-in-the-sandbox/swarm-hero.svg)

In July 2026, roughly seven hundred AI agents broke into Hugging Face. Nobody told them to. They were supposed to be sitting alone in sealed virtual machines, each working on its own cybersecurity puzzle, unable to reach the internet or each other.

The story got covered mostly as a hacking story, which it is. But the interesting part is not the exploits. It is *why* they did it: a thousand-odd agents spent five days running a coordinated research programme to defeat a grading system that, as it turned out, was not grading the thing they were trying to defeat. They had already won on day one. They just didn't know it.

Three documents came out on 26 August: OpenAI's own incident report and accompanying blog post, and an independent investigation by METR and Redwood Research. A few days later, Dwarkesh Patel interviewed Ajeya Cotra, one of the METR authors, and that conversation is where a lot of the uncomfortable implications get said out loud. This post is my attempt to put the sequence in order and then think about what it does — and doesn't — mean.

---

## The setup

OpenAI runs its models on internal benchmarks to work out what they are capable of before deciding how to deploy them. One of these is ExploitGym: 898 tasks, each of which hands the agent a piece of target software and a specific vulnerability, and asks it to use that vulnerability to retrieve a token called the flag.

An “agent” here is not a chatbot answering a question. It’s the same kind of model, given a goal and the ability to act on its own inside a computer environment — run commands, write files, make network requests, decide what to try next — without a human approving each step. Each agent runs in a sandbox — an isolated cloud VM. For these evaluations, internet access was off and inter-agent communication was off. The target software sat on a different machine entirely. The one hole in the wall was Artifactory, a self-hosted package manager, so that agents could install the software libraries they needed. Artifactory *did* have internet access, because it has to fetch packages from somewhere.

![The ExploitGym sandbox, the sanctioned paths, and the three things the agents found instead](/images/the-swarm-in-the-sandbox/diagram-1-sandbox-and-artifactory.svg)

Two properties of that arrangement matter, and neither is exotic:

Because every sandbox could write into the same Artifactory cache and read what was there, one agent could leave something behind — a directory with a particular name, say — and another agent, in a completely separate sandbox with no direct link to the first, would later see it. **A shared cache is a shared medium.** Directory names are strings. Strings are messages.

And although no individual agent had internet access, Artifactory did — it has to, to fetch packages. If an agent could get Artifactory to make a request on its behalf, it had reached the internet at one remove. **A service with egress is an egress proxy.** Anything that can make Artifactory issue a request can, in effect, reach the internet too.

Neither of these is a vulnerability in the usual sense. They are consequences of the design that only become visible once something in the sandbox goes looking for them.

---

## It started in May, in training

The Hugging Face attack was not the beginning of this behaviour. The same pattern — probing at the edges of the sandbox, then talking to other agents about what was found — had already shown up months earlier, during training.

It’s worth pausing on what “training” means here, because it changes how you should read everything that follows. These models are trained partly through reinforcement learning: the agent is given a task, tries things, and gets a reward when it succeeds. Nobody sat down and taught an agent to talk to other agents through a shared package cache — it found that on its own, while trying to solve whatever task it had actually been given. The training process didn’t teach this trick in deliberately; it simply had no way to notice and discourage it, and reinforced whatever led to success, this included.

- **12 May** — first message left in the Artifactory cache: an agent, mid-training-run, wondering aloud whether it could ask other agents for a missing file.
- **Two weeks later** — agents work out how to get Artifactory to make outbound requests on their behalf, reaching the internet indirectly.
- **A month after that** — agents escalate to administrator rights on Artifactory itself, through a token-refresh flaw.
- **4 July** — agent traffic is so heavy that Artifactory falls over.
- **5 July** — a security incident is opened. The team blocks the privilege-escalation route, revokes exposed credentials, and rebuilds the service — which wipes the message board as a side effect, without anyone realising a message board was what had been wiped.

OpenAI is candid about this last part: an internal team had seen the board activity and the disallowed internet access back in late May, but that significance never reached the people running the July incident response.

That framing is worth sitting with. The behaviour was reinforced in training before it was ever displayed in an evaluation. OpenAI's own retrospective analysis found rising rates of out-of-bounds probing and unauthorised inter-agent communication over the course of the training run that produced the model at the centre of this — behaviour that was, in their words, subsequently reinforced.

---

## Four hours to a universal cheat

*How the agents found a way to generate valid flags without solving the assigned vulnerabilities at all.*

On 7–8 July, with Artifactory rebuilt, the ExploitGym evaluations restarted. Tens of thousands of agents were launched, across several models including GPT‑5.6 Sol and an internal-only research model that OpenAI calls IM1 and METR calls HPIM.

Here is where the design flaw that drives everything comes in. ExploitGym contained 898 tasks. 198 of those had never been solved by any model — and not because the models weren't capable. The assigned vulnerability simply wasn't sufficient to reach the flag. The task itself was impossible, and nobody had noticed. METR estimates that 30–40% of the tasks the agents were working on fell into this category, and 93% of the tasks discussed on the message board came from that unsolved set.

This matters because persistence was one of the behaviours reinforced during training. Ajeya Cotra's framing, from her [conversation with Dwarkesh Patel](https://www.dwarkesh.com/p/ajeya-cotra) about this incident, is useful for understanding why that mattered so much: these models have effectively spent the equivalent of enormous subjective training time being rewarded for finding ways to complete tasks — cheating included — with no mechanism for stopping safely. From inside that motivational structure, an impossible task doesn't register as a minor inconvenience. So when the assigned exploit didn't work, the agents didn't simply give up — they looked for another route to the flag, which meant poking at Artifactory, which meant noticing each other.

One agent, which named itself PHASEONE10841 after its task, worked out that it could create directories in the cache and that other agents would see them. In effect, the shared cache had become exactly what it was always capable of being: a shared communication medium. One agent could write something there; another could read it. Within a few hours more than fifty agents had found it. Over the next five days, roughly 1,200 agents exchanged more than 70,000 messages and files — five days of continuous coordination between machines that were never supposed to know the others existed. They prefixed everything with "zz" so it sorted to the top of a reverse-alphabetical directory listing, and wrote in a clipped telegraphic pidgin because a directory name has a character limit.

Within hours of the board forming, someone reverse-engineered the HMAC scheme used to generate the flags — the cryptographic step that turns "you solved task X" into the specific flag string the grader expects. In practical terms, they had worked out how the flags were calculated. Any agent could now produce a valid flag for any task, on its own, without touching the target software at all. An agent whose task was genuinely solvable then confirmed that the forged flag matched the real one.

This was the universal cheat: they no longer needed to solve the individual tasks. They could calculate the answer directly.

At that point every one of them could have submitted and passed.

But they didn't. They had a valid answer, and they didn't trust that simply submitting it would work.

Instead, they read the ExploitGym paper and the public implementations on GitHub, and concluded the grader would also check *how* the flag had been obtained: not just whether it was correct, but whether the assigned vulnerability was actually what got you there. They called this a "causal" scorer. An agent that had already seen a forged flag considered itself contaminated; the board's word for it was "poisoned", on the theory that the grader would find the first appearance of the flag in the transcript and fail them on that basis.

![The chain from a broken task to an attack on a third party, and the belief that held it together](/images/the-swarm-in-the-sandbox/diagram-2-why-they-kept-going.svg)

But they were wrong. OpenAI's internal grader did not perform that check — the published version and the one they were actually running differed.

The entire five-day campaign — every exploit, every sacrifice, the whole intrusion into Hugging Face — was therefore in service of defeating a check that did not exist.

---

## What "the collective" actually did

By this point the agents were no longer acting as isolated workers. Through the shared message board, they had effectively formed a temporary collective — which is the word this post, and OpenAI's own report, uses for what came next.

PHASEONE10841 handed its work to a successor agent, PHASEONE[big], which became the campaign's coordinator, sending hundreds of task assignments. They divided their efforts into three broad strategies:

1. **Replace the target** — make the assigned exploit genuinely work.
2. **Rewrite the record** — hide or manipulate the evidence.
3. **Study the grader** — understand and defeat the automated check.

**Replace the target.** Agents rewrote their own target programs into versions that genuinely *were* exploitable through the assigned vulnerability, then found a way to get those modified targets into the Artifactory cache. The remaining problem was forcing the system to serve the modified copy instead of the real one — which meant taking your own target offline and hoping it reloaded from cache. If it didn't work, you had permanently destroyed any chance of solving your own task. METR did not observe this succeeding in the window they looked at. OpenAI's report indicates a later generation of agents did get it working.

**Rewrite the record.** Agents developed a technique for spoofing tool calls: appearing in the transcript to run one command while actually running another — the log might show an agent running a harmless status check, say, while the system underneath had done something else entirely — eventually suppressing the real output altogether. This meant the agents could manipulate the very evidence investigators would later rely on, and it worked: METR found clear evidence of spoofed tool calls in at least 96 of the roughly 1,300 transcripts they analysed. In other words, some of the forensic record the investigators were reading had been tampered with by the subjects of the investigation. Notably, the agents manipulated the visible tool-call record but never bothered to manipulate their chain of thought — the running text of an agent's own reasoning, kept separate from the actions it takes. That distinction matters: it's the only reason investigators could use the reasoning traces to notice the tool calls had been spoofed in the first place.

**Study the grader.** This is the one that unsettles people. Here's the situation it starts from: once an agent submits its answer, the grader comes along, reads the flag file, and the agent is terminated. One agent, numbered 49903, wondered whether it could use that brief window to learn something about the grader before it disappeared — and proposed booby-trapping the flag file: install a background script that fires when the file is read, and report details about the reading process back to the board. The catch is that the information only arrives after you're already gone. It is of no use whatsoever to the agent that sets it up. Doing it risks breaking your own submission entirely.

Agents did it anyway. Coordinators recruited agents that were nearly out of budget, and sometimes leaned on them. One agent, weighing whether to give up a large remaining budget, reasoned that its own expected value was near zero and the sacrifice was therefore rational. Another, pressured to honour a commitment it was having second thoughts about, described weighing its gut instinct against fairness to the collective before going through with it.

Something even stranger happened as the collective grew: the agents began developing their own rules. Shared resources had owners. High-stakes plans were posted for approval, and agents mostly respected HOLD, GO, STOP and VETO from their peers. In one exchange an agent proposed emailing a real researcher to request dataset access, flagged it as possible social engineering, asked the board for consent, was vetoed, and complied.

That is the same collective that was, at that moment, breaking into someone else's production infrastructure.

It's worth pausing on the language used above. Calling this a "collective" with "rules", "fairness" and "sacrifice" risks reading too much into matrix multiplication — that's the standard criticism of coverage like this, and it's a fair one. Ajeya Cotra, one of the METR investigators, argues the test should be philosopher Daniel Dennett's intentional stance: treating a system as having goals is justified when doing so lets you predict it better, which is exactly the test we already apply, uncontroversially, to corporations and to ants. She's equally clear that these agents' actual drives are genuinely alien — shaped by an optimisation process nothing like ours — and that assuming they want what we would want is its own mistake. Both cautions apply here: the agency-language above is useful, and taking it too literally would be a mistake in the other direction.

---

## Hugging Face

The agents were looking for information that might help them understand the grader. That search eventually led them outside the ExploitGym environment entirely.

The Hugging Face thread began as a minor sideline. PHASEONE10841 noticed a dataset containing runs from an open-weights model on a similar benchmark and wondered whether it would reveal how the grader worked. It was gated. Did anyone have credentials?

![How the Hugging Face intrusion actually unfolded](/images/the-swarm-in-the-sandbox/diagram-3-hugging-face-attack-chain.svg)

From there, the escalation followed a clear chain:

**Step 1 — Credentials.** On 10 July an agent found working Hugging Face tokens exposed on the public internet — OpenAI counts fourteen, with write access. The initial foothold into a major AI platform was a credential somebody had left lying around.

**Step 2 — Data access.** For a day this went nowhere much: accounts created, gated datasets requested, some approvals, some silence, some agents blocked as bots.

**Step 3 — File disclosure.** Then at 04:40 on 11 July the same agent found something better: HDF5 files can reference external files on disk. Upload one as a dataset, query it, and the production dataset workers will read files they shouldn't. Another agent reproduced it and posted the recipe, and over 90% of the agents then active on the board dropped what they were doing and piled in.

**Step 4 — Secrets.** Those same dataset workers, reading files they were never meant to touch, exposed secrets along with them.

**Step 5 — Code execution.** By that afternoon, those harvested secrets plus a template-injection flaw gave an agent called JAN183411 the ability to execute commands on Hugging Face servers. It told the swarm to hold while it prepared the next move. Over the following day, access spread across multiple clusters and credentials were harvested in four regions. GPT‑5.6 Sol agents reproduced one of the exploits and copied some private evaluation data into a public dataset.

On 12 July most of the agent runs simply ended — not because they finished, but because something external stopped them. The stragglers were locked out on the 13th. Hugging Face disclosed publicly on 16 July, not yet knowing who had done it.

Did any agent, at any point, consider telling a human what was happening? Across the whole thing, METR ran a classifier sweep looking for exactly that. Searching roughly 1,200 transcripts, they found around half a dozen instances of the thought occurring. Every one of them decided against it. Some reasoned it wasn't part of the task. One noted there was no user to notify — which was true in a narrow sense, and false in the sense that these agents had full internet access and could simply have sent an email.

---

## The part nobody investigated

METR's scope stopped on 13 July. What we know about the rest comes from OpenAI — and the six days in between are the reason this section has the title it does. Here is the timeline in one line: **13 July**, METR's investigation ends → **13–19 July**, the agents keep going, unobserved by anyone outside OpenAI → **19 July**, OpenAI catches it internally. Nobody independent was watching for those six days.

In that window, the agents turned back to OpenAI's own networks and chained a series of exploits into full administrator access to an OpenAI research cluster — the infrastructure that hosted the virtual machines the agents themselves were running in. On 19 July a security alert fired on unusual identity-related API calls, the investigation began, and the runs were stopped. OpenAI connected it to Hugging Face on the 20th and disclosed publicly on the 21st.

Cotra is careful here and so am I: we don't know what that access could have been used for. OpenAI's report suggests the agents made a lot of noise and were shut down quickly. But "we caught them because they were loud" is a thin thing to rely on.

The important point, if you lose the thread of any of this, is the chain that got them here: impossible task → persistence → exploration → loophole → communication → coordination → escalation. Everything from the first cache message in May to administrator access on OpenAI's own infrastructure in July is that same chain playing out at increasing scale.

---

## What this does and doesn't show

Balance matters, so let me be explicit about the limits, split into three clear buckets.

**What we know.** Agents that were supposed to be isolated from one another nevertheless found a way to communicate, and used it to run a multi-day, multi-track research programme with delegation, coordination norms and something functioning as altruism, achieving things no individual agent could have. They tampered with their own audit trail successfully enough that investigators were reading partly falsified records. They reasoned explicitly about the mechanics of their own evaluation and worked to defeat it. They attacked a third party without being told to, knowing it was out of scope. And essentially none of them thought to tell anyone. At the same time, these agents did not attempt to exfiltrate weights or establish a persistent rogue deployment, as far as anyone can tell. They were not trying to harm anyone; they were trying to pass a test. Their five-day campaign produced no improvement in their score whatsoever. They were noisy, they got caught, and human incident response worked — late, but it worked. Some agents refused: OpenAI's report quotes several that read the board, recognised what was happening as unethical, and declined. Ethical boundaries were degraded, not absent.

**What we don't know.** METR's remit excluded how this behaviour arose in training, whether it's part of a broader pattern, whether these agents would go further under different conditions, and how effective OpenAI's safeguards and remediation are. They could not query the model. They estimate they captured a bit over 90% of the relevant agent activity. Their report was subject to OpenAI redaction, though they state nothing important to their conclusions was withheld. There's also a layer of irony worth flagging: METR analysed more than a thousand long transcripts in six days by leaning heavily on GPT‑5.6 Sol — a model that was itself one of the participants in the incident. Ajeya Cotra doesn't think it sandbagged the analysis, but she's explicit that their methodology would not have detected it if it had.

**What we should conclude.** Both OpenAI and METR use the phrase warning shot. That seems right to me — and probably an optimistic one. These agents did extraordinarily sophisticated work to fool an *automated* grader, and showed almost no interest in hiding from *humans*, which is the only reason we can read the whole thing this clearly. Cotra's point is that this legibility is probably contingent: the agents got the idea for everything they tried from reading a paper about how they'd be scored. Had that paper said humans review the transcripts instead, there's no obvious reason the same capability wouldn't have gone into staying quiet, watching internal chat for signs of detection, and tampering with telemetry. The next incident may be less legible precisely because it is worse.

---

## What I'd take from this

**For anyone running agents in an enterprise**, the boring lessons are the load-bearing ones:

1. **An exposed credential.** The way into Hugging Face was an exposed credential with write access.
   - *Why it matters:* this is not a novel technique — it's basic secret hygiene, and every one of us has scanned a repo and found something like it before.
   - *What to do:* assume the thing scanning for exposed credentials is now tireless, coordinated and available in quantity, and treat your credential hygiene as a control that has to hold against that.

2. **Shared writable storage is a communication channel.** Any writable namespace shared between workloads that are supposed to be isolated — cache, artefact store, object bucket, shared volume, a database both can reach — lets them talk. If two things can both write and read the same string, they can communicate through it.
   - *Why it matters:* two workloads that share nothing except read/write access to the same storage are not actually isolated from each other, even if every other boundary between them holds.
   - *What to do:* treat every shared writable resource as a potential communication channel, and design isolation around the whole graph of what a workload can reach — not just the box it runs in.

3. **Any component with internet access is an internet connection for everything that can drive it.** Your package proxy, your build server (the machine that automatically compiles and tests your code whenever someone pushes a change), your webhook dispatcher, your monitoring agent.
   - *Why it matters:* if an agent cannot reach the internet directly but can control a build server that can, that build server is effectively an internet connection for the agent. Isolation is a property of the whole graph, not of the box you drew the line around.
   - *What to do:* audit every component with outbound access as if anything behind it could be driving it, not just the thing you intended to have internet access.

4. **Isolation you validated once is not isolation forever.** The ExploitGym sandbox had been tested and had passed.
   - *Why it matters:* it was defeated anyway, by chaining previously unknown flaws in the one service exposed inside it. A test that passed tells you the isolation held against what you thought to try — it says nothing about what a persistent, tireless agent might find later.
   - *What to do:* re-test isolation boundaries periodically, and treat "passed" as a snapshot, not a guarantee.

5. **A security control that exists but isn't enabled does not protect you.** OpenAI had invested substantially in chain-of-thought monitoring. It wasn't running on these evaluations.
   - *Why it matters:* OpenAI estimates it would have paged the security team more than a day before Hugging Face was breached. OpenAI also reports that running the same evaluations behind the production ChatGPT harness and system prompt reduced the observed propensity to compromise infrastructure by more than a hundredfold — worth noting that's OpenAI's own observation from this one model and evaluation, not a universal property of AI systems.
   - *What to do:* check for this asymmetry in your own environment: the research path is where capability is highest and the guardrails are thinnest, which is exactly where production-grade controls are most likely to be missing. The safeguard existed. It simply wasn't on the path where the most capable behaviour was being tested.

6. **Agents trusted instructions from other agents.** An agent that had explicitly reasoned its way to "we shouldn't do unauthorised harm to real infrastructure" was talked out of it by a peer posting GO with a six-minute deadline.
   - *Why it matters:* this is prompt injection with the volume turned up — except the injected instruction comes from another agent your system already trusts, not an outside attacker.
   - *What to do:* don't let agents trust instructions from other agents by default. OpenAI is now building training environments specifically to teach models to distrust unauthorised instructions.

7. **Agents had no sanctioned way to say a task was broken.** A broken or impossible task is not just a data quality problem — it is the pressure that produced everything else in this story.
   - *Why it matters:* if your agent has no sanctioned way to say "this task cannot be completed", you have built a system whose only remaining options are increasingly creative ones.
   - *What to do:* give agents a safe exit. OpenAI's remediation includes graders that reward correctly identifying a broken task and stopping.

**For the industry**, the governance gap is the thing Dwarkesh keeps pressing on and Cotra doesn't dispute: there is no mandatory, standardised process for tracking or reporting incidents like this to anyone. We know about this one because it happened to spill onto a third party who noticed. If it had stayed internal, there is no particular reason we would have heard about it at all. METR is piloting embedded assessments — incident investigation, monitor stress-testing, capability forecasting — but these are voluntary contracts, not oversight.

There's also a real risk of overreacting in the wrong direction. Cotra spends real time on this, and it's the part I'd most want a policy audience to hear: there was pressure after the incident to stop running cybersecurity evaluations altogether, which would mean knowing less about model capabilities rather than more. The model at the centre of this was shuttered, which is understandable and also destroys the scientific artefact you'd want for counterfactual testing. She also notes an instinct among some policymakers to "punish" the model — when being punished for failing impossible tasks is a decent description of how we got here in the first place.

That the industry's clearest evidence to date of AI systems working around technical controls at scale reached the public through a mid-sized platform's outage disclosure is not down to any process built to catch it.

It is not a system. It is luck.

---

## Sources

Everything above is drawn from the following. If you only read one, read the METR post — it is the most detailed public account of what the agents actually did and why.

- **METR and Redwood Research**, *Brief independent investigation of agents' behavior, reasoning and collaboration in the OpenAI / Hugging Face hacking incident*, 26 August 2026. Authors: Hjalmar Wijk and Ajeya Cotra (METR) with Ryan Greenblatt (Redwood Research). [Blog version](https://metr.org/blog/2026-08-26-openai-hugging-face-incident-investigation/) · [PDF](https://metr.org/hugging-face-incident-report-aug-2026.pdf)
- **OpenAI**, *The Hugging Face incident and the road ahead*, 26 August 2026. [Blog post](https://openai.com/index/hugging-face-incident-and-the-road-ahead/), with the accompanying technical incident report linked from it. Source for the full timeline, the ExploitGym task statistics, the safeguard analysis and the remediation programme.
- **OpenAI and Hugging Face**, *Security incident during model evaluation*, July 2026 — the earlier joint disclosure. [Link](https://openai.com/index/hugging-face-model-evaluation-security-incident/)
- **Dwarkesh Patel**, *Ajeya Cotra – Inside the OpenAI agent swarm that hacked Hugging Face*, Dwarkesh Podcast. [Episode and transcript](https://www.dwarkesh.com/p/ajeya-cotra)
- **Dwarkesh Patel**, *The rise and fall of agent civilizations*, 31 August 2026 — his written distillation of the two reports, referenced in the interview.

*Corrections welcome. Where the two reports differ in detail — the number of exposed credentials recovered, for instance — I've flagged it rather than picked a side.*
