"""TikTok Live Manager - Producer that captures stream events."""

import asyncio
import logging
import time
from typing import Optional

from TikTokLive import TikTokLiveClient
from TikTokLive.events import (
    ConnectEvent,
    DisconnectEvent,
    GiftEvent,
    CommentEvent,
    LikeEvent,
    JoinEvent,
    FollowEvent,
)

from .config import MAX_RETRIES, BASE_DELAY, MAX_DELAY, GIFT_DIAMOND_VALUES
from .events import EventType, ConnectionState, GameEvent

logger = logging.getLogger(__name__)


class TikTokManager:
    """Producer class that connects to TikTok Live stream and captures events."""
    
    def __init__(self, queue: asyncio.Queue, unique_id: str):
        self.queue = queue
        self.unique_id = unique_id.lstrip("@")
        self.client: Optional[TikTokLiveClient] = None
        self._running = False
        self._reconnect_task: Optional[asyncio.Task] = None
        self._connection_state = ConnectionState.DISCONNECTED
        
    def _create_client(self) -> TikTokLiveClient:
        """Create a new TikTok client instance."""
        client = TikTokLiveClient(unique_id=self.unique_id)
        self._setup_handlers(client)
        return client
    
    def _extract_username(self, event) -> str:
        """Extract username from event using TikTokLive 6.6.5 proto field names."""
        import time

        # TikTokLive 6.6.5 User proto fields:
        #   nick_name  (field 3)  — display name, almost always populated
        #   username   (field 38) — TikTok @handle, sometimes omitted
        # ExtendedUser adds properties: nickname (→ nick_name), unique_id (→ username)
        # NOTE: 'id' (field 1) is the numeric user ID (int64) — NOT a display name, excluded.

        # String-only attrs to try on any User/ExtendedUser object (ordered by reliability)
        _STRING_ATTRS = ('nick_name', 'username', 'nickname', 'unique_id', 'display_id')

        def _try_user_obj(user) -> str:
            """Return first non-empty string attr from a user object, or ''."""
            for attr in _STRING_ATTRS:
                try:
                    if not hasattr(user, attr):
                        continue
                    val = getattr(user, attr, None)
                    # Only accept actual strings (exclude int fields like 'id')
                    if val and isinstance(val, str) and val.strip():
                        return val.strip()
                except Exception:
                    continue
            return ''

        # Method 1: event.user (ExtendedUser — works for CommentEvent and GiftEvent)
        try:
            if hasattr(event, 'user') and event.user:
                result = _try_user_obj(event.user)
                if result:
                    return result
        except Exception:
            pass

        # Method 2: event.user_info (CommentEvent direct field — User proto)
        try:
            if hasattr(event, 'user_info') and event.user_info:
                result = _try_user_obj(event.user_info)
                if result:
                    return result
        except Exception:
            pass

        # Method 3: event.from_user (GiftEvent direct field — ExtendedUser)
        try:
            if hasattr(event, 'from_user') and event.from_user:
                result = _try_user_obj(event.from_user)
                if result:
                    return result
        except Exception:
            pass

        # Fallback: timestamp-based name (only when all proto fields are empty)
        fallback_name = f"Usuario{int(time.time() * 1000) % 10000}"
        logger.debug(f"⚠️ Could not extract username from event, using fallback: {fallback_name}")
        return fallback_name
    
    def _extract_diamond_count(self, event, gift_name: str) -> int:
        """Extract diamond count from event or use default mapping."""
        try:
            # Try to get from proto
            if hasattr(event, '_proto') and event._proto:
                proto = event._proto
                gift_proto = getattr(proto, 'gift', None)
                if gift_proto:
                    # Try different attribute names
                    for attr in ['diamond_count', 'diamondCount', 'diamonds']:
                        val = getattr(gift_proto, attr, None)
                        if val and val > 0:
                            return int(val)
            
            # Try direct access
            if hasattr(event, 'gift') and event.gift:
                try:
                    if hasattr(event.gift, 'diamond_count'):
                        return int(event.gift.diamond_count)
                except:
                    pass
        except Exception as e:
            logger.debug(f"Error extracting diamond count: {e}")
        
        # Fallback to config mapping
        return GIFT_DIAMOND_VALUES.get(gift_name, 1)
    
    def _setup_handlers(self, client: TikTokLiveClient) -> None:
        """Set up event handlers for the TikTok client."""
        logger.info("🔧 Setting up TikTok event handlers...")
        
        @client.on(ConnectEvent)
        async def on_connect(event: ConnectEvent) -> None:
            self._connection_state = ConnectionState.CONNECTED
            logger.info(f"Connected to @{self.unique_id}'s stream")
            await self._push_status(
                ConnectionState.CONNECTED,
                f"Conectado al stream de @{self.unique_id}"
            )
        
        @client.on(DisconnectEvent)
        async def on_disconnect(event: DisconnectEvent) -> None:
            if self._connection_state == ConnectionState.CONNECTED:
                logger.warning("Disconnected from stream")
                await self._push_status(
                    ConnectionState.DISCONNECTED,
                    "Desconectado del stream"
                )
            if self._running:
                self._start_reconnect()
        
        @client.on(GiftEvent)
        async def on_gift(event: GiftEvent) -> None:
            """Handle incoming gifts."""
            try:
                # Check if still streaking
                streaking = False
                streakable = False
                
                try:
                    streaking = getattr(event, 'streaking', False)
                    if hasattr(event, 'gift') and event.gift:
                        streakable = getattr(event.gift, 'streakable', False)
                except:
                    pass
                
                if hasattr(event, '_proto') and event._proto:
                    proto = event._proto
                    gift_proto = getattr(proto, 'gift', None)
                    if gift_proto:
                        gift_type = getattr(gift_proto, 'type', 0)
                        is_repeating = getattr(proto, 'repeatCount', 1) > 1
                        repeat_end = getattr(proto, 'repeatEnd', 0)
                        
                        if gift_type == 1 and is_repeating and repeat_end != 1:
                            return
                
                if streakable and streaking:
                    return
                
                # Extract data
                username = self._extract_username(event)
                
                # Get gift name
                gift_name = "Regalo"
                if hasattr(event, '_proto') and event._proto:
                    gift_proto = getattr(event._proto, 'gift', None)
                    if gift_proto:
                        gift_name = getattr(gift_proto, 'name', None) or "Regalo"
                elif hasattr(event, 'gift') and event.gift:
                    try:
                        gift_name = event.gift.name
                    except:
                        pass
                
                # Get count
                count = 1
                if hasattr(event, '_proto') and event._proto:
                    count = getattr(event._proto, 'repeatCount', 1) or 1
                elif hasattr(event, 'repeat_count'):
                    try:
                        count = event.repeat_count or 1
                    except:
                        pass
                
                # Get diamond count
                diamond_count = self._extract_diamond_count(event, gift_name)
                
                await self.queue.put(GameEvent(
                    type=EventType.GIFT,
                    username=username,
                    content=str(gift_name),
                    extra={
                        "count": int(count),
                        "diamond_count": diamond_count,
                    },
                    created_at_sec=time.perf_counter(),
                ))
            except Exception as e:
                logger.error(f"Error processing gift: {e}")

        @client.on(LikeEvent)
        async def on_like(event: LikeEvent) -> None:
            """Handle stream likes (retention bar / Meteor Shower goal). One event = likes received."""
            try:
                # Each LikeEvent typically means one or more likes; extract count if available
                count = 1
                if hasattr(event, "count") and event.count is not None:
                    count = max(1, int(event.count))
                elif hasattr(event, "_proto") and event._proto:
                    count = getattr(event._proto, "count", None) or getattr(
                        event._proto, "likeCount", 1
                    )
                    count = max(1, int(count))
                await self.queue.put(GameEvent(
                    type=EventType.LIKE,
                    username="",
                    content="",
                    extra={"count": count},
                    created_at_sec=time.perf_counter(),
                ))
            except Exception as e:
                logger.error(f"Error processing like: {e}")

        @client.on(JoinEvent)
        async def on_join(event: JoinEvent) -> None:
            """Handle viewer entering the livestream (Visual Welcome retention mechanic)."""
            try:
                username = self._extract_username(event)
                await self.queue.put(GameEvent(
                    type=EventType.JOIN,
                    username=username,
                    content="",
                    extra={"room_join": True},
                    created_at_sec=time.perf_counter(),
                ))
            except Exception as e:
                logger.error(f"Error processing join: {e}")

        @client.on(FollowEvent)
        async def on_follow(event: FollowEvent) -> None:
            """Handle new follower: queue banner and hype event."""
            try:
                username = (
                    getattr(event.user, "unique_id", None)
                    or getattr(event.user, "nickname", None)
                    or "someone"
                ) if hasattr(event, "user") and event.user else "someone"
                follow_game_event = GameEvent(
                    type=EventType.FOLLOW,
                    username=username,
                )
                try:
                    self.queue.put_nowait(follow_game_event)
                except asyncio.QueueFull:
                    logger.warning("Queue full, dropping follow event")
            except Exception as e:
                logger.error(f"Error processing follow: {e}")

        @client.on(CommentEvent)
        async def on_comment(event: CommentEvent) -> None:
            """Handle chat comments: minimal work, push to queue only (no heavy logs)."""
            try:
                from .config import GAME_MODE, COUNTRY_SHORTCUTS

                username = self._extract_username(event)
                message = ""
                if hasattr(event, "comment") and event.comment:
                    message = str(event.comment)
                elif hasattr(event, "_proto") and event._proto:
                    proto_comment = getattr(event._proto, "content", None)
                    if proto_comment:
                        message = str(proto_comment)
                elif hasattr(event, "text"):
                    message = str(event.text)

                if not message:
                    return

                created = time.perf_counter()
                clean_message = message.strip()

                if GAME_MODE == "COMMENT":
                    for shortcut, country in COUNTRY_SHORTCUTS.items():
                        if shortcut.isdigit():
                            if shortcut == clean_message:
                                await self.queue.put(GameEvent(
                                    type=EventType.VOTE,
                                    username=username,
                                    content=country,
                                    extra={"shortcut": shortcut, "original_message": message},
                                    created_at_sec=created,
                                ))
                                return
                        else:
                            if shortcut.lower() == clean_message.lower():
                                await self.queue.put(GameEvent(
                                    type=EventType.VOTE,
                                    username=username,
                                    content=country,
                                    extra={"shortcut": shortcut, "original_message": message},
                                    created_at_sec=created,
                                ))
                                return

                if GAME_MODE == "GIFT":
                    from .config import COUNTRY_KEYWORDS
                    for keyword, country in COUNTRY_KEYWORDS.items():
                        if keyword in clean_message:
                            await self.queue.put(GameEvent(
                                type=EventType.JOIN,
                                username=username,
                                content=country,
                                extra={"keyword": keyword, "original_message": message},
                                created_at_sec=created,
                            ))
                            break

                await self.queue.put(GameEvent(
                    type=EventType.COMMENT,
                    username=username,
                    content=message,
                    created_at_sec=created,
                ))
            except Exception as e:
                logger.error(f"Error processing comment: {e}", exc_info=True)
    
    async def _push_status(self, state: ConnectionState, message: str) -> None:
        self._connection_state = state
        await self.queue.put(GameEvent(
            type=EventType.CONNECTION_STATUS,
            content=message,
            extra={"state": state},
            created_at_sec=time.perf_counter(),
        ))
    
    def _start_reconnect(self) -> None:
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(self._reconnect_loop())
    
    async def _reconnect_loop(self) -> None:
        attempt = 0
        while self._running and attempt < MAX_RETRIES:
            attempt += 1
            delay = min(BASE_DELAY * (2 ** (attempt - 1)), MAX_DELAY)
            await self._push_status(
                ConnectionState.RECONNECTING,
                f"Reconectando... intento {attempt}/{MAX_RETRIES}"
            )
            logger.info(f"Reconnection attempt {attempt}/{MAX_RETRIES} in {delay}s")
            await asyncio.sleep(delay)
            
            if not self._running:
                break
            
            try:
                self.client = self._create_client()
                await self.client.start()
                logger.info("Reconnection successful")
                return
            except Exception as e:
                logger.error(f"Reconnection attempt {attempt} failed: {e}")
                if self.client:
                    try:
                        await self.client.disconnect()
                    except Exception:
                        pass
        
        if self._running:
            await self._push_status(
                ConnectionState.FAILED,
                "No se pudo reconectar"
            )
            await self.queue.put(GameEvent(type=EventType.QUIT, created_at_sec=time.perf_counter()))
    
    async def start(self) -> None:
        self._running = True
        self.client = self._create_client()
        
        from .config import INITIAL_CONNECT_TIMEOUT
        
        try:
            await self._push_status(
                ConnectionState.RECONNECTING,
                f"Conectando a @{self.unique_id}... (hasta {INITIAL_CONNECT_TIMEOUT}s)"
            )
            
            # Timeout más largo para conexión inicial
            try:
                await asyncio.wait_for(self.client.start(), timeout=INITIAL_CONNECT_TIMEOUT)
                logger.info(f"✅ Conexión inicial exitosa a @{self.unique_id}")
            except asyncio.TimeoutError:
                logger.warning(f"⏱️ Timeout de conexión inicial ({INITIAL_CONNECT_TIMEOUT}s). Iniciando reconexión...")
                raise ConnectionError("Initial connection timeout")
                
        except Exception as e:
            logger.error(f"Initial connection failed: {e}")
            await self._push_status(
                ConnectionState.DISCONNECTED,
                f"Error de conexión inicial. Reintentando..."
            )
            self._start_reconnect()
    
    async def stop(self) -> None:
        self._running = False
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        
        if self.client and self.client.connected:
            try:
                await self.client.disconnect()
                logger.info("TikTok client disconnected cleanly")
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")
    
    @property
    def connected(self) -> bool:
        return self._connection_state == ConnectionState.CONNECTED
    
    @property
    def connection_state(self) -> ConnectionState:
        return self._connection_state