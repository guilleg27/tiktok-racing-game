#!/usr/bin/env python3
"""
Test script for Global Ranking Panel functionality.
"""

import asyncio
import logging
from src.cloud_manager import CloudManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

async def test_global_ranking():
    """Test the global ranking fetch."""
    
    print("\n" + "="*70)
    print("  🏆 TEST: GLOBAL RANKING PANEL")
    print("="*70 + "\n")
    
    manager = CloudManager()
    
    if not manager.enabled:
        print("❌ CloudManager está deshabilitado. Verifica tu .env")
        return
    
    print("📊 Obteniendo ranking global (Top 3)...\n")
    
    ranking = await manager.get_global_ranking(limit=3)
    
    if not ranking:
        print("⚠️ No hay datos de ranking disponibles")
        print("   Ejecuta algunas carreras primero para generar datos\n")
        return
    
    print(f"✅ Ranking obtenido: {len(ranking)} países\n")
    print("━" * 70)
    print("🏆 RÉCORDS MUNDIALES")
    print("━" * 70)
    
    medals = ['🥇', '🥈', '🥉']
    
    for i, entry in enumerate(ranking):
        country = entry.get('country', 'Unknown')
        wins = entry.get('total_wins', 0)
        diamonds = entry.get('total_diamonds', 0)
        
        medal = medals[i] if i < 3 else f"{i+1}."
        
        # Get flag emoji
        flag_map = {
            'Argentina': '🇦🇷', 'Brasil': '🇧🇷', 'Mexico': '🇲🇽',
            'España': '🇪🇸', 'Colombia': '🇨🇴', 'Chile': '🇨🇱',
            'Peru': '🇵🇪', 'Venezuela': '🇻🇪'
        }
        flag = flag_map.get(country, '🏴')
        
        print(f"{medal} {flag} {country:12} - {wins:3} victorias | {diamonds:,} diamantes")
    
    print("━" * 70)
    print("\n✅ Test completado exitosamente")
    print("\nEste mismo ranking se mostrará en el juego (esquina superior derecha)")
    print("cuando esté en estado IDLE.\n")

if __name__ == "__main__":
    asyncio.run(test_global_ranking())
