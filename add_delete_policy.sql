-- ============================================
-- Agregar política DELETE para hall_of_fame
-- ============================================

-- Eliminar política existente si hay
DROP POLICY IF EXISTS "Allow public delete access hall" ON global_hall_of_fame;
DROP POLICY IF EXISTS "Enable delete access for all users hall" ON global_hall_of_fame;

-- Crear política DELETE
CREATE POLICY "Enable delete access for all users hall" 
ON global_hall_of_fame
FOR DELETE 
USING (true);

-- También agregar DELETE para country_stats por si acaso
DROP POLICY IF EXISTS "Enable delete access for all users" ON global_country_stats;

CREATE POLICY "Enable delete access for all users" 
ON global_country_stats
FOR DELETE 
USING (true);

-- Verificar políticas activas
SELECT 
    tablename,
    policyname,
    cmd
FROM pg_policies 
WHERE tablename IN ('global_country_stats', 'global_hall_of_fame')
ORDER BY tablename, cmd;
