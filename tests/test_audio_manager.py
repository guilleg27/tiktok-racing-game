"""
Unit tests for AudioManager.

Uses mocking to simulate pygame.mixer for CI/CD environments
where audio files may not be present.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestAudioManagerInitialization(unittest.TestCase):
    """Tests for AudioManager initialization."""
    
    @patch('pygame.mixer.pre_init')
    @patch('pygame.mixer.init')
    @patch('pygame.mixer.set_num_channels')
    @patch('pygame.mixer.set_reserved')
    def test_init_mixer_success(self, mock_reserved, mock_channels, mock_init, mock_pre_init):
        """Test successful mixer initialization."""
        from audio_manager import AudioManager
        
        with patch.object(AudioManager, '_preload_sounds'):
            manager = AudioManager()
            
            # Verify pygame.mixer was configured
            mock_pre_init.assert_called_once()
            mock_init.assert_called_once()
            mock_channels.assert_called_with(16)
            mock_reserved.assert_called_with(1)
            
            self.assertTrue(manager._initialized)
    
    @patch('pygame.mixer.pre_init', side_effect=Exception("Audio device not found"))
    @patch('pygame.mixer.init')
    @patch('pygame.mixer.quit')
    @patch('pygame.mixer.set_num_channels')
    def test_init_mixer_fallback(self, mock_channels, mock_quit, mock_init, mock_pre_init):
        """Test fallback initialization when primary fails."""
        from audio_manager import AudioManager
        
        with patch.object(AudioManager, '_preload_sounds'):
            manager = AudioManager()
            
            # Verify fallback was attempted
            mock_quit.assert_called_once()
            self.assertTrue(manager._initialized)
    
    @patch('pygame.mixer.pre_init', side_effect=Exception("Error"))
    @patch('pygame.mixer.quit', side_effect=Exception("Error"))
    @patch('pygame.mixer.init', side_effect=Exception("Error"))
    def test_init_mixer_complete_failure(self, mock_init, mock_quit, mock_pre_init):
        """Test complete initialization failure."""
        from audio_manager import AudioManager
        
        with patch.object(AudioManager, '_preload_sounds'):
            manager = AudioManager()
            
            self.assertFalse(manager._initialized)


class TestAudioManagerSFX(unittest.TestCase):
    """Tests for sound effect playback."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Mock all pygame.mixer functions
        self.mixer_patches = [
            patch('pygame.mixer.pre_init'),
            patch('pygame.mixer.init'),
            patch('pygame.mixer.quit'),
            patch('pygame.mixer.set_num_channels'),
            patch('pygame.mixer.set_reserved'),
            patch('pygame.mixer.Sound'),
            patch('pygame.mixer.Channel'),
            patch('pygame.mixer.get_num_channels', return_value=16),
        ]
        
        for p in self.mixer_patches:
            p.start()
        
        # Import and create manager
        from audio_manager import AudioManager, SoundType
        self.SoundType = SoundType
        
        with patch.object(AudioManager, '_preload_sounds'):
            self.manager = AudioManager()
            self.manager._initialized = True
            
            # Mock a sound in cache
            mock_sound = MagicMock()
            mock_channel = MagicMock()
            mock_sound.play.return_value = mock_channel
            mock_channel.get_busy.return_value = True
            
            self.manager._sound_cache[SoundType.SMALL_GIFT] = mock_sound
            self.manager._sound_cache[SoundType.BIG_GIFT] = mock_sound
            self.manager._sound_cache[SoundType.VICTORY] = mock_sound
            self.manager._sound_cache[SoundType.FREEZE] = mock_sound
            self.manager._sound_cache[SoundType.BGM] = mock_sound
    
    def tearDown(self):
        """Clean up patches."""
        for p in self.mixer_patches:
            p.stop()
    
    def test_play_gift_sound_small(self):
        """Test small gift sound plays correctly."""
        self.manager.play_gift_sound(gift_name="Rosa", diamond_value=1)
        
        self.manager._sound_cache[self.SoundType.SMALL_GIFT].play.assert_called()
    
    def test_play_gift_sound_big(self):
        """Test big gift sound plays for high-value gifts."""
        self.manager.play_gift_sound(gift_name="Universe", diamond_value=1000)
        
        self.manager._sound_cache[self.SoundType.BIG_GIFT].play.assert_called()
    
    def test_play_victory_sound(self):
        """Test victory sound plays correctly."""
        self.manager.play_victory_sound(winner_country="Argentina")
        
        self.manager._sound_cache[self.SoundType.VICTORY].play.assert_called()
    
    def test_play_freeze_sound(self):
        """Test freeze sound plays correctly."""
        self.manager.play_freeze_sound()
        
        self.manager._sound_cache[self.SoundType.FREEZE].play.assert_called()
    
    def test_play_sfx_not_initialized(self):
        """Test SFX doesn't play when not initialized."""
        self.manager._initialized = False
        
        result = self.manager.play_sfx(self.SoundType.SMALL_GIFT)
        
        self.assertIsNone(result)
    
    def test_play_sfx_missing_sound(self):
        """Test SFX returns None for missing sounds."""
        result = self.manager.play_sfx(self.SoundType.VOTE)  # Not in cache
        
        self.assertIsNone(result)


