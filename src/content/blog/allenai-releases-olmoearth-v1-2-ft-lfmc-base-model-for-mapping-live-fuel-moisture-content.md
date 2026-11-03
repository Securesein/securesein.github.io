---
title: "AllenAI Releases OlmoEarth-v1_2-FT-LFMC-Base Model for Mapping Live Fuel Moisture Content"
description: "AllenAI has launched the OlmoEarth-v1_2-FT-LFMC-Base model, fine-tuned for mapping live fuel moisture content (LFMC) in woody vegetation."
pubDate: 2026-11-03
kind: "release"
format: "news"
topics: ["multimodal", "training", "inference"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/allenai/OlmoEarth-v1_2-FT-LFMC-Base"
  publisher: "HF org \u2014 Ai2"
release:
  vendor: "ai2"
  family: "OlmoEarth"
  version: "v1_2-FT-LFMC-Base"
  eventType: "new_model"
  openWeights: true
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 52.7
  whyRelevant: "This model's open-weight architecture allows for local inference and exploration of LLM mechanisms, relevant for understanding interpretability and security in deployment."
  candidateId: "r691aea7ca2e2710"
---

AllenAI has launched the OlmoEarth-v1_2-FT-LFMC-Base model, fine-tuned for mapping live fuel moisture content (LFMC) in woody vegetation. This multimodal model processes twelve timesteps of satellite imagery, including Sentinel-2 and Sentinel-1 mosaics, to predict LFMC as a percentage at each 10 m pixel. It is licensed under the OlmoEarth Artifact License and adheres to Ai2's Responsible Use Guidelines. The model can be run locally using `rslearn`, with instructions provided for setup and execution. According to the model card, the model achieves an RMSE of 24.0 and an MAE of 16.1 on a held-out test set, with a bias of -2.0. These performance metrics highlight its potential utility in environmental monitoring and management.
