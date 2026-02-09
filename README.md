# TikTok Live Interactive Racing Bot

Juego de carreras en tiempo real para TikTok Live: los espectadores votan o envían regalos y las banderas de países compiten en pista. Incluye físicas Pymunk, audio, partículas, combate (Rosa/Pesa/Helado), sincronización opcional con Supabase y mecánicas de retención (Visual Welcome, Ghost Participation, Meteor Shower).

![Python](https://img.shields.io/badge/Python-3.12-blue)
![Pygame](https://img.shields.io/badge/Pygame-2.6-green)
![Pymunk](https://img.shields.io/badge/Pymunk-6.6-orange)
![SQLite](https://img.shields.io/badge/SQLite-3-lightblue)

## ✨ Características

### Conectividad
- ✅ **Conexión WebSocket asíncrona** a TikTok Live (TikTokLive)
- ✅ **Reconexión automática** con backoff exponencial (hasta 15 reintentos)
- ✅ **Manejo de desconexiones** graceful
- ✅ **Eventos de join** para Visual Welcome cuando entran espectadores

### Carrera y Físicas
- ✅ **Carrera horizontal** por banderas (países) con Pymunk (sin gravedad, groove joints)
- ✅ **Movimiento por objetivo (Lerp)** según votos/regalos
- ✅ **Combate**: Rosa (+5m), Pesa (-10m al líder), Helado (congelar 3s)
- ✅ **Combos**: 5+ regalos = "COMBO!", 10+ = "ON FIRE" con trails
- ✅ **Detección de ganador** al cruzar la meta

### Visualización
- ✅ **Renderizado Pygame** 460×820 vertical (zona segura para comentarios TikTok)
- ✅ **Fondo verde croma** para OBS
- ✅ **Parallax** (estrellas, líneas de velocidad), modo tensión y Final Stretch
- ✅ **Sistema de partículas** (explosiones, confetti, trails)
- ✅ **Header** con líder y estado de conexión

### Retención
- ✅ **Visual Welcome**: mensaje flotante cuando un espectador entra al live
- ✅ **Ghost Participation**: votos fantasma tras inactividad para mantener la carrera viva
- ✅ **Likes goal bar** y **Meteor Shower**: meta de likes que al completarse dispara lluvia de meteoros (audio + shake)

### Audio
- ✅ **BGM**, SFX por regalo/voto, combo, victoria, final stretch, freeze
- ✅ **TTS** (pyttsx3) para anuncios, cola thread-safe
- ✅ **Pitch dinámico** en combos

### Persistencia
- ✅ **SQLite** (gift_logs) con guardado asíncrono
- ✅ **Supabase opcional** (global_country_stats, hall_of_fame) con sync por carrera

## 🚀 Instalación

```bash
python3 -m venv venv
source venv/bin/activate   # macOS/Linux
# venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

## 🎮 Uso

```bash
python main.py @streamer_username
```

**Probar sin TikTok (modo IDLE):**
```bash
python main.py --idle
```
→ Ventana abierta, sin conexión. Usa teclas para simular votos/regalos. Pulsa **L** para conectar cuando quieras ir LIVE.

Ver **[TESTING_BEFORE_LIVE.md](TESTING_BEFORE_LIVE.md)** para la guía completa de pruebas pre-LIVE.

## ⌨️ Controles

### Controles Básicos
- **ESC** - Salir
- **C/R** - Reset carrera (volver a IDLE)
- **L** - Conectar a TikTok (en modo IDLE)

### Test Mode (sin conexión TikTok)
- **T** - Regalo pequeño | **Y** - Regalo grande
- **1/2/3** - Votos (COMMENT) o Rosa/Pesa/Helado (GIFT)
- **J** - Usuario se une a equipo
- **W** - Simular entrada de espectador (Visual Welcome)
- **F** - Combo ON FIRE | **G** - Final Stretch | **V** - Secuencia victoria

**Modo COMMENT:** 1/2/3 simulan votos. **Modo GIFT:** 1/2/3 activan Rosa/Pesa/Helado.

## 🎥 OBS Setup

1. Añadir Fuente → Captura de Ventana
2. Aplicar Filtro → Croma Key (Verde)
3. Similitud: 400-500, Suavidad: 80-100

## 📁 Estructura

```
racing_go/
├── main.py
├── requirements.txt
├── build_app.py          # PyInstaller → TikTokRacingGoLive.app / .exe
├── tiktok_events.db
├── .env                  # Opcional: SUPABASE_URL, SUPABASE_KEY
├── src/
│   ├── config.py
│   ├── events.py
│   ├── resources.py      # resource_path() para empaquetado
│   ├── tiktok_manager.py
│   ├── game_engine.py
│   ├── physics_world.py
│   ├── database.py
│   ├── cloud_manager.py  # Supabase (opcional)
│   ├── audio_manager.py
│   ├── asset_manager.py
│   ├── background_manager.py
│   └── camera.py
├── assets/
│   ├── audio/            # BGM
│   ├── sounds/           # SFX
│   ├── gifts/            # Sprites regalos/banderas
│   ├── icons/            # Rosa, Pesa, Helado
│   └── fonts/            # Opcional
├── tests/
└── test_*.py             # test_audio.py, test_resources.py, test_cloud_manager.py, etc.
```

## 💾 Base de Datos

```sql
-- Ver últimos regalos
SELECT * FROM gift_logs ORDER BY timestamp DESC LIMIT 10;

-- Top donadores
SELECT username, SUM(diamond_count * gift_count) as total
FROM gift_logs GROUP BY username ORDER BY total DESC;
```

## ⚙️ Configuración

Edita `src/config.py`:

### Modo de Juego
```python
GAME_MODE = "COMMENT"  # o "GIFT"
```

**COMMENT**: Votos gratis en chat (1, 2, 3, arg, bra, mex...)  
**GIFT**: Regalos de TikTok (modo original)

Ver [COMMENT_MODE.md](COMMENT_MODE.md) para detalles completos.

### Configuración Visual
```python
SCREEN_WIDTH = 460
SCREEN_HEIGHT = 820
GAME_MARGIN = 40  # Borde externo
FPS = 60
```

### Retención (config.py)
- **Ghost Participation**: `GHOST_INACTIVITY_THRESHOLD`, `GHOST_VOTE_INTERVAL_MIN/MAX`
- **Visual Welcome**: `WELCOME_COOLDOWN`, `MAX_SIMULTANEOUS_WELCOMES`, `WELCOME_TEXT_LIFESPAN`
- **Likes / Meteor Shower**: `LIKES_GOAL_INITIAL` (meta de likes; al completarse → Meteor Shower)

### Colores por Regalo

```python
GIFT_COLORS = {
    "Rosa": (255, 105, 180),
    "TikTok": (0, 242, 234),
    "León": (255, 165, 0),
    "Galaxia": (75, 0, 130),
}
```

### Valores de Diamantes

```python
GIFT_DIAMOND_VALUES = {
    "Rosa": 1,
    "Corazón": 5,
    "TikTok": 50,
    "León": 100,
    "Galaxia": 500,
    "Universo": 1000,
}
```

## 🎯 Características Técnicas

### Carrera
- Carrera horizontal por banderas (8 países por defecto: Argentina, Brasil, México, etc.)
- Zona segura: inicio y meta evitan zona de comentarios y botones de TikTok
- Lerp suave hacia `target_x` según votos/diamantes

### Recursos y Build
- **Siempre** usar `resource_path()` (src/resources.py) para assets; obligatorio con PyInstaller (`sys._MEIPASS`)
- Assets cargados vía `AssetManager` y `AudioManager`

### Build ejecutable

```bash
python build_app.py
```

- **macOS:** `dist/TikTokRacingGoLive.app` → `open dist/TikTokRacingGoLive.app`
- **Windows:** `dist/TikTokRacingGoLive/TikTokRacingGoLive.exe`

Ver [CLAUDE.md](CLAUDE.md) para comandos de tests y CI.

## 🏗️ Arquitectura

```
TikTokManager (Productor) → asyncio.Queue → GameEngine (Consumidor)
                                                    ├── PhysicsWorld (Pymunk)
                                                    ├── Database (SQLite)
                                                    ├── CloudManager (Supabase, opcional)
                                                    ├── AudioManager
                                                    ├── AssetManager
                                                    ├── BackgroundManager / Camera
                                                    └── Renderer (Pygame + partículas)
```

## 🐛 Troubleshooting

- **Las banderas no se mueven:** Comprueba que el streamer esté en vivo y que el modo (COMMENT/GIFT) coincida con lo que hace la audiencia.
- **Lag / FPS bajo:** C reduce partículas y resetea; el juego hace auto-limpieza de partículas si FPS &lt; 30.
- **Database locked:** Cierra otras instancias del bot.
- **Supabase:** Si no hay `.env` o falla la red, el juego sigue en local (SQLite). Ver [CLOUD_INTEGRATION.md](CLOUD_INTEGRATION.md).

## 📚 Documentación

- [CLAUDE.md](CLAUDE.md) — Arquitectura, comandos, reglas de desarrollo
- [COMMENT_MODE.md](COMMENT_MODE.md) — Modo votos por chat
- [CLOUD_INTEGRATION.md](CLOUD_INTEGRATION.md) — Supabase y sync
- [TESTING_GUIDE.md](TESTING_GUIDE.md) — Tests y pruebas pre-LIVE
- [TESTING_BEFORE_LIVE.md](TESTING_BEFORE_LIVE.md) — Guía de pruebas antes de ir LIVE

## 📝 Notas

**Stack:** Python 3.12, TikTokLive, Pygame, Pymunk, SQLite, Supabase (opcional), pyttsx3 (TTS)  
**Build:** `python build_app.py` → TikTokRacingGoLive.app / TikTokRacingGoLive.exe  
**Estado:** ✅ Funcional

---

¡Disfruta tu TikTok Live Racing Bot! 🏁
