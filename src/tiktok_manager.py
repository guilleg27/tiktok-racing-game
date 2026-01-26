"""TikTok Live Manager - Producer that captures stream events."""

import asyncio
import logging
from typing import Optional

from TikTokLive import TikTokLiveClient
from TikTokLive.events import (
    ConnectEvent, 
    DisconnectEvent, 
    GiftEvent,
    CommentEvent,
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
        import time
        
        # Método 1: Atributos directos del event.user (más seguro)
        try:
            if hasattr(event, 'user') and event.user:
                user = event.user
                
                # Intentar acceder a cada atributo de forma segura
                safe_attrs = [
                    'unique_id',
                    'uniqueId',
                    'nickname',
                    'display_name',
                    'displayName',
                    'username',
                    'userName',
                    'id',
                    'displayId',
                    'display_id',
                ]
                for attr in safe_attrs:
                    try:
                        if hasattr(user, attr):
                            val = getattr(user, attr, None)
                            if val and str(val).strip():
                                return str(val).strip()
                    except Exception:
                        continue  # Continuar con el siguiente atributo si este falla
                
                # Fallback: intentar str(user) si es legible
                try:
                    raw = str(user).strip()
                    if raw and raw != repr(user):
                        return raw
                except Exception:
                    pass
        except Exception:
            pass  # Continuar con otros métodos
        
        # Método 2: Proto buffer (acceso más seguro)
        try:
            if hasattr(event, '_proto') and event._proto:
                proto = event._proto
                if hasattr(proto, 'user') and proto.user:
                    user = proto.user
                    
                    # Probar múltiples nombres de atributos de forma segura
                    safe_attrs = [
                        'uniqueId',
                        'unique_id',
                        'nickname',
                        'nick_name',
                        'displayName',
                        'display_name',
                        'username',
                        'userName',
                        'id',
                        'displayId',
                        'display_id',
                    ]
                    for attr in safe_attrs:
                        try:
                            if hasattr(user, attr):
                                val = getattr(user, attr, None)
                                if val and str(val).strip():
                                    return str(val).strip()
                        except Exception:
                            continue  # Continuar con el siguiente atributo si este falla
                    
                    # Fallback adicional con str(user)
                    try:
                        raw = str(user).strip()
                        if raw and raw != repr(user):
                            return raw
                    except Exception:
                        pass
        except Exception:
            pass  # Continuar con fallback
        
        # Método 3: Intentar acceder directamente a atributos del evento
        try:
            # Algunos eventos tienen el username directamente
            if hasattr(event, 'username'):
                val = getattr(event, 'username', None)
                if val and str(val).strip():
                    return str(val).strip()
        except Exception:
            pass
        
        # Método 4: Fallback con ID único temporal (solo si todo falla)
        fallback_name = f"Usuario{int(time.time() * 1000) % 10000}"
        logger.warning(f"⚠️ Could not extract username from event, using fallback: {fallback_name}")
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
                ))
                logger.info(f"🎁 {username} envió {count}x {gift_name} ({diamond_count}💎)")
                    
            except Exception as e:
                logger.error(f"Error processing gift: {e}")
        
        @client.on(CommentEvent)
        async def on_comment(event: CommentEvent) -> None:
            """Handle chat comments for keyword binding and votes."""
            logger.info("📨 CommentEvent received!")
            try:
                from .config import GAME_MODE, COUNTRY_SHORTCUTS
                
                logger.info(f"   GAME_MODE: {GAME_MODE}")
                username = self._extract_username(event)
                logger.info(f"   Username extracted: {username}")
                
                # Debug: log event attributes
                logger.info(f"   Event attributes: {[attr for attr in dir(event) if not attr.startswith('_')]}")
                
                # Get message content - try all possible methods
                message = ""
                if hasattr(event, 'comment') and event.comment:
                    message = str(event.comment)
                elif hasattr(event, '_proto') and event._proto:
                    proto_comment = getattr(event._proto, 'content', None)
                    if proto_comment:
                        message = str(proto_comment)
                elif hasattr(event, 'text'):
                    message = str(event.text)
                
                if not message:
                    logger.debug(f"Empty message from {username}")
                    return
                
                # Clean message for keyword matching - simple strip
                clean_message = message.strip()
                
                # TEMPORARY: Log all comments that look like votes for debugging
                if clean_message.isdigit() or (len(clean_message) <= 4 and clean_message.isalpha()):
                    logger.info(f"🔍 Potential vote from {username}: '{message}' -> cleaned: '{clean_message}'")
                
                # COMMENT MODE: Check for country shortcuts (siglas/números)
                if GAME_MODE == "COMMENT":
                    # Check exact match (case-insensitive for text, exact for numbers)
                    for shortcut, country in COUNTRY_SHORTCUTS.items():
                        # For numbers, compare directly (exact match)
                        if shortcut.isdigit():
                            if shortcut == clean_message:
                                await self.queue.put(GameEvent(
                                    type=EventType.VOTE,
                                    username=username,
                                    content=country,
                                    extra={
                                        "shortcut": shortcut,
                                        "original_message": message,
                                    },
                                ))
                                logger.info(f"🗳️ {username} voted for {country} ({shortcut})")
                                return
                        else:
                            # For text, compare case-insensitive
                            if shortcut.lower() == clean_message.lower():
                                await self.queue.put(GameEvent(
                                    type=EventType.VOTE,
                                    username=username,
                                    content=country,
                                    extra={
                                        "shortcut": shortcut,
                                        "original_message": message,
                                    },
                                ))
                                logger.info(f"🗳️ {username} voted for {country} ({shortcut})")
                                return
                    
                    # If we get here and it looked like a vote, log why it didn't match
                    if clean_message.isdigit() or (len(clean_message) <= 4 and clean_message.isalpha()):
                        logger.warning(f"⚠️ '{clean_message}' from {username} didn't match any shortcut. Available: {list(COUNTRY_SHORTCUTS.keys())[:15]}...")
                
                # GIFT MODE: Check for country keywords (for JOIN)
                if GAME_MODE == "GIFT":
                    from .config import COUNTRY_KEYWORDS
                    for keyword, country in COUNTRY_KEYWORDS.items():
                        if keyword in clean_message:
                            # Send JOIN event
                            await self.queue.put(GameEvent(
                                type=EventType.JOIN,
                                username=username,
                                content=country,
                                extra={"keyword": keyword, "original_message": message}
                            ))
                            logger.info(f"🏁 {username} wants to join {country} (keyword: {keyword})")
                            break  # Solo el primer match
                        
                # Also send regular COMMENT event for chat display
                await self.queue.put(GameEvent(
                    type=EventType.COMMENT,
                    username=username,
                    content=message
                ))
                
            except Exception as e:
                logger.error(f"❌ Error processing comment: {e}", exc_info=True)
    
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