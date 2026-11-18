---
title: "NVIDIA Releases Nemotron-Labs-Sigma-Distill-8B-NFE16 Model"
description: "NVIDIA has launched the Nemotron-Labs-Sigma-distill-8B-nfe16, an 8 billion-parameter diffusion language model."
pubDate: 2026-11-18
kind: "release"
format: "news"
topics: ["llms", "inference", "generative-ai"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/nvidia/Nemotron-Labs-Sigma-distill-8B-nfe16"
  publisher: "HF org \u2014 NVIDIA (Nemotron)"
release:
  vendor: "nvidia"
  family: "Nemotron"
  version: "Sigma-distill-8B-nfe16"
  eventType: "new_model"
  openWeights: false
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 11.2
  whyRelevant: "This release provides insights into training methodologies that can enhance understanding of LLM internals and improve inference efficiency in production environments."
  candidateId: "r5c0aec89e7fd86e"
---

NVIDIA has introduced the Nemotron-Labs-Sigma-distill-8B-nfe16, an 8 billion-parameter continuous diffusion language model designed for fast few-step text generation. This model, distilled using Phased Distribution Matching Distillation from a multiscale SUSReg-regularized 8B teacher, features a maximum context length of 4,096 tokens and generates text in 32-token blocks. It is available for both commercial and non-commercial use under the NVIDIA Nemotron Open Model License. The model runs offline on the user's hardware, specifically requiring a CUDA-capable NVIDIA GPU, as CPU inference is not supported. NVIDIA claims that by leveraging their GPU-accelerated systems, the model achieves faster training and inference times compared to CPU-only solutions. The model is particularly suited for latency-sensitive generation research and deployment-oriented experimentation, according to the model card.
