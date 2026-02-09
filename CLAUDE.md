# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TikTok Live Interactive Racing Bot - A real-time racing game that connects to TikTok Live streams and translates viewer engagement (gifts or chat votes) into competitive racing visualizations. Built with Python 3.12, Pygame, Pymunk physics, SQLite, and optional Supabase cloud sync.

## Common Commands

### Development

```bash
# Setup virtual environment
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# or: venv\Scripts\activate  # Windows
pip install -r requirements.txt

# Run in development mode (IDLE - starts disconnected)
python main.py --idle

# Run connected to TikTok Live
python main.py @username

# Run specific test scripts
python check_policies.py              # Verify Supabase RLS policies
python test_multiple_races.py         # Test consecutive race syncs
python test_audio.py                  # Test audio system
python test_resources.py              # Test resource loading

# Run unit tests
python -m pytest test_cloud_manager.py -v
python -m unittest test_cloud_manager.py

# Run E2E test
python test_e2e_cloud_sync.py

# Syntax validation
python -m py_compile main.py src/*.py
```

### Build & Package

```bash
# Build executable (macOS/Windows)
python build_app.py

# Output locations:
# - macOS: dist/TikTokLiveBot.app
# - Windows: dist/TikTokLiveBot/TikTokLiveBot.exe

# Run packaged app
open dist/TikTokLiveBot.app  # macOS
# or: dist\TikTokLiveBot\TikTokLiveBot.exe  # Windows
```

### Testing Shortcuts (IDLE Mode)

| Key | Action |
|-----|--------|
| T | Small random gift |
| Y | Large random gift |
| 1/2/3 | Vote country 1/2/3 (COMMENT mode) or Rosa/Pesa/Helado (GIFT mode) |
| J | User joins team |
| W | Simulate room join (Visual Welcome) |
| F | Trigger ON FIRE combo |
| G | Activate Final Stretch |
| V | Victory sequence |
| C/R | Reset race to IDLE |
| L | Connect to TikTok |
| ESC | Exit |

## Architecture

### High-Level Components

```
TikTok Live Stream (WebSocket)
       ↓
[TikTokManager] → asyncio.Queue → [GameEngine]
   (Producer)      (Event Bus)      (Consumer)
                                        ↓
                              ┌─────────┴──────────┐
                              ↓                    ↓
                        [PhysicsWorld]       [Renderer]
                        (Pymunk)             (Pygame)
                              ↓                    ↓
                        [Database]          [AudioManager]
                        (SQLite)            [ParticleSystem]
                              ↓
                        [CloudManager]
                        (Supabase - Optional)
```

### Core Modules (src/)

**tiktok_manager.py** - Producer
- WebSocket connection to TikTok Live using TikTokLive library
- Exponential backoff reconnection (up to 15 retries, max 120s delay)
- Normalizes TikTok events into `GameEvent` objects
- Pushes events to async queue (non-blocking)
- Handles both GIFT mode (real money gifts) and COMMENT mode (free chat votes)

**game_engine.py** - Consumer & Orchestrator (~5000 lines)
- Consumes events from queue and routes them to subsystems
- Manages game state machine: IDLE → RACING → VICTORY
- 60 FPS rendering pipeline with double buffering
- Particle system (explosions, trails, confetti)
- Combat system (Rosa: +5m advance, Pesa: -10m setback, Helado: 3s freeze)
- Combo tracking (5+ rapid gifts = "COMBO!", 10+ = "ON FIRE" with neon trails)
- Performance monitoring (FPS, memory, auto particle cleanup)
- All I/O operations use asyncio.create_task() to prevent rendering blocks

**physics_world.py** - Racing Simulation
- Horizontal racing (12 lanes for 12 countries, no gravity)
- Pymunk physics with groove joints (constrains flags to X-axis only)
- Target-based Lerp movement instead of impulse forces (smooth animation)
- Freeze system for combat effects
- Winner detection when flag crosses RACE_FINISH_X

**database.py** - Local Persistence
- Async SQLite using aiosqlite (non-blocking)
- Logs all gift/vote events with username, diamond count, timestamp
- Indexed queries for top gifters and session stats
- Secondary to game loop (saves happen after event processing)

**cloud_manager.py** - Global Leaderboard (Optional)
- Singleton pattern, syncs to Supabase for global persistence
- Local-first design: SQLite is primary, Supabase is secondary
- Non-blocking: uses loop.run_in_executor() for all network calls
- Fail-safe: gracefully disables if .env missing or network fails
- Syncs once per race when winner detected
- Tables: `global_country_stats` (country wins), `global_hall_of_fame` (captains)

**audio_manager.py** - Sound System
- Pre-loads all sounds at startup (zero-latency playback)
- Platform-specific mixer init (DirectSound on Windows)
- Dynamic pitch shifting for combo effects
- TTS integration with thread-safe queue (pyttsx3)
- Separate volume controls for BGM, SFX, and events

**asset_manager.py** - Sprite Management
- Pre-loads all PNG assets at startup
- Name mapping (English ↔ Spanish gift names)
- Smart scaling with aspect ratio preservation
- Background removal for flag sprites
- Missing asset fallback (colored circles, silent audio)

