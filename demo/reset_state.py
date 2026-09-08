#!/usr/bin/env python3
"""
reset_state.py — reset FileManager's persisted state for a fresh demo take.

Deletes ONLY FileManager's own application state:
  - config:  user_config_dir("FileManager")
  - database/journal: user_data_dir("FileManager")
  - logs:    user_log_dir("FileManager")

It never touches the watch/downloads folder, and it never touches anything
outside those three platformdirs homes. Run once before every recording take.

Usage:
  python demo/reset_state.py            # reset everything
  python demo/reset_state.py --dry-run  # show what would be deleted
"""
import argparse
import platformdirs
import shutil
from pathlib import Path


def _homes() -> dict:
    """The three FileManager state homes (must match the app's platformdirs usage)."""
    return {
        "config": Path(platformdirs.user_config_dir("FileManager")),
        "data": Path(platformdirs.user_data_dir("FileManager")),
        "logs": Path(platformdirs.user_log_dir("FileManager")),
    }


def reset(what: list, dry_run: bool = False) -> list:
    """Deletes FileManager state homes. Returns a list of removed paths."""
    homes = _homes()
    removed = []
    for name in what:
        home = homes.get(name)
        if home is None or not home.exists():
            continue
        for child in home.iterdir():
            target = home / child.name
            if dry_run:
                print(f"[dry-run] would delete: {target}")
            else:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                print(f"deleted: {target}")
            removed.append(str(target))
    return removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--what",
        nargs="+",
        choices=["config", "data", "logs"],
        default=["config", "data", "logs"],
        help="Which state homes to reset (default: all)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted")
    args = parser.parse_args()

    homes = _homes()
    print("FileManager state homes:")
    for name, home in homes.items():
        print(f"  {name:6s} -> {home}")
    reset(args.what, dry_run=args.dry_run)
    print("Done. Next app launch re-creates defaults." if not args.dry_run else "Dry run — nothing deleted.")


if __name__ == "__main__":
    main()