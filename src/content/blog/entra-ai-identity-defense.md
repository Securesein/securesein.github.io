---
title: "AI in Microsoft Entra identity defense: what it does and where it stops"
description: "The features behind Microsoft's 'AI-powered identity protection' pitch, taken apart: ID Protection risk detections, the new MFA approval detection, risk-based Conditional Access and the Security Copilot agents in Entra. What each part does, what it needs, and where it falls short."
pubDate: 2026-10-29
kind: "enterprise"
format: "deepdive"
topics: ["ai-security", "agents"]
credit: "directed"
model: "Claude"
contributions:
  chose: true
source:
  url: "https://techcommunity.microsoft.com/blog/microsoft-entra-blog/identity-under-attack-how-ai-strengthens-defense/4566649"
  publisher: "Microsoft Entra Blog"
  publishedAt: 2026-10-27
---

On 27 October Microsoft published "Identity under attack: How AI strengthens defense" on the Entra blog. The argument is that identity attacks such as MFA fatigue now move faster than a SOC can triage them, and that the AI in Entra closes that gap with earlier detection and automated response. The post names outcomes ("fewer successful MFA fatigue exploits", faster escalation, fewer false positives) but no figures, and it doesn't say which features produce them, what they require or where they stop working.

This post fills that in. I skip the threat-landscape part and look only at the technology.

## Three different things called "AI"

When Microsoft talks about AI in Entra identity defense, it bundles three layers that behave very differently:

1. Machine learning risk detections in Entra ID Protection. These score sign-ins and users.
2. Risk-based Conditional Access. This turns those scores into enforcement. There is no AI in this layer; it is ordinary policy that you write.
3. Security Copilot in Entra and the Entra agents. These use a language model to investigate, summarize and suggest (or perform) remediation.

Each layer has its own licensing, its own latency and its own way of failing. Keeping them apart is most of the work in judging what you actually get.

## Layer 1: risk detections in ID Protection

ID Protection calculates two kinds of risk. Sign-in risk is the probability that a specific authentication request did not come from the account owner. User risk is the probability that the account itself is compromised. Detections such as atypical travel, unfamiliar sign-in properties, anomalous token, password spray and leaked credentials feed into one or both.

Two properties of each detection decide how useful it is to you.

The first is timing. A real-time detection is evaluated during the sign-in, so Conditional Access can act on it in that same sign-in. An offline detection is calculated afterwards from logs and can take hours to appear (Microsoft documents up to 48 hours for some). An offline detection raises user risk after the attacker may already hold a token.

The second is licensing. Microsoft splits detections into premium and non-premium. Full details on most detections require Entra ID P2. Tenants without P2 see premium detections only as "Additional risk detected", with no detail on what was detected. Leaked credentials detection in a hybrid tenant also depends on password hash synchronization.

### The new MFA approval detection

The part of Microsoft's post about MFA fatigue rests mostly on one detection that appeared in the documentation in April 2026. It was first listed as "Authenticator-assisted phishing detection" and renamed a day later to Suspicious MFA authentication approval. In logs and Graph it shows up with riskEventType `authenticatorPhishing`.

It is a real-time, premium sign-in risk detection. It fires during sessions that use password plus MFA, and it uses telemetry from the Microsoft Authenticator app. That scope has consequences:

- It only covers Microsoft Authenticator. Push approvals through a third-party MFA provider, SMS or voice calls produce none of this telemetry.
- It only looks at password-plus-MFA sign-ins. Passwordless and phishing-resistant sign-ins are outside its scope, which is fine, because those are not vulnerable to push fatigue in the same way.
- Because it is real-time, a sign-in risk policy in Conditional Access can block or step up the sign-in before a token is issued.

Number matching has been mandatory for Authenticator push in Entra since February 2023, and that already stopped most blind approvals. What is left is the user who approves anyway, for example because the attacker called them, pretended to be the helpdesk and read out the number. That is the case this detection targets: it judges the context of the approval, not just whether MFA succeeded.

### User-reported suspicious activity

The older signal still works and doesn't need P2. With Report suspicious activity enabled in the Authentication methods settings, a user who gets an unexpected prompt can report it from Authenticator. Entra then sets that user to high user risk. The event appears in the sign-in logs (as MFA denied), in the audit logs and in the risk detections report as User Reported Suspicious Activity. One exception: a user is not marked high risk if they report a prompt during passwordless authentication.

This is the cheapest MFA fatigue control in the product. If it isn't on in your tenant, turn it on before anything else in this post.

## Layer 2: enforcement through Conditional Access

The risk score does nothing by itself. Conditional Access policies with a sign-in risk or user risk condition decide what happens: require MFA or a specific authentication strength at medium sign-in risk, require a secure password change at high user risk, or block.