**background_manager.py** - Parallax System
- Multi-layer parallax stars (3 layers, different speeds)
- Speed lines for velocity effect
- Tension mode when racing past 80% of track
- Warp mode during Final Stretch (3x speed line density)

### Key Architectural Patterns

1. **Producer-Consumer** - TikTokManager pushes to queue, GameEngine consumes
2. **Event-Driven** - All interactions flow through GameEvent objects
3. **State Machine** - IDLE → RACING → VICTORY with clear transitions
4. **Non-Blocking I/O** - All database/cloud operations use asyncio to prevent frame drops
5. **Singleton** - CloudManager, AssetManager use singleton pattern
6. **Strategy Pattern** - Dual game modes (GIFT vs COMMENT) swap behavior
7. **Object Pool** - Particle recycling to avoid GC spikes

### Game Modes

**GIFT Mode**
- Players send TikTok gifts (real money)
- Gift diamond value determines advancement distance
- Supports combat items: Rosa (+5m), Pesa (-10m to leader), Helado (freeze 3s)
- Monetization-focused

**COMMENT Mode**
- Players type shortcuts in chat ("1", "ARG", "argentina")
- Free participation, no money required
- Each vote = 1 point advancement
- Anti-spam: 1-second cooldown per user
- Configured in `src/config.py`: `GAME_MODE = "COMMENT"`

### Event Flow: TikTok → Visualization

```
TikTok Gift/Comment Event
  → TikTokManager.on_gift() / on_comment()
  → Extract username, gift/vote, diamonds
  → Create GameEvent(type, username, data)
  → asyncio.Queue.put()
  → GameEngine.process_events()
  → Route by EventType (GIFT/VOTE/JOIN)
  → PhysicsWorld.apply_gift_impulse()
  → racer.target_x += distance
  → Apply combat effect if applicable
  → Emit particles + play audio
  → PhysicsWorld.update() (Lerp to target)
  → GameEngine.render() (draw flag at new position)
  → pygame.display.flip() (60 FPS)
```

### Physics Implementation

- **Horizontal racing** with 12 lanes (one per country)
- **No gravity**: `space.gravity = (0, 0)`
- **Groove joints** constrain flags to X-axis only (prevents vertical drift)
- **Target-based Lerp** instead of forces:
  ```python
  racer.target_x += diamonds * 0.8  # Queue movement
  # In update():
  new_x = current_x + (target_x - current_x) * 0.12  # Smooth interpolation
  ```
- **Freeze system**: Sets velocity to (0, 0) and skips Lerp update
- **Winner detection**: First flag past RACE_FINISH_X (400px)

### Database & Cloud Sync

**Local (SQLite)**
- Primary data store: `tiktok_events.db`
- Async writes using aiosqlite (non-blocking)
- Table: `gift_logs` (username, gift_name, diamond_count, timestamp, streamer)

**Cloud (Supabase - Optional)**
- Syncs once per race when winner detected
- Non-blocking: `asyncio.create_task()` + `run_in_executor()`
- Fail-safe: game continues if sync fails
- Tables:
  - `global_country_stats`: country → total_wins, total_diamonds
  - `global_hall_of_fame`: captain achievements with timestamps
- Requires `.env` with `SUPABASE_URL` and `SUPABASE_KEY`

## Critical Development Rules

### Resource Path Management
**NEVER use direct string paths for assets**. Always use `resource_path()` from `src/resources.py`.

```python
# ❌ BAD
image = pygame.image.load("assets/flags/Argentina.png")

# ✅ GOOD
from src.resources import resource_path
image = pygame.image.load(resource_path("assets/flags/Argentina.png"))
```

**Rationale**: PyInstaller packages assets into `sys._MEIPASS` in executables. Direct paths break the packaged app.

**File path operations**:
- Always use `os.path.normpath()` and `os.path.join()` for cross-platform compatibility
- Asset loading MUST go through `AssetManager` or `AudioManager` (they handle `resource_path()`)

### Non-Blocking I/O
**NEVER block the main game loop** (60 FPS target).

```python
# ❌ BAD - Blocks rendering
result = supabase.table('stats').insert(data).execute()

# ✅ GOOD - Non-blocking
asyncio.create_task(
    loop.run_in_executor(None, _sync_blocking)
)
```

**Rationale**: Network/database calls can take 100-500ms. Blocking drops FPS to <10, causing stuttering.

### Physics Preservation
**DO NOT modify Pymunk step or collision handling** unless explicitly requested.

- Keep `PHYSICS_STEPS = 10` (substeps for stability)
- Don't change groove joint constraints (prevents flags escaping lanes)
- Don't add gravity to the race (horizontal movement only)

### Cross-Platform Compatibility
**Maintain Windows + macOS support**.

- Use platform-specific paths: `assets/audio;assets/sounds` (Windows) vs `assets/audio:assets/sounds` (macOS)
- Audio mixer init: DirectSound on Windows, default on macOS
- Test resource_path() with `sys._MEIPASS` fallback

### Security
**NEVER commit secrets**. Use `.env` for all sensitive data.

