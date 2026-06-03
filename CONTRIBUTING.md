# Contributing to Aegis Suite

Thank you for your interest in contributing to Aegis Suite! We welcome contributions from developers of all skill levels. To ensure a smooth process, please follow these guidelines.

---

## Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please report any unacceptable behavior to the project maintainers.

## Getting Started

1. **Fork the Repository**: Create a personal copy of the repository on GitHub.
2. **Clone the Fork**:
   ```cmd
   git clone https://github.com/YourUsername/Aegis-Suite.git
   cd Aegis-Suite
   ```
3. **Set Up the Development Environment**:
   We recommend running Aegis directly from source during development.
   ```cmd
   python run.py
   ```
   This launcher automatically sets up a python virtual environment (`.venv`), installs dependencies, and resolves your path for `ffmpeg`.

## Development Guidelines

* **Python Version Compatibility**: All code must target Python 3.12+.
* **Coding Standards**: We follow standard PEP 8 styles. Clean architecture boundaries must be maintained.
* **Imports Hierarchy**: Avoid importing root-level files (such as `bot_manager.py` or `utils.py`) directly from within core modular packages like `aegis/core` or `aegis/config/loader.py` to prevent cyclic dependencies.

## Testing

Always verify your changes against our test suite before proposing updates.
1. Run the test suite:
   ```cmd
   .venv\Scripts\python.exe -m pytest
   ```
2. Verify that all 215+ tests pass successfully.
3. Write test cases for any new functionality introduced.

## Submitting Pull Requests

1. **Create a Branch**: Create a feature branch off of `master`:
   ```cmd
   git checkout -b feature/my-amazing-feature
   ```
2. **Commit Changes**: Make clear, logical commits:
   ```cmd
   git commit -m "docs: improve contributing guidelines"
   ```
3. **Push to GitHub**: Push your branch to your fork:
   ```cmd
   git push origin feature/my-amazing-feature
   ```
4. **Open a Pull Request**: Target the `master` branch on the upstream repository. Include a clear description of your changes, what issues are fixed, and how they were tested.

Thank you for helping make Aegis Suite better!
