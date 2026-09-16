# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-09-16

### Added

- **Release automation**: pushing a `v*` tag now builds PyInstaller executables on
  Windows, Linux, and macOS, computes a `SHA256SUMS.txt`, and creates a draft GitHub
  release with all assets (`.github/workflows/release.yml`).
- **CodeQL security scanning** on push/PR + weekly schedule (`.github/workflows/codeql.yml`).
- **Dependabot** for pip and GitHub Actions dependencies (monthly).
- Issue templates (bug report with structured OS/run-mode logging, feature request),
  PR template with checklist, `CONTRIBUTING.md`, `SECURITY.md`.
- CI status + license badges in the README.

### Fixed

- Cross-platform test suite now green on **Windows, Linux, and macOS** (Python 3.12),
  including three previously platform-dependent tests:
  - stat-mock tests no longer miscount `exists()` probes on Python 3.12.
  - undo tests use a holder-file pattern instead of relying on inode reuse.
  - the rules-agent path assertion is drive-relative on Windows.
  - case-sensitivity is probed at runtime instead of assumed from `os.name`.

## [1.0.1] - 2026-09-16

### Changed

- Docs cleanup: removed interview-recording scaffolding from public docs, fixed
  mermaid diagram label syntax. (No code changes.)

## [1.0.0] - 2026-09-16

### Added

- Initial release — see [release notes](https://github.com/MohamedGhoniem11/FileManager/releases/tag/v1.0.0)
  for the full feature set.