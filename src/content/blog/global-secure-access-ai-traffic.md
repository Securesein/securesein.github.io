---
title: "Global Secure Access and AI traffic: what Microsoft's July update adds and what it costs you"
description: "A technical look at the July 2026 update to Microsoft Entra Internet Access and Private Access: Shadow MCP visibility, BYOD for Private Access, PAC-based browser access, network DLP for AI prompts and agent network controls. What works, what is still preview, and what TLS inspection demands from your PKI and your mobile fleet."
pubDate: 2026-10-30
kind: "enterprise"
format: "deepdive"
topics: ["ai-security", "agents"]
credit: "directed"
model: "Claude"
contributions:
  chose: true
source:
  url: "https://techcommunity.microsoft.com/blog/microsoft-entra-blog/secure-ai-web-and-private-apps-with-zero-trust/4516387"
  publisher: "Microsoft Entra Blog"
  publishedAt: 2026-07-20
---

On 20 July 2026 Microsoft published "Secure AI, web, and private apps with Zero Trust" on the Entra blog. The title suggests identity protection, but the post is about something else: Global Secure Access, Microsoft's Security Service Edge. That is Entra Internet Access (a secure web gateway) and Entra Private Access (zero trust network access, the VPN replacement). The post announces a mix of generally available features and previews, most of them aimed at AI traffic.

As with the [previous post on AI in Entra identity defense](/blog/entra-ai-identity-defense/), I skip the SASE positioning and look at what the features do, what they depend on and where they stop.

## How Global Secure Access gets the traffic

Every feature in this update depends on one thing: the traffic has to pass through Microsoft's edge. There are now four ways to get it there.

The Global Secure Access client is the main one. It acquires traffic per forwarding profile: the Microsoft profile (Microsoft 365 and Entra traffic), the Internet Access profile and the Private Access profile. On Windows the client uses a lightweight filter driver instead of a VPN adapter, which lets it run next to another SSE or VPN client. Clients exist for Windows, macOS, Android and iOS. On iOS and iPadOS there is no separate agent; Microsoft Defender for Endpoint routes the traffic.

Remote networks connect a branch office over IPsec, so devices there need no client.

New in this update is browser-based access. Internet Access can now serve kiosk and BYOD devices through a PAC file that points the browser at the service as a proxy. No client is installed, which also means only traffic that honors the proxy setting is covered.

Policy is applied through Conditional Access. You build security profiles (web filtering, TLS inspection, prompt policies and so on) and link them to users and groups with a Conditional Access policy. That ties network policy to the same identity, device and risk signals that govern sign-in.

## TLS inspection: the prerequisite for nearly everything AI

Shadow AI discovery works from destination data. Everything that looks inside the traffic needs TLS inspection: prompt inspection, MCP payloads, file policies, and the preview DLP features. Microsoft's documentation states explicitly that TLS inspection is a prerequisite for capturing generative AI prompts and MCP payloads on end-user devices. TLS inspection has been generally available since November 2025.

The setup is a classic break-and-inspect design. You generate a certificate signing request in the Global Secure Access portal, sign it with your own root or intermediate CA, and upload the result. The service uses that certificate as an intermediate CA, creates a short-lived second intermediate, and generates leaf certificates on the fly. Every client must trust your root CA, or every inspected connection fails.

The documented limits are worth reading before you plan anything:

- Only one active certificate at a time, and the signed certificate must stay valid for at least six months. Each CSR needs a unique name.
- HTTP/2 negotiation is not supported. Most sites fall back to HTTP/1.1; sites that require HTTP/2 won't load.
- TLS 1.3 with Encrypted Client Hello is not supported, because the service can't read the server name to generate a leaf certificate.
- Apps with certificate pinning break. Microsoft maintains a system bypass list (WhatsApp, Signal, Zoom, Webex, iCloud, Windows Update and others), and you add your own bypass rules by domain or category.
- Developer tools such as Git keep their own CA bundle and will fail until you add your root to it or point them at the OS store.

