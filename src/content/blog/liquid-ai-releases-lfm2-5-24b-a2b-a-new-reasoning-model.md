---
title: "Liquid AI Releases LFM2.5-24B-A2B: A New Reasoning Model"
description: "Liquid AI launches LFM2.5-24B-A2B, a 24B-parameter reasoning model designed for fast, private on-device agents."
pubDate: 2026-10-14
kind: "release"
format: "news"
topics: ["llms", "reasoning", "inference"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/LiquidAI/LFM2.5-24B-A2B"
  publisher: "HF org \u2014 Liquid AI"
release:
  vendor: "liquid"
  family: "LFM"
  version: "2.5-24B-A2B"
  eventType: "new_model"
  openWeights: false
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "LiquidAI/LFM2.5-24B-A2B offers insights into LLM architecture and performance, relevant for understanding mechanistic interpretability and deploying models effectively."
  candidateId: "r70de1f9007989ad"
---

LFM2.5-24B-A2B, a 24B-parameter reasoning model from Liquid AI, is engineered for swift, private agentic tasks on-device, utilizing only 2B active parameters per token. This text-only model supports a context window of 131,072 tokens and is optimized for reasoning, tool use, and agentic workflows, though it is recommended to pair it with retrieval or web search for knowledge-heavy tasks. Developers can deploy LFM2.5-24B-A2B locally using various formats like Transformers, vLLM, SGLang, llama.cpp, and ONNX, or on Apple Silicon with MLX. Liquid AI claims the model is competitive with Qwen3.6-35B-A3B on agentic tasks, achieving a score of 48.09 on LiveClaw, and runs up to 1.7× faster than comparable MoEs on-device, delivering 184 tok/s on an Apple M5 Max and up to 21K output tok/s on a single NVIDIA B300 GPU. The model's versatility is further enhanced by its support for multiple languages and its tool-calling capabilities, making it suitable for a wide range of applications.
