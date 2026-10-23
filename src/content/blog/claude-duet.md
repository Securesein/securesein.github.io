---
title: "Claude Duet: what it is, and what it can't do yet"
description: "Anthropic's new proactive agent watches your apps, works while you're away and asks before it acts. A practitioner's look at what it does, where it falls short, and what it means for IT governance."
pubDate: 2026-10-23
kind: "enterprise"
format: "deepdive"
topics: ["agents", "ai-security", "llms"]
credit: "directed"
model: "Claude"
contributions:
  chose: true
hero: "/images/claude-duet/hero.png"
heroAlt: "A phone showing a morning brief, standing on a reflective horizon in front of a rising-sun halo"
---
On October 21, 2026, Anthropic opened a research preview of Claude Duet: a separate app in which Claude doesn't wait for your question but comes to you. Duet watches your connected apps, sends a short brief every morning, keeps working while you're away, and asks for approval before it sends, pays for or signs anything on your behalf.

That sounds like yet another AI assistant, but the shift is real. Until now, Claude was something you open. Duet is something that reaches out to you. For anyone looking at AI from an IT, security or governance angle, this is exactly the moment to pay attention: what can it actually do, where are the limits, and who stays in control?

## What is Claude Duet?

Claude Duet is a proactive agent you direct through messages, by text or voice, in one continuous thread. Anthropic explicitly targets professionals and small business owners who have more on their plate than they can keep track of. Under the hood it runs on Claude Opus 5.5.

Anthropic sums up the difference with the regular Claude app like this: in the Claude app you open a chat, Duet comes to you. The building blocks are the same, though. Duet carries over your memory, skills and connected apps from your existing Claude account, so there is little to set up.

### How it works technically

- **Its own cloud computer.** Duet runs in a virtual machine with its own browser. Your laptop or phone doesn't need to be on while it works.
- **Periodic checks, not a live stream.** Duet looks at your connected accounts every few hours, not continuously. Anthropic says this is deliberate: watching nonstop would burn through your usage limits too fast. The trade-off is that something arriving between two checks can be missed.
- **Morning brief and notifications.** A short summary of what matters every morning, then a message only when something needs your attention. You can tell it what you want to hear about and how often.
- **Approval when it matters.** Reading, drafting and preparing happen on their own. Sending, paying, signing or deleting only happen after you see exactly what it is about to do and approve it.

### Availability

| Item | Status as of October 23, 2026 |
| --- | --- |
| Stage | Research preview, access via waitlist |
| Plans | Claude Pro and Max; Team and Enterprise not yet |
| Region | United States only |
| Platforms | Standalone app for iOS and Android, plus claude.ai on desktop |
| Cost | No extra charge; Duet shares the usage limits of your Claude plan |

For readers in Europe this means, in practice, that you can't start using it yet, not even with a Pro or Max subscription.

## What it can do

Duet does three things: it keeps track of what needs your attention, it carries out tasks you hand it by message, and it prepares actions for you to approve. For this it can use the more than 6,000 connectors and plugins in the Claude Marketplace.

### Keeping watch and flagging

The morning brief pulls together the most important items from your connected apps. During the day, Duet looks for missed emails and Slack messages, clashing meetings and approaching deadlines. Anthropic shares examples from early testers: a real estate broker was told, unprompted, that a property showing was on her calendar for the wrong day, and a brand strategist got a prep brief for a client call plus an offer to move it because it fell right before her flight.

### Running tasks in the background

You describe a task in a short message; Duet works out which apps and steps it needs and checks back when it's done or needs a decision. The scope is broad: from scheduling meetings to building dashboards, financial or sales forecasts, prototypes and web apps. It delivers work as a document, spreadsheet or deck. You follow running tasks in a separate Tasks tab.

### Running a small business

This is where the product's focus is clearest. Examples Anthropic gives:

