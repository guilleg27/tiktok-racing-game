# 🔍 Troubleshooting: Carreras No Se Guardan

## ✅ Verificación: El Código Está Correcto

El test `test_game_sync.py` confirma que el código funciona correctamente:
- Carrera 1 → ✅ Sincronizada
- Carrera 2 → ✅ Sincronizada  
- Carrera 3 → ✅ Sincronizada

## 🐛 Posibles Causas Si No Funciona en el Juego

### 1. Juego Usando Código Viejo (MÁS PROBABLE)

**Problema:** El juego está cargado en memoria con el código antiguo (antes del fix).

**Solución:**
```bash
# 1. Cerrar COMPLETAMENTE el juego si está corriendo
# 2. Reiniciar el juego
python main.py --idle
```

⚠️ **IMPORTANTE:** Python cachea los módulos. Si modificaste el código mientras el juego estaba corriendo, necesitas reiniciarlo completamente.

---

### 2. Verificar Que Los Cambios Estén en el Archivo

**Ejecuta esto para verificar:**
```bash
grep -n "Reset winner animation time" src/game_engine.py
```

**Debe mostrar:**
```
2052:        # 🎬 Reset winner animation time for next race
```

Si NO aparece, el archivo no tiene los cambios. Aplícalos manualmente.

---

### 3. Las Carreras No Llegan a Estado IDLE

**Problema:** Si presionas teclas o haces acciones antes de que la carrera termine completamente y vuelva a IDLE, el reset no se ejecuta.

**Cómo funciona:**
```
Victoria detectada → Animación (~10 segundos) → Vuelve a IDLE → Reset flags
```

**Solución:** Espera a que la animación de victoria termine completamente antes de empezar la siguiente carrera.

---

### 4. Logs No Se Ven Pero Sí Se Sincroniza

**Problema:** Los logs no aparecen en consola pero la sincronización sí ocurre en segundo plano.

**Verificación:**
```bash
# Mientras el juego corre, en otra terminal:
python view_supabase_stats.py

# Deberías ver las carreras incrementándose
```

---

## 🧪 Test de Diagnóstico

Ejecuta esto MIENTRAS el juego corre en otra terminal:

```bash
# Terminal 1: Iniciar el juego
python main.py --idle

# Terminal 2: Monitorear sincronización
watch -n 2 "python view_supabase_stats.py"
```

Luego en el juego:
1. Presiona `T` varias veces para simular regalos
2. Deja que la carrera termine COMPLETAMENTE
3. Espera a ver "Game state: IDLE" en los logs
4. Repite 2-3 veces

**En Terminal 2** deberías ver incrementarse los números.

---

## 📊 Verificar Sincronización Manualmente

Después de cada carrera, ejecuta:

```bash
python -c "
from dotenv import load_dotenv
import os
from supabase import create_client

load_dotenv()
client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# Última carrera
response = client.table('global_hall_of_fame').select('*').order('race_timestamp', desc=True).limit(1).execute()
if response.data:
    row = response.data[0]
    print(f'Última carrera: {row[\"captain_name\"]} - {row[\"country\"]} - {row[\"total_diamonds\"]}💎')
    print(f'Timestamp: {row[\"race_timestamp\"]}')
else:
    print('No hay carreras registradas')
"
```

---

## 🔬 Debug Profundo

Si ninguna de las soluciones anteriores funciona, activa el debug logging:

1. **Modificar temporalmente** `src/game_engine.py` línea 1008:

```python
# ANTES:
if not self.race_synced and self.winner_animation_time < dt * 2:

# AGREGAR DEBUG (temporalmente):
logger.info(f"🔍 DEBUG: race_synced={self.race_synced}, winner_time={self.winner_animation_time:.4f}, threshold={dt*2:.4f}")
if not self.race_synced and self.winner_animation_time < dt * 2:
```

2. **Reiniciar el juego** y observar los logs

3. Deberías ver cada frame:
```
🔍 DEBUG: race_synced=False, winner_time=0.0000, threshold=0.0333
☁️ Queued cloud sync: ...
```

---

## ✅ Checklist de Verificación

Ejecuta estos comandos en orden:

```bash
# 1. Verificar que el código tiene los cambios
echo "=== Verificando código ==="
grep -A 2 "Reset winner animation time" src/game_engine.py

# 2. Verificar CloudManager funciona
echo "=== Testing CloudManager ==="
python test_multiple_races.py

# 3. Verificar estado de Supabase
echo "=== Estado actual Supabase ==="
python view_supabase_stats.py
```

**Resultados esperados:**
1. Debe aparecer "Reset winner animation time" en línea ~2052
2. Test debe pasar con "✅ TEST PASADO"
3. Debe mostrar estadísticas actuales

---

## 💡 Si Nada Funciona

Ejecuta el test simulado que copia EXACTAMENTE la lógica del juego:

```bash
python test_game_sync.py
```

Si este test pasa pero el juego no funciona, entonces:
- ✅ El código de sincronización está bien
- ❌ Hay un problema en cómo `_return_to_idle()` se llama en el juego real

En ese caso, agregaremos más logs para rastrear exactamente cuándo se llama `_return_to_idle()`.

---

## 📞 Información para Reportar

Si después de todo esto sigue sin funcionar, provee:

1. **Logs completos** de una sesión donde corras 2-3 carreras
2. **Output de:**
   ```bash
   grep -n "def _return_to_idle" src/game_engine.py
   grep -n "Reset winner animation time" src/game_engine.py
   ```
3. **Resultado de:**
   ```bash
   python test_game_sync.py
   python test_multiple_races.py
   ```
4. **Cómo estás probando:** ¿Presionando T? ¿Con TikTok real? ¿Cuánto esperas entre carreras?
