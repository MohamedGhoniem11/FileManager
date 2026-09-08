"""
Gate tests — band boundaries, per-category overrides, risk cap (ADR-015)
------------------------------------------------------------------------
Hermetic: pure function, no config/DB/IO dependency.
"""
import pytest

from src.core.gate import decide, DEFAULT_THRESHOLDS, RISK_CONFIDENCE_CAP

# -- global bands -------------------------------------------------------------


def test_high_confidence_auto():
    d = decide("Documents", 0.95)
    assert d.action == "auto"
    assert d.band == "auto"
    assert d.effective_confidence == 0.95


def test_exact_auto_boundary_is_auto():
    # >= 0.80 is auto; 0.79 is NOT
    assert decide("Documents", 0.80).action == "auto"
    assert decide("Documents", 0.79).action == "ask"


def test_ask_band():
    assert decide("Documents", 0.50).action == "ask"
    assert decide("Documents", 0.60).action == "ask"
    assert decide("Documents", 0.74).action == "ask"  # discrete: no sub-bands


def test_below_ask_is_hold():
    assert decide("Documents", 0.49).action == "hold"
    assert decide("Documents", 0.30).action == "hold"
    assert decide("Documents", 0.00).action == "hold"


def test_confidence_capped_at_one():
    d = decide("Documents", 1.0)
    assert d.action == "auto"
    assert d.effective_confidence == 1.0


def test_reason_is_explanatory():
    d = decide("Documents", 0.60)
    assert "0.60" in d.reason
    assert "ask" in d.reason


# -- per-category overrides ----------------------------------------------------


def test_category_override_stricter_than_global():
    thresholds = {"auto": 0.90, "ask": 0.70, "categories": {"Work": {"auto": 0.95}}}
    # Work raises the auto bar: 0.92 is ask there, auto elsewhere
    assert decide("Work", 0.92, thresholds).action == "ask"
    assert decide("Documents", 0.92, thresholds).action == "auto"


def test_category_override_relaxes_global():
    thresholds = {"auto": 0.80, "ask": 0.50, "categories": {"Screenshots": {"auto": 0.70}}}
    assert decide("Screenshots", 0.75, thresholds).action == "auto"


def test_missing_category_uses_global():
    thresholds = {"auto": 0.90, "ask": 0.70, "categories": {"Work": {"auto": 0.95}}}
    assert decide("Unknown", 0.85, thresholds).action == "ask"  # global auto 0.90


def test_partial_override_falls_back_to_global():
    # override only sets "ask"; auto falls back to global 0.80
    thresholds = {"auto": 0.80, "ask": 0.50, "categories": {"Work": {"ask": 0.60}}}
    assert decide("Work", 0.90, thresholds).action == "auto"  # 0.90 >= global auto 0.80
    assert decide("Work", 0.62, thresholds).action == "ask"  # 0.62 >= override ask 0.60
    assert decide("Work", 0.55, thresholds).action == "hold"  # 0.55 < override ask 0.60


def test_none_thresholds_use_defaults():
    d = decide("Documents", 0.85, None)
    assert d.action == "auto"
    assert d.band == "auto"


# -- risk flag (ADR-015 risk cap) ---------------------------------------------


def test_risk_caps_confidence_and_never_auto():
    # 0.95 would be auto, but risky -> effective capped at 0.70 -> ask
    d = decide("Documents", 0.95, risk_flagged=True)
    assert d.action == "ask"
    assert d.band == "ask"
    assert d.effective_confidence == RISK_CONFIDENCE_CAP


def test_risk_high_confidence_is_not_auto_even_with_relaxed_override():
    # Even if a category override lowered auto to 0.60, a risky file must
    # never auto-move: raw band is "auto" (0.70 >= 0.60) but the decision
    # is demoted to "ask".
    thresholds = {"auto": 0.80, "ask": 0.50, "categories": {"Setups": {"auto": 0.60}}}
    d = decide("Setups", 0.95, thresholds, risk_flagged=True)
    assert d.action == "ask"
    assert d.band == "auto"
    assert "demoted" in d.reason


def test_risk_low_confidence_is_hold():
    d = decide("Documents", 0.40, risk_flagged=True)
    assert d.action == "hold"
    assert d.band == "hold"


def test_risk_in_ask_band_stays_ask():
    d = decide("Documents", 0.55, risk_flagged=True)
    assert d.action == "ask"
    assert d.band == "ask"


def test_risk_reason_mentions_flag():
    d = decide("Documents", 0.95, risk_flagged=True)
    assert "risk" in d.reason.lower()