| Area | Example | Integration |
| --- | --- | --- |
| Invoicing | Find unpaid invoices and draft reminders | QuickBooks, Stripe |
| Payroll | Prepare payroll with hours, bonuses and reimbursements | Gusto |
| Contracts | Prepare agreements and send them for signature | Docusign |
| Sales | Follow-up emails based on contact and deal history | HubSpot |
| Hiring | Draft a job post and publish it after approval | LinkedIn |
| Marketing | Turn a product launch into a social campaign | Canva |
| Webshop | Set up, design and manage a Shopify store | Shopify |
| Purchasing | Buy items with a virtual card, after your approval | Stripe Link, Shop Pay |

The purchasing flow is interesting from a security point of view. Duet first confirms the item, then Link asks you to approve the spend, and payment goes through a virtual card so your real card number is never shared. Signing in with accounts saved in 1Password is on the roadmap, again only with your permission.

## What it can't do yet, and what to watch for

Anthropic is unusually upfront about the limitations. That makes a fair assessment easier.

### Acknowledged limitations

- **Judgment isn't reliable yet.** Duet can misread a thread or misjudge urgency. That judgment is the main selling point, so this weighs heavily.
- **Gaps between checks.** Because Duet only looks every few hours, something that arrives in between can sit until the next round.
- **No view into the browser.** You can't watch what Duet does in its cloud browser or take it over. You do get an overview of what it has done and is working on.
- **Personal errands are weaker.** Booking tickets and similar private tasks work less well; the product is built around work.
- **Connectors with limits.** Some integrations, Slack is named explicitly, don't work fully inside Duet.
- **A separate app.** For now, Duet lives apart from the regular Claude app. How the two come together depends on what Anthropic learns from the preview.

### Usage limits

Duet draws on the same limits as the rest of your Claude plan, including the five-hour window and the weekly limit. Background checks count, and large tasks like a financial model or a deck take many model turns. If you already use Claude Code heavily, you'll notice quickly. Engadget called it a recipe for blowing through your rate limits, and not without reason.

### Safeguards

Security is layered and builds on existing Anthropic components:

- **Credentials kept away from the model.** Duet never directly sees your passwords or sign-in tokens, following the Claude Managed Agents design. When a site asks for a password, you type it into a separate form on your own device.
- **Action classifier.** Actions pass through the auto mode classifier that also stops Claude Code from taking steps you didn't ask for.
- **Prompt injection.** Defences against hidden instructions in emails and web pages come from Anthropic's browser-use research.
- **Leak prevention.** A new classifier checks every message. Credit card numbers and government IDs are refused; health and financial details only go out when you explicitly ask.
- **Hard limits.** Trading securities, moving money between accounts or using someone else's account is off-limits, even with your approval.
- **Testing.** Red teams and an outside firm ran penetration tests, and Duet is covered by the public bug bounty programme.

Anthropic says it will publish more detail on the safety design in the coming days. Until then, these are vendor claims, not independently verified.

### The governance question

For IT admins, the biggest caveat isn't the product itself but who it's available to. Duet only runs on personal Pro and Max accounts; Team and Enterprise aren't supported yet. That means no admin console, no central policy and no audit log for the organisation.

At the same time, the target audience is exactly the professional who connects their work email, Slack and CRM. That's the classic recipe for shadow AI: an agent with read access to company data, set up on a personal subscription, out of IT's sight. If you're responsible for managed endpoints or identity, it makes sense to decide now which OAuth grants to consumer AI services you allow, rather than waiting until Duet reaches Europe.

Engadget put the underlying trade-off neatly: how much you get out of Duet depends on how much of your digital life you're willing to hand to an AI agent.

## How Duet compares

Anthropic is the last of three big players to ship a proactive agent. Meta released Muse on September 8, 2026, and OpenAI followed three weeks later with Dots in ChatGPT. All three run on their own cloud computer, keep working while you're away, and ask permission before sensitive actions. The differences are in price, audience and who can get access.

