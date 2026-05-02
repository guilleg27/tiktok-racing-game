"""Tests for versus LED scoreboard pulse decay and digital font fallback."""

import unittest
from unittest.mock import MagicMock, patch

import core.config as _core_config
import variants.versus.config as _versus_config

for _k, _v in vars(_versus_config).items():
    if not _k.startswith("_"):
        setattr(_core_config, _k, _v)

from variants.versus.game_engine import VersusGameEngine  # noqa: E402
from core.asset_manager import AssetManager  # noqa: E402


class TestVersusScorePulseDecay(unittest.TestCase):
    """Score pulse values decay each update according to duration config."""

    def test_pulse_decays_after_update(self):
        eng = object.__new__(VersusGameEngine)
        eng.team_left_name = "River"
        eng.team_right_name = "Boca"
        eng._score_pulse = {"River": 1.0, "Boca": 0.0}
        eng._versus_anim_time = 0.0
        eng._versus_last_dt = 0.0
        eng.versus_victory_active = False
        eng.versus_victory_time = 0.0
        eng.victory_screen_duration = 12.0
        eng._reset_versus = MagicMock()
        eng.game_state = "IDLE"
        eng.victory_mode = "score"
        eng.match_start_time = None
        eng.in_extra_time = False
        eng.extra_time_start = None
        eng.golden_goal_active = False
        eng.match_elapsed = 0.0
        eng.match_duration = 60.0
        eng.extra_time_secs = 60.0
        eng._evaluate_time_winner = MagicMock()
        eng._trigger_set_victory = MagicMock()
        pw = MagicMock()
        pw.racers = {"River": MagicMock(), "Boca": MagicMock()}
        pw.is_country_frozen = MagicMock(return_value=False)
        eng.physics_world = pw
        eng._pin_versus_racers_static = MagicMock()

        half = float(_core_config.VERSUS_SCORE_PULSE_DURATION_SEC) * 0.5
        with patch.object(VersusGameEngine.__bases__[0], "update", lambda self, dt: None):
            with patch.object(_core_config, "VERSUS_AMBIENT_ENABLED", False):
                VersusGameEngine.update(eng, half)

        self.assertAlmostEqual(eng._score_pulse["River"], 0.5, delta=0.05)
        self.assertEqual(eng._score_pulse["Boca"], 0.0)


class TestVersusDigitalFontFallback(unittest.TestCase):
    """AssetManager falls back to SysFont when the TTF cannot be loaded."""

    def test_get_versus_digital_font_fallback(self):
        am = object.__new__(AssetManager)
        am.assets_path = MagicMock()
        am._cache = {}
        am._scale_cache = {}
        am._missing_assets = set()
        am._versus_digital_font_cache = {}

        with patch("core.asset_manager.pygame.font.Font", side_effect=OSError("no file")):
            with patch("core.asset_manager.pygame.font.SysFont") as sysfont:
                mock_font = MagicMock(name="SysFontMock")
                sysfont.return_value = mock_font
                f = AssetManager.get_versus_digital_font(am, 24)
        sysfont.assert_called_once()
        self.assertIs(f, mock_font)


class TestScoreboardEase(unittest.TestCase):
    """Sanity check for scoreboard helper."""

    def test_ease_out_cubic_endpoints(self):
        from variants.versus.scoreboard_ui import _ease_out_cubic

        self.assertAlmostEqual(_ease_out_cubic(0.0), 0.0, delta=1e-6)
        self.assertAlmostEqual(_ease_out_cubic(1.0), 1.0, delta=1e-6)
        self.assertGreater(_ease_out_cubic(0.5), 0.5)
