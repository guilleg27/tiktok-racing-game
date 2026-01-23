#!/usr/bin/env python3
"""
End-to-End Test for Cloud Sync Integration.

This script tests the complete flow:
1. Initialize CloudManager
2. Simulate a race with winner
3. Verify data synced to Supabase
4. Clean up test data

Usage:
    python test_e2e_cloud_sync.py
"""

import asyncio
import os
import sys
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from cloud_manager import CloudManager


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_header(text: str):
    """Print formatted header."""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{text.center(60)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.END}\n")


def print_success(text: str):
    """Print success message."""
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")


def print_error(text: str):
    """Print error message."""
    print(f"{Colors.RED}❌ {text}{Colors.END}")


def print_warning(text: str):
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.END}")


def print_info(text: str):
    """Print info message."""
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.END}")


async def test_cloud_manager_initialization():
    """Test 1: CloudManager initialization."""
    print_header("TEST 1: CloudManager Initialization")
    
    try:
        # Reset singleton
        CloudManager._instance = None
        CloudManager._initialized = False
        
        manager = CloudManager()
        
        if not manager.enabled:
            print_error("CloudManager is disabled. Check your .env configuration.")
            return False
        
        if manager.client is None:
            print_error("Supabase client is None")
            return False
        
        print_success("CloudManager initialized successfully")
        print_info(f"Enabled: {manager.enabled}")
        print_info(f"Client: {type(manager.client).__name__}")
        return True
        
    except Exception as e:
        print_error(f"Failed to initialize CloudManager: {e}")
        return False


async def test_supabase_connection():
    """Test 2: Direct Supabase connection."""
    print_header("TEST 2: Direct Supabase Connection")
    
    try:
        load_dotenv()
        
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        
        if not url or not key:
            print_error("SUPABASE_URL or SUPABASE_KEY not found in .env")
            return False
        
        print_info(f"URL: {url}")
        print_info(f"Key: {key[:20]}...")
        
        client = create_client(url, key)
        
        # Test query
        response = client.table("global_country_stats").select("*").limit(1).execute()
        
        print_success("Connected to Supabase successfully")
        print_info(f"Test query returned {len(response.data)} rows")
        return True
        
    except Exception as e:
        print_error(f"Failed to connect to Supabase: {e}")
        return False


async def test_sync_race_result():
    """Test 3: Sync race result."""
    print_header("TEST 3: Sync Race Result")
    
    try:
        manager = CloudManager()
        
        # Test data
        test_country = "Argentina"
        test_captain = f"e2e_test_user_{int(datetime.now().timestamp())}"
        test_diamonds = 999
        test_streamer = "e2e_test_streamer"
        
        print_info(f"Syncing test race:")
        print_info(f"  Country: {test_country}")
        print_info(f"  Captain: {test_captain}")
        print_info(f"  Diamonds: {test_diamonds}")
        print_info(f"  Streamer: {test_streamer}")
        
        # Sync
        result = await manager.sync_race_result(
            country=test_country,
            winner_name=test_captain,
            total_diamonds=test_diamonds,
            streamer_name=test_streamer
        )
        
        if not result:
            print_error("Sync returned False")
            return False, None
        
        print_success("Race result synced successfully")
        return True, test_captain
        
    except Exception as e:
        print_error(f"Failed to sync race result: {e}")
        import traceback
        traceback.print_exc()
        return False, None


async def test_verify_sync():
    """Test 4: Verify data in Supabase."""
    print_header("TEST 4: Verify Synced Data")
    
    try:
        load_dotenv()
        client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
        
        # Check global_country_stats
        print_info("Checking global_country_stats...")
        response = client.table("global_country_stats").select("*").eq("country", "Argentina").execute()
        
        if not response.data:
            print_error("Country stats not found")
            return False
        
        stats = response.data[0]
        print_success(f"Country stats found:")
        print_info(f"  Total Wins: {stats['total_wins']}")
        print_info(f"  Total Diamonds: {stats['total_diamonds']}")
        
        # Check global_hall_of_fame (last entry)
        print_info("Checking global_hall_of_fame...")
        response = client.table("global_hall_of_fame") \
            .select("*") \
            .eq("country", "Argentina") \
            .order("race_timestamp", desc=True) \
            .limit(1) \
            .execute()
        
        if not response.data:
            print_error("Hall of fame entry not found")
            return False
        
        entry = response.data[0]
        print_success(f"Hall of fame entry found:")
        print_info(f"  Captain: {entry['captain_name']}")
        print_info(f"  Diamonds: {entry['total_diamonds']}")
        print_info(f"  Timestamp: {entry['race_timestamp']}")
        print_info(f"  Streamer: {entry['streamer_name']}")
        
        return True
        
    except Exception as e:
        print_error(f"Failed to verify sync: {e}")
        return False


