---
title: "GLM 5.3 by Z.ai Now Available on Amazon Bedrock"
description: "Z.ai's GLM 5.3 is now generally available on Amazon Bedrock, offering enhanced capabilities for agentic coding and software engineering."
pubDate: 2026-10-06
kind: "release"
format: "news"
topics: ["llms", "inference", "reasoning"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://aws.amazon.com/about-aws/whats-new/2026/10/amazon-bedrock-glm-5-3/"
  publisher: "AWS \u2014 What's New"
release:
  vendor: "zhipu"
  family: "GLM"
  version: "5.3"
  eventType: "availability"
  openWeights: true
  modality: ["text"]
scout:
  qualityScore: 80.0
  relevanceScore: 71.0
  whyRelevant: "GLM 5.3's release on Amazon Bedrock offers insights into LLM deployment and inference efficiency, relevant for understanding model internals and security."
  candidateId: "r2031db561396c5c"
---

Z.ai's GLM 5.3 is now generally available on Amazon Bedrock, featuring a mixture-of-experts architecture with 753B total parameters and approximately 40B active per token. This version retains the base model of GLM 5.2 but incorporates improvements from scaled post-training, offering a 1-million-token context window and up to 128K output tokens. Reasoning is always enabled with selectable effort levels, allowing users to balance latency and token consumption against task performance. You can run GLM 5.3 through the Amazon Bedrock console or programmatically via supported APIs, available to eligible enterprise customers across US and Global cross-Region inference profiles. According to the model card, GLM 5.3 includes explicit prompt caching with cache points on system prompts and messages, designed to reduce latency and input costs when reusing context across model calls.
