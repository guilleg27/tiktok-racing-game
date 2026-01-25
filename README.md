# TikTok Live Interactive Bot - MVP

Sistema interactivo en tiempo real para streams de TikTok Live con simulación de físicas y persistencia de datos.

![Python](https://img.shields.io/badge/Python-3.12-blue)
![Pygame](https://img.shields.io/badge/Pygame-2.6-green)
![Pymunk](https://img.shields.io/badge/Pymunk-6.6-orange)
![SQLite](https://img.shields.io/badge/SQLite-3-lightblue)

## ✨ Características

### Conectividad
- ✅ **Conexión WebSocket asíncrona** a TikTok Live
- ✅ **Reconexión automática** con backoff exponencial
- ✅ **Manejo de desconexiones** graceful

### Físicas Realistas
- ✅ **Motor de física Pymunk** con gravedad y colisiones
- ✅ **Tamaño proporcional** al valor del regalo (escala logarítmica)
- ✅ **Elasticidad y fricción** configurables
- ✅ **Límite de 50 objetos** con auto-limpieza

### Visualización
- ✅ **Renderizado Pygame** 1080x1920 vertical
- ✅ **Fondo verde croma** (0,255,0) para OBS
- ✅ **Colores personalizados** por regalo
- ✅ **Header con estado de conexión**

### Persistencia
- ✅ **Base de datos SQLite** con tabla gift_logs
- ✅ **Guardado asíncrono** sin bloquear rendering

## 🚀 Instalación

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 🎮 Uso

```bash
python main.py @streamer_username
```

## ⌨️ Controles

### Controles Básicos
- **ESC** - Salir
- **C/R** - Reset carrera (volver a IDLE)

### Test Mode (sin conexión TikTok)
- **T** - Regalo pequeño aleatorio
- **Y** - Regalo grande aleatorio
- **1/2/3** - Votos de prueba (modo COMMENT) o efectos combate (modo GIFT)
- **J** - Simular usuario uniéndose
- **K** - Simular puntos de capitán

**Modo COMMENT:** Teclas 1/2/3 simulan votos de usuarios aleatorios
**Modo GIFT:** Teclas 1/2/3 activan efectos Rosa/Pesa/Helado

## 🎥 OBS Setup

1. Añadir Fuente → Captura de Ventana
2. Aplicar Filtro → Croma Key (Verde)
3. Similitud: 400-500, Suavidad: 80-100

## 📁 Estructura

```
tiktok-live-bot/
├── main.py
├── requirements.txt
├── tiktok_events.db
└── src/
    ├── config.py
    ├── events.py
    ├── tiktok_manager.py
    ├── game_engine.py
    ├── physics_world.py
    └── database.py
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

### Tamaño Proporcional
- Escala logarítmica: 1💎 = 15px, 1000💎 = 120px
- Masa proporcional al área
- Regalos caros empujan a los pequeños

### Física Orgánica
- Elasticidad 0.85 para rebotes naturales
- Fricción 0.4 para deslizamiento realista
- Damping 0.95 reduce velocidad gradualmente
- Rotación inicial aleatoria

### Límite Inteligente
- Máximo 50 bolas en pantalla
- Auto-elimina la más antigua
- Previene lag

## 🏗️ Arquitectura

```
TikTokManager (Productor)
    ↓ asyncio.Queue
GameEngine (Consumidor)
    ├── PhysicsWorld (Pymunk)
    ├── Database (SQLite)
    └── Renderer (Pygame)
```

## 🐛 Troubleshooting

**Las bolas no aparecen**
- Verifica que el streamer esté en vivo
- Revisa logs en consola

**Lag con muchas bolas**
- Presiona C para limpiar
- Reduce MAX_BALLS en config

**Database locked**
- Cierra otras instancias del bot

## 🔮 Roadmap

- [ ] Texturas/sprites personalizados
- [ ] Efectos de partículas
- [ ] Sonidos al recibir regalos
- [ ] Comandos de chat
- [ ] Dashboard web de estadísticas
- [ ] Export a CSV/JSON

## 📝 Notas

**Stack:** Python 3.12 + TikTokLive + Pygame + Pymunk + SQLite  
**Versión:** 1.0.0 MVP  
**Estado:** ✅ Funcional

---

¡Disfruta tu TikTok Live Bot! 🎉
