---
title: "NVIDIA and Baker Lab Release RFD4-Prote\u00edna for Biomolecular Design"
description: "NVIDIA and Baker Lab have released RFD4-Prote\u00edna, a flow-matching model for joint sequence\u2013structure generation in biomolecular design."
pubDate: 2026-10-27
kind: "release"
format: "news"
topics: ["generative-ai", "deep-learning", "training"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/nvidia/RFD4-Proteina-Diffusers"
  publisher: "HF org \u2014 NVIDIA (Nemotron)"
release:
  vendor: "nvidia"
  family: "RFD4"
  version: "1.0"
  eventType: "new_model"
  openWeights: true
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "This item provides insights into model deployment and security, relevant for understanding LLMs' internal workings and enhancing inference efficiency."
  candidateId: "r51ba21fefe6290e"
---

NVIDIA and Baker Lab have released RFD4-Proteína, a flow-matching model designed for biomolecular design tasks. This model can generate protein sequences and all-atom structures simultaneously, conditioned on specific molecular contexts such as binding targets or enzyme motifs. It features a 147-class residue vocabulary and a 32-dimensional latent space, resulting from a LoRA fine-tune of the pretrained base model. The model is available via the Hugging Face Diffusers library, with weights stored in FP32 and recommended to run in BF16 on a CUDA GPU. According to the model card, RFD4-Proteína supports various tasks, including protein binder design and motif scaffolding, with the ability to handle up to 1024-token designs on a 16 GB GPU. The model and weights are licensed under the BSD 3-Clause, and users can install the necessary dependencies from GitHub until the next Diffusers release.
