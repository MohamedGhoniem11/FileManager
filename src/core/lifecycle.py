"""
Lifecycle Engine — age/size/category policies (roadmap 7.1)
-----------------------------------------------------------
Policies declare WHEN a file is "ready to leave" the active folders and
WHERE it goes next. Shape (config ``lifecycle_policies``)::

    {
      "name": "archive-old-docs",
      "when": {"age_days_gte": 30, "size_gte": 1000, "category_is": "Documents"},
      "then": {"move_to": "~/Archive"}
    }

``run_policies(paths, dry_run)`` is the scheduled-run entry point: it
evaluates every policy against every path and returns PolicyActions.
With ``dry_run=False`` it actually moves journaled files via
organizer.move_file; the default stays dry so scheduling can preview
before anything mutates.
"""
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, NamedTuple, Optional

from src.services.config_service import config_service
from src.core.organizer import organizer
from src.core.classifier import classifier


class PolicyAction(NamedTuple):
    """One proposed/executed lifecycle move."""
    source: Path
    target: Path
    policy_name: str
    reason: str


def evaluate_policy(path: Path, policy: Dict[str, Any]) -> Optional[PolicyAction]:
    """Pure matcher: returns the action for one path+policy, or None."""
    when = policy.get("when", {})
    age_days_gte = when.get("age_days_gte")
    size_gte = when.get("size_gte")
    category_is = when.get("category_is")

    try:
        if age_days_gte is not None:
            age_days = (time.time() - path.stat().st_mtime) / 86400.0
            if age_days < age_days_gte:
                return None
        if size_gte is not None and path.stat().st_size < size_gte:
            return None
    except OSError:
        return None

    if category_is is not None and classifier.classify(path) != category_is:
        return None

    move_to = policy.get("then", {}).get("move_to")
    if not move_to:
        return None

    target = Path(move_to).expanduser()
    if not target.is_absolute():
        target = path.parent / move_to

    name = policy.get("name", "unnamed-policy")
    return PolicyAction(
        source=path,
        target=target,
        policy_name=name,
        reason=f"policy '{name}' matched {path.name}",
    )


def run_policies(
    paths: Iterable[Path],
    policies: Optional[List[Dict[str, Any]]] = None,
    dry_run: bool = True,
) -> List[PolicyAction]:
    """Evaluates all policies over all paths; executes when not dry_run."""
    if policies is None:
        policies = config_service.get("lifecycle_policies", [])

    actions: List[PolicyAction] = []
    for path in paths:
        for policy in policies:
            action = evaluate_policy(path, policy)
            if action is None:
                continue
            if not dry_run:
                final = organizer.move_file(action.source, action.target)
                action = PolicyAction(
                    source=action.source,
                    target=final or action.target,
                    policy_name=action.policy_name,
                    reason=action.reason,
                )
            actions.append(action)
    return actions