For an EMM team the mobile side is the hard part. Microsoft itself notes that many mobile apps use certificate pinning, so TLS inspection support on mobile is limited. Distributing the root CA is easy with an Intune trusted certificate profile. On Android it doesn't get you far: apps that target API level 24 or higher ignore user-added CA certificates unless they opt in through a network security configuration, so on Android inspection mostly works for browsers. Plan TLS inspection as a Windows and macOS feature first.

There is also a non-technical step. Decrypting employee traffic, including what they type into AI tools, is monitoring. In the Netherlands that means a works council and a GDPR assessment before you switch it on, not after.

## What became generally available

### Shadow MCP visibility

This is the most interesting new feature. Global Secure Access now logs and analyzes Model Context Protocol traffic between MCP clients on devices and remote MCP servers: which servers are used, which tools and resources they expose, and how those tools are called.

It fills a real gap. MCP servers give AI assistants and agents direct access to tools and data, and most organizations have no inventory of which ones their users connect to. Two limits follow from how it works. It needs TLS inspection to see payloads. And it only sees remote MCP servers reached over the network. A local MCP server that talks to its client over stdio on the same machine never touches the tunnel, and that is how a large share of MCP servers run today.

### BYOD with client for Private Access

Private Access now supports unmanaged devices with the client installed. On Windows, the device no longer has to be domain-joined; Entra registration is enough. This makes Private Access usable for contractors and personal devices that previously needed a classic VPN.

Check what your Conditional Access policies on Private Access apps require. A policy that requires a compliant device will block an unmanaged device by design, so BYOD access needs its own policy set (authentication strength, sign-in risk, possibly app-specific restrictions) and a decision about which private apps are acceptable from an unmanaged device at all.

### Browser-based access with a PAC file

Described above: Internet Access for kiosk and BYOD devices without a client. It is the right tool for shared devices and short-term access. It does nothing for native apps that ignore proxy settings, and it is easy for a user on a personal device to remove.

### Earlier in 2026

The July update builds on features that went GA earlier in the year: Shadow AI discovery (a generative AI filter in the Global Secure Access application insights, GA since 31 March), prompt injection protection through prompt policies in the AI Gateway, and network content filtering by file type, which can block uploads of documents, spreadsheets or PDFs to generative AI and SaaS apps.

Prompt injection protection deserves a short explanation, because the name promises more than a network control can deliver. You configure prompt policies under Global Secure Access > Secure > Prompt policies, add them to a security profile and link that profile through Conditional Access. After TLS decryption, the service inspects prompts sent to supported AI services and blocks those it classifies as injection or jailbreak attempts. Matches show up in the Generative AI Insights logs. It only works for services on Microsoft's supported list, which is still changing, and it is a classifier: expect false negatives and false positives.

## What is still in preview

The headline AI features of the July post are public previews:

- Network DLP with Microsoft Purview. Purview data security extends to traffic through Internet Access: discovering sensitive content in AI and cloud apps, and blocking file uploads, AI prompts and AI responses based on identity and activity. This is the feature most organizations will want, and it is not GA.
- Network controls for agents. The same controls apply to Copilot Studio agents, agents on endpoints and local agents: detecting unsanctioned AI use, limiting agents to approved web destinations, filtering file movement and blocking prompt attacks. The August 2026 macOS client release already added agentic detection support.
- Custom acquire and agentic acquire. New traffic acquisition options so the AI Gateway and agent scenarios can run next to another SSE vendor, instead of requiring Global Secure Access to take all traffic.
- Windows 365 for Agents. Agentic Cloud PCs get web filtering, traffic monitoring and threat blocking from Global Secure Access.

Preview means preview terms, no production SLA and behavior that can change. Test these in a separate tenant or a small pilot group.

## What works

Network policy uses the same Conditional Access engine as sign-in. A user whose risk goes up in ID Protection can lose access to private apps and get stricter web filtering through the same policy logic, without a second identity integration.

The client covers four operating systems, and on Windows it coexists with other VPN and SSE clients. That makes a phased migration possible.

Shadow AI discovery and Shadow MCP visibility answer a question few other tools in a Microsoft stack answer today: which AI services and MCP servers are actually in use, by whom, from which device.

