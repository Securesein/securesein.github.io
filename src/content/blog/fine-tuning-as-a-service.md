---
title: "Fine-Tuning-as-a-Service: What It Is and What It's Used For"
description: "How hosted fine-tuning works under the hood, what organisations use it for, and why a few training examples can undo a model's safety."
pubDate: 2026-10-13
kind: "explainer"
format: "explainer"
topics: ["training", "llms", "ai-safety"]
credit: "directed"
model: "Claude"
contributions:
  chose: true
hero: "/images/fine-tuning-as-a-service/hero.png"
heroAlt: "A stack of frozen transformer layers under a padlock, with one thin adapter slotted in between them and a .jsonl training file feeding it."
---
Fine-tuning-as-a-service lets you take a hosted large language model, upload a file of a few hundred example conversations, and get back a private version of that model that behaves the way your examples do. You never touch a GPU or the model weights: the provider runs the training and hosts the result behind an API.

That makes model customisation a procurement decision instead of a research project. It also makes it a new attack surface, which is where most practitioners have not looked yet. This post covers what the service is, how it works under the hood, what organisations actually use it for, and where it can go wrong.

## What fine-tuning actually is

Fine-tuning is continued training of a model that already exists, on a small set of your own examples. It does not build a model from scratch, and the difference in scale is enormous.

Take Meta's Llama 3.1 8B as a reference point. Its pretraining used roughly 15 trillion tokens of text and about 1.46 million H100 GPU-hours ([model card](https://huggingface.co/unsloth/Llama-3.1-8B)). That is where all of its language ability and world knowledge comes from. A typical fine-tuning job, by contrast, uses a few hundred to a few thousand examples and runs in minutes to hours. The model learns no new fundamentals; it gets a nudge in behaviour.

Fine-tuning is one of three ways to bend a general model towards your use case:

| Approach | What changes | Good for |
| --- | --- | --- |
| Prompting | Nothing in the model; you add instructions per request | Quick experiments, behaviour you can describe in words |
| Retrieval (RAG) | Nothing in the model; relevant documents are injected at request time | Facts that change, internal knowledge bases, anything that needs a citation |
| Fine-tuning | The model itself (or an adapter on top of it) | Consistent format, tone or classification behaviour that is hard to describe but easy to show |

A useful rule of thumb: RAG changes what the model *knows* in the moment, fine-tuning changes how it *behaves* every time.

## How the service works

