---
title: "Introducing HiRO-ACEv2: High-Resolution Climate Simulation"
description: "Ai2 releases HiRO-ACEv2, a diffusion model for high-resolution climate simulation."
pubDate: 2026-10-15
kind: "release"
format: "news"
topics: ["generative-ai", "inference"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/allenai/HiRO-ACEv2"
  publisher: "HF org \u2014 Ai2"
release:
  vendor: "ai2"
  family: "HiRO-ACE"
  version: "v2"
  eventType: "new_model"
  openWeights: true
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "HiRO-ACEv2 provides insights into LLM behavior and interpretability, relevant for understanding internal mechanisms and enhancing security and efficiency in model deployment."
  candidateId: "rd9a7cbedf8c97d5"
---

Ai2 has released HiRO-ACEv2, a diffusion model designed to generate high-resolution climate data, including 3 km precipitation, 10 m eastward and northward winds, and sea level pressure fields. The model is capable of downscaling fields from 100 km resolution inputs to 3 km resolution outputs, and it generates 6-hourly averaged surface precipitation rates and instantaneous winds and sea level pressure at 6-hour intervals. HiRO-ACEv2 is part of the Ai2 Climate Emulator (ACE) family, which simulates atmospheric variability over time scales from days to centuries. You can run HiRO-ACEv2 locally by downloading the repository and configuring the necessary paths in the inference config files. According to Ai2, HiROv2 quickly generates realistic fields for events with high regional impacts, such as tropical cyclones, and maintains low time-mean biases against the X-SHiELD model. The model is licensed under Apache 2.0, intended for research and educational use.
