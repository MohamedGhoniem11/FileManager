"""
Rules Agent — declarative matching with dry-run evaluation (roadmap 6.2)
-----------------------------------------------------------------------
Rules live in config ``rules`` (schema v2) as a list of dicts::

    {
      "name": "bank-statements",
      "when": {
        "extensions": [".pdf"],
        "filename_contains": ["statement", "bank"],
        "path_contains": ["inbox"],
        "size_gte": 10000,
        "age_days_gte": 30
      },
      "then": {
        "move_to": "~/Finance/Statements",
        "target_category": "Statements",
        "cap_confidence": 0.60,
        "risky": true
      }
    }

``evaluate(path)`` performs pure matching — it NEVER moves, deletes, or
writes anything (that is the dry-run / preview contract). A matched rule
surfaces as a RuleMatch; Step 9's universal preview turns matches into
MatchActions the user can confirm before anything mutates.

- ``when`` keys AND together; list values OR within themselves.
- Extensions are matched case-insensitively on suffix.
- ``move_to`` wins over ``target_category`` when both are set.
- ``cap_confidence`` lowers the effective confidence the gate sees.
- ``risky`` forces the gate to ask/hold (never auto-move).
"""
import os
import time
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional

from src.services.config_service import config_service


class RuleMatch(NamedTuple):
    """One matched rule — the dry-run result for a single file."""
    name: str
    move_to: Optional[str] = None
    target_category: Optional[str] = None
    cap_confidence: Optional[float] = None
    risky: bool = False


class MatchAction(NamedTuple):
    """A concrete, user-confirmable proposal (Step 9 universal preview)."""
    rule_name: str
    target: Path
    reason: str


class RulesAgent:
    """Pure rule matcher; the module singleton reads from config_service."""

    def __init__(self, rules: Optional[List[Dict[str, Any]]] = None):
        self._static_rules = rules

    # -- evaluation ----------------------------------------------------------

    def evaluate(self, path: Path) -> List[RuleMatch]:
        """Returns every rule that matches ``path``; no side effects."""
        matches: List[RuleMatch] = []
        for rule in self._current_rules():
            if self._matches(rule.get("when", {}), path):
                then = rule.get("then", {})
                matches.append(
                    RuleMatch(
                        name=rule.get("name", "unnamed-rule"),
                        move_to=then.get("move_to"),
                        target_category=then.get("target_category"),
                        cap_confidence=then.get("cap_confidence"),
                        risky=bool(then.get("risky", False)),
                    )
                )
        return matches

    # -- matching ------------------------------------------------------------

    def _matches(self, when: Dict[str, Any], path: Path) -> bool:
        """All ``when`` conditions must pass; list values are ORed."""
        extension = path.suffix.lower()
        if "extensions" in when and extension not in {
            e.lower() for e in when["extensions"]
        }:
            return False

        name = path.name.lower()
        if "filename_contains" in when and not any(
            token.lower() in name for token in when["filename_contains"]
        ):
            return False

        full = str(path).lower()
        if "path_contains" in when and not any(
            token.lower() in full for token in when["path_contains"]
        ):
            return False

        try:
            st_size = path.stat().st_size
            st_mtime = path.stat().st_mtime
        except OSError:
            return False

        if "size_gte" in when and st_size < when["size_gte"]:
            return False

        if "age_days_gte" in when:
            age_days = (time.time() - st_mtime) / 86400.0
            if age_days < when["age_days_gte"]:
                return False

        return True

    # -- config plumbing (hot-reload friendly) --------------------------------

    def _current_rules(self) -> List[Dict[str, Any]]:
        if self._static_rules is not None:
            return self._static_rules
        return config_service.get("rules", [])


#: Module singleton used by the observer; reads rules from config each call,
#: so a config hot-reload is picked up without restarting the process.
rules_agent = RulesAgent()


# -- Step 9 groundwork: dry-run rules -> confirmable actions -------------------

def generate_actions(
    matches: List[RuleMatch], base_dir: Path
) -> List[MatchAction]:
    """Turns matched rules into concrete move proposals (no execution)."""
    actions: List[MatchAction] = []
    for match in matches:
        if match.move_to:
            target = Path(match.move_to).expanduser()
            if not target.is_absolute():
                target = base_dir / match.move_to
        elif match.target_category:
            target = base_dir / match.target_category
        else:
            continue
        actions.append(
            MatchAction(
                rule_name=match.name,
                target=target,
                reason=f"rule '{match.name}' matched",
            )
        )
    return actions


# -- authoring helper ----------------------------------------------------------

def load_yaml_rules(path: Path) -> List[Dict[str, Any]]:
    """Parses a YAML rules file (list of rule dicts). pyyaml is a dep."""
    import yaml

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError):
        return []
    if isinstance(data, dict):
        data = data.get("rules", [])
    return [dict(rule) for rule in data] if isinstance(data, list) else []