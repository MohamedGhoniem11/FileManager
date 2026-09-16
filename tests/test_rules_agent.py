"""
Rules Agent tests — declarative matching + dry-run contract (roadmap 6.2)
------------------------------------------------------------------------
Hermetic: pure matcher over tmp_path files; no config/DB/IO side effects.
"""
import time
from pathlib import Path

from src.core.rules_agent import (
    RulesAgent,
    RuleMatch,
    generate_actions,
    load_yaml_rules,
)


def _file(tmp_path: Path, name: str, size: int = 100, age_days: float = 0.0) -> Path:
    p = tmp_path / name
    p.write_bytes(b"x" * size)
    if age_days:
        old = time.time() - age_days * 86400
        import os

        os.utime(p, (old, old))
    return p


# -- conditions ----------------------------------------------------------------


def test_extension_match(tmp_path):
    agent = RulesAgent([{"name": "pdfs", "when": {"extensions": [".pdf"]}, "then": {}}])
    pdf = _file(tmp_path, "doc.pdf")
    assert agent.evaluate(pdf) == [RuleMatch(name="pdfs")]
    assert agent.evaluate(_file(tmp_path, "doc.txt")) == []


def test_extension_case_insensitive(tmp_path):
    agent = RulesAgent([{"name": "imgs", "when": {"extensions": [".PNG"]}, "then": {}}])
    png = _file(tmp_path, "shot.png")
    assert agent.evaluate(png) == [RuleMatch(name="imgs")]


def test_filename_contains_any_of(tmp_path):
    agent = RulesAgent(
        [{"name": "bank", "when": {"filename_contains": ["statement", "bank"]}, "then": {}}]
    )
    assert agent.evaluate(_file(tmp_path, "bank-statement.pdf")) == [RuleMatch(name="bank")]
    assert agent.evaluate(_file(tmp_path, "invoice.pdf")) == []


def test_path_contains(tmp_path):
    agent = RulesAgent([{"name": "inbox", "when": {"path_contains": ["inbox"]}, "then": {}}])
    sub = tmp_path / "inbox"
    sub.mkdir()
    assert agent.evaluate(_file(sub, "file.txt")) == [RuleMatch(name="inbox")]
    assert agent.evaluate(_file(tmp_path, "file.txt")) == []


def test_size_gte(tmp_path):
    agent = RulesAgent([{"name": "big", "when": {"size_gte": 100}, "then": {}}])
    assert agent.evaluate(_file(tmp_path, "ok.bin", size=100)) == [RuleMatch(name="big")]
    assert agent.evaluate(_file(tmp_path, "small.bin", size=99)) == []


def test_age_days_gte(tmp_path):
    agent = RulesAgent([{"name": "old", "when": {"age_days_gte": 7}, "then": {}}])
    assert agent.evaluate(_file(tmp_path, "old.txt", age_days=8)) == [RuleMatch(name="old")]
    assert agent.evaluate(_file(tmp_path, "fresh.txt", age_days=1)) == []


def test_all_conditions_and_together(tmp_path):
    agent = RulesAgent(
        [{
            "name": "old-bank-pdfs",
            "when": {"extensions": [".pdf"], "filename_contains": ["bank"], "size_gte": 50},
            "then": {},
        }]
    )
    assert agent.evaluate(_file(tmp_path, "bank.pdf", size=60)) == [RuleMatch(name="old-bank-pdfs")]
    assert agent.evaluate(_file(tmp_path, "bank.txt", size=60)) == []  # wrong ext
    assert agent.evaluate(_file(tmp_path, "bank.pdf", size=10)) == []  # too small
    assert agent.evaluate(_file(tmp_path, "invoice.pdf", size=60)) == []  # wrong name


def test_empty_when_matches_everything(tmp_path):
    agent = RulesAgent([{"name": "catch-all", "when": {}, "then": {}}])
    assert agent.evaluate(_file(tmp_path, "anything.xyz")) == [RuleMatch(name="catch-all")]


def test_multiple_rules_return_multiple_matches(tmp_path):
    agent = RulesAgent(
        [
            {"name": "r1", "when": {"extensions": [".pdf"]}, "then": {}},
            {"name": "r2", "when": {"filename_contains": ["bank"]}, "then": {}},
        ]
    )
    assert [m.name for m in agent.evaluate(_file(tmp_path, "bank.pdf"))] == ["r1", "r2"]