This is the part you control. The model decides the score; your policy decides the consequence, and that policy is deterministic and visible in the sign-in logs. If an AI-driven decision ever needs explaining to an auditor, this is where the explanation lives.

One administrative change to check: Microsoft's documentation states that the legacy user risk and sign-in risk policies configured inside the ID Protection blade retire on 1 October 2026, with Conditional Access as the replacement. That date has passed. If a tenant still relies on the old policies, verify what is actually being enforced now.

A risk-based policy is only evaluated when a token is issued. An access token that was handed out before the risk went up stays valid until it expires, unless something revokes it. Two mechanisms cover that gap:

- Continuous Access Evaluation. For apps that support it (Exchange Online, SharePoint Online, Teams, Microsoft Graph), a high user risk detected by ID Protection is one of the critical events that makes the app reject the existing token close to real time.
- Explicit revocation. `Revoke-MgUserSignInSession` invalidates refresh tokens and session cookies. The Graph permission needed is `User.RevokeSessions.All`; there is no reason to grant broader user write permissions to an automation that only needs this.

Microsoft's own post lists "prioritize session security" as a starting point, and that is the right call: detection without revocation leaves the attacker's session running.

## Layer 3: Security Copilot in Entra and the agents

This is the layer the word "AI" usually refers to in 2026, and it is the newest.

Security Copilot in Entra became generally available in July 2025. It is a chat interface inside the Entra admin center that answers natural-language questions over Microsoft Graph data: users, groups, sign-in logs, audit logs and the risky users report. "List the recent risky sign-ins for this user" is the typical prompt. It saves time for admins who don't write KQL or Graph queries every day. It does not see anything you couldn't already query yourself.

On top of that sit the agents. Two are relevant here.

The Conditional Access Optimization Agent was the first agent in Entra designed to run on its own. It compares your Conditional Access policies with your users and apps, and suggests changes when users or apps fall outside policy coverage. Microsoft cites a study where admins using it finished Conditional Access tasks 43% faster and 48% more accurately. Note what that measures: admin task speed in tested scenarios, not attacks stopped.

The Identity Risk Management Agent is the one Microsoft's post leans on. It is built into the Risky users report in ID Protection. For each risky user it produces a summary, a list of risk factors, a map of risky sign-ins and a verdict: Compromised or Not compromised. From the report you can apply its suggested remediation per user. A few operational details from the documentation:

- Security Administrator is needed to activate the agent the first time and to act on its suggestions.
- Security Reader and Global Reader can see the agent and its suggestions but can't act on them. That split is useful for a four-eyes review process.
- One agent run consumes on average less than one Security Compute Unit (SCU).
- Each agent gets its own identity through Microsoft Entra Agent ID, with explicitly assigned permissions.

Licensing for this layer is the least transparent part. Security Copilot is billed in SCUs. Since late 2025 Microsoft includes Security Copilot agents for Microsoft 365 E5 customers, with conditions attached. Check the actual terms in your agreement before assuming the agents are free.

## What works

The detection layer is strong where Microsoft has data you don't. A single tenant can't see that an IP address was used for password spray against a thousand other tenants this morning; ID Protection can. The new Authenticator-based detection also covers a real gap that number matching left open, and it does so in real time, so it can stop the sign-in instead of reporting it afterwards.

The design keeps enforcement out of the AI's hands by default. Machine learning produces a score, a Conditional Access policy you wrote acts on it, and both are logged. That is easier to defend in an audit than a black box that blocks users directly.

The agents fit into existing screens instead of adding a new console, and the read-only roles make it possible to run them as advisors first.

## Where it falls short

Licensing shapes what you get more than the technology does. A P1 tenant gets the user-reported signal and a vague "Additional risk detected", but no detection details and no risk-based Conditional Access. The agent layer adds SCU consumption on top of that.

The models are a black box. You can't tune thresholds, see why a sign-in was scored medium instead of high, or add your own signals. Your only feedback channel is confirming users as compromised or dismissing the risk, which Microsoft uses to train the models.

Offline detections arrive late. By the time user risk turns high, a token may have been used for hours. Without Continuous Access Evaluation or revocation automation, the score arrives after the damage.

False positives are a known cost. Shared VPN or proxy egress addresses, mobile carrier IP ranges and staff who travel trigger atypical travel and unfamiliar sign-in properties regularly. Every false positive that leads to a forced password change or a block lands at the helpdesk.

Coverage stops at Entra. Third-party MFA, apps that authenticate somewhere else, and tokens used outside CAE-capable apps are out of scope for most of what's described here.

