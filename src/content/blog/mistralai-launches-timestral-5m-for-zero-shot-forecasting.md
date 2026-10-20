---
title: "MistralAI Launches Timestral-5M for Zero-Shot Forecasting"
description: "MistralAI introduces Timestral-5M, a time series foundation model designed for zero-shot forecasting."
pubDate: 2026-10-20
kind: "release"
format: "news"
topics: ["deep-learning", "inference", "evaluation"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/mistralai/Timestral-5M"
  publisher: "HF org \u2014 Mistral"
release:
  vendor: "mistral"
  family: "Timestral"
  version: "5M"
  eventType: "new_model"
  openWeights: true
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "Timestral-5M offers open-weight models that can enhance understanding of LLM internals and improve reasoning efficiency in production deployments."
  candidateId: "r88d6ca864eb028a"
---

MistralAI has released Timestral-5M, a 5M parameter model within their Timestral family, aimed at zero-shot probabilistic forecasting. This patch-based transformer model features time attention and variate attention, with a context length of up to 32,768 time steps and a forecast horizon of up to 1,024 time steps. It supports univariate or multivariate inputs and outputs 21 quantiles. The model is available under a Modified MIT license and can be run locally using PyTorch on CPU or GPU. According to the model card, Timestral-5M offers a trade-off between model size and forecasting performance, and all Timestral models outperform every other model at their respective sizes. The model has not been deployed by any inference provider yet, but users can request support.
