# 🌐 Integración con Supabase - Documentación Técnica

## 📋 Resumen

Este documento explica cómo el sistema TikTok Racing Game se integra con Supabase para persistencia global, manteniendo el principio **Local First** y asegurando que las operaciones de red no bloqueen el rendering del juego.

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│                    GAME ENGINE                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Race Finished + Winner Detected                 │  │
│  │    ↓                                              │  │
│  │  Check: race_synced == False?                    │  │
│  │    ↓ Yes                                          │  │
│  │  Set race_synced = True                          │  │
│  │    ↓                                              │  │
│  │  asyncio.create_task(cloud_sync)  ← NON-BLOCKING │  │
│  └──────────────────────────────────────────────────┘  │
│                    ↓ (async)                            │
│  ┌──────────────────────────────────────────────────┐  │
│  │          CLOUD MANAGER (Singleton)               │  │
│  │                                                   │  │
│  │  1. Check if enabled (has .env config)           │  │
│  │  2. Run sync in executor (background thread)     │  │
│  │  3. Return immediately (event loop continues)    │  │
│  └──────────────────────────────────────────────────┘  │
│                    ↓ (in executor)                      │
│  ┌──────────────────────────────────────────────────┐  │
│  │            SUPABASE CLIENT                       │  │
│  │                                                   │  │
│  │  1. Upsert global_country_stats                  │  │
│  │     (increment total_wins and total_diamonds)    │  │
│  │  2. Insert global_hall_of_fame                   │  │
│  │     (record captain achievement)                 │  │
│  │  3. Log result (success/failure)                 │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘

        ⚡ GAME CONTINUES RENDERING AT 60 FPS ⚡
```

## 🎯 Principios de Diseño

### 1. **Local First**
- SQLite sigue siendo la fuente primaria de datos
- Todas las operaciones críticas (regalo, puntos, capitán) se guardan en SQLite **inmediatamente**
- Supabase es secundario y opcional

### 2. **Non-Blocking**
- La sincronización con Supabase NO bloquea el game loop
- Se usa `asyncio.create_task()` para ejecutar en background
- Se usa `loop.run_in_executor()` para operaciones bloqueantes de red
- El rendering continúa a 60 FPS sin interrupciones

### 3. **Fail-Safe**
- Si Supabase no está configurado (.env falta): juego funciona normalmente
- Si hay error de red: se loggea pero no se muestra al usuario
- Si la sincronización falla: no afecta la experiencia del streamer

### 4. **Single-Sync per Race**
- Flag `race_synced` previene múltiples sincronizaciones
- Solo se sincroniza una vez cuando se detecta el ganador por primera vez
- El flag se resetea cuando la carrera vuelve a IDLE

## 📁 Estructura de Archivos

```
racing_go/
├── .env                           # Credenciales de Supabase (NO commitear)
├── src/
│   ├── cloud_manager.py          # Módulo de persistencia global (Singleton)
│   ├── game_engine.py            # Integración: líneas 1003-1020, 2031
│   ├── database.py               # Persistencia local (SQLite) - sin cambios
│   └── config.py                 # Sin cambios
├── test_cloud_manager.py         # Tests unitarios del CloudManager
├── test_supabase_connection.py   # Test de conexión básico
└── CLOUD_INTEGRATION.md          # Este documento
```

## 🔌 Puntos de Integración en GameEngine

### 1. Inicialización (`__init__`)

```python
# Línea 147
self.cloud_manager = CloudManager()

# Línea 230 (nuevo)
self.race_synced = False  # Flag para prevenir múltiples syncs
```

### 2. Detección de Victoria (`update()`)

```python
# Líneas 1003-1020 (modificado)
if self.physics_world.race_finished and self.physics_world.winner:
    # ☁️ CLOUD SYNC: Solo la primera vez
    if not self.race_synced and self.winner_animation_time < dt * 2:
        self.race_synced = True
        winner_country = self.physics_world.winner
        winner_captain = self.current_captains.get(winner_country, "Unknown")
        winner_points = self.session_points.get(winner_country, {}).get(winner_captain, 0)
        
        # Async sync (non-blocking)
        asyncio.create_task(
            self.cloud_manager.sync_race_result(
                country=winner_country,
                winner_name=winner_captain,
                total_diamonds=winner_points,
                streamer_name=self.streamer_name
            )
        )
        logger.info(f"☁️ Queued cloud sync: {winner_country} - {winner_captain} ({winner_points}💎)")
    
    # ... resto de la animación de victoria
```

### 3. Reset al volver a IDLE (`_return_to_idle()`)

```python
# Línea 2031 (nuevo)
self.race_synced = False  # Reset flag para próxima carrera
```

## 🧪 Cómo Probar

### Prueba 1: Test Unitarios

```bash
# Ejecutar todos los tests del CloudManager
python -m pytest test_cloud_manager.py -v