Network-level controls are app-agnostic. A file upload to an AI service is seen whether it comes from Edge, Chrome or a desktop app, as long as the traffic is acquired and inspected.

## Where it falls short

Licensing is the first barrier. The Microsoft traffic profile is included with Entra ID P1 and P2. Internet Access and Private Access are separate: either standalone or as part of the Microsoft Entra Suite. Microsoft 365 E5 does not include Internet Access, so most of the AI features in this post are an extra cost even for E5 customers. Check current pricing before you scope a project.

TLS inspection is an operational project of its own: PKI, certificate distribution, bypass maintenance, HTTP/2 and ECH breakage, help desk tickets for pinned apps, and the privacy and works council track. Without it, most of the AI features reduce to destination-level visibility.

Mobile coverage is thin. Certificate pinning and Android's CA trust model limit inspection on phones, and on iOS the path runs through Defender for Endpoint.

Coverage stops where acquisition stops. Local stdio MCP servers, traffic on devices without the client, apps that ignore the PAC proxy, ECH connections and anything on the bypass list are invisible to these controls.

The features that matter most for AI data protection (network DLP, agent controls) are in preview, while the GA features are mostly about visibility.

There is overlap with Defender for Cloud Apps, Purview endpoint DLP and Edge for Business. Microsoft publishes a coexistence guide for Global Secure Access and Defender for Cloud Apps, which is a sign that the boundaries aren't obvious. Decide which layer enforces what before you configure the same rule in three places.

## Where to start

1. Enable the Microsoft traffic profile. It's included in P1/P2, needs no TLS inspection and gives you the compliant network check in Conditional Access.
2. Pilot Internet Access with Shadow AI discovery to get an inventory of AI use before you write any blocking policy.
3. Prepare TLS inspection on a Windows pilot group: sign the CSR with your CA, deploy the root through Intune, build the bypass list, and settle the privacy and works council questions.
4. Add prompt policies and look at the Shadow MCP data once inspection is stable.
5. Evaluate Private Access with BYOD for contractors who now use the classic VPN, with a separate Conditional Access policy set for unmanaged devices.
6. Test network DLP and agent controls in a test tenant, and wait for GA before relying on them.

The July update makes Global Secure Access a serious candidate for controlling AI traffic in a Microsoft-centric environment, but the value sits behind two gates: a separate license and a working TLS inspection setup. Organizations that clear both get visibility into AI and MCP use that is hard to get elsewhere. Organizations that don't get a VPN replacement and a URL filter.

---

### Sources

- Microsoft Entra Blog: [Secure AI, web, and private apps with Zero Trust](https://techcommunity.microsoft.com/blog/microsoft-entra-blog/secure-ai-web-and-private-apps-with-zero-trust/4516387)
- Big Hat Group: [Microsoft Entra ID Late July 2026](https://www.bighatgroup.com/blog/entra-id-whats-new-2026-07-21/) (summary of the July announcement)
- Microsoft Learn: [Transport Layer Security inspection](https://learn.microsoft.com/en-us/entra/global-secure-access/concept-transport-layer-security)
- Microsoft Learn: [Frequently asked questions for TLS inspection](https://learn.microsoft.com/en-us/entra/global-secure-access/faq-transport-layer-security)
- Microsoft Learn: [Global Secure Access clients](https://learn.microsoft.com/en-us/Entra/global-secure-access/concept-clients)
- Microsoft Learn: [Global Secure Access and Microsoft Defender for Cloud Apps coexistence](https://learn.microsoft.com/en-us/entra/global-secure-access/reference-microsoft-defender-cloud-apps-coexistence)
- Microsoft Learn: [Microsoft Entra releases and announcements](https://learn.microsoft.com/en-us/entra/fundamentals/whats-new)
- Microsoft Learn: [Global Secure Access client for macOS release notes](https://learn.microsoft.com/en-us/entra/global-secure-access/reference-macos-client-release-history)
- Microsoft Entra Blog: [What's New in Microsoft Entra: May 2026](https://techcommunity.microsoft.com/blog/microsoft-entra-blog/whats-new-in-microsoft-entra-may-2026/4517884)
