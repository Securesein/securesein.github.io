---
title: "NVIDIA Releases Nemotron-Labs-Sigma-distill-3B-nfe8 Model"
description: "NVIDIA has launched the Nemotron-Labs-Sigma-distill-3B-nfe8, a 3 billion-parameter continuous diffusion language model."
pubDate: 2026-11-18
kind: "release"
format: "news"
topics: ["llms", "inference", "generative-ai"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/nvidia/Nemotron-Labs-Sigma-distill-3B-nfe8"
  publisher: "HF org \u2014 NVIDIA (Nemotron)"
release:
  vendor: "nvidia"
  family: "Nemotron"
  version: "Sigma-distill-3B-nfe8"
  eventType: "new_model"
  openWeights: true
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 11.2
  whyRelevant: "This release provides insights into training methodologies that can enhance understanding of LLM internals and improve inference efficiency in production environments."
  candidateId: "r8af2407400f1a20"
---

The Nemotron-Labs-Sigma-distill-3B-nfe8 model is designed for fast few-step text generation with a maximum context length of 4,096 tokens. It is a distilled version of a 3B teacher model from the same architecture family, utilizing Phased Distribution Matching Distillation (Phased DMD). The model generates text in 32-token blocks using exactly 8 denoising function evaluations (NFE) plus one final readout. It is available for both commercial and non-commercial use under the NVIDIA Nemotron Open Model License. The model can be run locally on a user's hardware, specifically requiring a CUDA-capable NVIDIA GPU, as CPU inference is not supported due to numerical degradation. NVIDIA claims that the model achieves faster training and inference times when leveraging NVIDIA's GPU-accelerated systems and software frameworks. The model is integrated with PyTorch (>= 2.4) and Hugging Face Transformers (>= 4.55), and it is optimized to run on NVIDIA's Ampere, Blackwell, Hopper, and Lovelace microarchitectures.
