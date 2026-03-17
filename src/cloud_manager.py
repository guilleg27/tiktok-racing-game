"""
Cloud Manager - Supabase integration for global persistence.

This module handles asynchronous synchronization with Supabase without blocking
the main game loop. Follows the project's rules for non-blocking operations.
"""

import os
import sys
import logging
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime

# Import Supabase client (optional dependency)
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    create_client = None  # type: ignore[assignment]
    Client = None  # type: ignore[assignment]

# Import dotenv separately so we can still load .env
# even if Supabase library is missing.
try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - defensive fallback
    def load_dotenv(*args: Any, **kwargs: Any) -> None:
        """Fallback no-op load_dotenv when python-dotenv is not installed."""
        return

logger = logging.getLogger(__name__)


class CloudManager:
    """
    Singleton class for managing Supabase cloud persistence.
    
    Features:
    - Non-blocking async operations
    - Graceful error handling (fails silently in UI)
    - Thread-safe singleton pattern
    - Local-first architecture (SQLite remains primary)
    """
    
    _instance: Optional['CloudManager'] = None
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CloudManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """
        Initialize CloudManager singleton.
        Only initializes once, subsequent calls are no-ops.
        """
        if CloudManager._initialized:
            return
        
        self.client: Optional[Client] = None
        self.enabled = False
        
        # Load environment variables with an explicit path so it works regardless
        # of the current working directory (important on Windows).
        # - Frozen exe: .env sits next to the .exe
        # - Development: .env is at the project root (two levels up from src/)
        if getattr(sys, 'frozen', False):
            _env_path = os.path.join(os.path.dirname(sys.executable), '.env')
        else:
            _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
        load_dotenv(_env_path)

        # Initialize Supabase client
        self._initialize_client()
        
        CloudManager._initialized = True
    
    def _initialize_client(self) -> None:
        """
        Initialize Supabase client from environment variables.
        
        Raises:
            No exceptions - logs errors and sets enabled=False on failure
        """
        if not SUPABASE_AVAILABLE:
            logger.warning("⚠️ Supabase library not installed. Cloud sync disabled.")
            return
        
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        
        if not supabase_url or not supabase_key:
            logger.warning(
                "⚠️ SUPABASE_URL or SUPABASE_KEY not found in .env. "
                "Cloud sync disabled. Game will continue with local persistence only."
            )
            return
        
        try:
            self.client = create_client(supabase_url, supabase_key)
            self.enabled = True
            logger.info("✅ CloudManager initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Supabase client: {e}")
            self.enabled = False
    
    async def sync_race_result(
        self,
        country: str,
        winner_name: str,
        total_diamonds: int,
        streamer_name: str = ""
    ) -> bool:
        """
        Synchronize race result to Supabase (non-blocking).
        
        This function performs two operations:
        1. Upsert to global_country_stats (increment wins)
        2. Insert to global_hall_of_fame (record captain achievement)
        
        Args:
            country: Winning country name
            winner_name: Captain/MVP username
            total_diamonds: Total diamonds earned by winner
            streamer_name: Streamer's TikTok username
            
        Returns:
            bool: True if sync succeeded, False if failed (logged but silent)
        """
        if not self.enabled:
            logger.debug("Cloud sync disabled, skipping sync_race_result")
            return False
        
        try:
            # Run sync in executor to avoid blocking event loop
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                self._sync_race_result_blocking,
                country,
                winner_name,
                total_diamonds,
                streamer_name
            )
            return result
        except Exception as e:
            logger.error(f"❌ Cloud sync failed: {e}")
            return False
    
    def _sync_race_result_blocking(
        self,
        country: str,
        winner_name: str,
        total_diamonds: int,
        streamer_name: str
    ) -> bool:
        """
        Blocking version of sync_race_result (runs in thread executor).
        
        Args:
            Same as sync_race_result
            
        Returns:
            bool: Success status
            
        Raises:
            No exceptions - catches all and logs
        """
        try:
            # 1. Upsert country stats (increment wins)
            response = self.client.table("global_country_stats").select("*").eq("country", country).execute()
            
            if response.data and len(response.data) > 0:
                # Country exists, increment wins
                current_wins = response.data[0].get("total_wins", 0)
                current_diamonds = response.data[0].get("total_diamonds", 0)
                
                self.client.table("global_country_stats").update({
                    "total_wins": current_wins + 1,
                    "total_diamonds": current_diamonds + total_diamonds,
                    "last_updated": datetime.now().isoformat()
                }).eq("country", country).execute()
            else:
                # Country doesn't exist, insert
                self.client.table("global_country_stats").insert({
                    "country": country,
                    "total_wins": 1,
                    "total_diamonds": total_diamonds,
                    "last_updated": datetime.now().isoformat()
                }).execute()
            
            # 2. Insert hall of fame record
            self.client.table("global_hall_of_fame").insert({
                "country": country,
                "captain_name": winner_name,
                "total_diamonds": total_diamonds,
                "race_timestamp": datetime.now().isoformat(),
                "streamer_name": streamer_name
            }).execute()
            
            logger.info(f"☁️ Synced to cloud: {country} ({winner_name}, {total_diamonds}💎)")
            return True
            
        except Exception as e:
            logger.error(f"❌ Supabase sync error: {e}")
            return False
    
    async def get_global_leaderboard(self, limit: int = 10) -> list[Dict[str, Any]]:
        """
        Fetch global hall of fame (top captains).
        
        Args:
            limit: Maximum number of records to fetch
            
        Returns:
            List of captain records sorted by diamonds DESC
        """
        if not self.enabled:
            return []
        
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                self._get_global_leaderboard_blocking,
                limit
            )
            return result
        except Exception as e:
            logger.error(f"❌ Failed to fetch global leaderboard: {e}")
            return []
    
    def _get_global_leaderboard_blocking(self, limit: int) -> list[Dict[str, Any]]:
        """Blocking version of get_global_leaderboard."""
        try:
            response = self.client.table("global_hall_of_fame") \
                .select("*") \
                .order("total_diamonds", desc=True) \
                .limit(limit) \
                .execute()
            
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"❌ Supabase query error: {e}")
            return []
    
    async def get_global_ranking(self, limit: int = 3) -> list[Dict[str, Any]]:
        """
        Fetch global ranking of countries by total wins.
        
        Args:
            limit: Maximum number of countries to fetch (default: 3 for Top 3)
            
        Returns:
            List of country records sorted by wins DESC
            Format: [{'country': 'Argentina', 'total_wins': 45, 'total_diamonds': 15000}, ...]
        """
        if not self.enabled:
            return []
        
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                self._get_global_ranking_blocking,
                limit
            )
            return result
        except Exception as e:
            logger.error(f"❌ Failed to fetch global ranking: {e}")
            return []
    
    def _get_global_ranking_blocking(self, limit: int) -> list[Dict[str, Any]]:
        """Blocking version of get_global_ranking."""
        try:
            response = self.client.table("global_country_stats") \
                .select("country, total_wins, total_diamonds, last_updated") \
                .order("total_wins", desc=True) \
                .order("total_diamonds", desc=True) \
                .limit(limit) \
                .execute()
            
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"❌ Supabase query error: {e}")
            return []
    
    async def get_daily_ranking(self, limit: int = 5) -> list[Dict[str, Any]]:
        """
        Fetch today's ranking by aggregating global_hall_of_fame records.

        Filters races where race_timestamp >= today 00:00:00 UTC, then
        groups by country in Python (no GROUP BY support in Supabase client).

        Args:
            limit: Maximum number of countries to return

        Returns:
            List sorted by wins DESC: [{'country': ..., 'wins': ..., 'total_diamonds': ...}, ...]
        """
        if not self.enabled:
            return []

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                self._get_daily_ranking_blocking,
                limit
            )
            return result
        except Exception as e:
            logger.error(f"❌ Failed to fetch daily ranking: {e}")
            return []

    def _get_daily_ranking_blocking(self, limit: int) -> list[Dict[str, Any]]:
        """Blocking version of get_daily_ranking."""
        try:
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            response = self.client.table("global_hall_of_fame") \
                .select("country, total_diamonds") \
                .gte("race_timestamp", today_start) \
                .execute()

            if not response.data:
                return []

            # Aggregate in Python
            aggregated: Dict[str, Dict[str, Any]] = {}
            for row in response.data:
                country = row.get("country", "Unknown")
                diamonds = row.get("total_diamonds", 0)
                if country not in aggregated:
                    aggregated[country] = {"country": country, "wins": 0, "total_diamonds": 0}
                aggregated[country]["wins"] += 1
                aggregated[country]["total_diamonds"] += diamonds

            sorted_list = sorted(
                aggregated.values(),
                key=lambda x: (x["wins"], x["total_diamonds"]),
                reverse=True
            )
            return sorted_list[:limit]

        except Exception as e:
            logger.error(f"❌ Supabase daily ranking error: {e}")
            return []

    async def get_country_stats(self, country: str) -> Optional[Dict[str, Any]]:
        """
        Fetch global stats for a specific country.
        
        Args:
            country: Country name
            
        Returns:
            Dict with total_wins and total_diamonds, or None if not found
        """
        if not self.enabled:
            return None
        
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                self._get_country_stats_blocking,
                country
            )
            return result
        except Exception as e:
            logger.error(f"❌ Failed to fetch country stats: {e}")
            return None
    
    def _get_country_stats_blocking(self, country: str) -> Optional[Dict[str, Any]]:
        """Blocking version of get_country_stats."""
        try:
            response = self.client.table("global_country_stats") \
                .select("*") \
                .eq("country", country) \
                .execute()

            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"❌ Supabase query error: {e}")
            return None

    def update_telemetry(self, payload: dict) -> bool:
        """Push a telemetry snapshot to Supabase (synchronous, background-thread safe).

        Args:
            payload: Metrics dict with a ``session_id`` key.

        Returns:
            bool: True if the upsert succeeded, False otherwise.
        """
        if not self.enabled:
            return False
        return self._update_telemetry_blocking(payload)

    def _update_telemetry_blocking(self, payload: dict) -> bool:
        """Blocking upsert to the ``live_telemetry`` table."""
        if "last_update" not in payload:
            from datetime import datetime, timezone
            payload = {**payload, "last_update": datetime.now(timezone.utc).isoformat()}
        try:
            self.client.table("live_telemetry").upsert(
                payload, on_conflict="session_id"
            ).execute()
            logger.debug(
                "Telemetry pushed: session=%s fps=%.1f",
                payload.get("session_id", "?"),
                payload.get("fps", 0.0),
            )
            return True
        except Exception as e:
            logger.error(
                "Telemetry push error (possible schema mismatch — check live_telemetry columns): %s",
                e,
            )
            return False