"""TikTok Live Manager - Producer that captures stream events."""

import asyncio
import logging
from typing import Optional

from TikTokLive import TikTokLiveClient
from TikTokLive.events import (
    ConnectEvent, 
    DisconnectEvent, 
    GiftEvent,
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
        """Extract username from event using multiple fallback methods."""
        try:
            if hasattr(event, '_proto') and event._proto:
                proto = event._proto
                if hasattr(proto, 'user') and proto.user:
                    user = proto.user
                    for attr in ['nickname', 'nickName', 'nick_name', 'uniqueId', 'unique_id']:
                        if hasattr(user, attr):
                            val = getattr(user, attr)
                            if val:
                                return str(val)
            
            if hasattr(event, 'user'):
                user = event.user
                if hasattr(user, 'unique_id') and user.unique_id:
                    return str(user.unique_id)
                if hasattr(user, 'nickname') and user.nickname:
                    return str(user.nickname)
        except Exception as e:
            logger.debug(f"Error extracting username: {e}")
        
        return "Usuario"
    
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
                ))
                logger.info(f"🎁 {username} envió {count}x {gift_name} ({diamond_count}💎)")
                    
            except Exception as e:
                logger.error(f"Error processing gift: {e}")
    
    async def _push_status(self, state: ConnectionState, message: str) -> None:
        self._connection_state = state
        await self.queue.put(GameEvent(
            type=EventType.CONNECTION_STATUS,
            content=message,
            extra={"state": state},
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
            await self.queue.put(GameEvent(type=EventType.QUIT))
    
    async def start(self) -> None:
        self._running = True
        self.client = self._create_client()
        
        try:
            await self._push_status(
                ConnectionState.RECONNECTING,
                f"Conectando a @{self.unique_id}..."
            )
            await self.client.start()
        except Exception as e:
            logger.error(f"Initial connection failed: {e}")
            await self._push_status(
                ConnectionState.DISCONNECTED,
                f"Error de conexión: {e}"
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