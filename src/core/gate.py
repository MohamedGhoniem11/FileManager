"""
Confidence Gate — auto / ask / hold decisions (roadmap 6.1, ADR-015)
--------------------------------------------------------------------
A classification's confidence, optional per-category thresholds, and a
risk flag decide whether FileManager may act on a file automatically,
must ask the user first, or must hold the file entirely.

Bands are discrete and asymmetric by design (ADR-015): only two
thresholds split the space, so 0.74 and 0.79 both land in "ask" — no
intermediate band exists. The risk flag caps the effective confidence
and forces ask/hold, so a rule flagged `risky: true` can never fire a
mutating action unattended.
"""

from typing import Any, Dict, NamedTuple, Optional

#: ADR-015 global defaults: auto >= 0.80, ask >= 0.50, below = hold.
DEFAULT_THRESHOLDS: Dict[str, float] = {"auto": 0.80, "ask": 0.50}

#: Risk-flagged classifications never exceed this effective confidence.
RISK_CONFIDENCE_CAP: float = 0.70


class GateDecision(NamedTuple):
    """One gate verdict for a single classification."""
    action: str  # final action: "auto" | "ask" | "hold"
    band: str  # raw threshold band before risk demotion
    effective_confidence: float
    reason: str


def decide(
    category: str,
    confidence: float,
    thresholds: Optional[Dict[str, Any]] = None,
    risk_flagged: bool = False,
) -> GateDecision:
    """Returns the gate verdict for a classification.

    ``thresholds`` (optional)::

        {
            "auto": 0.80,
            "ask": 0.50,
            "categories": {"Images": {"auto": 0.90, "ask": 0.60}},
        }

    Per-category overrides win over the global values; any missing key
    falls back to DEFAULT_THRESHOLDS. ``risk_flagged`` caps the
    effective confidence to RISK_CONFIDENCE_CAP and demotes an "auto"
    verdict to "ask".
    """
    thresholds = thresholds or {}
    auto_t = thresholds.get("auto", DEFAULT_THRESHOLDS["auto"])
    ask_t = thresholds.get("ask", DEFAULT_THRESHOLDS["ask"])
    overrides = thresholds.get("categories", {}).get(category, {})
    if overrides:
        auto_t = overrides.get("auto", auto_t)
        ask_t = overrides.get("ask", ask_t)

    effective = min(confidence, RISK_CONFIDENCE_CAP) if risk_flagged else confidence

    if effective >= auto_t:
        band = "auto"
    elif effective >= ask_t:
        band = "ask"
    else:
        band = "hold"

    action = "ask" if (risk_flagged and band == "auto") else band

    if risk_flagged and band == "auto":
        reason = (
            f"risk-flagged: effective {effective:.2f} (capped from "
            f"{confidence:.2f}) >= auto {auto_t:.2f}, demoted to ask"
        )
    elif risk_flagged:
        reason = (
            f"risk-flagged: effective {effective:.2f} "
            f"(capped from {confidence:.2f}) -> {band}"
        )
    elif band == "auto":
        reason = f"confidence {effective:.2f} >= auto {auto_t:.2f}"
    elif band == "ask":
        reason = f"confidence {effective:.2f} in ask band [{ask_t:.2f}, {auto_t:.2f})"
    else:
        reason = f"confidence {effective:.2f} < ask {ask_t:.2f}"

    return GateDecision(action, band, round(effective, 2), reason)