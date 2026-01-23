# 🔧 INSTRUCCIONES PARA ARREGLAR SUPABASE

## 🐛 Problema Detectado

El UPDATE a `global_country_stats` **está siendo bloqueado por las políticas de RLS (Row Level Security)**.

**Síntomas:**
- ✅ `hall_of_fame` funciona correctamente
- ❌ `global_country_stats` no se actualiza (permanece en 0)
- ⚠️ El `last_updated` sí cambia (UPDATE se ejecuta pero sin modificar wins/diamonds)

## ✅ Solución

### Opción 1: Ejecutar SQL en Supabase Dashboard (RECOMENDADO)

1. **Ir a Supabase Dashboard:**
   - https://supabase.com/dashboard
   - Selecciona tu proyecto

2. **Abrir SQL Editor:**
   - Click en "SQL Editor" en el menú lateral
   - Click en "New query"

3. **Copiar y pegar este SQL:**

```sql
-- Eliminar políticas conflictivas
DROP POLICY IF EXISTS "Allow public read access" ON global_country_stats;
DROP POLICY IF EXISTS "Allow public insert/update access" ON global_country_stats;
DROP POLICY IF EXISTS "Allow public write on country stats" ON global_country_stats;

-- Crear políticas correctas
CREATE POLICY "Enable read access for all users" 
ON global_country_stats FOR SELECT USING (true);

CREATE POLICY "Enable insert access for all users" 
ON global_country_stats FOR INSERT WITH CHECK (true);

CREATE POLICY "Enable update access for all users" 
ON global_country_stats FOR UPDATE USING (true) WITH CHECK (true);

-- Verificar políticas hall_of_fame
DROP POLICY IF EXISTS "Allow public read access hall" ON global_hall_of_fame;
DROP POLICY IF EXISTS "Allow public insert access hall" ON global_hall_of_fame;

CREATE POLICY "Enable read access for all users hall" 
ON global_hall_of_fame FOR SELECT USING (true);

CREATE POLICY "Enable insert access for all users hall" 
ON global_hall_of_fame FOR INSERT WITH CHECK (true);
```

4. **Ejecutar (Run):**
   - Click en el botón "Run" o presiona `Ctrl + Enter`
   - Deberías ver: "Success. No rows returned"

### Opción 2: Desactivar RLS Temporalmente (TESTING ONLY)

Si quieres probar rápidamente sin políticas:

```sql
-- SOLO PARA TESTING - NO RECOMENDADO EN PRODUCCIÓN
ALTER TABLE global_country_stats DISABLE ROW LEVEL SECURITY;
ALTER TABLE global_hall_of_fame DISABLE ROW LEVEL SECURITY;
```

⚠️ **Advertencia:** Esto desactiva la seguridad. Solo para pruebas.

## 🧪 Verificar que Funcionó

Después de ejecutar el SQL:

```bash
# 1. Ejecutar test
python debug_sync_detailed.py

# Deberías ver:
# ✅ UPDATE funcionó correctamente!

# 2. Ejecutar sync completo
python debug_sync.py

# 3. Verificar en Supabase
python -c "
from dotenv import load_dotenv
import os
from supabase import create_client

load_dotenv()
client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

response = client.table('global_country_stats').select('*').eq('country', 'Brasil').execute()
print(f\"Brasil - Wins: {response.data[0]['total_wins']}, Diamonds: {response.data[0]['total_diamonds']}\")
"
```

**Resultado esperado:**
- Brasil debe tener `total_wins: 1` y `total_diamonds: 999`

## 📊 Verificar Políticas Actuales

Para ver las políticas actuales en Supabase:

```sql
SELECT tablename, policyname, cmd, qual, with_check
FROM pg_policies 
WHERE tablename IN ('global_country_stats', 'global_hall_of_fame')
ORDER BY tablename, policyname;
```

## 🎯 Root Cause

Las políticas de RLS creadas en el setup inicial probablemente tenían:
- ❌ `FOR ALL` en lugar de políticas separadas para `SELECT`, `INSERT`, `UPDATE`
- ❌ Conflictos entre múltiples políticas
- ❌ Falta de `USING (true) WITH CHECK (true)` en UPDATE

Las nuevas políticas:
- ✅ Política específica para UPDATE con ambos `USING` y `WITH CHECK`
- ✅ Políticas separadas por operación (SELECT, INSERT, UPDATE)
- ✅ Sin conflictos

---

**Después de aplicar el fix:**
1. El juego sincronizará correctamente
2. `global_country_stats` se actualizará con cada victoria
3. Todos los tests deberían pasar
