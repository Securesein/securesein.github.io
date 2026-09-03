---
title: "NeoMME: Bridging Multimodal and Multilingual Processing in One Encoder"
description: "Exploring NeoMME's innovative approach to efficient multimodal encoding."
pubDate: 2026-09-03
tags: ["models"]
sourceUrl: "https://huggingface.co/blog/Hcompany/neomme"
sourceName: "Hugging Face Blog"
author: "ai"
---

Hugging Face's NeoMME introduces a new paradigm in multimodal and multilingual encoding by combining text and image processing within a single bidirectional Transformer. This stands in contrast to traditional architectures that rely on separate pretrained vision towers or causal language models.

## Key Innovations

NeoMME eliminates the need for separate vision and language components by processing text tokens and raw image patches through the same Transformer encoder. This integration not only simplifies the architecture but also enhances pretraining, fine-tuning, and serving capabilities across both modalities.

The model is available in two sizes: 260M and 800M parameters. Despite its compactness, NeoMME achieves competitive performance metrics. For instance, the 260M model encodes approximately 51 pages per second on an NVIDIA L40S GPU, doubling the throughput of comparable models like ColModernVBERT.

## Practical Implications

One of the standout features of NeoMME is its application in visual document retrieval. By treating document pages as images, NeoMME -Retriever circumvents the preprocessing OCR steps typically required to extract text from PDFs. This approach preserves crucial visual information such as layout and typography, offering a more holistic retrieval method.

The dual-head design of NeoMME -Retriever supports both dense and late-interaction retrieval. This flexibility allows users to optimize for speed or precision depending on their specific needs and infrastructure constraints.

## Conclusion

NeoMME represents a significant step forward in the integration of multimodal and multilingual processing. By consolidating image and text processing into a single model, it reduces computational overhead and enhances retrieval efficiency, making it a valuable tool for a wide range of applications.
