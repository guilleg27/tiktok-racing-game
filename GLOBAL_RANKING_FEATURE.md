# 🏆 Panel de Ranking Global - Documentación

## Resumen

Hemos implementado un **Panel de Ranking Global** que muestra en tiempo real el Top 3 de países con más victorias acumuladas en Supabase.

---

## 📝 Cambios Implementados

### 1. **CloudManager** (`src/cloud_manager.py`)

**Nueva función agregada:**

```python
async def get_global_ranking(limit: int = 3) -> list[Dict[str, Any]]
```

**Funcionalidad:**
- Obtiene el ranking global de países ordenados por `total_wins` (victorias) y `total_diamonds` (como desempate)
- Retorna una lista con formato: `[{'country': 'Argentina', 'total_wins': 45, 'total_diamonds': 15000}, ...]`
- Implementada de forma non-blocking usando `run_in_executor` para no bloquear el rendering

---

### 2. **GameEngine** (`src/game_engine.py`)

#### A. Nuevas Variables de Estado

```python
self.global_rank_data: list[dict] = []  # Top 3 countries by wins
self.global_rank_last_update = 0.0      # Timestamp of last update
self.global_rank_loading = False         # Flag to prevent multiple fetches
```

#### B. Funciones Nuevas

**`_sync_and_update_ranking()`**
- Sincroniza el resultado de la carrera y luego actualiza el ranking automáticamente
- Se ejecuta después de cada victoria

**`_fetch_global_ranking()`**
- Obtiene el ranking global de forma asíncrona
- Actualiza `self.global_rank_data` con los datos frescos
- Se llama:
  1. Al iniciar el juego (primera vez en estado IDLE)
  2. Después de cada sync exitoso de carrera

**`_trigger_ranking_update()`**
- Helper para disparar la actualización del ranking de forma non-blocking

**`_render_global_ranking()`**
- Renderiza el panel visual del ranking en la esquina superior derecha
- Solo se muestra en estado IDLE
- Incluye:
  - Título: "🏆 RÉCORDS MUNDIALES"
  - Top 3 con medallas (🥇🥈🥉)
  - Banderas de países
  - Número de victorias
  - Timestamp de última actualización

**`_get_country_flag()`**
- Helper que retorna el emoji de bandera según el país

---

## 🎨 Diseño Visual

### Ubicación
- **Posición:** Esquina superior derecha
- **Margen:** 20px desde el borde

### Dimensiones
- **Ancho:** 280px
- **Alto:** 160px

### Estilo
- **Fondo:** Gradiente oscuro (azul oscuro) con transparencia
- **Borde:** Dorado (#FFD700) con esquinas redondeadas
- **Título:** Dorado claro (#FFDF80)
- **Texto:** Blanco/gris claro
- **Primer lugar:** Color dorado destacado

### Contenido
```
🏆 RÉCORDS MUNDIALES
───────────────────────
🥇 🇦🇷 Argentina: 45
🥈 🇧🇷 Brasil: 38
🥉 🇲🇽 Mexico: 32

Actualizado hace 5m
```

---

## 🔄 Flujo de Actualización

### 1. Carga Inicial
```
Game Start → IDLE State → _fetch_global_ranking() → Display Panel
```

### 2. Actualización Después de Victoria
```
Race Finished → _sync_and_update_ranking() → Sync Result → Update Ranking → Refresh Panel
```

### 3. Optimización
- ✅ No se descarga en cada frame
- ✅ Solo se actualiza cuando hay nuevos datos
- ✅ Flag `global_rank_loading` previene múltiples fetches simultáneos
- ✅ Timestamp permite mostrar "frescura" de los datos

---

## 🧪 Testing

### Test Manual

1. **Inicia el juego:**
   ```bash
   python main.py --idle
   ```

2. **Verifica el panel:**
   - Deberías ver el panel en la esquina superior derecha (estado IDLE)
   - Si hay datos en Supabase, mostrará el Top 3

3. **Simula victorias:**
   - Presiona `T` varias veces para simular regalos
   - Espera a que termine la carrera (~15 segundos)
   - El panel debería actualizarse después de cada victoria

### Test de Sincronización

```bash
python test_global_ranking.py
```

---

## 📊 Datos de Supabase

El panel obtiene datos de la tabla `global_country_stats`:

```sql
SELECT country, total_wins, total_diamonds, last_updated
FROM global_country_stats
ORDER BY total_wins DESC, total_diamonds DESC
LIMIT 3;
```

---

## 🎯 Características

### Implementado ✅
- [x] Fetch de ranking global desde Supabase
- [x] Panel visual elegante en IDLE
- [x] Top 3 con medallas
- [x] Banderas de países
- [x] Actualización automática después de cada victoria
- [x] Carga inicial no-bloqueante
- [x] Timestamp de última actualización
- [x] Prevención de múltiples fetches simultáneos
- [x] Gradiente y estilo visual atractivo

### Mejoras Futuras (Opcionales)
- [ ] Animación de entrada/salida del panel
- [ ] Efecto de resaltado cuando cambia el ranking
- [ ] Mostrar también top diamantes
- [ ] Gráfico de barras visual
- [ ] Panel expandible con más posiciones

---

## 🐛 Troubleshooting

### El panel no aparece
1. Verifica que hay datos en `global_country_stats` en Supabase
2. Verifica logs: Debería ver `🏆 Global ranking updated: X countries`
3. Asegúrate de estar en estado IDLE (presiona ESC si estás en carrera)

### El panel no se actualiza
1. Verifica logs: Busca `☁️ Sync successful, updating ranking...`
2. Verifica que el sync a Supabase funciona
3. Chequea el timestamp en el footer del panel

### Errores de conexión
1. Verifica `.env` tiene credenciales correctas
2. Verifica conexión a internet
3. Revisa logs de Supabase en `src.cloud_manager`

---

## 📚 Archivos Modificados

1. **`src/cloud_manager.py`**
   - Agregada función `get_global_ranking()`
   - Agregada función `_get_global_ranking_blocking()`

2. **`src/game_engine.py`**
   - Import de `time` agregado
   - Variables de estado agregadas
   - 5 funciones nuevas
   - Integración con loop de renderizado IDLE

---

## 🚀 Estado

**Completamente implementado y funcional** ✅

El panel se mostrará automáticamente cuando:
- El juego esté en estado IDLE
- Haya al menos 1 país con victorias en Supabase

Se actualizará automáticamente después de cada victoria sincronizada.
