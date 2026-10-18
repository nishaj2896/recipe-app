"""Match scoring, in integer quarter units (ADR-0003 rules 1, 4 and 8)."""

import math
from fractions import Fraction

# Bump whenever the weights, the score formula, the tiers or the sort key
# change (ADR-0003 rule 9), and add a row to SCORING_FINGERPRINTS in the tests.
SCORING_VERSION = 1

# Weights in quarter units: 4 is 1.0, 2 is 0.5, 1 is 0.25 (ADR-0003 rule 1).
MAIN = 4
SUPPORTING = 2
EXCLUDED_STAPLE = 1


def score_int(matched_q: int, core_q: int) -> int:
    """The scored-tier sort value: match ratio times log10(matched weight + 1)."""
    _check(matched_q, core_q)
    composite = float(Fraction(matched_q, core_q)) * math.log10(matched_q / 4 + 1)
    return round(composite * 1_000_000)


def match_tenths(matched_q: int, core_q: int) -> int:
    """The match percentage in tenths, rounded half up with integers only."""
    _check(matched_q, core_q)
    return (matched_q * 2000 + core_q) // (2 * core_q)


def _check(matched_q: int, core_q: int) -> None:
    # Only a caller bug gets here: the scored tier always has a match.
    if not 1 <= matched_q <= core_q:
        raise ValueError(f"need 1 <= matched_q <= core_q, got {matched_q} and {core_q}")
