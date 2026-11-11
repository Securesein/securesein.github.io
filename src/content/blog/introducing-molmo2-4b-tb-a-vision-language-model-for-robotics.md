---
title: "Introducing Molmo2-4B-tb: A Vision-Language Model for Robotics"
description: "Ai2 releases Molmo2-4B-tb, a high-level model for robot block-stacking."
pubDate: 2026-11-11
kind: "release"
format: "news"
topics: ["multimodal", "training", "evaluation"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/allenai/Molmo2-4B-tb"
  publisher: "HF org \u2014 Ai2"
release:
  vendor: "ai2"
  family: "Molmo"
  version: "2-4B-tb"
  eventType: "new_model"
  openWeights: true
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "This model provides insights into LLM architecture and performance, relevant for understanding mechanistic interpretability and deploying models effectively in production."
  candidateId: "rd5215c4f01c0245"
---

Ai2 has released Molmo2-4B-tb, a vision-language model designed for the ToyBlocks robot block-stacking project. This model, fine-tuned from Molmo2-4B, is capable of reading a stacking goal, analyzing the robot's front camera feed, and determining the next action in the sequence. It boasts about 4.5 billion parameters and processes input at approximately 6 Hz, with the ability to output a short plan and action target. The model is available for download via Hugging Face, with float32 weights in the native Molmo2 format and requires about 20 GB of GPU memory for operation. According to the model card, Ai2 claims Molmo2-4B-tb achieves a closed-loop success rate of up to 97.5% in easy test scenarios within the ToyBlocks simulation, when paired with a motion planner or learned ManiFlow policy. The model is licensed under Apache 2.0, intended for research and educational use, and can be fine-tuned for specific tasks or integrated with custom planning systems.
