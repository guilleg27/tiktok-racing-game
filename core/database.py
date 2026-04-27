"""Async SQLite database for event persistence."""

import aiosqlite
import logging
from datetime import datetime
from typing import Optional

from .config import DATABASE_PATH

logger = logging.getLogger(__name__)


class Database:
    """Async SQLite database manager for storing TikTok events."""
    
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None
    
    async def connect(self) -> None:
        """Initialize the database connection and create tables."""
        try:
            self._connection = await aiosqlite.connect(self.db_path)
            await self._create_tables()
            logger.info(f"Database connected: {self.db_path}")
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    async def _create_tables(self) -> None:
        """Create the required database tables."""
        await self._connection.execute("""
            CREATE TABLE IF NOT EXISTS gift_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                gift_name TEXT NOT NULL,
                diamond_count INTEGER DEFAULT 1,
                gift_count INTEGER DEFAULT 1,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                streamer TEXT
            )
        """)
        
        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_gift_logs_username ON gift_logs(username)
        """)
        
        await self._connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_gift_logs_timestamp ON gift_logs(timestamp)
        """)
        
        await self._connection.commit()
        logger.info("Database tables initialized")
    
    async def save_event_to_db(
        self, 
        user: str, 
        gift_name: str, 
        diamond_count: int,
        gift_count: int = 1,
        streamer: str = ""
    ) -> int:
        """
        Save a gift event to the database.
        
        Args:
            user: Username who sent the gift
            gift_name: Name of the gift
            diamond_count: Value of the gift in diamonds
            gift_count: Number of gifts sent
            streamer: Streamer username
            
        Returns:
            The ID of the inserted record
        """
        try:
            cursor = await self._connection.execute(
                """
                INSERT INTO gift_logs (username, gift_name, diamond_count, gift_count, timestamp, streamer)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user, gift_name, diamond_count, gift_count, datetime.now(), streamer)
            )
            await self._connection.commit()
            logger.debug(f"DB: {user} sent {gift_count}x {gift_name} ({diamond_count} diamonds)")
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to save gift to database: {e}")
            return -1
    
    async def get_top_gifters(self, limit: int = 10) -> list[tuple]:
        """Get top gifters by total diamond value."""
        cursor = await self._connection.execute(
            """
            SELECT username, SUM(diamond_count * gift_count) as total_diamonds
            FROM gift_logs
            GROUP BY username
            ORDER BY total_diamonds DESC
            LIMIT ?
            """,
            (limit,)
        )
        return await cursor.fetchall()
    
    async def get_session_stats(self, streamer: str) -> dict:
        """Get statistics for current session."""
        cursor = await self._connection.execute(
            """
            SELECT 
                COUNT(*) as total_gifts,
                SUM(diamond_count * gift_count) as total_diamonds,
                COUNT(DISTINCT username) as unique_gifters
            FROM gift_logs
            WHERE streamer = ?
            """,
            (streamer,)
        )
        row = await cursor.fetchone()
        return {
            "total_gifts": row[0] or 0,
            "total_diamonds": row[1] or 0,
            "unique_gifters": row[2] or 0
        }
    
    async def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            logger.info("Database connection closed")