# ADR-014: Cross-Platform Path Resolution via platformdirs

## Status
Accepted

## Context
The old system used relative config/log paths (audit H4): behavior depended on the working directory, breaking packaged EXEs and any launch-from-elsewhere scenario. It also unconditionally imported Windows-only modules in `startup_service.py` (audit C3), making the app Windows-only in practice despite README claims.

## Decision
Use `platformdirs` for all application state locations:
- config → `user_config_dir("FileManager")`
- logs → `user_log_dir("FileManager")`
- journal/DB + cache → `user_data_dir("FileManager")`
Guard all Windows-only imports (`winshell`, `win32com`) behind `sys.platform == "win32"` checks, and make startup-registration a no-op on non-Windows.

## Alternatives Considered
- **CWD-relative paths (status quo)**:
  - Pros: Nothing to add.
  - Cons: Breaks from any other CWD or as EXE (proven baggage).
- **Hardcoded `~/.filemanager`**:
  - Pros: Simple.
  - Cons: Wrong per-OS conventions; bad citizen on Windows/macOS.

## Rationale
`platformdirs` is the de-facto standard for OS-native app data locations, zero-config, and makes the "cross-platform" claim real. The Windows-only imports were a one-file fix once the state lives in OS-standard places.

## Consequences
- **Benefits**: Launch-from-anywhere works; packaged apps work; CI can run the suite on Linux/macOS/Windows (Step 8 in the roadmap).
- **Limitations**: Existing users' old relative-config files need a one-time migration fallback (read old location if new absent).