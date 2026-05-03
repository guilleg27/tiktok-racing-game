"""Matchup dataclass — single source of truth for a 1v1 duelo."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Tuple


@dataclass
class TeamDef:
    """Definition of one team inside a matchup.

    Args:
        name: Full team name used as the game key (e.g. ``"River"``).
        short: 3-letter abbreviation for compact displays (e.g. ``"RIV"``).
        color: Primary RGB display color.
        accent: Accent / highlight RGB color.
        keywords: Chat comment keywords that register a fan vote for this team.
        escudo_path: Relative asset path for the large crest PNG.
            Falls back to a colored circle if the file is missing.
        marcador_path: Relative asset path for the small scoreboard badge PNG.
            Falls back to a colored circle if the file is missing.
    """

    name: str
    short: str
    color: Tuple[int, int, int]
    accent: Tuple[int, int, int]
    keywords: list[str]
    escudo_path: str = ""
    marcador_path: str = ""


# Left team always gets Dona gift; right team always gets Capibara.
GIFT_LEFT  = "dona"      # asset key / TikTok gift name for the left team
GIFT_RIGHT = "capibara"  # asset key / TikTok gift name for the right team

GIFT_LEFT_PATH  = "assets/versus/images/dona.png"
GIFT_RIGHT_PATH = "assets/versus/images/capibara.png"


@dataclass
class Matchup:
    """Full configuration for one versus duelo.

    Args:
        id: URL-safe slug used as CLI argument and config key.
        label: Human-readable name shown in the startup dropdown.
        left: Left-side team definition.
        right: Right-side team definition.
        gift_team_map: Maps lowercase gift/keyword names to team names.
            Auto-built if left empty (uses ``GIFT_LEFT`` / ``GIFT_RIGHT``).
    """

    id: str
    label: str
    left: TeamDef
    right: TeamDef
    gift_team_map: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.gift_team_map:
            self.gift_team_map = {
                GIFT_LEFT:    self.left.name,
                "rosquilla":  self.left.name,
                "doughnut":   self.left.name,
                GIFT_RIGHT:   self.right.name,
                "capybara":   self.right.name,
            }

    def as_team_left_dict(self) -> dict:
        """Return a dict compatible with the ``TEAM_LEFT`` config shape."""
        return {
            "name":     self.left.name,
            "short":    self.left.short,
            "color":    self.left.color,
            "accent":   self.left.accent,
            "keywords": self.left.keywords,
        }

    def as_team_right_dict(self) -> dict:
        """Return a dict compatible with the ``TEAM_RIGHT`` config shape."""
        return {
            "name":     self.right.name,
            "short":    self.right.short,
            "color":    self.right.color,
            "accent":   self.right.accent,
            "keywords": self.right.keywords,
        }
