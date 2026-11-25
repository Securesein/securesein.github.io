---
title: "AllenAI Releases ACE2.5-ERA5 Climate Emulator"
description: "AllenAI has launched the ACE2.5-ERA5 model, an advanced climate emulator."
pubDate: 2026-11-25
kind: "release"
format: "news"
topics: ["deep-learning", "inference", "evaluation"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/allenai/ACE2.5-ERA5"
  publisher: "HF org \u2014 Ai2"
release:
  vendor: "ai2"
  family: "ACE"
  version: "2.5"
  eventType: "new_model"
  openWeights: true
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "ACE2.5-ERA5 provides insights into LLM behavior and performance, relevant for understanding mechanistic interpretability and enhancing inference efficiency in production settings."
  candidateId: "rb509869c14e5791"
---

AllenAI has introduced the ACE2.5-ERA5, a new model in the ACE family designed to simulate atmospheric variability over timescales ranging from days to centuries. This stochastic model is trained on the ERA5 dataset and offers calibrated ensemble predictions with realistic small-scale structures, achieving this at a significantly lower computational cost compared to its predecessor, ACE2-ERA5. The model is available in three configurations, each trained on ERA5, and can be run locally by downloading a checkpoint from the repository and setting up the necessary dependencies and configuration files. According to the model card, ACE2.5-ERA5 features a noise-conditioned layer normalization that produces calibrated ensembles, retaining 86% of ERA5's spectral power at certain wavenumbers, and is 10 times smaller than ACE2-ERA5 due to spectral bottlenecking. It also boasts a 3.2 times faster inference speed, offering an efficient tool for climate emulation.
