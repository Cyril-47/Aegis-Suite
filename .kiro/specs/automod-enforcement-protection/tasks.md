# AutoMod Enforcement Tasks — Link & Discord Invite Protection

## 1. Implementation Phases

### Phase 1: Pydantic Schema Expansion
* **Task 1.1**: Update `AutomodSettingsModel` in [aegis/config/schema.py](file:///K:/Aegis/aegis/config/schema.py) with `block_invites`, `whitelisted_domains`, and `whitelisted_invites`.
* **Task 1.2**: Update `AutomodSettingsModel` in [aegis/web/routes/dashboard.py](file:///K:/Aegis/aegis/web/routes/dashboard.py) with the new fields.
* **Task 1.3**: Update `AutomodSettingsModel` in [web_server.py](file:///K:/Aegis/web_server.py) with the new fields.
* **Task 1.4**: Update configuration template example file `config.example.json` with the new fields.

### Phase 2: Core AutoMod Filtering & Enforcement in `bot_manager.py`
* **Task 2.1**: Implement invite parser logic inside `on_message` checks in [bot_manager.py](file:///K:/Aegis/bot_manager.py) to check for invites, verifying whitelisted codes.
* **Task 2.2**: Implement link parser logic inside `on_message` checks in [bot_manager.py](file:///K:/Aegis/bot_manager.py) to check for links/domains, verifying whitelisted domains (including parent/subdomain structures).
* **Task 2.3**: Refactor enforcement logic so that multiple infractions are batched, warning messages are singular, and duplicate deletes/logs do not occur.
* **Task 2.4**: Ensure administrators, staff members, and guild owner bypass all AutoMod checks.

### Phase 3: Dashboard Web UI Integration
* **Task 3.1**: Add a checkbox for "Block Discord Invites" and textareas for whitelisted domains and whitelisted invite codes in [static/index.html](file:///K:/Aegis/static/index.html).
* **Task 3.2**: Update [static/app.js](file:///K:/Aegis/static/app.js) `populateAutomodForm` to parse arrays into textareas, and `saveModerationSettings` to read textareas back into lists.

### Phase 4: Integration Verification & Testing
* **Task 4.1**: Create comprehensive mock-based unit tests for link and invite parsing/blocking in `tests/`.
* **Task 4.2**: Verify that all AutoMod checks (Profanity, Mentions, Links, Invites) run together harmoniously.

---

## 2. Dependencies & Blockers
- **Strict Schema Backwards Compatibility**: Adding defaults to schema fields prevents configuration load crashes.
- **Backtracking Audits**: Confirming regex pattern safety.
- **Fail-Safe Operation**: If configuration values are corrupt, default to restrictive blocks for links/invites.