From the customer's side, fine-tuning-as-a-service is four steps, and you never see the model weights at any point. OpenAI's documentation describes the flow like this ([supervised fine-tuning guide](https://developers.openai.com/api/docs/guides/supervised-fine-tuning)):

1. **Build a dataset.** Each line of a JSONL file holds one example conversation: a prompt and the answer you want. OpenAI accepts a minimum of 10 examples and recommends starting with around 50 well-crafted ones.
2. **Upload it.** The file goes to the provider with the purpose `fine-tune`.
3. **Start a job.** You pick a base model and point it at your file. Training takes minutes to hours.
4. **Call your model.** You get back a model ID (for example `ft:gpt-4.1-nano-...`) that you use in the same API as the base model.

A single training example for a ticket classifier looks like this:

```json
{"messages":[{"role":"user","content":"My work phone keeps asking for the Company Portal password"},{"role":"assistant","content":"category: authentication | priority: medium"}]}
```

### Under the hood: adapters inside the layers

Most providers do not retrain the whole model per customer. They use LoRA (Low-Rank Adaptation), and to see how that works you need one level of detail about the model itself.

A model like Llama 3.1 8B is a stack of 32 transformer layers. Every layer holds a handful of weight matrices: four in the attention block (usually called Q, K, V and O) and three in the feed-forward block. A question passes through all 32 layers once, and in each layer those matrices transform the text step by step.

LoRA attaches a small adapter to some of those matrices, commonly Q and V, in every layer. The original weights W stay frozen; only the adapter's two thin matrices, A and B, are trained. Each adapted matrix then computes:

```text
h = W x + B A x
```

So the adapter is not a post-processing step that rewrites the answer afterwards. It runs in parallel inside each layer, and its small correction is added to the original result before the text moves on to the next layer.

A toy example makes this concrete. Take input x = [1, 2] and a matrix W that leaves it unchanged, so W · x = [1, 2]. A rank-1 adapter with A = [1, 1] compresses x into a single number, 3, and B = [0.5, −0.5] expands that back into [1.5, −1.5]. Added together, the layer outputs [2.5, 0.5].

Because B · A is just another matrix, it can also be added to W ahead of time. The merged matrix [[1.5, 0.5], [−0.5, 1.5]] gives exactly the same [2.5, 0.5] with no extra computation, so a fine-tuned model can be shipped as one ordinary model.

At real scale the adapter stays tiny. For Llama 3.1 8B with a rank-8 adapter on Q and V:

| Matrix | Size | Adapter parameters (rank 8) |
| --- | --- | --- |
| Q, per layer | 4,096 × 4,096 | 65,536 |
| V, per layer | 4,096 → 1,024 | 40,960 |
| All 32 layers |  | ≈ 3.4 million (about 0.04% of 8 billion) |

Providers usually keep adapters separate instead of merging them. A request to your model is computed with the shared base model plus your adapter; the next customer's request uses the same base with theirs. That is how one GPU fleet serves thousands of custom models, and it is also what lets research such as SLDR (below) switch a safety adapter on or off per request.

For anyone who manages devices: the base model is a golden image, the adapter a configuration profile. It changes behaviour at the source, where the work happens, rather than acting like a proxy that rewrites the output afterwards.

## Who offers it

All three hyperscalers sell fine-tuning as a managed service, and the market is shifting: OpenAI is winding down its own fine-tuning platform, while Microsoft is expanding its catalogue. As of October 2026:

| Provider | Example base models | Worth knowing |
| --- | --- | --- |
| [Microsoft Foundry](https://learn.microsoft.com/en-gb/azure/foundry/openai/how-to/fine-tuning) | GPT-4o, GPT-4.1 family, o4-mini and GPT-5 (reinforcement fine-tuning), plus Ministral-3B, Qwen-32B, Llama-3.3-70B and gpt-oss-20b | Uses LoRA. Training requires the Foundry User role, deploying requires Foundry Owner. Standard tier keeps data in-region; Global and Developer tiers do not |
| [Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/custom-model-fine-tuning.md) | Amazon Nova family, Claude 3 Haiku, Llama 3.1, 3.2 and 3.3 | Fine-tuning runs in specific US regions (us-east-1 or us-west-2, depending on the model) |
| [Google Vertex AI](https://cloud.google.com/vertex-ai/generative-ai/docs/models/gemini-supervised-tuning) | Gemini models | You choose an adapter size; tuned data stays in the job region, but compute may be offloaded to other US or EU regions |
| [OpenAI](https://developers.openai.com/api/docs/guides/supervised-fine-tuning) | GPT-4.1, 4.1-mini, 4.1-nano | Closed to new users and being wound down; existing fine-tuned models stay available until their base model is deprecated |

Two cost details catch people out on Azure: a deployed fine-tuned model incurs an hourly hosting fee whether you call it or not, and a deployment that receives no calls for 15 days is deleted automatically (the model itself remains).

## What organisations use it for

Fine-tuning earns its keep on narrow, repetitive tasks where the desired output is easy to show and hard to describe. OpenAI lists classification, nuanced translation, a fixed output format and fixing instruction-following failures as the best fits ([source](https://developers.openai.com/api/docs/guides/supervised-fine-tuning)). In practice that looks like:

- **Classification and routing.** Sorting service-desk tickets into categories and priorities, or tagging incoming mail by intent.
- **Strict output formats.** Turning free-text requests into a fixed JSON schema, for example a configuration payload that downstream automation consumes.
- **House style and terminology.** Answers in a company's tone of voice, or consistent use of internal product names.
- **Distillation.** Training a small, cheap model on the outputs of a large one, so a narrow task runs at a fraction of the cost and latency.

The economic argument is mostly about prompts. Microsoft points out that a fine-tuned model needs fewer instructions and examples per call, which saves tokens and lowers latency, especially on smaller models ([source](https://learn.microsoft.com/en-gb/azure/foundry/openai/how-to/fine-tuning)). If a 2,000-token prompt shrinks to 200 tokens, you pay for 90% fewer input tokens on every single request.

### When not to fine-tune

- **Your facts change.** Fine-tuning bakes behaviour in; it is a poor way to teach a model this quarter's price list or policy. Use retrieval instead.
- **You cannot measure success.** Both OpenAI and Microsoft tell you to build evaluations first. Without a baseline you cannot tell whether the tuned model is better.
- **You have fewer than about 50 good examples.** Both providers recommend starting at 50 well-crafted examples, and Microsoft notes that low-quality data can make the model worse.
- **A better prompt would do.** If you can describe the behaviour in a paragraph, try that first: it is free and reversible.

## The security angle: safety is a thin layer

The same mechanism that makes fine-tuning cheap also makes it dangerous: a small nudge in behaviour can undo safety training just as easily as it adds a house style. In 2023, a team led by Xiangyu Qi jailbroke GPT-3.5 Turbo through OpenAI's own fine-tuning API with only 10 crafted examples, for less than USD 0.20 ([Qi et al., ICLR 2024](https://arxiv.org/abs/2310.03693v1)). The tuned model would follow nearly any harmful instruction.

The more uncomfortable finding for enterprises is in the paper's title: safety also degraded when the researchers fine-tuned on a perfectly benign dataset. You do not need an attacker to weaken a model's refusals; an ordinary business fine-tune can do it as a side effect.

### How providers defend

Providers now treat the customer's training file as untrusted input. OpenAI evaluates every finished fine-tune across 13 safety categories and blocks deployment when a category fails its threshold ([source](https://developers.openai.com/api/docs/guides/supervised-fine-tuning)). Microsoft likewise runs safety evaluations before a checkpoint becomes deployable ([source](https://learn.microsoft.com/en-gb/azure/foundry/openai/how-to/fine-tuning)).

Research is moving towards repairing models after the fact. A recent NeurIPS 2026 paper, SLDR ([code](https://github.com/Stardust457/SLDR)), finds the two layers of the model that most strongly push towards and away from refusing, retrains only those two with a small safety adapter, and switches that adapter on only when an incoming prompt looks harmful. On Llama 3.1 it cut harmful answers from 11.54% to 0.08% without hurting task accuracy. Its weak spot is the gate: prompts translated into Zulu slipped past it, with 61.5% still answered harmfully.

All of this only works because the provider holds the weights. Once a model's weights are downloaded and fine-tuned locally, as is possible with Llama or Qwen, none of these defences apply.

## Takeaways for practitioners

1. **Try prompting and retrieval first.** Fine-tune only for stable, narrow behaviour, and only once you have evaluations to prove it helped.
2. **Treat a fine-tune as a change to a production system.** Re-run your safety and refusal tests on the tuned model, not just your accuracy tests: a benign dataset can still erode guardrails.
3. **Govern who can train and who can deploy.** On Azure these are separate permissions; keep them with separate people, the same way you separate building a configuration profile from assigning it.
4. **Check data residency before you click Global.** Cheaper training tiers can move your data and weights out of region.
5. **Watch the lifecycle.** Hosted fine-tunes cost money while idle, can be removed when unused, and die with their base model, as OpenAI's wind-down shows.

Fine-tuning-as-a-service turned model customisation into a few API calls. That convenience is real, and so is the new attack surface. Both deserve the same discipline we already apply to everything else we push to managed endpoints.

## Sources

- [Llama 3.1 8B model card (Meta, via Hugging Face)](https://huggingface.co/unsloth/Llama-3.1-8B)
- [OpenAI: Supervised fine-tuning](https://developers.openai.com/api/docs/guides/supervised-fine-tuning)
- [Microsoft Learn: Customize a model with fine-tuning](https://learn.microsoft.com/en-gb/azure/foundry/openai/how-to/fine-tuning)
- [AWS: Customize a model with fine-tuning in Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/custom-model-fine-tuning.md)
- [Google Cloud: About supervised fine-tuning for Gemini models](https://cloud.google.com/vertex-ai/generative-ai/docs/models/gemini-supervised-tuning)
- [Qi et al., Fine-tuning Aligned Language Models Compromises Safety (ICLR 2024)](https://arxiv.org/abs/2310.03693v1)
- [Zhang, Yuan et al., SLDR (NeurIPS 2026), code repository](https://github.com/Stardust457/SLDR)
