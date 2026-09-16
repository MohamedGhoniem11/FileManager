# Contributing to Agentic FileManager

Thanks for your interest! This project is small but aims for production-grade engineering. Please read this before opening a PR.

## Development setup

```bash
git clone https://github.com/MohamedGhoniem11/FileManager
cd FileManager

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies (runtime + test)
pip install -r requirements.txt
```

Enable the project's git hooks (Conventional Commits enforcement):

```bash
git config core.hooksPath .githooks
```

## Running the app

```bash
python -m src.main
```

## Running tests

The full suite is `271` tests and must stay green on **Linux, Windows, and macOS** (Python 3.12):

```bash
pytest
```

Changes that touch `Path.stat`, filesystem behavior, or cross-platform paths **must** pass on all three OSes — the CI matrix runs the same command. When a test depends on platform behavior (case-sensitivity, inode reuse, drive-relative paths), write the test to *probe the environment at runtime* rather than branch on `os.name` unless unavoidable.

## Code style

- Keep modules small and single-responsibility: pure business logic in `src/core/`, singleton services in `src/services/`, view components in `src/gui/`.
- Follow existing naming (snake_case functions, explicit type hints).
- No `as any`-style type suppression, no empty `except` blocks.
- Comments explain *why*, not *what* — and the repo's commit hook will ask you to justify new comments, so keep them meaningful.

## Commit messages

The repo enforces **Conventional Commits** via its `commit-msg` hook:

```
feat(scope): summary
fix(scope): summary
docs(scope): summary
```

Rules: subject ≤ 72 chars, no vague subjects ("fix stuff"), no duplicate subjects. The hook runs automatically once `core.hooksPath` is set.

## Pull requests

1. Create a branch (`git checkout -b feat/your-change`).
2. If a user-facing behavior changes, add a line under **Unreleased** in [CHANGELOG.md](CHANGELOG.md).
3. Add or update tests; the suite must stay green on all three OSes.
4. Open the PR against `main` — the PR template covers the checklist.
5. CI must pass before merge.

## Releases

Releases are driven by tags. Pushing a `v*` tag triggers [.github/workflows/release.yml](.github/workflows/release.yml), which builds the PyInstaller executables on all three OSes, computes `SHA256SUMS.txt`, and creates a **draft** GitHub release with assets. The maintainer reviews the draft and publishes it.

```
git tag v1.1.0 && git push origin v1.1.0
```

## Reporting issues

Use the issue templates — bug reports should include steps to reproduce and relevant logs. See [SECURITY.md](SECURITY.md) for vulnerability reporting.