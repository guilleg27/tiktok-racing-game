-- ============================================
-- FIX: Políticas de RLS para global_country_stats
-- ============================================

-- 1. Eliminar políticas existentes que puedan estar causando conflictos
DROP POLICY IF EXISTS "Allow public read access" ON global_country_stats;
DROP POLICY IF EXISTS "Allow public insert/update access" ON global_country_stats;
DROP POLICY IF EXISTS "Allow public write on country stats" ON global_country_stats;

-- 2. Crear políticas correctas

-- Permitir SELECT público
CREATE POLICY "Enable read access for all users" 
ON global_country_stats
FOR SELECT 
USING (true);

-- Permitir INSERT público
CREATE POLICY "Enable insert access for all users" 
ON global_country_stats
FOR INSERT 
WITH CHECK (true);

-- Permitir UPDATE público (CRÍTICO - esta es la que faltaba funcionar correctamente)
CREATE POLICY "Enable update access for all users" 
ON global_country_stats
FOR UPDATE 
USING (true)
WITH CHECK (true);

-- 3. Verificar para hall_of_fame también
DROP POLICY IF EXISTS "Allow public read access hall" ON global_hall_of_fame;
DROP POLICY IF EXISTS "Allow public insert access hall" ON global_hall_of_fame;
DROP POLICY IF EXISTS "Allow public delete access hall" ON global_hall_of_fame;

-- Políticas para hall_of_fame
CREATE POLICY "Enable read access for all users hall" 
ON global_hall_of_fame
FOR SELECT 
USING (true);

CREATE POLICY "Enable insert access for all users hall" 
ON global_hall_of_fame
FOR INSERT 
WITH CHECK (true);

CREATE POLICY "Enable delete access for all users hall" 
ON global_hall_of_fame
FOR DELETE 
USING (true);

-- ============================================
-- Verificación: Mostrar políticas activas
-- ============================================
SELECT 
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd,
    qual,
    with_check
FROM pg_policies 
WHERE tablename IN ('global_country_stats', 'global_hall_of_fame')
ORDER BY tablename, policyname;