```python
# ✅ GOOD
from dotenv import load_dotenv
load_dotenv()
SUPABASE_URL = os.getenv('SUPABASE_URL')
```

Required `.env` vars (optional for local-only mode):
- `SUPABASE_URL`
- `SUPABASE_KEY`

### Documentation Standards
- **Docstrings**: Google Style format for all functions/classes
- **Language**: English for all documentation and comments
- **Type hints**: Use where it improves clarity

### Testing Requirements
- For new logic in `AssetManager`/`AudioManager`, suggest unit tests
- Use `unittest.mock` to simulate file access (no physical assets required in CI)
- Test both dev mode and packaged mode (with `sys._MEIPASS`)

## Configuration

All tuning in `src/config.py`:

**Game Mode**
```python
GAME_MODE = "COMMENT"  # or "GIFT"
```

**Display**
```python
SCREEN_WIDTH = 460
SCREEN_HEIGHT = 820
FPS = 60
GAME_MARGIN = 40  # Outer frame padding
```

**Race Setup**
```python
RACE_START_X = 50
RACE_FINISH_X = 400
FLAG_RADIUS = 12
RACE_COUNTRIES = [
    "Argentina", "Brasil", "Mexico", "España",
    "Colombia", "Chile", "Peru", "Venezuela",
    "USA", "Indonesia", "Russia", "Italy"
]
```

**Tuning Knobs**
```python
COMMENT_POINTS_PER_MESSAGE = 1
COMMENT_COOLDOWN = 1.0  # seconds
JOIN_NOTIFICATION_COOLDOWN = 5.0
```

## File Structure

```
racing_go/
├── main.py                          # Entry point, game loop, error handling
├── requirements.txt                 # Python dependencies
├── build_app.py                     # PyInstaller build script
├── tiktok_events.db                 # SQLite database (auto-created)
├── .env                             # Secrets (SUPABASE_URL, SUPABASE_KEY)
├── src/
│   ├── config.py                    # All configuration constants
│   ├── events.py                    # GameEvent, EventType definitions
│   ├── tiktok_manager.py            # WebSocket producer
│   ├── game_engine.py               # Main game logic (5000 lines)
│   ├── physics_world.py             # Pymunk racing simulation
│   ├── database.py                  # SQLite async operations
│   ├── cloud_manager.py             # Supabase sync (optional)
│   ├── audio_manager.py             # Sound + TTS
│   ├── asset_manager.py             # Sprite loading
│   ├── background_manager.py        # Parallax background
│   └── resources.py                 # resource_path() utility
├── assets/
│   ├── audio/                       # Background music
│   ├── gifts/                       # Gift sprites (Rosa.png, etc.)
│   ├── flags/                       # Country flags
│   └── sounds/                      # SFX files
├── tests/                           # Unit tests
├── test_*.py                        # Test scripts (see TESTING_GUIDE.md)
└── TESTING_GUIDE.md                 # Complete testing documentation
```

## Key Gotchas

1. **TTS Thread Safety**: pyttsx3 is not thread-safe. AudioManager uses a worker thread with a queue to prevent `run loop already started` errors.

2. **PyInstaller Asset Paths**: Assets must use `resource_path()` or they won't load in packaged executables.

3. **Supabase RLS Policies**: UPDATE operations require explicit policies. If `check_policies.py` fails, run `fix_supabase_policies.sql` in Supabase.

4. **Race Sync Flag**: `race_synced` must be reset to `False` when returning to IDLE, or only the first race will sync to cloud.

5. **Particle Cleanup**: When FPS drops below 30, automatically reduce particle count to prevent further lag.

6. **Username Extraction**: TikTok protobuf events have multiple username fields (`uniqueId`, `nickname`, `displayId`). Use fallback chain.

7. **Country Assignment**: Users are assigned to countries on first interaction. Use `_get_country_for_user()` to ensure consistent mapping.

8. **Combo Decay**: Combos reset after 2 seconds of inactivity. Track `last_gift_time` per country.

## Performance Targets

- **FPS**: 60 (drops below 30 trigger warnings)
- **Max Particles**: 150 confetti (auto-cleanup if lagging)
- **Event Queue**: Non-blocking drain (process all queued events per frame)
- **Database Writes**: < 5ms (async, don't block rendering)
- **Cloud Sync**: Background thread (0ms main thread impact)

## CI/CD

GitHub Actions workflow: `.github/workflows/build.yml`

**Jobs**:
- `build-windows`: Builds Windows .exe
- `build-macos`: Builds macOS .app
- `test`: Syntax checks + unit tests (Ubuntu)
- `release`: Attaches artifacts to version tags

**Triggers**: Push to main/master, version tags (`v*`)

## References

- `README.md` - User-facing setup and usage guide
- `TESTING_GUIDE.md` - Complete testing documentation
- `COMMENT_MODE.md` - Details on free voting mode
- `CLOUD_INTEGRATION.md` - Supabase integration guide
- `ARCHITECTURE_DIAGRAM.md` - Visual architecture diagrams
- `DOCS_INDEX.md` - Documentation index
