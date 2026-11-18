---
title: "NVIDIA Releases Nemotron-Labs-Sigma-distill-8B-nfe2 Model"
description: "NVIDIA has launched the Nemotron-Labs-Sigma-distill-8B-nfe2, an 8 billion-parameter continuous diffusion language model."
pubDate: 2026-11-18
kind: "release"
format: "news"
topics: ["llms", "deep-learning", "inference"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/nvidia/Nemotron-Labs-Sigma-distill-8B-nfe2"
  publisher: "HF org \u2014 NVIDIA (Nemotron)"
release:
  vendor: "nvidia"
  family: "Nemotron"
  version: "distill-8B-nfe2"
  eventType: "new_model"
  openWeights: true
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 11.2
  whyRelevant: "This release provides insights into training methods that could enhance understanding of LLM internals and improve inference efficiency in production environments."
  candidateId: "r13072a2022b097c"
---

NVIDIA has launched the Nemotron-Labs-Sigma-distill-8B-nfe2, an 8 billion-parameter continuous diffusion language model designed for fast few-step generation. This model, distilled using Phased Distribution Matching Distillation (Phased DMD), is part of the Nemotron-Labs-Sigma architecture family and is tailored for latency-sensitive generation research, speculative and parallel decoding studies, and deployment-oriented experimentation. It features a maximum context length of 4,096 tokens and generates text in 32-token blocks using exactly 2 denoising function evaluations (NFE) plus one final readout. The model is available for commercial or non-commercial use under the NVIDIA Nemotron Open Model License, and it can be run offline on a user's own hardware as NVIDIA hosts no service. According to the model card, the model achieves faster training and inference times when optimized to run on NVIDIA GPU-accelerated systems. It requires PyTorch (>= 2.4) with Hugging Face Transformers (>= 4.55) and a CUDA-capable NVIDIA GPU for execution, with CPU inference not supported due to numerical degradation.