# O con unittest
python test_cloud_manager.py
```

**Tests incluidos:**
- ✅ Singleton pattern
- ✅ Inicialización con/sin .env
- ✅ Sync exitoso (país existente)
- ✅ Sync exitoso (país nuevo)
- ✅ Manejo de errores de red
- ✅ Query de leaderboard
- ✅ Query de estadísticas de país
- ✅ Operaciones no bloqueantes

### Prueba 2: Test de Conexión

```bash
# Test básico de conexión a Supabase
python test_supabase_connection.py
```

**Salida esperada:**
```
URL: https://ykgoolwtyiauvlqavxrj.supabase.co
Key: eyJhbGciOiJIUzI1NiI...

✅ Conexión exitosa!
📊 Países encontrados: 8
   - Argentina: 0 wins
   - Brasil: 0 wins
   - Mexico: 0 wins
   ...
```

### Prueba 3: Test End-to-End (Carrera Completa)

```bash
# Iniciar el juego en modo test
python main.py --idle

# En la ventana del juego:
# 1. Presiona T varias veces para simular regalos
# 2. Espera a que un país llegue a la meta
# 3. Observa el log de consola para ver:
#    ☁️ Queued cloud sync: Argentina - testuser123 (500💎)
#    ☁️ Synced to cloud: Argentina (testuser123, 500💎)

# 4. Verifica en Supabase Table Editor:
#    - global_country_stats: debería ver wins incrementados
#    - global_hall_of_fame: debería ver nuevo record
```

### Prueba 4: Verificar que no Bloquea el Rendering

```bash
# Ejecutar el juego con stress test activo
# Editar src/config.py temporalmente:
AUTO_STRESS_TEST = True
STRESS_TEST_INTERVAL = 0.2  # Regalos cada 0.2s

# Ejecutar
python main.py --idle

# Presiona T para iniciar la carrera
# Observa que:
# - El FPS se mantiene estable ~60 FPS (mostrado en logs cada 1s)
# - Las partículas siguen animándose suavemente
# - No hay stuttering cuando se sincroniza a Supabase
```

## 🔍 Debugging y Logs

### Logs Importantes

**CloudManager Inicializado:**
```
✅ CloudManager initialized successfully
```

**Sincronización Encolada (en game loop):**
```
☁️ Queued cloud sync: Argentina - testuser123 (500💎)
```

**Sincronización Completa (en background):**
```
☁️ Synced to cloud: Argentina (testuser123, 500💎)
```

**Error de Red (silencioso en UI):**
```
❌ Cloud sync failed: HTTPException(504, 'Gateway timeout')
```

**Supabase Deshabilitado:**
```
⚠️ SUPABASE_URL or SUPABASE_KEY not found in .env.
Cloud sync disabled. Game will continue with local persistence only.
```

### Verificar Estado de Sincronización

```python
# En consola de Python (debugging)
from src.cloud_manager import CloudManager
manager = CloudManager()

print(f"Enabled: {manager.enabled}")
print(f"Client: {manager.client}")

# Test manual de sync
import asyncio
result = asyncio.run(manager.sync_race_result(
    country="Argentina",
    winner_name="debug_test",
    total_diamonds=999,
    streamer_name="debug"
))
print(f"Result: {result}")
```

## 📊 Esquema de Base de Datos

### Tabla: `global_country_stats`

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `country` | TEXT (PK) | Nombre del país |
| `total_wins` | INTEGER | Total de victorias globales |
| `total_diamonds` | BIGINT | Total de diamantes acumulados |
| `last_updated` | TIMESTAMP | Última actualización |

**Ejemplo:**
```sql
SELECT * FROM global_country_stats ORDER BY total_wins DESC;
```
```
country    | total_wins | total_diamonds | last_updated
-----------|------------|----------------|---------------------------
Argentina  | 25         | 12500          | 2026-01-19 15:30:00+00
Brasil     | 18         | 9000           | 2026-01-19 14:20:00+00
Mexico     | 12         | 6000           | 2026-01-19 13:10:00+00
```

### Tabla: `global_hall_of_fame`

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | UUID (PK) | ID único del record |
| `country` | TEXT (FK) | País ganador |
| `captain_name` | TEXT | Nombre del capitán/MVP |
| `total_diamonds` | INTEGER | Diamantes del capitán en esa carrera |
| `race_timestamp` | TIMESTAMP | Momento de la victoria |
| `streamer_name` | TEXT | Nombre del streamer |

**Ejemplo:**
```sql
SELECT * FROM global_hall_of_fame 
ORDER BY total_diamonds DESC 
LIMIT 10;
```
```
captain_name | country   | total_diamonds | race_timestamp           | streamer_name
-------------|-----------|----------------|--------------------------|---------------
megafan99    | Argentina | 5000          | 2026-01-19 15:30:00+00  | streamer123
topdonor     | Brasil    | 4500          | 2026-01-19 14:20:00+00  | streamer123
richviewer   | Mexico    | 3200          | 2026-01-19 13:10:00+00  | streamer456
```

## 🚨 Troubleshooting

### Problema: "Cloud sync disabled"

**Causa:** Archivo `.env` no encontrado o mal configurado

**Solución:**
```bash
# 1. Verificar que .env existe en la raíz
ls -la .env

