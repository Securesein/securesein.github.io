---
title: "NVIDIA Releases Metatron v1 for Interactive Humanoid Control"
description: "NVIDIA has launched Metatron v1, a model for interactive humanoid control."
pubDate: 2026-10-28
kind: "release"
format: "news"
topics: ["deep-learning", "reinforcement-learning", "inference"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/nvidia/Metatron-v1"
  publisher: "HF org \u2014 NVIDIA (Nemotron)"
release:
  vendor: "nvidia"
  family: "Metatron"
  version: "v1"
  eventType: "new_model"
  openWeights: false
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "Metatron-v1 provides insights into LLM architecture and performance, relevant for understanding mechanistic interpretability and optimizing inference efficiency in production environments."
  candidateId: "r9f5c79ede045093"
---

NVIDIA has released Metatron v1, a model designed for interactive humanoid control, locomotion, and recovery evaluation. This MaskedMimic-style transformer student model operates with a deterministic prior and decoder, and is available in ONNX format for use with ONNX Runtime Web, supporting both WebGPU and WebAssembly. Metatron v1 is licensed under the NVIDIA Open Model License, with source code under Apache-2.0. It is primarily aimed at researchers and developers working on browser-based humanoid control applications, with support for simulator and real G1 robot deployment workflows. According to the model card, NVIDIA claims that the browser integrations utilize MuJoCo WASM for simulation and ONNX Runtime Web for inference, recommending WebGPU on capable devices for optimal performance. The model is available for download from the Hugging Face repository, with native weights and serialized configurations hosted there.
