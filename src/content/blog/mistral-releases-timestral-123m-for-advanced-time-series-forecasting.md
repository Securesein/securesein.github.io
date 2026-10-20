---
title: "Mistral Releases Timestral-123M for Advanced Time Series Forecasting"
description: "Mistral introduces Timestral-123M, a powerful model for zero-shot time series forecasting."
pubDate: 2026-10-20
kind: "release"
format: "news"
topics: ["deep-learning", "inference", "evaluation"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/mistralai/Timestral-123M"
  publisher: "HF org \u2014 Mistral"
release:
  vendor: "mistral"
  family: "Timestral"
  version: "123M"
  eventType: "new_model"
  openWeights: true
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "Timestral-123M offers insights into LLM architecture and performance, relevant for understanding mechanistic interpretability and deploying models effectively in production."
  candidateId: "rcd15a73f855c316"
---

Mistral has released the Timestral-123M, a time series foundation model designed for zero-shot forecasting. The model features 123 million parameters and utilizes a patch-based transformer architecture with time and variate attention across 20 layers, supporting a context length of up to 32,768 time steps. It can handle univariate or multivariate inputs and outputs 21 quantiles. The model is available for inference using PyTorch on both CPU and GPU. According to the model card, Timestral-123M outperforms other models of similar size on major forecasting benchmarks such as GIFT-Eval and TIME, achieving a MASE of 0.659 and 0.628 respectively. It is released under a Modified MIT license, and its weights are open for use, allowing developers to integrate it into their local runtimes.