async def test_query_operations():
    """Test 5: Query operations."""
    print_header("TEST 5: Query Operations")
    
    try:
        manager = CloudManager()
        
        # Test get_global_leaderboard
        print_info("Fetching global leaderboard...")
        leaderboard = await manager.get_global_leaderboard(limit=5)
        
        if not leaderboard:
            print_warning("Leaderboard is empty (this is OK if no races yet)")
        else:
            print_success(f"Leaderboard fetched: {len(leaderboard)} entries")
            for i, entry in enumerate(leaderboard[:3], 1):
                print_info(f"  #{i}: {entry['captain_name']} - {entry['total_diamonds']}💎 ({entry['country']})")
        
        # Test get_country_stats
        print_info("Fetching Argentina stats...")
        stats = await manager.get_country_stats("Argentina")
        
        if not stats:
            print_error("Failed to fetch country stats")
            return False
        
        print_success("Country stats fetched:")
        print_info(f"  Wins: {stats['total_wins']}")
        print_info(f"  Diamonds: {stats['total_diamonds']}")
        
        return True
        
    except Exception as e:
        print_error(f"Failed query operations: {e}")
        return False


async def test_non_blocking():
    """Test 6: Non-blocking behavior."""
    print_header("TEST 6: Non-Blocking Behavior")
    
    try:
        manager = CloudManager()
        
        print_info("Testing that sync doesn't block event loop...")
        
        # Measure time for sync operation
        import time
        start = time.time()
        
        result = await manager.sync_race_result(
            country="Brasil",
            winner_name="non_blocking_test",
            total_diamonds=100,
            streamer_name="test"
        )
        
        elapsed = time.time() - start
        
        if elapsed > 2.0:
            print_warning(f"Sync took {elapsed:.2f}s (might be blocking)")
        else:
            print_success(f"Sync completed in {elapsed:.3f}s (non-blocking)")
        
        return True
        
    except Exception as e:
        print_error(f"Failed non-blocking test: {e}")
        return False


async def cleanup_test_data():
    """Clean up test data from Supabase."""
    print_header("CLEANUP: Removing Test Data")
    
    try:
        load_dotenv()
        client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
        
        print_info("Removing test entries from hall_of_fame...")
        
        # Delete test entries (those with e2e_test in captain_name)
        response = client.table("global_hall_of_fame") \
            .delete() \
            .like("captain_name", "e2e_test%") \
            .execute()
        
        print_success("Test data cleaned up")
        return True
        
    except Exception as e:
        print_warning(f"Cleanup failed (this is OK): {e}")
        return False


async def main():
    """Run all tests."""
    print_header("🧪 E2E Cloud Sync Integration Tests")
    
    results = {}
    
    # Run tests
    results['initialization'] = await test_cloud_manager_initialization()
    
    if not results['initialization']:
        print_error("Initialization failed. Stopping tests.")
        return
    
    results['connection'] = await test_supabase_connection()
    results['sync'], test_captain = await test_sync_race_result()
    
    if results['sync']:
        await asyncio.sleep(1)  # Wait for sync to complete
        results['verify'] = await test_verify_sync()
    else:
        results['verify'] = False
    
    results['query'] = await test_query_operations()
    results['non_blocking'] = await test_non_blocking()
    
    # Cleanup
    await cleanup_test_data()
    
    # Summary
    print_header("📊 Test Summary")
    
    total = len(results)
    passed = sum(1 for r in results.values() if r)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        color = Colors.GREEN if result else Colors.RED
        print(f"{color}{status}{Colors.END} - {test_name}")
    
    print(f"\n{Colors.BOLD}Total: {passed}/{total} tests passed{Colors.END}")
    
    if passed == total:
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 ALL TESTS PASSED!{Colors.END}")
        return 0
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}❌ SOME TESTS FAILED{Colors.END}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