# 2. Verificar contenido
cat .env

# Debe contener:
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_KEY=tu-anon-key-aqui

# 3. Verificar que las credenciales son correctas en Supabase Dashboard
```

### Problema: "Network timeout" en logs

**Causa:** Problemas de conectividad con Supabase

**Solución:**
1. Verificar conexión a internet
2. Verificar que el proyecto de Supabase esté activo (no pausado)
3. Verificar firewall/proxy no bloquea supabase.co
4. Probar conexión manual: `python test_supabase_connection.py`

### Problema: Datos no aparecen en Supabase

**Causa:** Políticas de RLS muy restrictivas

**Solución:**
```sql
-- Verificar políticas en Supabase SQL Editor
SELECT * FROM pg_policies WHERE tablename = 'global_country_stats';

-- Si no hay políticas o son muy restrictivas, crear políticas públicas:
CREATE POLICY "Allow public insert" ON global_country_stats
FOR INSERT WITH CHECK (true);

CREATE POLICY "Allow public update" ON global_country_stats
FOR UPDATE USING (true);
```

### Problema: FPS drops durante sincronización

**Causa:** Bug en la implementación (no debería pasar)

**Diagnóstico:**
```bash
# Ejecutar con stress test para medir FPS
AUTO_STRESS_TEST = True

# Observar logs de FPS
# Debe mantenerse estable ~60 FPS
```

**Solución:**
- Verificar que `asyncio.create_task()` se está usando correctamente
- Verificar que `run_in_executor()` está presente en CloudManager
- Revisar logs para excepciones no manejadas

## 📈 Métricas y Monitoreo

### Queries Útiles

**Top 10 Capitanes Globales:**
```sql
SELECT captain_name, country, total_diamonds, race_timestamp
FROM global_hall_of_fame
ORDER BY total_diamonds DESC
LIMIT 10;
```

**Estadísticas por País:**
```sql
SELECT country, total_wins, total_diamonds,
       ROUND(total_diamonds::numeric / NULLIF(total_wins, 0), 2) as avg_diamonds_per_win
FROM global_country_stats
ORDER BY total_wins DESC;
```

**Actividad Reciente (últimas 24 horas):**
```sql
SELECT captain_name, country, total_diamonds, race_timestamp, streamer_name
FROM global_hall_of_fame
WHERE race_timestamp > NOW() - INTERVAL '24 hours'
ORDER BY race_timestamp DESC;
```

**Top Streamers por Actividad:**
```sql
SELECT streamer_name, COUNT(*) as races, SUM(total_diamonds) as total_diamonds
FROM global_hall_of_fame
GROUP BY streamer_name
ORDER BY races DESC;
```

## 🔐 Seguridad

### Políticas de RLS Recomendadas (Producción)

Para producción, considera restringir las operaciones:

```sql
-- Solo permitir INSERT desde aplicación autenticada
ALTER TABLE global_hall_of_fame ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow authenticated insert" 
ON global_hall_of_fame 
FOR INSERT 
WITH CHECK (auth.role() = 'authenticated');

-- Permitir SELECT público (para leaderboards)
CREATE POLICY "Allow public read" 
ON global_hall_of_fame 
FOR SELECT 
USING (true);
```

### Rotar API Keys

Si necesitas rotar las API keys:

1. Generar nueva key en Supabase Dashboard → Settings → API
2. Actualizar `.env` con la nueva key
3. Reiniciar el juego
4. Verificar logs: "✅ CloudManager initialized successfully"

## 🎓 Próximos Pasos

### Mejoras Futuras

1. **Dashboard Web**
   - Visualizar leaderboard global en tiempo real
   - Gráficos de estadísticas por país
   - Timeline de victorias

2. **Rate Limiting**
   - Limitar syncs a max 1 por minuto por streamer
   - Queue de syncs fallidos para retry

3. **Caché Local**
   - Cachear leaderboard global en SQLite
   - Sync periódico en background

4. **Webhooks**
   - Notificar Discord/Telegram cuando hay nuevo record
   - Tweet automático de victorias épicas

---

**Documentación actualizada:** 2026-01-19  
**Versión del sistema:** 1.0.0  
**Autor:** Racing Game Team
