"""
Unit tests for Versus match flow (timer end, tie-break, single-set MVP).

Uses object.__new__ plus minimal attributes — no full GameEngine init.
"""

import importlib
import unittest
from unittest.mock import MagicMock, patch

# Patch core.config with versus values before importing VersusGameEngine
import core.config as _core_config
import variants.versus.config as _versus_config

for _k, _v in vars(_versus_config).items():
    if not _k.startswith("_"):
        setattr(_core_config, _k, _v)

from variants.versus.game_engine import VersusGameEngine  # noqa: E402


def teardown_module():
    """Restore core.config defaults so other test modules are not polluted."""
    importlib.reload(_core_config)


def _minimal_versus_engine():
    """Build a VersusGameEngine shell with only fields used by time-win logic."""
    eng = object.__new__(VersusGameEngine)
    eng.team_left_name = "River"
    eng.team_right_name = "Boca"
    eng.teams = ["River", "Boca"]
    eng.set_score = {"River": 0, "Boca": 0}
    eng.in_extra_time = False
    eng.extra_time_start = None
    eng.golden_goal_active = False
    eng.versus_victory_active = False
    eng._trigger_set_victory = MagicMock()
    eng._add_floating_text = MagicMock()
    return eng


class TestVersusEvaluateTimeWinner(unittest.TestCase):
    """Tests for VersusGameEngine._evaluate_time_winner (simplified Gol de Oro)."""

    def test_decisive_score_calls_trigger_with_leader(self):
        """Clear winner when time expires → victory triggered immediately."""
        eng = _minimal_versus_engine()
        eng.set_score = {"River": 4, "Boca": 2}
        VersusGameEngine._evaluate_time_winner(eng)
        eng._trigger_set_victory.assert_called_once_with("River")
        self.assertFalse(eng.in_extra_time)

    def test_tie_activates_golden_goal_no_trigger(self):
        """Tie on time expiry → golden goal (sudden death) without triggering victory."""
        eng = _minimal_versus_engine()
        eng.set_score = {"River": 3, "Boca": 3}
        VersusGameEngine._evaluate_time_winner(eng)
        eng._trigger_set_victory.assert_not_called()
        self.assertTrue(eng.in_extra_time)
        self.assertTrue(eng.golden_goal_active)
        self.assertIsNotNone(eng.extra_time_start)

    def test_tie_golden_goal_no_countdown(self):
        """After tie, golden goal state has no time limit — extra_time_secs is not consulted."""
        eng = _minimal_versus_engine()
        eng.set_score = {"River": 1, "Boca": 1}
        VersusGameEngine._evaluate_time_winner(eng)
        # No victory called — match waits for the next score
        eng._trigger_set_victory.assert_not_called()
        self.assertTrue(eng.golden_goal_active)


class TestVersusConfigPatch(unittest.TestCase):
    """Smoke: versus config disables autopilot."""

    def test_autopilot_disabled_in_versus_config(self):
        from core.config import AUTOPILOT_ENABLED

        self.assertFalse(AUTOPILOT_ENABLED)


class TestVersusTriggerSetVictory(unittest.TestCase):
    """Match win opens victory flow (no intermediate set / series)."""

    def test_trigger_set_victory_calls_show_match_victory(self):
        eng = _minimal_versus_engine()
        eng._show_match_victory = MagicMock()
        VersusGameEngine._trigger_set_victory(eng, "River")
        eng._show_match_victory.assert_called_once_with("River")


class TestVersusVictoryOverlayTimeout(unittest.TestCase):
    """Victory overlay elapsed time triggers full versus reset."""

    def test_reset_after_victory_screen_duration(self):
        eng = object.__new__(VersusGameEngine)
        eng.versus_victory_active = True
        eng.versus_victory_time = 11.0
        eng.victory_screen_duration = 12.0
        eng._reset_versus = MagicMock()
        eng.team_left_name = "River"
        eng.team_right_name = "Boca"
        eng._versus_anim_time = 0.0
        eng._versus_last_dt = 0.0
        eng._score_pulse = {"River": 0.0, "Boca": 0.0}
        eng._pin_versus_racers_static = MagicMock()
        eng.physics_world = MagicMock()
        eng.physics_world.racers = {}
        eng.game_state = "IDLE"
        eng.victory_mode = "score"
        eng.match_start_time = None
        eng._free_kick_active = False
        with patch("variants.versus.game_engine.GameEngine.update", MagicMock()):
            with patch.object(_core_config, "VERSUS_AMBIENT_ENABLED", False):
                VersusGameEngine.update(eng, 2.0)
        eng._reset_versus.assert_called_once()


if __name__ == "__main__":
    unittest.main()
