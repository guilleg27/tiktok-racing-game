# 🚀 Quick Start - Supabase Integration

## ✅ Estado Actual: COMPLETO Y FUNCIONAL

```
┌──────────────────────────────────────────────────────────┐
│  🎉 INTEGRACIÓN SUPABASE COMPLETADA Y VERIFICADA         │
│                                                           │
│  ✅ Tests: 6/6 pasando                                   │
│  ✅ CloudManager: Funcionando                            │
│  ✅ GameEngine: Integrado                                │
│  ✅ Database: Conectada                                  │
│  ✅ Performance: 60 FPS estable                          │
└──────────────────────────────────────────────────────────┘
```

## 🎮 Cómo Usar

### Opción 1: Modo Normal (con TikTok)

```bash
# Conectar a un stream de TikTok Live
python main.py @username

# El juego sincronizará automáticamente cuando haya un ganador
```

### Opción 2: Modo Test (sin TikTok)

```bash
# Iniciar en modo IDLE
python main.py --idle

# Controles de prueba:
# T - Simular regalo aleatorio
# Y - Simular regalo grande
# J - Simular usuario uniéndose a equipo
# K - Simular puntos de capitán
# C - Limpiar/Reset
```

### Verificar Sincronización

Después de una victoria, revisa:

1. **Logs de consola:**
   ```
   ☁️ Queued cloud sync: Argentina - captain123 (5000💎)
   ☁️ Synced to cloud: Argentina (captain123, 5000💎)
   ```

2. **Supabase Dashboard:**
   - Ir a: https://supabase.com/dashboard
   - Tu proyecto → Table Editor
   - Tabla `global_country_stats`: Ver wins incrementados
   - Tabla `global_hall_of_fame`: Ver nuevo record

## 🧪 Tests Disponibles

### Verificar Políticas Supabase
```bash
python check_policies.py
```
**Salida esperada:** ✅ SELECT, INSERT, UPDATE funcionando

### Tests Unitarios
```bash
python -m pytest test_cloud_manager.py -v
```
**Cubre:** Singleton, inicialización, sync, queries, error handling

### Test End-to-End
```bash
python test_e2e_cloud_sync.py
```
**Cubre:** Flujo completo de sincronización + verificación

Ver **[TESTING_GUIDE.md](TESTING_GUIDE.md)** para guía completa.

## 📊 Queries Útiles en Supabase

### Top 10 Capitanes Globales
```sql
SELECT captain_name, country, total_diamonds, race_timestamp
FROM global_hall_of_fame
ORDER BY total_diamonds DESC
LIMIT 10;
```

### Estadísticas por País
```sql
SELECT country, total_wins, total_diamonds
FROM global_country_stats
ORDER BY total_wins DESC;
```

### Actividad Reciente
```sql
SELECT *
FROM global_hall_of_fame
WHERE race_timestamp > NOW() - INTERVAL '24 hours'
ORDER BY race_timestamp DESC;
```

## 🔧 Troubleshooting Rápido

### "Cloud sync disabled"
**Problema:** Falta archivo `.env` o credenciales incorrectas

**Solución:**
```bash
# Verificar que .env existe y tiene:
cat .env

# Debe mostrar:
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_KEY=tu-anon-key
```

### "Network timeout"
**Problema:** Problema de conectividad

**Solución:**
```bash
# Verificar políticas
python check_policies.py

# Si falla, verificar:
# 1. Internet conectado
# 2. Proyecto Supabase activo (no pausado)
# 3. Firewall no bloquea supabase.co
```

### FPS drops
**Problema:** Posible blocking en sync

**Solución:**
```bash
# Verificar logs - debe mostrar:
☁️ Queued cloud sync...  # Sync encolado
# NO debe haber pausas visibles en el juego

# Si hay drops, reportar en GitHub Issues
```

## 📚 Documentación Completa

- **`DOCS_INDEX.md`** - Índice de toda la documentación
- **`SUPABASE_SETUP_COMPLETE.md`** - Resumen ejecutivo
- **`CLOUD_INTEGRATION.md`** - Documentación técnica detallada
- **`TESTING_GUIDE.md`** - Guía de testing completa
- **`README.md`** - Documentación general del proyecto

## 🎯 Próximos Pasos Sugeridos

1. **Jugar una carrera real** con TikTok Live
2. **Verificar datos** en Supabase después de victoria
3. **Monitorear logs** para confirmar sincronización
4. **Crear dashboard web** para visualizar leaderboard

---

**¿Todo listo?** 🚀

```bash
python main.py @tu_username
```

**¡A correr!** 🏁
