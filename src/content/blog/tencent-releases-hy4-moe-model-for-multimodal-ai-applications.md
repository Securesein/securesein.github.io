---
title: "Tencent Releases Hy4 MoE Model for Multimodal AI Applications"
description: "Tencent's Hy Team has launched the Hy4 model, a new-generation Mixture-of-Experts (MoE) model designed for text, image, and video understanding."
pubDate: 2026-11-25
kind: "release"
format: "news"
topics: ["llms", "multimodal", "deep-learning"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/tencent/Hy4-base"
  publisher: "HF org \u2014 Tencent (Hunyuan)"
release:
  vendor: "tencent"
  family: "Hy4"
  version: "base"
  eventType: "new_model"
  openWeights: false
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "Hy4-base provides insights into LLM architecture and performance, relevant for understanding mechanistic interpretability and deploying models effectively in production."
  candidateId: "r89866f0f158ad64"
---

Hy4 features a language backbone with 770B total parameters, activating 49B per token, and supports a context length of 1,048,576 tokens. The model includes a ViT for dynamic image resolutions and a 5-layer DFly2 drafter for speculative decoding. It is available for deployment via Hugging Face and supports various inference frameworks including vLLM and SGLang. According to the model card, Hy4 significantly enhances instruction following, long-context understanding, and deep research capabilities compared to its preview version, while also adding vision capabilities.