def test_no_rule_matches(tmp_path):
    agent = RulesAgent([{"name": "ast", "when": {"extensions": [".pdf"]}, "then": {}}])
    assert agent.evaluate(_file(tmp_path, "data.csv")) == []


# -- then payload -------------------------------------------------------------


def test_then_payload_forwarded(tmp_path):
    agent = RulesAgent(
        [{
            "name": "risky-pdf",
            "when": {"extensions": [".pdf"]},
            "then": {"move_to": "~/Finance/Statements", "cap_confidence": 0.60, "risky": True},
        }]
    )
    match = agent.evaluate(_file(tmp_path, "bank.pdf"))[0]
    assert match.move_to == "~/Finance/Statements"
    assert match.cap_confidence == 0.60
    assert match.risky is True


def test_target_category_rule(tmp_path):
    agent = RulesAgent(
        [{"name": "to-sheets", "when": {"extensions": [".csv"]}, "then": {"target_category": "Sheets"}}]
    )
    assert agent.evaluate(_file(tmp_path, "data.csv"))[0].target_category == "Sheets"


def test_risky_defaults_false(tmp_path):
    agent = RulesAgent([{"name": "plain", "when": {}, "then": {}}])
    assert agent.evaluate(_file(tmp_path, "x.bin"))[0].risky is False


def test_risky_yaml_true_is_truthy(tmp_path):
    agent = RulesAgent([{"name": "r", "when": {}, "then": {"risky": "yes"}}])
    assert agent.evaluate(_file(tmp_path, "x.bin"))[0].risky is True


# -- dry-run contract ----------------------------------------------------------


def test_evaluate_is_dry_run_no_mutations(tmp_path):
    agent = RulesAgent(
        [{"name": "mover", "when": {}, "then": {"move_to": "/tmp/nowhere"}}]
    )
    src = _file(tmp_path, "keep-me.txt")
    target = tmp_path / "nowhere"
    before = sorted(p.name for p in tmp_path.iterdir())
    agent.evaluate(src)
    assert src.exists()  # not moved
    assert not target.exists()  # nothing created
    assert sorted(p.name for p in tmp_path.iterdir()) == before  # dir unchanged


def test_missing_file_returns_no_match(tmp_path):
    agent = RulesAgent([{"name": "r", "when": {}, "then": {}}])
    ghost = tmp_path / "ghost.txt"
    assert agent.evaluate(ghost) == []


# -- Step 9 groundwork: MatchAction generation ---------------------------------


def test_generate_actions_move_to_priority(tmp_path):
    matches = [
        RuleMatch(
            name="explicit",
            move_to="/abs/target",
            target_category="Cat",
        ),
        RuleMatch(name="category-only", target_category="OtherCat"),
        RuleMatch(name="no-target"),
    ]
    actions = generate_actions(matches, tmp_path)
    assert [a.rule_name for a in actions] == ["explicit", "category-only"]
    assert actions[0].target == Path("/abs/target").expanduser()  # move_to beats target_category
    assert actions[1].target == tmp_path / "OtherCat"


def test_generate_actions_relative_move_to(tmp_path):
    actions = generate_actions([RuleMatch(name="rel", move_to="RelDir")], tmp_path)
    assert actions[0].target == tmp_path / "RelDir"


def test_generate_actions_expands_tilde(tmp_path):
    import os

    home = Path(os.path.expanduser("~"))
    actions = generate_actions([RuleMatch(name="t", move_to="~/Sub")], tmp_path)
    assert actions[0].target == home / "Sub"


# -- yaml authoring helper ------------------------------------------------------


def test_load_yaml_rules(tmp_path):
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text(
        """
rules:
  - name: pdfs
    when:
      extensions: [.pdf]
    then:
      target_category: PDFs
"""
    )
    assert load_yaml_rules(rules_file) == [{
        "name": "pdfs",
        "when": {"extensions": [".pdf"]},
        "then": {"target_category": "PDFs"},
    }]


def test_load_yaml_rules_bad_file_returns_empty(tmp_path):
    assert load_yaml_rules(tmp_path / "missing.yaml") == []