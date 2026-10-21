---
title: "Agentic Automation on Android 17: What It Means for Your Organisation's Data"
description: "Android 17 gives AI agents an official way to operate apps on your behalf and keeps them out of the work profile by design. What that means per deployment mode, where setNearbyAppStreamingPolicy and setAppFunctionsPolicy fall short, and what EMM admins should decide before it lands on their fleet."
pubDate: 2026-10-21
kind: "enterprise"
format: "deepdive"
topics: ["agents", "ai-security"]
credit: "directed"
model: "Claude"
contributions:
  chose: true
---
## TL;DR

Android 17 (API level 37) gives AI agents an official way to operate apps on your behalf, and it keeps them out of the work profile by design. On fully managed devices and on the personal side of COPE devices, admins get a kill switch: the existing `setNearbyAppStreamingPolicy` now also disables agentic automation. A second, separate switch, `setAppFunctionsPolicy`, controls whether assistants can pull device state and app data through AppFunctions.

For most organisations the headline is good news: corporate data in a work profile is not agent-reachable out of the box. The work is in the deployment modes where there is no work profile boundary, and in the gaps the two policies don't cover.

- **BYOD / work profile:** agents can't automate work apps; no admin action needed to get that baseline.
- **COPE:** work profile is protected; the personal profile can be locked down with the new policy behaviour.
- **Fully managed (COBO) and dedicated:** there is no profile boundary, so the policy is your only platform-level control. Decide on it explicitly.

## How agents act on Android apps

