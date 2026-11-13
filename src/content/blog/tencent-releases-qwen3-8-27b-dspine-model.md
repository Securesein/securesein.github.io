---
title: "Tencent Releases Qwen3.8-27B-DSpine Model"
description: "Tencent has launched the Qwen3.8-27B-DSpine model, a new speculative decoding model."
pubDate: 2026-11-13
kind: "release"
format: "news"
topics: ["llms", "inference", "evaluation"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/tencent/Qwen3.8-27B-DSpine-b16"
  publisher: "HF org \u2014 Tencent (Hunyuan)"
release:
  vendor: "tencent"
  family: "Qwen"
  version: "3.8"
  eventType: "new_model"
  openWeights: false
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "This model's architecture and open weights provide insights into LLM internals and facilitate local inference, relevant for mechanistic interpretability and deployment."
  candidateId: "r933fb9737a01f17"
---

Tencent has introduced the Qwen3.8-27B-DSpine model, a speculative decoding model designed to generate draft tokens in parallel, featuring a five-layer draft architecture with a block size of 16 and an 8,192-token sliding window. This model is suitable for high reasoning tasks, supporting up to 32,768 new tokens per request, and utilizes temperature sampling with a temperature of 1.0, top_p of 0.95, and top_k of 20. It is available for local runtimes and can be installed via GitHub. According to the model card, Tencent claims that the DSpine model achieves significant throughput improvements, with up to 3.84× speedup over autoregressive decoding in certain benchmarks. The model operates under the Apache 2.0 license.
