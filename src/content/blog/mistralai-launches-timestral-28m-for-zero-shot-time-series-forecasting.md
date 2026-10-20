---
title: "MistralAI Launches Timestral-28M for Zero-Shot Time Series Forecasting"
description: "MistralAI has released the Timestral-28M model, a new addition to their time series foundation models."
pubDate: 2026-10-20
kind: "release"
format: "news"
topics: ["deep-learning", "inference", "evaluation"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/mistralai/Timestral-28M"
  publisher: "HF org \u2014 Mistral"
release:
  vendor: "mistral"
  family: "Timestral"
  version: "28M"
  eventType: "new_model"
  openWeights: true
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "Timestral-28M offers insights into LLM architecture and performance, relevant for understanding mechanistic interpretability and deploying models effectively in production."
  candidateId: "r0afd844c30d61b8"
---

MistralAI has released the Timestral-28M, a time series foundation model designed for zero-shot forecasting, featuring 28 million parameters. This patch-based transformer model incorporates time and variate attention across 12 layers with an embedding dimension of 384 and supports a context length of up to 32,768 time steps. The model is capable of forecasting up to 1,024 time steps in a single forward pass and outputs 21 quantiles. It can be run locally using PyTorch on both CPU and GPU. According to the model card, Timestral-28M offers a balance between model size and forecasting performance, achieving notable scores on benchmarks such as GIFT-Eval and TIME. The model is available under a Modified MIT license, with the restriction that it must not be used in a manner that violates third-party rights.
