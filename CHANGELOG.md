# Changelog

All notable changes to the Aegis Suite project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.1.0-RC1] - 2026-06-03

### Added
- Created `pyproject.toml` supporting `pip install -e .` editable developer setups.
- Implemented automatic invocation of the console onboarding wizard `first_run_wizard.py` in launcher `run.py` when config is absent.
- Expanded CI/CD pull request workflows in `verify.yml` to run the full pytest suite.
- Added comprehensive `ARCHITECTURE.md` detailing system modules, event loop concurrency, database migration rollbacks, and security models.
- Established issue and pull request templates inside `.github/`.
- Created structured governance files (`CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`).

### Changed
- Standardized release workflows to correctly target the `master` branch.
- Synchronized Inno Setup build settings and versions inside `setup.iss` to `2.1.0-RC1`.
- Cleaned PyInstaller specifications inside `build_exe.py` to auto-resolve packaged modules.
- Modernized tests (`test_hosting_mode_selector.py` and `test_managed_hosting.py`) to import directly from production modules.
- Relocated developer utility script `clean_release.py` into the `scripts/` folder.

### Removed
- Removed the legacy `sys.modules["web_server"]` mock shim from `conftest.py`.
- Removed screenshot placeholders and table layouts from `README.md` (replaced with diagnostic Mermaid diagrams).
