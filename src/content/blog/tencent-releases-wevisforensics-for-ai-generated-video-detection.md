---
title: "Tencent Releases WeVisForensics for AI-Generated Video Detection"
description: "Tencent has launched WeVisForensics, a self-evolving agent for detecting AI-generated videos."
pubDate: 2026-11-25
kind: "release"
format: "news"
topics: ["agents", "multimodal", "ai-security"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/tencent/WeVisForensics"
  publisher: "HF org \u2014 Tencent (Hunyuan)"
release:
  vendor: "tencent"
  family: "WeVisForensics"
  eventType: "new_model"
  openWeights: false
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "WeVisForensics provides insights into LLM behavior, aiding understanding of internal mechanisms and security implications, relevant for deploying and interpreting models effectively."
  candidateId: "rd1c6c6e7356d32e"
---

Tencent has launched WeVisForensics, a self-evolving agent designed for the forensic detection of AI-generated videos. The model utilizes a main investigator agent to coordinate sub-agents that inspect visual appearance, physical consistency, common sense, on-screen text, speech content, and voice profile. The release includes five LoRA adapters for WeVisForensics-4B, trained on top of Qwen3.5-4B. Developers can run the model by cloning the code repository and deploying it via multi-GPU, single GPU, or Transformers setup. According to the model card, Tencent claims the release is intended for research purposes in AI-generated video forensics and is not meant for malicious use or autonomous high-impact decisions about individuals. The adapters and Tencent-authored code are available under the Apache License 2.0.
