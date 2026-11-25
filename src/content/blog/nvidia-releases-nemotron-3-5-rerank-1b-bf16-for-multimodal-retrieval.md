---
title: "NVIDIA Releases Nemotron-3.5-Rerank-1B-BF16 for Multimodal Retrieval"
description: "NVIDIA has launched the Nemotron-3.5-Rerank-1B-BF16 model, designed for multilingual and multimodal question-answering retrieval."
pubDate: 2026-11-25
kind: "release"
format: "news"
topics: ["multimodal", "deep-learning", "inference"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/nvidia/Nemotron-3.5-Rerank-1B-BF16"
  publisher: "HF org \u2014 NVIDIA (Nemotron)"
release:
  vendor: "nvidia"
  family: "Nemotron"
  version: "3.5-Rerank-1B-BF16"
  eventType: "new_model"
  openWeights: false
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "This model provides insights into LLM performance and efficiency, relevant for understanding internal mechanisms and enhancing deployment strategies."
  candidateId: "r5048ea4a2abf586"
---

NVIDIA has released the Nemotron-3.5-Rerank-1B-BF16, a model tailored for multilingual and multimodal question-answering retrieval tasks. This reranker is optimized to produce logits that represent the relevance of documents, which may include text, page images, or both, to a text query. The model supports a maximum context length of 32,768 tokens and can be integrated into vision Retrieval-Augmented Generation (RAG) pipelines. It is available for use under the OpenMDW License Agreement, version 1.1. Developers can access the model via Hugging Face, where it can be run using NVIDIA GPU-accelerated systems, leveraging CUDA libraries for enhanced performance. According to NVIDIA, this model achieves faster training and inference times compared to CPU-only solutions, thanks to its design and optimization for NVIDIA hardware. The model has been evaluated across 34 languages for text retrieval and 18 languages for image retrieval, offering a robust solution for diverse multilingual and multimodal applications.