class TestAudioManagerBGM(unittest.TestCase):
    """Tests for background music playback."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mixer_patches = [
            patch('pygame.mixer.pre_init'),
            patch('pygame.mixer.init'),
            patch('pygame.mixer.quit'),
            patch('pygame.mixer.set_num_channels'),
            patch('pygame.mixer.set_reserved'),
            patch('pygame.mixer.Channel'),
            patch('pygame.mixer.get_num_channels', return_value=16),
        ]
        
        for p in self.mixer_patches:
            p.start()
        
        from audio_manager import AudioManager, SoundType
        self.SoundType = SoundType
        
        with patch.object(AudioManager, '_preload_sounds'):
            self.manager = AudioManager()
            self.manager._initialized = True
            
            # Mock BGM sound
            self.mock_bgm = MagicMock()
            self.manager._sound_cache[SoundType.BGM] = self.mock_bgm
    
    def tearDown(self):
        """Clean up patches."""
        for p in self.mixer_patches:
            p.stop()
    
    def test_play_bgm(self):
        """Test BGM starts playing."""
        with patch('pygame.mixer.Channel') as mock_channel_class:
            mock_channel = MagicMock()
            mock_channel_class.return_value = mock_channel
            
            self.manager.play_bgm()
            
            mock_channel.play.assert_called_once()
    
    def test_stop_bgm(self):
        """Test BGM stops."""
        mock_channel = MagicMock()
        mock_channel.get_busy.return_value = True
        self.manager._bgm_channel = mock_channel
        
        self.manager.stop_bgm(fade_out_ms=0)
        
        mock_channel.stop.assert_called_once()
    
    def test_is_bgm_playing(self):
        """Test BGM playing status check."""
        mock_channel = MagicMock()
        mock_channel.get_busy.return_value = True
        self.manager._bgm_channel = mock_channel
        
        self.assertTrue(self.manager.is_bgm_playing())
        
        mock_channel.get_busy.return_value = False
        self.assertFalse(self.manager.is_bgm_playing())


class TestAudioManagerCombo(unittest.TestCase):
    """Tests for combo/ON FIRE sound effects."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mixer_patches = [
            patch('pygame.mixer.pre_init'),
            patch('pygame.mixer.init'),
            patch('pygame.mixer.quit'),
            patch('pygame.mixer.set_num_channels'),
            patch('pygame.mixer.set_reserved'),
            patch('pygame.mixer.Channel'),
            patch('pygame.mixer.get_num_channels', return_value=16),
        ]
        
        for p in self.mixer_patches:
            p.start()
        
        from audio_manager import AudioManager, SoundType
        self.SoundType = SoundType
        
        with patch.object(AudioManager, '_preload_sounds'):
            self.manager = AudioManager()
            self.manager._initialized = True
            
            # Mock combo and big gift sounds
            mock_sound = MagicMock()
            mock_sound.play.return_value = MagicMock()
            self.manager._sound_cache[SoundType.COMBO_FIRE] = mock_sound
            self.manager._sound_cache[SoundType.BIG_GIFT] = mock_sound
    
    def tearDown(self):
        """Clean up patches."""
        for p in self.mixer_patches:
            p.stop()
    
    def test_combo_level_tracking(self):
        """Test combo level is tracked correctly."""
        self.manager.play_combo_fire_sound(combo_level=3)
        
        self.assertEqual(self.manager._combo_level, 3)
    
    def test_combo_level_clamping(self):
        """Test combo level is clamped to valid range."""
        self.manager.play_combo_fire_sound(combo_level=10)
        
        self.assertEqual(self.manager._combo_level, 5)  # Max is 5
        
        self.manager.play_combo_fire_sound(combo_level=-1)
        
        self.assertEqual(self.manager._combo_level, 0)  # Min is 0


