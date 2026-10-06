---
title: "OpenAI DevDay 2026: the new features at a glance"
description: "Dots, GPT-6.1 Sol, Ultrafast, the Agents API and plugins — the announcements that matter from DevDay 2026, and what they mean if you administer IT."
pubDate: 2026-10-06
kind: "release"
format: "news"
topics: ["agents", "llms", "inference"]
credit: "directed"
model: "Claude"
contributions:
  chose: true
source:
  url: "https://openai.com/index/devday-2026-recap/"
  publisher: "OpenAI"
  publishedAt: 2026-09-29
release:
  vendor: "openai"
  family: "gpt-sol"
  version: "6.1"
  eventType: "version_bump"
  openWeights: false
  modality: ["text"]
hero: "/images/openai-devday-2026/hero.png"
heroAlt: "A 24-hour clock with three agents orbiting a centre, beside the title OpenAI DevDay 2026"
---

## Agents that keep working when you stop

On 29 September 2026, OpenAI held DevDay at Fort Mason in San Francisco. By its own account the largest edition so far, with more than twenty announcements spread across ChatGPT, Codex, the API and the models themselves.

The thread running through all of it: AI is shifting from a chatbot you ask something to agents that pick up work continuously, including while your laptop is shut. Alongside that, OpenAI is opening ChatGPT further as a platform on which developers can build their own experiences for 1.2 billion weekly users.

This post lists the features that matter, and looks at what you should be watching for if you run an organisation or administer its IT.

## The big three: Dots, GPT-6.1 Sol and Ultrafast

### Dots: an agent that is always on

