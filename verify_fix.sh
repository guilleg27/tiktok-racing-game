#!/bin/bash

echo ""
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                                                                  ║"
echo "║         🔍 VERIFICACIÓN DEL FIX DE SINCRONIZACIÓN               ║"
echo "║                                                                  ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# Colores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Verificar que el fix está en el código
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1️⃣  Verificando que el fix está en el código..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if grep -q "Reset winner animation time for next race" src/game_engine.py; then
    echo -e "${GREEN}✅ Fix encontrado en el código${NC}"
    LINE=$(grep -n "self.winner_animation_time = 0.0" src/game_engine.py | tail -1 | cut -d: -f1)
    echo "   Ubicación: línea $LINE en _return_to_idle()"
else
    echo -e "${RED}❌ Fix NO encontrado${NC}"
    echo "   El código no tiene el fix aplicado"
    exit 1
fi

# 2. Verificar que _return_to_idle resetea el flag
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "2️⃣  Verificando reset de race_synced..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Buscar _return_to_idle y verificar que resetea race_synced
python3 << 'PYEOF'
with open('src/game_engine.py', 'r') as f:
    lines = f.readlines()

in_function = False
found_race_synced = False
found_winner_time = False

for i, line in enumerate(lines):
    if 'def _return_to_idle' in line:
        in_function = True
    elif in_function:
        if 'self.race_synced = False' in line:
            found_race_synced = True
        if 'self.winner_animation_time = 0.0' in line:
            found_winner_time = True
        if line.strip().startswith('def ') and 'def _return_to_idle' not in line:
            break

if found_race_synced and found_winner_time:
    print("\033[0;32m✅ _return_to_idle() resetea correctamente:\033[0m")
    print("   - race_synced = False")
    print("   - winner_animation_time = 0.0")
else:
    print("\033[0;31m❌ _return_to_idle() NO resetea correctamente\033[0m")
    if not found_race_synced:
        print("   ❌ Falta: race_synced = False")
    if not found_winner_time:
        print("   ❌ Falta: winner_animation_time = 0.0")
PYEOF

# 3. Ejecutar test de múltiples carreras
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "3️⃣  Ejecutando test de múltiples carreras..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

source venv/bin/activate 2>/dev/null || true

python test_game_sync.py 2>&1 | grep -E "(CARRERA|Queued cloud sync|Synced to cloud|TEST COMPLETADO)" | head -20

# 4. Estado actual de Supabase
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "4️⃣  Estado actual de Supabase..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

python view_supabase_stats.py 2>/dev/null | head -30

# Resumen final
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ RESUMEN"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Si todos los checks pasaron:"
echo -e "${GREEN}→ El código está correcto${NC}"
echo -e "${GREEN}→ Los tests funcionan${NC}"
echo ""
echo -e "${YELLOW}Si el juego aún no funciona:${NC}"
echo "→ REINICIA el juego completamente (cierra y abre de nuevo)"
echo "→ Presiona T varias veces"
echo "→ ESPERA a que termine la animación (~10 segundos)"
echo "→ Verifica que veas: '🎮 Game state: IDLE'"
echo "→ Repite para 2-3 carreras"
echo ""
echo "Luego ejecuta:"
echo "  python view_supabase_stats.py"
echo ""
