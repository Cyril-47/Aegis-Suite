# Aegis Suite Project Roadmap

This document outlines the strategic priorities, release stages, and feature milestones for the Aegis Suite project.

---

## 📅 Milestones

### Milestone 1: Stability & Cleanliness (Current - v2.1.0-RC1)
* [x] **Complete package structure cleanup**: Relocate all scripts (`auth.py`, `utils.py`, `secret_store.py`, `audit_log.py`, `bot_manager.py`) into the structured Python package folders.
* [x] **Unified entrypoints**: Run through standard packaging CLI (`aegis`).
* [x] **First-run UX**: Automate console onboarding validations.
* [x] **Harden CI/CD pipelines**: Run full pytest checks on all PR branches.

### Milestone 2: SQL Migration & Scaling (v2.2.0)
* [ ] **Retire JSON Databases**: Port `config.json`, `giveaways.json`, and `audit_log.json` to SQLite tables using SQLAlchemy ORM and `aiosqlite`.
* [ ] **Concurrency improvements**: Establish transaction levels to prevent lock contentions in multi-tenant environments.
* [ ] **Developer documentation**: Set up full ReadTheDocs/Sphinx build pipelines.

### Milestone 3: Feature Expansions (v2.3.0)
* [ ] **Dashboard Customization**: Support dark/light/glassmorphism interface styling preferences.
* [ ] **Advanced AutoMod Engine**: Incorporate machine learning spam detectors and toxic phrase analyzers.
* [ ] **Dashboard Multi-User RBAC**: Allow server owners to grant dashboard editor permissions to moderator roles.
