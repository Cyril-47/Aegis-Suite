# AutoMod Enforcement Test Plan — Link & Discord Invite Protection

## 1. Test Scenarios

### 1.1 Link Detection
* **Test Link-1: Protocol Links**
  - **Inputs**: Message: `Check out http://example.com/test and https://google.com/search`.
  - **Expected Outcome**: Identified as link infraction.
* **Test Link-2: Protocol-less Links**
  - **Inputs**: Message: `Visit www.example.com or sub.domain.org or google.com`.
  - **Expected Outcome**: Identified as link infraction.
* **Test Link-3: Markdown Links**
  - **Inputs**: Message: `[Click Here](http://phishing-site.ru)`.
  - **Expected Outcome**: Identified as link infraction.
* **Test Link-4: Whitelisted Domains**
  - **Inputs**: Configuration: `whitelisted_domains = ["google.com", "github.com"]`. Message: `Check https://google.com and github.com/user/repo`.
  - **Expected Outcome**: Bypassed (allowed).
* **Test Link-5: Subdomain Whitelisting**
  - **Inputs**: Configuration: `whitelisted_domains = ["google.com"]`. Message: `Search on mail.google.com`.
  - **Expected Outcome**: Bypassed (allowed).

### 1.2 Discord Invite Detection
* **Test Invite-1: Standard Formats**
  - **Inputs**: Messages: `discord.gg/abc`, `discord.com/invite/xyz`, `discordapp.com/invite/123`.
  - **Expected Outcome**: Identified as invite infraction.
* **Test Invite-2: Embedded Invites**
  - **Inputs**: Message: `Hey join our server here: discord.gg/aegis-suite for cool stuff`.
  - **Expected Outcome**: Identified as invite infraction.
* **Test Invite-3: Whitelisted Invites**
  - **Inputs**: Configuration: `whitelisted_invites = ["aegis-suite"]`. Message: `Join discord.gg/aegis-suite`.
  - **Expected Outcome**: Bypassed (allowed).

### 1.3 Deduplication & Enforcement
* **Test Enforcement-1: Single Infraction Warn & Log**
  - **Inputs**: Message: `Visit discord.gg/xyz and write badword`. Profanity filter and invite filter both enabled.
  - **Expected Outcome**: One delete call, one warning message sent, and one infraction logged listing both reasons: `Contains Blocked Invites; Contains Blocked Words`.

### 1.4 Ignored Users (Bypass)
* **Test Bypass-1: Staff Roles**
  - **Inputs**: User is Guild Owner or holds Discord `administrator` permission.
  - **Expected Outcome**: Allowed (all checks bypassed).

### 1.5 Performance Gates
* **Test Performance-1: Processing Time**
  - **Goal**: Verify processing resolves in < 5ms.
  - **Expected Outcome**: Evaluation of 1000 messages takes < 5 seconds.
