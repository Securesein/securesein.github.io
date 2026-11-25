---
title: "Tencent Releases WeMM-Video-2B for Multimodal Understanding"
description: "Tencent has launched WeMM-Video-2B, a dense 2B checkpoint model for joint audio-visual understanding and reasoning."
pubDate: 2026-11-25
kind: "release"
format: "news"
topics: ["multimodal", "deep-learning", "inference"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/tencent/WeMM-Video-2B"
  publisher: "HF org \u2014 Tencent (Hunyuan)"
release:
  vendor: "tencent"
  family: "WeMM-Video"
  version: "2B"
  eventType: "new_model"
  openWeights: false
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 25.2
  whyRelevant: "This model's multimodal capabilities may provide insights into LLM interpretability and efficiency in reasoning, relevant for understanding internal mechanisms and deployment."
  candidateId: "r78964bd9426c799"
---

WeMM-Video-2B, part of Tencent's WeMM-Video family, is a Chinese–English bilingual model designed for joint audio-visual understanding and reasoning. It processes text, images, audio, and video inputs to generate text responses, supporting both Chinese and English languages. The model's architecture includes vision and audio encoders that convert media into tokens, which are then processed alongside text by the language model. Pretrained on approximately 1.2 trillion multimodal tokens, the model underwent post-training with multi-teacher OPD and reinforcement learning techniques. You can run WeMM-Video-2B via the Hugging Face Transformers library, with weights available in BF16 Safetensors format. According to the model card, WeMM-Video-2B is capable of describing events, transcribing speech, and reasoning about visual and auditory content, even from silent videos or standalone audio. The model is released under the Apache License 2.0, allowing for broad usage and adaptation.
