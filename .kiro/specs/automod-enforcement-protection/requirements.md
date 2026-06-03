# AutoMod Enforcement Requirements — Link & Discord Invite Protection

## 1. Functional Requirements

### FR 1: Enhanced Link Protection
1. **Link Detection**: The system MUST detect any HTTP or HTTPS URLs (e.g. `http://example.com`, `https://example.com/page`).
2. **Domain Matching**: The system MUST detect links that do not have `http://` or `https://` prefixes (e.g. `example.com`, `www.example.com`, `sub.example.com`).
3. **Markdown Link Detection**: The system MUST scan and detect markdown-formatted links (e.g. `[Click Here](http://example.com)` or `[example.com](http://malicious.site)`).
4. **Shortened URLs**: The system MUST detect shortened URL formats (e.g., `bit.ly`, `tinyurl.com`, `t.co`).
5. **Whitelist Domains**: The system MUST allow a configurable whitelist of domains. Messages containing links to whitelisted domains (or subdomains thereof) MUST NOT trigger link protection infractions.

### FR 2: Discord Invite Protection
1. **Invite Detection**: The system MUST detect Discord invite links matching the following formats:
   - `discord.gg/xxxx`
   - `discord.com/invite/xxxx`
   - `discordapp.com/invite/xxxx`
2. **Embedded Invites**: The system MUST detect invites embedded inside larger paragraphs or texts.
3. **Whitelist Invites**: The system MUST support a whitelist of approved invite codes. Messages containing these specific invite codes MUST NOT trigger invite protection infractions.
4. **Independent Toggling**: Invite protection MUST be configurable and toggleable independently from general link protection.

### FR 3: Enforcer & Logger Logic
1. **Enforcement**: When an infraction is detected (link or invite filter violation) and the filter is enabled:
   - The offending message MUST be deleted immediately.
   - The user MUST be warned in the channel where the message was sent (warning message deleted after 5 seconds).
2. **Logging**: The infraction MUST be logged in the designated moderation logs channel, detailing the offending user, channel, reason, and original message content.
3. **Ignored Users**: The enforcement logic MUST ignore users holding administrative or message-management permissions (`administrator` or `manage_messages`).

---

## 2. Non-Functional & Security Requirements

### NFR 1: Low Latency Processing
1. Message processing MUST execute in **under 5 milliseconds** average to prevent blocking or degrading the bot message loops.
2. Link parsing and regex evaluations MUST be cache-friendly and avoid any synchronous or asynchronous blocking network calls.

### NFR 2: Regex Catastrophic Backtracking Prevention
1. All regex patterns used for domain and invite extraction MUST be audited and configured to prevent catastrophic backtracking vulnerabilities.

### NFR 3: Deduplication
1. A single message triggering multiple AutoMod infractions (e.g. containing a blocked word AND a blocked link) MUST only receive one delete enforcement action, one warning message, and one infraction log entry to avoid duplicate punishment spam.

---

## 3. Acceptance Criteria
1. GIVEN Link Protection is enabled with domain `google.com` whitelisted:
   - Invoking `https://google.com` is **allowed**.
   - Invoking `google.com/search` is **allowed**.
   - Invoking `http://malicious.com` is **deleted and logged**.
2. GIVEN Invite Protection is enabled with invite `aegis-dev` whitelisted:
   - Invoking `discord.gg/aegis-dev` is **allowed**.
   - Invoking `discord.gg/other-invite` is **deleted and logged**.
3. GIVEN a user with `manage_messages` permission sends a blocked invite code:
   - The invite is **allowed** (bypass works).
