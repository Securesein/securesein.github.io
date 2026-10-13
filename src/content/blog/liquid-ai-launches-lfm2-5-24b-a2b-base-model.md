---
title: "Liquid AI Launches LFM2.5-24B-A2B-Base Model"
description: "Liquid AI introduces the LFM2.5-24B-A2B-Base, a 24B-parameter hybrid model optimized for on-device deployment."
pubDate: 2026-10-13
kind: "release"
format: "news"
topics: ["llms", "agents", "inference"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/LiquidAI/LFM2.5-24B-A2B-Base"
  publisher: "HF org \u2014 Liquid AI"
release:
  vendor: "liquid"
  family: "LFM2.5"
  version: "24B-A2B-Base"
  eventType: "new_model"
  openWeights: true
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "LiquidAI's LFM2.5-24B-A2B-Base model offers insights into LLM architecture and efficiency, relevant for understanding mechanistic interpretability and deploying models effectively."
  candidateId: "r1ab117ad6244911"
---

The LFM2.5-24B-A2B-Base from Liquid AI is a new hybrid model designed for on-device deployment, featuring 24 billion parameters with only 2 billion active parameters. This model supports a context window of 131,072 tokens and a vocabulary size of 128,000 tokens, making it suitable for tasks requiring extensive fine-tuning, such as language-specific assistants or domain-specific applications. It is available for deployment via API, cloud, or local runtimes, including formats like ONNX for cross-platform deployment and MLX for Apple Silicon. Liquid AI claims that the model's pre-training and mid-training phases, which include tool calls and multi-turn trajectories, prepare it for agentic workloads, as stated in their documentation.