Android now has two official routes for an AI agent to get work done inside your apps, and they need two different policies. Google laid both out in [The Intelligent OS: Making AI agents more helpful for Android apps](https://android-developers.googleblog.com/2026/02/the-intelligent-os-making-ai-agents.html) (February 2026) and broadened them in Android 17.

- **AppFunctions (structured).** An app declares self-describing functions that an agent can discover and call through natural language. Google itself compares it to an MCP server, but running on the device. The app developer decides exactly what is exposed. Admin control: `setAppFunctionsPolicy`.
- **UI automation (unstructured).** For apps without an AppFunctions integration, the agent operates the app's UI the way a user would: reading the screen, tapping, typing, completing multi-step tasks in the background. The app developer does nothing to opt in. Admin control: `setNearbyAppStreamingPolicy`.

The consumer face of all this is Gemini Intelligence, previewed at The Android Show: I/O Edition in May 2026: cross-app tasks, Intelligent Autofill drawing on context from connected apps, and generated widgets. Google's Android lead described Android 17 as the release where early agentic capabilities start rolling out more broadly, initially for a limited set of apps.

The UI automation route is the one that matters most for enterprise data. An AppFunctions call only reaches what a developer chose to expose; a UI-automating agent reaches whatever is on screen.

Note the third route that has existed for years: third-party agents built on the Accessibility API (projects like DroidRun and AppAgent). These are not part of the new framework, so the new policy behaviour should not be assumed to cover them. They remain governed by the permitted accessibility services allowlist.

## What Android 17 changes, per deployment mode

The work profile is the enforcement boundary: inside it, agentic automation is blocked by the platform. Everywhere else, the default is allowed and the admin has to act. [Google's enterprise release notes for Android 17](https://developer.android.com/work/versions/android-17) name `setNearbyAppStreamingPolicy` as the kill switch for fully managed devices and the COPE personal profile.

That API is not new. It arrived in Android 12 to control streaming of apps to nearby devices (think phone-to-Chromebook app streaming). Android 17 reuses it as the control point for agentic automation, as [Jason Bayton's Android 17 enterprise overview](https://bayton.org/android/android-enterprise-faq/android-17-enterprise-features/) also notes. Setting it to `NEARBY_STREAMING_DISABLED` therefore switches off two things at once: nearby app streaming and agent UI automation.

| Deployment mode | Agent UI automation on corporate data | UI automation control | AppFunctions control |
|---|---|---|---|
| BYOD (work profile on personal device) | Blocked in the work profile by the platform | None needed for work data; personal side is out of admin scope | AMAPI `appFunctions` for work-profile apps; `crossProfileAppFunctions` for personal-to-work calls |
| COPE (corporate-owned work profile) | Blocked in the work profile; allowed in the personal profile by default | `setNearbyAppStreamingPolicy` on the personal profile | As BYOD, plus device-wide `setAppFunctionsPolicy` |
| Fully managed (COBO) | **Allowed by default:** no profile boundary | `setNearbyAppStreamingPolicy` device-wide | `setAppFunctionsPolicy` device-wide |
| Dedicated (COSU / kiosk) | **Allowed by default:** same platform owner model as COBO | `setNearbyAppStreamingPolicy` device-wide | `setAppFunctionsPolicy` device-wide |

The COBO row is the one to pay attention to. A fully managed device is usually where an organisation puts its most sensitive mobile workflows, precisely because there is no personal side. On Android 17 that same design means there is no profile wall between an agent and your line-of-business apps, so the policy is the wall.

On the user side, Android 17 QPR2 (API 37.2) adds an app interaction access layer: [`AppInteractionManager`](https://developer.android.com/reference/android/app/AppInteractionManager) tracks which agent (the *interactor*) may act on which app (the *target*), with system screens where the user grants and revokes that access per pair. That is a consent mechanism for the user, not a control for the admin.

## What this means for organisational data

An agent that operates the UI is, from a data protection standpoint, a second user with the first user's permissions and a direct line to an AI model. Every risk below follows from that.

**1. A new egress path.** Whatever the agent reads on screen becomes model context. Depending on the agent, that context is processed on the device or in the vendor's cloud. For an organisation this is the question that matters: is customer, patient or citizen data leaving the device to a provider you have no processing agreement with? Under the GDPR that is a data processing question, not a UX feature.

**2. Actions with the user's authority.** UI automation doesn't just read, it acts: sending a message, approving a request, changing a record. In your backend logs that action looks exactly like the user did it. That blurs accountability and makes forensic reconstruction harder.

**3. Prompt injection meets business apps.** An agent that reads an email, a ticket or a web page can be steered by text hidden in it. On a fully managed device with line-of-business apps, an injected instruction could drive the agent into those apps. The platform's user oversight helps, but users approve prompts quickly.

**4. The control is coarse.** `setNearbyAppStreamingPolicy` is all-or-nothing per device or per personal profile. There is no admin allowlist of trusted agents or protected apps; the per-pair access control in API 37.2 is in the user's hands. If you want an approved agent on a fully managed device but want it kept away from your ERP app, the platform gives you no admin-side way to express that today.

**5. What the policy does not cover.** Three gaps stand out:

- **Accessibility-based agents.** Third-party agents that drive the UI through an accessibility service are outside the new framework. Google Play policy prohibits apps that use `AccessibilityService` to autonomously plan and execute actions, but sideloaded or privately distributed apps are another matter. The permitted accessibility services allowlist remains the control.
- **Unenrolled devices (MAM-only).** With app protection policies and no device enrollment there is no device or profile owner, so there is nobody to set the policy. The managed app sits in the personal space, next to whatever agent the user installed. App-level controls such as screenshot blocking may or may not stop a UI automation agent; test before you rely on it.
- **AppFunctions on the personal side.** On BYOD, the personal profile is the user's. An assistant can read personal-side device state via AppFunctions and you have no say; that is by design, and only becomes your concern if work data leaks into the personal side through clipboard, sharing or contacts.

## What to do as an EMM admin

Make an explicit decision per deployment mode before Android 17 lands on your fleet; Pixels got it in June 2026, and other OEMs follow from late Q3.

### Where the controls are today

| Control | Android Management API | Intune | Custom DPC / other EMMs |
|---|---|---|---|
| Agent UI automation (via nearby app streaming) | `nearbyAppStreaming` → `NEARBY_APP_STREAMING_DISABLED`, added June 2026 ([release notes](https://developers.google.com/android/management/release-notes)) | No dedicated setting found in the [settings catalog reference](https://learn.microsoft.com/en-us/intune/intune-service/configuration/settings-catalog-android); verify in your tenant | `setNearbyAppStreamingPolicy`; check your vendor's roadmap |
| AppFunctions exposure | `appFunctions`, `crossProfileAppFunctions` (Android 16+) | *Block apps from exposing app functions* (COBO, COSU, COPE work profile) | `setAppFunctionsPolicy(APP_FUNCTIONS_DISABLED)` |
| Accessibility-based agents | `permittedAccessibilityServices` | Verify in the settings catalog | `setPermittedAccessibilityServices` |

One caveat on the first row: Google documents the AMAPI field as a mirror of the platform API, but does not state in so many words that it governs agent automation. Test it on an Android 17 device before you report the risk as mitigated.

### Recommended steps

1. **Fully managed and dedicated: disable by default.** Set nearby app streaming to disabled. On a kiosk or a shared clinical device there is no business case for a consumer agent, and the side effect (no nearby app streaming) is rarely missed.
2. **COPE personal profile: decide deliberately.** The personal profile is the employee's space on a company device. Blocking agents there protects nothing in the work profile; do it only if your risk analysis says the personal side carries corporate data.
3. **Block AppFunctions exposure for managed apps** unless you have a sanctioned agent integration, and keep `crossProfileAppFunctions` disallowed so personal-side agents can't call work apps.
4. **Lock down accessibility services** to a short allowlist. This closes the older, uncontrolled automation route.
5. **Revisit MAM-only for sensitive roles.** If unenrolled Android 17 devices handle data you would not paste into a public chatbot, require enrollment with a work profile for those users.
6. **Run a DPIA for any agent you do allow.** Map what the agent sees, where it is processed and how its actions are logged.
7. **Tell users.** Explain why the assistant can't operate work apps; otherwise they will find a workaround, such as copying data to the personal side.

## Open questions and closing thoughts

Google made the right call on the default: the work profile is closed to agents from day one. That keeps BYOD and COPE work data safe without anyone touching a policy. The weak spot is the fully managed device, where the default is open and the only control is an old streaming API that most admins have never set.

Questions I'm still testing:

- Does the AMAPI `nearbyAppStreaming` field, and each EMM's implementation of it, actually block Gemini's UI automation on Android 17?
- Do app-level controls such as `FLAG_SECURE` or Intune's screen capture block stop a UI automation agent on unenrolled devices?
- Will Google add an admin allowlist of approved agents, or admin control over the API 37.2 interactor/target access?
- Do OEM skins such as Samsung One UI add their own agent frameworks outside this policy?

Agentic automation will become the normal way people use their phones. The question for organisations is not whether to allow AI, but where the boundary sits and who draws it. On Android 17, the work profile draws it for you; on a fully managed device, you have to draw it yourself.

---

### Sources

- Android Developers: [What's new for enterprise in Android 17](https://developer.android.com/work/versions/android-17)
- Android Developers Blog: [The Intelligent OS: Making AI agents more helpful for Android apps](https://android-developers.googleblog.com/2026/02/the-intelligent-os-making-ai-agents.html) (February 2026)
- Android Developers: [Overview of AppFunctions](https://developer.android.com/ai/appfunctions)
- Android API reference: [AppInteractionManager](https://developer.android.com/reference/android/app/AppInteractionManager)
- Google for Developers: [Android Management API release notes](https://developers.google.com/android/management/release-notes)
- Microsoft Learn: [Android settings catalog reference](https://learn.microsoft.com/en-us/intune/intune-service/configuration/settings-catalog-android)
- Jason Bayton: [New in Android 17 for enterprise](https://bayton.org/android/android-enterprise-faq/android-17-enterprise-features/)
- getaibook.com: Android 17 integrates OS-level Gemini agentic automation
- DEV Community: How an AI agent can use Android apps that have no API
