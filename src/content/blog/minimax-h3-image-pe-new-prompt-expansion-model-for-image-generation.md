---
title: "MiniMax-H3-Image-PE: New Prompt Expansion Model for Image Generation"
description: "MiniMaxAI releases MiniMax-H3-Image-PE for enhanced text-to-image generation and editing."
pubDate: 2026-11-10
kind: "release"
format: "news"
topics: ["multimodal", "generative-ai", "inference"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/MiniMaxAI/MiniMax-H3-Image-PE"
  publisher: "HF org \u2014 MiniMax"
release:
  vendor: "minimax"
  family: "MiniMax-H3"
  version: "Image-PE"
  eventType: "new_model"
  openWeights: true
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 25.2
  whyRelevant: "This model's multimodal capabilities may provide insights into LLM interpretability and efficiency in reasoning, relevant for understanding internal mechanisms and deployment."
  candidateId: "r09b812e7c387377"
---

MiniMaxAI has shipped the MiniMax-H3-Image-PE, a new model designed for prompt expansion in text-to-image generation. This model turns brief prompts into detailed image descriptions with aspect-ratio recommendations, and it supports both text-to-image and image editing workflows. MiniMax-H3-Image-PE is available via API on platform.minimax.io and platform.minimax.cn, and can also run locally using Modular Diffusers blocks in Transformers. According to the model card, MiniMax-H3-Image-PE uses FP4 weights fine-tuned from Qwen3.8-27B, requiring about 19 GiB of GPU memory for operation. The vendor claims that GPUs with native FP4 support can run the NVFP4 weights directly, while others can utilize bitsandbytes FP4 for compatibility.
