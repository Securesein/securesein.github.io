---
title: "NVIDIA Releases Nemotron-Labs-Sigma-distill-3B-nfe2 Model"
description: "NVIDIA has launched the Nemotron-Labs-Sigma-distill-3B-nfe2, a 3 billion-parameter continuous diffusion language model."
pubDate: 2026-11-18
kind: "release"
format: "news"
topics: ["llms", "inference", "generative-ai"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/nvidia/Nemotron-Labs-Sigma-distill-3B-nfe2"
  publisher: "HF org \u2014 NVIDIA (Nemotron)"
release:
  vendor: "nvidia"
  family: "Nemotron"
  version: "Sigma-distill-3B-nfe2"
  eventType: "new_model"
  openWeights: true
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 11.2
  whyRelevant: "This release provides insights into training methodologies that can enhance understanding of LLM internals and improve inference efficiency in production environments."
  candidateId: "r913eca282ea65ba"
---

NVIDIA has released the Nemotron-Labs-Sigma-distill-3B-nfe2, a 3 billion-parameter language model designed for fast few-step text generation using Phased Distribution Matching Distillation. This model, part of the Nemotron-Labs-Sigma architecture family, features a maximum context length of 4,096 tokens and is optimized for latency-sensitive generation tasks. It is available for both commercial and non-commercial use under the NVIDIA Nemotron Open Model License. The model runs offline on user hardware, specifically requiring a CUDA-capable NVIDIA GPU, as CPU inference is not supported. According to the model card, NVIDIA claims that the model achieves faster training and inference times by leveraging NVIDIA's GPU-accelerated systems and software frameworks, such as CUDA libraries.
