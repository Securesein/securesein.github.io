---
title: "Tencent Releases WeMM-Video-2B for Bilingual Audio-Visual Understanding"
description: "Tencent has launched WeMM-Video-2B, a new model for joint audio-visual understanding and reasoning."
pubDate: 2026-11-27
kind: "release"
format: "news"
topics: ["multimodal", "inference", "training"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/tencent/WeMM-Video-2B-NVFP4"
  publisher: "HF org \u2014 Tencent (Hunyuan)"
release:
  vendor: "tencent"
  family: "WeMM-Video"
  version: "2B-NVFP4"
  eventType: "new_model"
  openWeights: false
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 25.2
  whyRelevant: "This model's multimodal capabilities may provide insights into LLM interpretability and efficiency in reasoning, relevant for understanding internal mechanisms and deployment."
  candidateId: "r5ab03ec8127d5ea"
---

Tencent has launched WeMM-Video-2B, a Chinese–English bilingual model designed for joint audio-visual understanding and reasoning. This model can process text, images, audio, and video inputs to generate text responses in both Chinese and English. The model's architecture includes vision and audio encoders that convert media into tokens for the language model, and it was pretrained on approximately 1.2 trillion multimodal tokens. You can run WeMM-Video-2B using a patched vLLM 0.31.0 with ModelOpt Mixed Precision and Marlin on local runtimes. According to the model card, Tencent claims that WeMM-Video-2B can describe events, transcribe speech, and reason about what is seen and heard, utilizing timestamps on video frames to enhance its understanding. The model is available under the Apache License 2.0, and the serving guide provides detailed instructions for setup and deployment.