[Dots](https://openai.com/index/introducing-dots/) is the headline of DevDay. A dot is a personal agent built on GPT-6 Astra, with its own cloud computer and browser. It learns from your feedback and can connect to over 4,000 apps through plugins.

You talk to your dot through ChatGPT (desktop, web, mobile, including by voice), Slack or Teams. When you are idle it performs "proactive research": it reads along, read-only, in your connected apps and comes back with suggestions.

For control there are Custom Rules (allow, ask for approval, or block), an Activity View showing everything the dot does, and automatic review of any action that touches an account. Sensitive operations, changing a password for instance, always stay with you.

Availability: Pro and Business Premium in certain markets. For Enterprise, Edu and Healthcare it is a beta that is off by default until an admin turns it on.

The interesting part for organisations is **specialist dots**: agents with their own identity, their own credentials and even IT-issued hardware, for bounded tasks such as invoice processing or support. Those start as enterprise pilots, and OpenAI is working with Microsoft on managing them through Agent 365.

### GPT-6.1 Sol

[GPT-6.1 Sol](https://openai.com/index/introducing-gpt-6-1-sol/) is the model release of the day: a substantial upgrade on GPT-6 Sol, strong at agentic coding, computer use and professional work. OpenAI promises close to Astra-level capability at a fifth of the Astra token price. Available in the API and to Plus, Pro, Business, Enterprise and Edu.

### Ultrafast

Ultrafast is a paid speed tier: up to 8× faster token generation in Codex (300 tokens per second) and up to 6× in the API. GPT-6 Astra Ultrafast is available in the API now and, in ChatGPT Work and Codex, on Pro 500 and Enterprise. An Ultrafast version of GPT-6.1 Sol follows shortly.

### Private Intelligence

For organisations with sensitive data, OpenAI is introducing Private Intelligence. Zero Data Retention with Private Safety Processing allows automated safety reviews to run without OpenAI staff being able to see the content. Private Inference, built on confidential computing, arrives as a preview this autumn.

## For developers: Codex and the API

Codex is growing into a platform that keeps working without your laptop, and the API is getting the building blocks for agents that operate software.

| Feature | What it does | Available to |
| --- | --- | --- |
| Codex in the cloud | Run Codex on your own machine, from your phone, or in the cloud, with reusable shared development environments carrying fixed settings and permissions | Plus, Pro, Business, Healthcare, Edu, Enterprise |
| Reworked Codex CLI | Start and steer tasks by voice, a new `/agents` overview for several tasks at once, better worktree and session flows | All plans |
| Code Review | Review changes in the ChatGPT desktop app, with feedback posted to GitHub PRs or GitLab MRs; an automatic first review runs in the cloud | All plans |
| Codex Security Cloud | Scan whole GitHub repositories, on demand or on a schedule, with new commits staying checked and fixes prepared in the cloud | Pro, Business, Enterprise, Edu |
| Decisions API | Fast classification with the Luna model: you define the question and its fixed answer options, the API picks based on text or an image | Limited preview, broadly within days |
| Agents API with computer use | Agents that operate software, plus multi-agent, tool search and context compaction taken from Codex; OpenAI hosts the infrastructure | API; Codex and ChatGPT Work on Pro 500 and Enterprise |
| Bedrock Managed Agents | OpenAI agents running entirely inside AWS and integrating with AWS resources | Through [AWS Bedrock](https://aws.amazon.com/bedrock/managed-agents-openai/) |

The Decisions API is subtle but useful: a lot of agent workflows are made of small routing decisions, and you do not need an expensive frontier model for those. The AWS collaboration shows OpenAI wants its agents running outside Azure and its own cloud too.

## ChatGPT as a platform and a workplace

### Plugins become full applications

OpenAI is opening up the platform it builds ChatGPT's own features on. With **plugin extensions** a plugin gets a place in the sidebar, interactive panels next to the conversation, and its own viewers for its file types. A **Plugin Creator** and a new submission flow make publishing easier, and better ranking is meant to make plugins findable.

ChatGPT also now supports the proposed [MCP Events specification](https://modelcontextprotocol.io/community/working-groups/triggers-events). That lets a plugin start an automation when something happens in a connected app — a new task on a project board, say. **Sites** (Business and above) can now host plugins as well, with each colleague using their own data and permissions.

### Working with people and agents

- **ChatGPT Space**: a shared team environment where colleagues, ChatGPT and your dot build on the same body of knowledge (Pro, Business, Enterprise).
- **Pages**: a new document type for collaboration between people and agents, with research, charts and images inside the document.
- **Collaborative slides**: build presentations together and export to PowerPoint or Google Slides; arriving in the coming weeks.
- **Teams and team tasks**: delegate recurring work such as weekly updates, on a schedule or triggered by an email or a Slack message (Business, Enterprise).
- **@ChatGPT in Slack and Teams**: call ChatGPT into a channel or DM, including for colleagues without their own licence (Business, Enterprise).
- **Meetings plugin**: notes and summaries with action points; the audio is deleted once the notes are ready. Beta on macOS for Pro and Business.
- **Shareable profiles**: share the Sites and plugins you have built from a single profile page.

### Plans and ecosystem

- **Sign in with ChatGPT**: spend your ChatGPT credit at 16 partners, among them Devin, Notion and Vercel, with a per-tool limit. Signing in with your ChatGPT account works worldwide.
- **Pro 500**: a new top tier with 25× the Plus usage allowance and access to Ultrafast.
- **OpenAI Marketplace**: enterprise customers can put part of their OpenAI commitment towards software from 32 partners, including Figma, Salesforce, ServiceNow, Palo Alto Networks and CrowdStrike.

## What does this mean for IT administration?

Agents with their own computer, their own identity and access to thousands of apps are not chatbots any more: they are digital staff you have to manage. A few things to watch.

- **Turn it on deliberately.** In Enterprise, Edu and Healthcare workspaces, dots are off by default. Use that moment to write the policy first: which apps may be connected, and which actions need approval through Custom Rules?
- **Agents are identities.** Specialist dots get their own credentials and sometimes IT-issued hardware. Treat them like a service account: least privilege, a lifecycle, logging. For Microsoft environments the Agent 365 integration is where to watch this.
- **Read-only is still access.** Proactive research cannot change anything, but it does read along in connected apps. Look carefully at which data is reachable through plugins.
- **Event-driven automations.** With MCP Events and team tasks, an incoming email or Slack message can set an agent going. That is powerful, and it is also a way in for prompt injection through external content.
- **Licences and shadow IT.** @ChatGPT in Slack and Teams works for colleagues without a licence, and Sign in with ChatGPT connects external tools to personal accounts. Fold this into your policy for OAuth consent and app approval.
- **Compliance.** Zero Data Retention and the coming Private Inference matter for GDPR and sector rules. Business, Enterprise and Edu data is, according to OpenAI, not used for training by default.
- **Endpoints.** The Meetings plugin runs as a beta in the ChatGPT desktop app on macOS. If you manage Macs, you want to know whether and how that app gets deployed and configured, and how recording in meetings sits with your internal agreements.

## In closing

DevDay 2026 is less about one new model and more about the shape of work: agents that pick up tasks continuously, and ChatGPT as a shared workplace where people, agents and plugins meet. For developers, the Agents API with computer use and the Decisions API are the building blocks to experiment with. For IT administrators the real work starts now: agents need the same identity and access management as employees.

Many of these features are still beta or preview, and the performance claims come from OpenAI itself. It is worth watching over the coming weeks which of them hold up in practice.

## Sources

- [DevDay 2026 Recap](https://openai.com/index/devday-2026-recap/) (OpenAI, 29 September 2026)
- [Introducing dots](https://openai.com/index/introducing-dots/) (OpenAI, 29 September 2026)