The agent verdicts are language model output. Microsoft's documentation itself says the findings, summary and risk factors are AI-generated and dynamic. A "Not compromised" verdict is an opinion, not evidence, and shouldn't close an investigation by itself. Letting an agent remediate on its own also means giving a non-human identity the right to change the state of your users. The agent reasons over sign-in and audit data that attackers partly control (user agent strings, app display names, device names), so treat its permissions the way you would treat any other privileged automation account.

## MFA fatigue: detection is the backstop, not the fix

Microsoft's post presents AI detection as the answer to MFA fatigue. The more durable answer is to remove the approval prompt from the attack path altogether. Phishing-resistant methods (passkeys in Microsoft Authenticator, FIDO2 security keys, Windows Hello for Business, Platform SSO on macOS) don't give the user a prompt to approve by mistake. A Conditional Access policy that requires the built-in "Phishing-resistant MFA" authentication strength, starting with administrators, does more against push fatigue than any detection.

For the users who stay on password plus push for now, the order is: number matching (already enforced), Report suspicious activity, the Suspicious MFA authentication approval detection with a sign-in risk policy behind it, and session revocation when risk goes up.

## Checking it in your own logs

If the sign-in and risk logs are sent to Log Analytics or Sentinel, two queries give a quick picture.

Bursts of failed MFA attempts per user (result code 500121 is a failed strong authentication request). Tune the threshold to your environment before turning it into an alert:

```kql
SigninLogs
| where TimeGenerated > ago(1d)
| where ResultType == "500121"
| summarize Attempts = count(),
            Apps = make_set(AppDisplayName),
            IPs = make_set(IPAddress)
    by UserPrincipalName, bin(TimeGenerated, 10m)
| where Attempts >= 5
| order by Attempts desc
```

How often the MFA-related risk detections actually fire:

```kql
AADUserRiskEvents
| where TimeGenerated > ago(30d)
| where RiskEventType in ("authenticatorPhishing", "userReportedSuspiciousActivity")
| project TimeGenerated, UserPrincipalName, RiskEventType,
          RiskLevel, DetectionTimingType, IpAddress
| order by TimeGenerated desc
```

The same data is available through Microsoft Graph at `/identityProtection/riskDetections`, filtered on `riskEventType eq 'authenticatorPhishing'`. Reading it needs `IdentityRiskEvent.Read.All`, and nothing more.

## A rollout order that holds up

1. Check who is licensed for Entra ID P2. Risk-based policies only work for those users.
2. Enable Report suspicious activity in the Authentication methods settings.
3. Confirm that risk policies live in Conditional Access now that the legacy ID Protection policies are retired. Use report-only mode for anything new.
4. Require the Phishing-resistant MFA authentication strength for administrators.
5. Automate session revocation for high user risk and check which of your apps support Continuous Access Evaluation.
6. Turn on the Identity Risk Management Agent with Security Readers reviewing its suggestions. Compare its verdicts with your analysts' conclusions for a few weeks before you allow it to remediate anything on its own.

Strip the marketing from Microsoft's post and what remains is a set of tools that work well together: a detection layer with signal no single tenant has, enforcement you write yourself, and an agent layer that is useful as an advisor and still unproven as a decision-maker. The order in which you deploy them, and the licenses you have, decide most of the outcome.

---

### Sources

- Microsoft Entra Blog: [Identity under attack: How AI strengthens defense](https://techcommunity.microsoft.com/blog/microsoft-entra-blog/identity-under-attack-how-ai-strengthens-defense/4566649)
- Microsoft Learn: [What are risk detections?](https://learn.microsoft.com/entra/id-protection/concept-identity-protection-risks)
- Microsoft Learn: [Configure Microsoft Entra multifactor authentication settings](https://learn.microsoft.com/en-us/entra/identity/authentication/howto-mfa-mfasettings) (Report suspicious activity)
- Microsoft Learn: [Review agent findings in the Risky user report](https://learn.microsoft.com/en-us/entra/id-protection/identity-risk-management-agent-risky-user-report)
- Microsoft Learn: [Security Copilot in Microsoft Entra](https://learn.microsoft.com/en-us/entra/security-copilot/security-copilot-in-entra)
- Microsoft Security Blog: [Four priorities for AI-powered identity and network access security in 2026](https://www.microsoft.com/en-us/security/blog/2026/01/20/four-priorities-for-ai-powered-identity-and-network-access-security-in-2026/)
- Microsoft Security Blog: [Agents built into your workflow: Get Security Copilot with Microsoft 365 E5](https://www.microsoft.com/en-us/security/blog/2025/11/18/agents-built-into-your-workflow-get-security-copilot-with-microsoft-365-e5/)
