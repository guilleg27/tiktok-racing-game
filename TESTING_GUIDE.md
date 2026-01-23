# 🧪 Guía de Testing del Juego

## Scripts de Test Disponibles

### 1. `check_policies.py` - Verificación de Políticas RLS
**Propósito:** Verifica que las políticas de Row Level Security de Supabase estén configuradas correctamente.

**Cuándo usar:**
- Después de configurar Supabase por primera vez
- Si sospechas problemas con permisos de UPDATE/INSERT
- Después de modificar políticas en Supabase

**Uso:**
```bash
python check_policies.py
```

**Resultado esperado:**
```
✅ SELECT funciona
✅ INSERT funciona
✅ UPDATE funciona
✅ INCREMENTO FUNCIONA PERFECTAMENTE!
```

---

### 2. `test_multiple_races.py` - Test de Múltiples Carreras
**Propósito:** Verifica que múltiples carreras consecutivas se sincronicen correctamente.

**Cuándo usar:**
- Para verificar que el fix de sincronización funciona
- Antes de un stream importante
- Después de modificar la lógica de sincronización

**Uso:**
```bash
python test_multiple_races.py
```

**Resultado esperado:**
```
🏁 CARRERA 1/3 → ✅ Sincronización exitosa
🏁 CARRERA 2/3 → ✅ Sincronización exitosa
🏁 CARRERA 3/3 → ✅ Sincronización exitosa
✅ TEST PASADO: Todas las carreras se sincronizaron correctamente!
```

---

### 3. `test_cloud_manager.py` - Tests Unitarios del CloudManager
**Propósito:** Tests unitarios completos del módulo `CloudManager` usando mocks.

**Cuándo usar:**
- Durante desarrollo de nuevas features en CloudManager
- Para CI/CD
- Para verificar lógica sin conexión a Supabase

**Uso:**
```bash
python -m pytest test_cloud_manager.py -v
# o
python -m unittest test_cloud_manager.py
```

**Tests incluidos:**
- Singleton pattern
- Inicialización con/sin env vars
- Sincronización de resultados
- Manejo de errores de red
- Non-blocking behavior

---

### 4. `test_e2e_cloud_sync.py` - Test End-to-End
**Propósito:** Test completo de integración que verifica todo el flujo de sincronización.

**Cuándo usar:**
- Después de cambios importantes en CloudManager o game_engine
- Antes de releases
- Para verificar integración completa

**Uso:**
```bash
python test_e2e_cloud_sync.py
```

**Verifica:**
- Inicialización de CloudManager
- Conexión directa a Supabase
- Sincronización de carreras
- Queries de leaderboard y stats
- Comportamiento non-blocking
- Limpieza de datos de test

---

### 5. `test_audio.py` - Test del Sistema de Audio
**Propósito:** Verifica que el sistema de audio y recursos funcione correctamente.

**Cuándo usar:**
- Después de agregar nuevos sonidos
- Si hay problemas con audio en el juego
- Para verificar `resource_path()` funciona

**Uso:**
```bash
python test_audio.py
```

---

### 6. `test_resources.py` - Test del Sistema de Recursos
**Propósito:** Verifica que el sistema de carga de recursos (imágenes, fuentes, etc.) funcione.

**Cuándo usar:**
- Después de agregar nuevos assets
- Si hay problemas cargando recursos
- Para verificar compatibilidad con PyInstaller

**Uso:**
```bash
python test_resources.py
```

---

## 🔄 Workflow de Testing

### Testing Rápido (Pre-Stream)
```bash
# 1. Verificar conexión y políticas
python check_policies.py

# 2. Verificar múltiples carreras
python test_multiple_races.py
```

Si ambos pasan → **Listo para stream** ✅

---

### Testing Completo (Pre-Release)
```bash
# 1. Tests unitarios
python -m pytest test_cloud_manager.py -v

# 2. Test E2E
python test_e2e_cloud_sync.py

# 3. Verificar políticas
python check_policies.py

# 4. Test de múltiples carreras
python test_multiple_races.py

# 5. Tests de recursos
python test_audio.py
python test_resources.py
```

Si todos pasan → **Listo para release** 🚀

---

## 🐛 Troubleshooting con Tests

### Problema: "UPDATE bloqueado por RLS"
```bash
python check_policies.py
# Si muestra: ❌ UPDATE bloqueado por RLS
# Solución: Ejecutar fix_supabase_policies.sql en Supabase
```

### Problema: "Solo la primera carrera se sincroniza"
```bash
python test_multiple_races.py
# Si falla en carrera 2 o 3:
# Revisar que winner_animation_time se resetee en _return_to_idle()
```

### Problema: "CloudManager deshabilitado"
```bash
python check_policies.py
# Si muestra: CloudManager enabled: False
# Solución: Verificar .env tiene SUPABASE_URL y SUPABASE_KEY
```

### Problema: "Linter errors"
```bash
# Verificar imports y sintaxis
python -m pylint src/cloud_manager.py
python -m mypy src/cloud_manager.py
```

---

## 📊 Verificación Manual en Supabase

Después de ejecutar los tests (o después de jugar):

```bash
# Ver stats de países
python -c "
from dotenv import load_dotenv
import os
from supabase import create_client

load_dotenv()
client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

print('=== COUNTRY STATS ===')
response = client.table('global_country_stats').select('*').order('total_wins', desc=True).execute()
for row in response.data:
    print(f\"{row['country']:12} | Wins: {row['total_wins']:3} | Diamonds: {row['total_diamonds']:6}\")

print('\n=== HALL OF FAME (Top 10) ===')
response = client.table('global_hall_of_fame').select('*').order('total_diamonds', desc=True).limit(10).execute()
for i, row in enumerate(response.data, 1):
    print(f\"{i:2}. {row['captain_name']:20} | {row['total_diamonds']:5}💎 | {row['country']}\")
"
```

---

## ✅ Checklist Pre-Stream

- [ ] `python check_policies.py` → Todos ✅
- [ ] `python test_multiple_races.py` → ✅ TEST PASADO
- [ ] Verificar `.env` tiene credenciales correctas
- [ ] Verificar logs del último stream para errores de sync
- [ ] Opcional: Limpiar datos de test en Supabase

---

## 🚀 Checklist Pre-Release

- [ ] Todos los tests unitarios pasan
- [ ] Test E2E pasa
- [ ] Políticas RLS verificadas
- [ ] Test de múltiples carreras pasa
- [ ] Tests de recursos pasan
- [ ] Documentación actualizada
- [ ] CHANGELOG actualizado
- [ ] Version bump en archivos relevantes

---

## 📝 Notas

- **Tests con `pytest`:** Usa `-v` para verbose, `-s` para ver prints
- **Tests con `unittest`:** Usa `-v` para verbose
- **Cleanup:** Los tests limpian sus datos automáticamente
- **Network:** Tests de Supabase requieren conexión a internet
- **Mocks:** `test_cloud_manager.py` NO requiere Supabase real

---

## 🆘 Ayuda

Si un test falla:
1. Lee el mensaje de error completo
2. Verifica que `.env` esté configurado
3. Verifica conexión a internet (para tests de Supabase)
4. Consulta `SYNC_FIX_SUMMARY.md` para fixes conocidos
5. Consulta `CLOUD_INTEGRATION.md` para detalles técnicos

Para más información:
- `DOCS_INDEX.md` - Índice de toda la documentación
- `QUICK_START.md` - Guía rápida de inicio
- `CLOUD_INTEGRATION.md` - Detalles técnicos de Supabase
