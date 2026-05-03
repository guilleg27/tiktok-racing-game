"""Versus matchup registry.

Import ``get_matchup`` to resolve a matchup by ID, or ``ALL_MATCHUPS`` for
the full ordered list used in the startup selector.
"""

from variants.versus.matchups.base import Matchup
from variants.versus.matchups.river_boca import RIVER_BOCA
from variants.versus.matchups.arg_bra import ARG_BRA

# Ordered list shown in the startup dropdown.
ALL_MATCHUPS: list[Matchup] = [
    RIVER_BOCA,
    ARG_BRA,
]

_REGISTRY: dict[str, Matchup] = {m.id: m for m in ALL_MATCHUPS}

DEFAULT_MATCHUP = RIVER_BOCA


def get_matchup(matchup_id: str) -> Matchup:
    """Return the Matchup for the given ID, falling back to the default.

    Args:
        matchup_id: Slug string (e.g. ``"river_boca"``).

    Returns:
        Matching ``Matchup`` instance, or ``DEFAULT_MATCHUP`` if not found.
    """
    return _REGISTRY.get(matchup_id, DEFAULT_MATCHUP)