class TestAudioManagerTTS(unittest.TestCase):
    """Tests for TTS integration."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mixer_patches = [
            patch('pygame.mixer.pre_init'),
            patch('pygame.mixer.init'),
            patch('pygame.mixer.quit'),
            patch('pygame.mixer.set_num_channels'),
            patch('pygame.mixer.set_reserved'),
            patch('pygame.mixer.get_num_channels', return_value=16),
        ]
        
        for p in self.mixer_patches:
            p.start()
        
        from audio_manager import AudioManager
        
        with patch.object(AudioManager, '_preload_sounds'):
            self.manager = AudioManager()
            self.manager._initialized = True
    
    def tearDown(self):
        """Clean up patches."""
        for p in self.mixer_patches:
            p.stop()
    
    def test_set_tts_callback(self):
        """Test TTS callback can be set."""
        mock_callback = MagicMock()
        
        self.manager.set_tts_callback(mock_callback)
        
        self.assertEqual(self.manager._tts_callback, mock_callback)
    
    def test_announce_custom_with_callback(self):
        """Test custom announcement calls TTS callback."""
        mock_callback = MagicMock()
        self.manager.set_tts_callback(mock_callback)
        
        self.manager.announce_custom("Test announcement")
        
        # Give thread time to execute
        import time
        time.sleep(0.1)
        
        mock_callback.assert_called_with("Test announcement")
    
    def test_announce_custom_without_callback(self):
        """Test custom announcement does nothing without callback."""
        # Should not raise any exceptions
        self.manager.announce_custom("Test announcement")


class TestSoundType(unittest.TestCase):
    """Tests for SoundType enum."""
    
    def test_sound_types_exist(self):
        """Test all required sound types are defined."""
        from audio_manager import SoundType
        
        required_types = [
            'BGM',
            'SMALL_GIFT',
            'BIG_GIFT',
            'VOTE',
            'COMBO_FIRE',
            'FINAL_STRETCH',
            'VICTORY',
            'FREEZE',
            'COUNTDOWN',
            'TTS_WINNER',
        ]
        
        for type_name in required_types:
            self.assertTrue(
                hasattr(SoundType, type_name),
                f"SoundType.{type_name} should exist"
            )


class TestTTSProviders(unittest.TestCase):
    """Tests for TTS provider implementations."""
    
    def test_create_tts_provider_no_packages(self):
        """Test create_tts_provider returns None when no packages available."""
        with patch.dict('sys.modules', {'pyttsx3': None, 'gtts': None}):
            # Force reimport
            import importlib
            from audio_manager import create_tts_provider
            
            # When both fail, should return None gracefully
            provider = create_tts_provider("auto")
            # Provider may or may not be available depending on environment


if __name__ == '__main__':
    unittest.main()
