---
title: "Mistral Releases Mistral Large 4 NVFP4 Model"
description: "Mistral has released the Mistral Large 4 NVFP4, a 1 trillion-parameter natively multimodal Mixture-of-Experts model."
pubDate: 2026-11-03
kind: "release"
format: "news"
topics: ["llms", "multimodal", "inference"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/mistralai/Mistral-Large-4-1T-A52B-NVFP4"
  publisher: "HF org \u2014 Mistral"
release:
  vendor: "mistral"
  family: "Mistral-Large"
  version: "4-1T-A52B-NVFP4"
  eventType: "new_model"
  openWeights: true
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "This release provides insights into the architecture and performance of a new open-weight LLM, relevant for understanding mechanistic interpretability and deployment."
  candidateId: "r3e5be64594ac0b2"
---

Mistral has released the Mistral Large 4 NVFP4, a 1 trillion-parameter natively multimodal Mixture-of-Experts model with 49 billion active parameters per token, designed for multimodal input and text output. This model supports a 1M context window and offers configurable reasoning effort per request, with native function calling and strict JSON schema output. It is available under the Mistral Ecosystem Open-Weight License, with commercial use requiring a separate license. You can run the model using the Mistral AI API, or deploy it locally with vLLM, SGLang, or llama.cpp. According to the model card, the NVFP4 checkpoint matches the FP8 behavior across multiple domains, offering similar performance with reduced memory requirements. Mistral claims that the model is optimized for Blackwell GPUs, providing substantial memory reduction and faster inference compared to its FP8 counterpart.
