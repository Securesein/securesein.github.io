---
title: "MistralAI Releases Timestral-209M for Advanced Time Series Forecasting"
description: "MistralAI unveils Timestral-209M, a new model for zero-shot time series forecasting."
pubDate: 2026-10-21
kind: "release"
format: "news"
topics: ["deep-learning", "inference", "evaluation"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/mistralai/Timestral-209M"
  publisher: "HF org \u2014 Mistral"
release:
  vendor: "mistral"
  family: "Timestral"
  version: "209M"
  eventType: "new_model"
  openWeights: true
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "Timestral-209M offers insights into LLM architecture and performance, relevant for understanding mechanistic interpretability and deploying models effectively in production."
  candidateId: "r11c18defa6ebdbd"
---

MistralAI has released Timestral-209M, a 209 million parameter model designed for zero-shot time series forecasting. This model supports univariate and multivariate forecasting, handles past-only and known-future covariates, and provides probabilistic predictions across 21 quantiles. It boasts a context window of up to 32,768 historical time steps and can forecast up to 1,024 steps in a single forward pass. Timestral-209M is available for use via PyTorch on both CPU and GPU, and its source code can be accessed on GitHub. According to the model card, Timestral-209M achieves state-of-the-art zero-shot accuracy across major forecasting benchmarks like GIFT-Eval, TIME, and fev-bench, outperforming other models in metrics such as MASE and CRPS.
