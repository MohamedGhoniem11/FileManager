"""GUI preview formatting (deep pass): proposals render as one safety-flagged
line each, without instantiating a widget or requiring a display.

Exercises MaintenanceFrame._format_proposal as a pure function via the
staticmethod — no ctk widgets, no Tk root.
"""
from pathlib import Path

from src.gui.maintenance import MaintenanceFrame
from src.services.health_service import ProposedAction


def _action(**overrides):
    defaults = {
        "kind": "deduplicate_move", "source": Path("/tmp/dup.txt"),
        "target": Path("/tmp/Misc/dup.txt"),
        "reason": "duplicate of keeper", "undoable": True,
        "requires_confirmation": False,
    }
    defaults.update(overrides)
    return ProposedAction(**defaults)


def test_confirmation_gated_delete_line():
    line = MaintenanceFrame._format_proposal(
        _action(kind="orphan_delete", target=None,
                undoable=False, requires_confirmation=True)
    )
    assert line == "[CONFIRM REQUIRED] orphan_delete: dup.txt -> (delete)"


def test_undoable_move_line():
    line = MaintenanceFrame._format_proposal(_action())
    assert line == "[UNDOABLE] deduplicate_move: dup.txt -> /tmp/Misc/dup.txt"


def test_irreversible_overwrite_line():
    line = MaintenanceFrame._format_proposal(
        _action(kind="empty_folder_remove", target=None,
                undoable=False, requires_confirmation=True)
    )
    assert "[CONFIRM REQUIRED]" in line
    assert "(delete)" in line