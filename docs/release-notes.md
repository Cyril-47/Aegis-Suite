## v2.3.0 - Adaptive Slowmode & Intelligence UI Overhaul
**Release Date:** June 23, 2026

---

### New Features

**Adaptive Slowmode System** - 6-layer intelligence replacing static burst threshold:
- **Raid Hook** (guild-scoped): Critical/high raid threats force 10s/5s slowmode immediately
- **Catastrophic Flood**: 30+ msg/s absolute flood triggers 10s slowmode
- **Baseline-Aware Flood**: 15+ msg/s with 3+ senders and baseline < 5 triggers 5s
- **Dynamic Threshold**: max(3.0, baseline x multiplier) with member scaling (<100: 1.3x, <1000: 1.6x, 1000+: 2.0x)
- **Progressive Escalation**: 1st trigger = 3s, 2nd = 5s, 3rd+ = 10s, 4th+ = 15s
- **Admin Protection + Auto-Remove**: Respects manual slowmode, removes bot-set slowmode after 3x duration

**Baseline Drift Protection**: Dual-window baseline min(5min, 60min) prevents attackers from training the detector by slowly ramping activity.

**Scaled Unique Sender Requirement**: >= max(3, rate/10) makes raid spoofing harder at scale (20 msg/s needs 3 senders, 50 msg/s needs 5).

**Server Health Gauge Animation**: Animated SVG circle fill with number counter on both Command Center and Smart Features. Smooth 1.2s cubic-bezier transition with staggered dimension bar animations.

**Maturity Index Dashboard**: 6-dimension server health scoring (Security, Moderation, Automation, Growth, Reliability, Community) with animated progress bars.

**Chronological Incident Timeline**: 24-hour rolling incident log with automated mitigation action tracking.

**Config Snapshot History**: Config change tracking and rollback capability.

**Welcome Message Variables**: {user} now shows display name (username/nickname). New {mention} variable for clickable mentions. {username} for raw username.

**Sentiment Evasion Normalization**: Abbreviation expansion (kys, stfu, gtfo), leetspeak mapping, repeated char collapse (3+ repeats only), apostrophe normalization - all before VADER analysis. Catches 81.5% of evasion patterns.

**Maintenance Cog**: Scheduled role cleanup (daily), DB vacuum (weekly), channel archive (daily).

**AutoFixEngine Expanded**: 18 action mappings covering all raid detector and spam detector actions.

---

### Bug Fixes

- **Welcome message showing raw @ID** instead of username - now uses member.display_name
- **Server Health stuck on "Loading Auditor..."** - duplicate element IDs in index.html caused JS to update wrong element
- **Config Snapshot History stuck loading** - same duplicate ID issue, skeleton loaders never replaced
- **Skeleton loaders degrading to infinite loading** - replaced with "Loading..." text for graceful degradation
- **Emergency slowmode bypassing unique sender checks** - 15+ msg/s now requires 3 senders + low baseline
- **Raid threat not guild-scoped** - one guild's raid threat was applying slowmode to all guilds
- **Server Health gauge missing circle animation** - CSS/HTML mismatch on score circle
- **Duplicate element IDs** - cc-config-history, cc-timeline in index.html fixed

---

### Build & Release

- **EXE**: 68.1 MB single-file executable, works out of box on any Windows machine
- **pyproject.toml**: Added missing vaderSentiment dependency
- **AegisOptimizer.spec**: Dynamic Discord path resolution (no more hardcoded user paths)
- **build_exe.py**: Updated with all new hidden imports (slowmode, cogs, intelligence, smart features)
- **22 development summary files** moved to docs/changelog-archive/ for cleaner repo root
- **SECURITY.md**: Updated supported versions to v2.2.x
- **18/18 slowmode tests passing**

---

### What's Included in the EXE

- Discord bot with 8 modular cogs (Moderation, Raid, Welcome, Ticket, Giveaway, Leveling, Music, Maintenance)
- FastAPI web dashboard with Intelligence Center
- Adaptive slowmode with 6-layer detection
- Adaptive raid detector with guild-scoping
- Sentiment analyzer with VADER + evasion normalization
- Smart features: Maturity Index, Incident Timeline, Config Snapshots
- Server Health animated gauges
- First-run wizard for setup
