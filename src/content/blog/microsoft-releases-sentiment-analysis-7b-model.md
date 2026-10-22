---
title: "Microsoft Releases Sentiment-Analysis-7B Model"
description: "Microsoft has launched Sentiment-Analysis-7B, a 7B-parameter language model for sentiment classification."
pubDate: 2026-10-22
kind: "release"
format: "news"
topics: ["llms", "reinforcement-learning", "evaluation"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://huggingface.co/microsoft/Sentiment-Analysis-7B"
  publisher: "HF org \u2014 Microsoft (Phi)"
release:
  vendor: "microsoft"
  family: "Sentiment-Analysis"
  version: "7B"
  eventType: "new_model"
  openWeights: true
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 21.2
  whyRelevant: "This model provides insights into sentiment analysis, which can enhance understanding of LLM behavior and improve reasoning efficiency in practical applications."
  candidateId: "re7b11e5af76afd9"
---

Microsoft has released Sentiment-Analysis-7B, a 7B-parameter autoregressive language model fine-tuned for sentiment classification of user messages directed at a service, product, or agent. This model is based on mistralai/Mistral-7B-Instruct-v0.2 and employs reinforcement learning with an LLM as a judge on a small internal training set of approximately 300 examples. Sentiment-Analysis-7B generates responses with a sentiment label (Negative, Neutral, or Positive) followed by a short explanation. The model is accessible via the Hugging Face platform and can be run using the AutoModelForCausalLM. According to the model card, Sentiment-Analysis-7B achieves an accuracy of 72.8%, surpassing the 62.0% accuracy of its base model. This model is designed to be used with a system prompt that defines the 'Target' and sentiment rules, allowing for precise sentiment analysis in user interactions.
