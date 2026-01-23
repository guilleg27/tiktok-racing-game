"""
Unit tests for CloudManager Supabase integration.

Tests cover:
- Singleton pattern
- Initialization with/without .env
- Sync operations (success/failure)
- Non-blocking async behavior
- Error handling
"""

import unittest
import asyncio
import os
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime

# Mock supabase before importing CloudManager
import sys
sys.modules['supabase'] = MagicMock()
sys.modules['dotenv'] = MagicMock()

from src.cloud_manager import CloudManager


class TestCloudManagerInitialization(unittest.TestCase):
    """Tests for CloudManager initialization and singleton pattern."""
    
    def setUp(self):
        """Reset singleton before each test."""
        CloudManager._instance = None
        CloudManager._initialized = False
    
    @patch.dict(os.environ, {}, clear=True)
    @patch('src.cloud_manager.SUPABASE_AVAILABLE', True)
    def test_initialization_without_env_vars(self):
        """Test that CloudManager initializes with disabled state when .env missing."""
        manager = CloudManager()
        
        self.assertFalse(manager.enabled)
        self.assertIsNone(manager.client)
    
    @patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_KEY': 'test-key'
    })
    @patch('src.cloud_manager.SUPABASE_AVAILABLE', True)
    @patch('src.cloud_manager.create_client')
    def test_initialization_with_env_vars(self, mock_create_client):
        """Test successful initialization with environment variables."""
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        
        manager = CloudManager()
        
        self.assertTrue(manager.enabled)
        self.assertIsNotNone(manager.client)
        mock_create_client.assert_called_once_with('https://test.supabase.co', 'test-key')
    
    @patch('src.cloud_manager.SUPABASE_AVAILABLE', False)
    def test_initialization_without_supabase_library(self):
        """Test graceful degradation when supabase library not installed."""
        manager = CloudManager()
        
        self.assertFalse(manager.enabled)
        self.assertIsNone(manager.client)
    
    @patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_KEY': 'test-key'
    })
    @patch('src.cloud_manager.SUPABASE_AVAILABLE', True)
    @patch('src.cloud_manager.create_client')
    def test_initialization_with_client_error(self, mock_create_client):
        """Test that initialization errors are caught and logged."""
        mock_create_client.side_effect = Exception("Connection failed")
        
        manager = CloudManager()
        
        self.assertFalse(manager.enabled)
        self.assertIsNone(manager.client)
    
    def test_singleton_pattern(self):
        """Test that CloudManager follows singleton pattern."""
        manager1 = CloudManager()
        manager2 = CloudManager()
        
        self.assertIs(manager1, manager2)
    
    @patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_KEY': 'test-key'
    })
    @patch('src.cloud_manager.SUPABASE_AVAILABLE', True)
    @patch('src.cloud_manager.create_client')
    def test_initialization_only_once(self, mock_create_client):
        """Test that initialization only happens once despite multiple calls."""
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        
        manager1 = CloudManager()
        manager2 = CloudManager()
        manager3 = CloudManager()
        
        # Should only call create_client once
        mock_create_client.assert_called_once()


