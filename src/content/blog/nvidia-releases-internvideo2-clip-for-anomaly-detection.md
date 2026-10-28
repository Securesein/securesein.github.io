---
title: "NVIDIA Releases InternVideo2-CLIP for Anomaly Detection"
description: "NVIDIA's InternVideo2-CLIP model fine-tuned for video anomaly detection is now available."
pubDate: 2026-10-28
kind: "release"
format: "news"
topics: ["multimodal", "training", "evaluation"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/nvidia/InternVideo2-CLIP-anomaly-detection"
  publisher: "HF org \u2014 NVIDIA (Nemotron)"
release:
  vendor: "nvidia"
  family: "InternVideo2-CLIP"
  eventType: "new_model"
  openWeights: false
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "This item may provide insights into anomaly detection techniques relevant for improving LLM security and reasoning efficiency in production environments."
  candidateId: "re0405348af710bb"
---

NVIDIA has released the InternVideo2-CLIP, a fine-tuned model designed for video anomaly detection and zero-shot action classification. This model, based on the OpenGVLab InternVideo2-CLIP-L14, leverages a MobileCLIP-B text encoder and is optimized for text-to-video retrieval. It operates in a shared 512-dimensional embedding space, with a focus on non-commercial research applications. The model is available on Hugging Face, and users can run it using PyTorch through NVIDIA TAO or deploy it via TensorRT for performance measurement. According to the model card, NVIDIA claims that the InternVideo2-CLIP achieves faster training and inference times when run on NVIDIA GPU-accelerated systems compared to CPU-only solutions. The model is not validated for autonomous safety decision systems, and its similarity scores require application-specific evaluation.
