# AutoMod Enforcement Design — Link & Discord Invite Protection

## 1. System Architecture

The enhanced AutoMod system integrates link and invite validation engines into the existing message processing pipeline inside the Discord Bot and Web API schemas.

```
       [ Message Received ]
               │
               ▼
     [ Staff Bypass Check ] ────► Staff? ───► Allow
               │ No
               ▼
    [ Content Lowercasing ]
               │
               ▼
     [ Profanity Check ] ────────► Match? ───► Infraction Detected
               │ No
               ▼
      [ Invite Check ] ──────────► Match? ───► Whitelisted? ───► No ───► Infraction Detected
               │ No                                              Yes
               ▼                                                  │
       [ Link Check ] ───────────► Match? ───► Whitelisted? ────┘
               │ No                                              Yes
               ▼                                                  │
     [ Mention Spam Check ] ─────► Match? ────────────────────────┘
               │ No
               ▼
            [ Allow ]
```

---

## 2. Regular Expressions & Catastrophic Backtracking Prevention

To prevent catastrophic backtracking, regex patterns must avoid overlapping wildcards (`*` or `+`) inside nested groupings.

### 2.1 Discord Invite Pattern
```python
# Captures standard discord invite formats, extracting the invite code securely.
DISCORD_INVITE_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li|club)|discord(?:app)?\.com/invite)/([a-zA-Z0-9-]{2,32})',
    re.IGNORECASE
)
```

### 2.2 Domain / URL Extraction Pattern
```python
# A simple, linear regex pattern that extracts domain names without backtracking vulnerabilities.
URL_DOMAIN_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?([a-zA-Z0-9][-a-zA-Z0-9]*[a-zA-Z0-9]\.[a-zA-Z]{2,24}(?:\.[a-zA-Z]{2,24})*)',
    re.IGNORECASE
)
```

---

## 3. Data Model Changes

The `AutomodSettingsModel` in the configuration schema contains the following extended properties:

```python
class AutomodSettingsModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool
    block_profanity: bool
    block_links: bool
    max_mentions: int
    log_channel_id: Optional[str] = None
    log_channel_name: str
    profanity_words: List[str] = Field(default_factory=list)
    
    # New Fields
    block_invites: bool = False
    whitelisted_domains: List[str] = Field(default_factory=list)
    whitelisted_invites: List[str] = Field(default_factory=list)
```

---

## 4. Permission & Enforcement Integration

### 4.1 Invite Validation Logic
1. For every invite link found:
   - Extract the invite code.
   - If the invite code is present in `whitelisted_invites`, bypass enforcement.
   - Otherwise, mark as an infraction.

### 4.2 Link Validation Logic
1. For every URL/Domain match found:
   - Extract the hostname/domain.
   - Standardize/lowercase the hostname.
   - Check if the domain (or any parent domain) is present in `whitelisted_domains` (e.g. if `google.com` is whitelisted, `sub.google.com` or `search.google.com` are allowed).
   - If a non-whitelisted URL is found, mark as an infraction.

### 4.3 Deduplicated Enforcement
If any of the checks fail, the message is marked for infraction.
1. The message is deleted exactly **once**.
2. A single warn message is sent.
3. A single audit-log entry is posted containing **all** infraction reasons identified (e.g., `Infraction: Contains Blocked Links; Contains Blocked Words`).

---

## 5. Web Interface & API Design

### 5.1 Endpoints
- The configuration API `POST /api/config` and `/api/guilds/{guild_id}/config` accepts the new schema attributes and validates them using the expanded Pydantic models.

### 5.2 Dashboard UX
1. Add a new checkbox in `static/index.html` for **Block Discord Invites**.
2. Add textarea fields for **Whitelisted Domains** (one per line) and **Whitelisted Invite Codes** (one per line).
3. Update `static/app.js` to extract textarea strings, split them into arrays, and submit them correctly via the PUT config endpoint.