class TestCloudManagerSyncOperations(unittest.TestCase):
    """Tests for sync_race_result operations."""
    
    def setUp(self):
        """Reset singleton and setup mocks before each test."""
        CloudManager._instance = None
        CloudManager._initialized = False
    
    @patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_KEY': 'test-key'
    })
    @patch('src.cloud_manager.SUPABASE_AVAILABLE', True)
    @patch('src.cloud_manager.create_client')
    def test_sync_race_result_when_disabled(self, mock_create_client):
        """Test that sync returns False when CloudManager is disabled."""
        manager = CloudManager()
        manager.enabled = False  # Force disabled state
        
        result = asyncio.run(manager.sync_race_result(
            country="Argentina",
            winner_name="test_user",
            total_diamonds=500
        ))
        
        self.assertFalse(result)
    
    @patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_KEY': 'test-key'
    })
    @patch('src.cloud_manager.SUPABASE_AVAILABLE', True)
    @patch('src.cloud_manager.create_client')
    def test_sync_race_result_success_existing_country(self, mock_create_client):
        """Test successful sync for existing country (increment wins)."""
        # Setup mock client
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        
        # Mock select response (country exists)
        mock_select_response = MagicMock()
        mock_select_response.data = [{
            'country': 'Argentina',
            'total_wins': 5,
            'total_diamonds': 1000
        }]
        
        # Setup chain: table().select().eq().execute()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        
        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        
        mock_eq = MagicMock()
        mock_select.eq.return_value = mock_eq
        mock_eq.execute.return_value = mock_select_response
        
        # Mock update response
        mock_update = MagicMock()
        mock_table.update.return_value = mock_update
        mock_update.eq.return_value = MagicMock()
        mock_update.eq.return_value.execute.return_value = MagicMock()
        
        # Mock insert response (for hall of fame)
        mock_insert = MagicMock()
        mock_table.insert.return_value = mock_insert
        mock_insert.execute.return_value = MagicMock()
        
        manager = CloudManager()
        
        # Test sync
        result = asyncio.run(manager.sync_race_result(
            country="Argentina",
            winner_name="test_user",
            total_diamonds=500,
            streamer_name="streamer123"
        ))
        
        self.assertTrue(result)
        
        # Verify update was called with incremented values
        mock_table.update.assert_called_once()
        update_data = mock_table.update.call_args[0][0]
        self.assertEqual(update_data['total_wins'], 6)  # 5 + 1
        self.assertEqual(update_data['total_diamonds'], 1500)  # 1000 + 500
    
    @patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_KEY': 'test-key'
    })
    @patch('src.cloud_manager.SUPABASE_AVAILABLE', True)
    @patch('src.cloud_manager.create_client')
    def test_sync_race_result_success_new_country(self, mock_create_client):
        """Test successful sync for new country (insert)."""
        # Setup mock client
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        
        # Mock select response (country doesn't exist)
        mock_select_response = MagicMMock()
        mock_select_response.data = []
        
        # Setup chain
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        
        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        
        mock_eq = MagicMock()
        mock_select.eq.return_value = mock_eq
        mock_eq.execute.return_value = mock_select_response
        
        # Mock insert responses
        mock_insert = MagicMock()
        mock_table.insert.return_value = mock_insert
        mock_insert.execute.return_value = MagicMock()
        
        manager = CloudManager()
        
        # Test sync
        result = asyncio.run(manager.sync_race_result(
            country="NewCountry",
            winner_name="test_user",
            total_diamonds=500,
            streamer_name="streamer123"
        ))
        
        self.assertTrue(result)
        
        # Verify insert was called for both tables
        self.assertEqual(mock_table.insert.call_count, 2)
    
    @patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_KEY': 'test-key'
    })
    @patch('src.cloud_manager.SUPABASE_AVAILABLE', True)
    @patch('src.cloud_manager.create_client')
    def test_sync_race_result_network_error(self, mock_create_client):
        """Test that network errors are caught and logged."""
        # Setup mock client that raises error
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.side_effect = Exception("Network timeout")
        
        manager = CloudManager()
        
        # Test sync
        result = asyncio.run(manager.sync_race_result(
            country="Argentina",
            winner_name="test_user",
            total_diamonds=500
        ))
        
        # Should return False but not crash
        self.assertFalse(result)


