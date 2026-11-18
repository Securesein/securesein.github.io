---
title: "NVIDIA Releases Llama-3.2-1B-Qwen3.8-27B-Draft Model"
description: "NVIDIA has launched the Llama-3.2-1B-Qwen3.8-27B-Draft model, designed for latency-optimized speculative decoding in AI systems."
pubDate: 2026-11-18
kind: "release"
format: "news"
topics: ["llms", "inference", "evaluation"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/nvidia/Llama-3.2-1B-Qwen3.8-27B-Draft"
  publisher: "HF org \u2014 NVIDIA (Nemotron)"
release:
  vendor: "nvidia"
  family: "Llama"
  version: "3.2"
  eventType: "new_model"
  openWeights: true
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "This release provides insights into LLM architectures and weights, relevant for understanding mechanistic interpretability and deploying models effectively in production."
  candidateId: "rca0de299d1179e3"
---

NVIDIA has released the Llama-3.2-1B-Qwen3.8-27B-Draft model, a new language model designed for speculative decoding in AI applications such as chatbots and AI agents. This model, featuring 1.48 billion parameters and a context length up to 128K, is intended for both commercial and non-commercial use under various licenses, including the NVIDIA Open Model Agreement and Apache 2.0. It can be deployed globally via Hugging Face, supporting runtimes like vLLM and hardware such as NVIDIA Groq 3 LPU. According to NVIDIA, the model achieves faster training and inference times when run on NVIDIA hardware, leveraging GPU cores and CUDA libraries. The model's performance is evaluated using SPEED-Bench, showing an overall acceptance rate of 3.42 in the qualitative subset and 3.07 in the throughput-32k subset, as per the model card. The draft model is built to match the output distribution of the Qwen3.8-27B target model, enhancing efficiency without altering the output quality.