|  | Claude Duet | OpenAI Dots | Meta Muse |
| --- | --- | --- | --- |
| Launch | Oct 21, 2026, research preview | late Sep 2026 | Sep 8, 2026 |
| Model | Claude Opus 5.5 | GPT-6 Astra | not stated in source |
| Personal entry price | Pro, about $20 per month | Pro 100, $100 per month | free tier with cap; $20 and $100 |
| Business plans | Not yet (no Team or Enterprise) | Business Premium; Enterprise in beta | not stated in source |
| Region | US only | Pro outside the EEA, Switzerland and UK | US and Canada |
| Focus | Work, small businesses | Research and recurring tasks, tied into ChatGPT Work and Codex | Personal: shopping, forms, travel |
| Usage limits | Shares limits with the rest of Claude | Only counts inside ChatGPT Work or Codex | Usage cap on free tier |

Two differences stand out. Duet is cheaper to get into than Dots, but OpenAI already has a business route with Business Premium seats. For organisations, that is a real difference right now. And Anthropic clearly chooses work and business operations, where Muse is more of a personal assistant.

### Within the Claude family

Duet fills its own slot next to the existing products. Claude Code is the agent for developers, Claude Cowork the desktop agent for knowledge work that you steer yourself. Duet is the mobile, proactive variant that takes the initiative. Because memory, skills and connectors are shared, it isn't a separate ecosystem but a different way of working on top of the same account.

## Verdict: promising, but not for the organisation yet

Claude Duet is a well-thought-out product with a clear choice: not a general assistant for everything, but an agent that keeps watch for people juggling too many things at once. The security design is more serious than you'd expect from a first preview, with approval for every action that has consequences, credentials kept out of the model, single-use cards and hard limits you can't lift yourself.

Three things weigh against it. Its main selling point, good judgment about what's urgent, is by Anthropic's own account not reliable yet. The shared usage limit makes Duet costly in tokens for heavy Claude users. And there is no management layer for organisations at all.

**Who should care right now?**

- **Freelancers and small business owners in the US** with a Pro or Max plan and a stack of QuickBooks, Gusto, HubSpot and Google Workspace. This is who Duet is designed for.
- **IT and security teams in Europe**, not as users but as an early warning. Proactive agents with read access to mail and chat are coming, from three vendors at once. It's wise to set policy now for OAuth consent and consumer AI, before employees start connecting things themselves.
- **Anyone following agent governance.** Duet's safety model, with a per-message classifier and categories of information that may never leave, is a useful reference for how you'd want to set this up inside your own organisation.

The real test comes when Duet becomes available for Team and Enterprise. That's when we'll see whether Anthropic is willing to give admins the same control it gives individual users.

## Sources

- [Introducing Claude Duet](https://claude.com/resources/articles/claude-duet), Anthropic, October 21, 2026
- [Claude Duet product page and FAQ](https://claude.com/product/claude-duet), Anthropic
- [Get started with Claude Duet](https://support.claude.com/en/articles/17631495), Claude Help Center
- [Claude Duet is Anthropic's answer to Meta Muse and OpenAI Dots](https://www.engadget.com/2293646/claude-duet-is-anthropics-answer-to-meta-muse-and-openai-dots/), Engadget, October 21, 2026
- [OpenAI Dot vs. Meta Muse: How do these AI agents compare?](https://www.engadget.com/2281289/openai-dot-vs-meta-muse-ai-agents-comparison/), Engadget, October 11, 2026
- [Claude Duet app is Anthropic's bet on agents](https://techcrunch.com/2026/10/22/claude-duet-app-is-anthropics-bet-on-agents/), TechCrunch, October 22, 2026
- [Anthropic takes on ChatGPT Dots and Meta Muse with Claude Duet](https://9to5mac.com/2026/10/21/anthropic-takes-on-chatgpt-dots-and-meta-muse-with-claude-duet/), 9to5Mac, October 21, 2026