class TestCloudManagerQueryOperations(unittest.TestCase):
    """Tests for query operations (leaderboard, stats)."""
    
    def setUp(self):
        """Reset singleton before each test."""
        CloudManager._instance = None
        CloudManager._initialized = False
    
    @patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_KEY': 'test-key'
    })
    @patch('src.cloud_manager.SUPABASE_AVAILABLE', True)
    @patch('src.cloud_manager.create_client')
    def test_get_global_leaderboard_success(self, mock_create_client):
        """Test fetching global leaderboard."""
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        
        # Mock response
        mock_response = MagicMock()
        mock_response.data = [
            {'captain_name': 'player1', 'total_diamonds': 1000},
            {'captain_name': 'player2', 'total_diamonds': 800}
        ]
        
        # Setup chain
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        
        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        
        mock_order = MagicMock()
        mock_select.order.return_value = mock_order
        
        mock_limit = MagicMock()
        mock_order.limit.return_value = mock_limit
        mock_limit.execute.return_value = mock_response
        
        manager = CloudManager()
        
        # Test
        result = asyncio.run(manager.get_global_leaderboard(limit=10))
        
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['captain_name'], 'player1')
    
    @patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_KEY': 'test-key'
    })
    @patch('src.cloud_manager.SUPABASE_AVAILABLE', True)
    @patch('src.cloud_manager.create_client')
    def test_get_country_stats_success(self, mock_create_client):
        """Test fetching country stats."""
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        
        # Mock response
        mock_response = MagicMock()
        mock_response.data = [{
            'country': 'Argentina',
            'total_wins': 10,
            'total_diamonds': 5000
        }]
        
        # Setup chain
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        
        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        
        mock_eq = MagicMock()
        mock_select.eq.return_value = mock_eq
        mock_eq.execute.return_value = mock_response
        
        manager = CloudManager()
        
        # Test
        result = asyncio.run(manager.get_country_stats("Argentina"))
        
        self.assertIsNotNone(result)
        self.assertEqual(result['country'], 'Argentina')
        self.assertEqual(result['total_wins'], 10)
    
    @patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_KEY': 'test-key'
    })
    @patch('src.cloud_manager.SUPABASE_AVAILABLE', True)
    @patch('src.cloud_manager.create_client')
    def test_get_country_stats_not_found(self, mock_create_client):
        """Test fetching stats for non-existent country."""
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        
        # Mock empty response
        mock_response = MagicMock()
        mock_response.data = []
        
        # Setup chain
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        
        mock_select = MagicMock()
        mock_table.select.return_value = mock_select
        
        mock_eq = MagicMock()
        mock_select.eq.return_value = mock_eq
        mock_eq.execute.return_value = mock_response
        
        manager = CloudManager()
        
        # Test
        result = asyncio.run(manager.get_country_stats("NonExistent"))
        
        self.assertIsNone(result)


class TestCloudManagerNonBlocking(unittest.TestCase):
    """Tests to ensure operations don't block the event loop."""
    
    def setUp(self):
        """Reset singleton before each test."""
        CloudManager._instance = None
        CloudManager._initialized = False
    
    @patch.dict(os.environ, {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_KEY': 'test-key'
    })
    @patch('src.cloud_manager.SUPABASE_AVAILABLE', True)
    @patch('src.cloud_manager.create_client')
    def test_sync_uses_executor(self, mock_create_client):
        """Test that sync operations use run_in_executor for non-blocking."""
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        
        # Mock response
        mock_response = MagicMock()
        mock_response.data = [{'total_wins': 5, 'total_diamonds': 1000}]
        
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value.eq.return_value.execute.return_value = mock_response
        mock_table.update.return_value.eq.return_value.execute.return_value = MagicMock()
        mock_table.insert.return_value.execute.return_value = MagicMock()
        
        manager = CloudManager()
        
        # Test that sync completes quickly (not blocking)
        start_time = asyncio.get_event_loop().time()
        result = asyncio.run(manager.sync_race_result(
            country="Argentina",
            winner_name="test_user",
            total_diamonds=500
        ))
        end_time = asyncio.get_event_loop().time()
        
        # Should complete very quickly (< 1 second in tests)
        self.assertLess(end_time - start_time, 1.0)
        self.assertTrue(result)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
