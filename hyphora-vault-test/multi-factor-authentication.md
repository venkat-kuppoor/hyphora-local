---
title: Multi-Factor Authentication
type: feature
tags: [#security, #authentication, #access-control]
---

Multi-factor authentication (MFA) in CollabVault provides an essential security layer that significantly reduces the risk of unauthorized access by requiring multiple forms of identity verification. The platform supports various authentication factors including hardware security keys, mobile authenticator apps, SMS codes, and biometric verification, all managed through a flexible policy engine that integrates with the [[access-control|access control system]] and [[compliance-framework|compliance framework]].

The MFA implementation uses adaptive authentication that adjusts requirements based on risk factors such as login location, device trust status, and the sensitivity of resources being accessed as determined by the [[data-classification|data classification system]]. High-risk scenarios, such as accessing restricted workspaces or performing administrative actions, automatically trigger additional authentication challenges. The system maintains detailed logs of all authentication attempts in the [[audit-logs|audit logs]], providing security teams with visibility into potential compromise attempts.

Organizations can configure MFA policies at multiple levels, from global requirements to specific rules for individual [[rbac-model|roles]] or [[workspace-isolation|workspaces]]. The platform supports delegation-resistant MFA methods that prevent social engineering attacks, and includes self-service enrollment workflows that guide users through secure setup while IT administrators maintain oversight through the [[real-time-monitoring|monitoring system]]. Recovery processes are carefully designed to balance security with usability, ensuring legitimate users can regain access while preventing unauthorized account recovery.