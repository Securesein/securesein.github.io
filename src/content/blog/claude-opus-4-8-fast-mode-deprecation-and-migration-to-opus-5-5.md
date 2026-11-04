---
title: "Claude Opus 4.8 Fast Mode Deprecation and Migration to Opus 5.5"
description: "Anthropic announces the deprecation of fast mode for Claude Opus 4.8."
pubDate: 2026-11-04
kind: "release"
format: "news"
topics: ["llms", "inference"]
credit: "scout"
model: "gpt-4o"
source:
  url: "https://docs.claude.com/en/release-notes/overview#october-29-2026"
  publisher: "Anthropic \u2014 Claude docs release notes"
release:
  vendor: "anthropic"
  family: "Claude"
  eventType: "deprecation"
  openWeights: false
  modality: ["text"]
scout:
  qualityScore: 25.0
  relevanceScore: 35.2
  whyRelevant: "This update on legacy APIs may impact how users analyze LLM performance and cost, relevant for those deploying and optimizing models in production."
  candidateId: "r9e40aeba6dfa444"
---

Anthropic has deprecated the fast mode for Claude Opus 4.8, with its removal scheduled for November 30, 2026. Users must migrate to Claude Opus 5.5 to continue utilizing fast mode. This change affects requests made to `claude-opus-4-8` with `speed: "fast"`, which will return an error post-removal. The migration deadline is crucial for maintaining uninterrupted service. The updated fast mode can be accessed via the Claude API, Claude Platform on AWS, Claude Models on Google Cloud (Anthropic managed), and Claude in Microsoft Foundry. According to Anthropic, Claude Opus 5.5 offers improved performance and is available without the need for the fast-mode-2026-02-01 beta header, now supporting a default fast mode rate limit across various usage tiers. Users are encouraged to transition to Claude Opus 5.5 to leverage these enhancements.
