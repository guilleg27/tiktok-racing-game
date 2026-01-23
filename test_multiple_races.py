#!/usr/bin/env python3
"""
Test para verificar que múltiples carreras se sincronizan correctamente.
Simula 3 carreras consecutivas.
"""

import asyncio
import logging
from src.cloud_manager import CloudManager
from dotenv import load_dotenv
import os
from supabase import create_client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

load_dotenv()

async def test_multiple_races():
    """Test de sincronización con múltiples carreras."""
    
    manager = CloudManager()
    client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
    
    if not manager.enabled:
        print("❌ CloudManager deshabilitado")
        return
    
    print("\n" + "="*70)
    print("  TEST: SINCRONIZACIÓN DE MÚLTIPLES CARRERAS")
    print("="*70 + "\n")
    
    # Obtener valores iniciales de Argentina
    initial = client.table('global_country_stats').select('*').eq('country', 'Argentina').execute()
    initial_wins = initial.data[0]['total_wins'] if initial.data else 0
    initial_diamonds = initial.data[0]['total_diamonds'] if initial.data else 0
    
    print(f"📊 Valores iniciales de Argentina:")
    print(f"   Total Wins: {initial_wins}")
    print(f"   Total Diamonds: {initial_diamonds}\n")
    
    # Simular 3 carreras
    races = [
        {"country": "Argentina", "captain": "test_captain_1", "diamonds": 1000},
        {"country": "Argentina", "captain": "test_captain_2", "diamonds": 1500},
        {"country": "Argentina", "captain": "test_captain_3", "diamonds": 2000},
    ]
    
    for i, race in enumerate(races, 1):
        print(f"\n{'─'*70}")
        print(f"🏁 CARRERA {i}/3")
        print(f"{'─'*70}")
        print(f"   País: {race['country']}")
        print(f"   Capitán: {race['captain']}")
        print(f"   Diamantes: {race['diamonds']}")
        
        # Sincronizar (simula lo que hace game_engine.py)
        result = await manager.sync_race_result(
            country=race['country'],
            winner_name=race['captain'],
            total_diamonds=race['diamonds'],
            streamer_name="test_streamer"
        )
        
        if result:
            print(f"   ✅ Sincronización exitosa")
            
            # Verificar que se actualizó
            current = client.table('global_country_stats').select('*').eq('country', race['country']).execute()
            if current.data:
                current_wins = current.data[0]['total_wins']
                current_diamonds = current.data[0]['total_diamonds']
                expected_wins = initial_wins + i
                expected_diamonds = initial_diamonds + sum(r['diamonds'] for r in races[:i])
                
                print(f"   📊 Stats actualizadas:")
                print(f"      Wins: {current_wins} (esperado: {expected_wins})")
                print(f"      Diamonds: {current_diamonds} (esperado: {expected_diamonds})")
                
                if current_wins == expected_wins and current_diamonds == expected_diamonds:
                    print(f"   ✅ Valores correctos")
                else:
                    print(f"   ❌ Valores incorrectos")
        else:
            print(f"   ❌ Sincronización falló")
        
        # Pequeña pausa entre carreras
        await asyncio.sleep(0.5)
    
    # Verificación final
    print(f"\n{'='*70}")
    print(f"  VERIFICACIÓN FINAL")
    print(f"{'='*70}\n")
    
    final = client.table('global_country_stats').select('*').eq('country', 'Argentina').execute()
    if final.data:
        final_wins = final.data[0]['total_wins']
        final_diamonds = final.data[0]['total_diamonds']
        expected_final_wins = initial_wins + 3
        expected_final_diamonds = initial_diamonds + 4500  # 1000 + 1500 + 2000
        
        print(f"📊 Argentina - Valores finales:")
        print(f"   Wins: {final_wins} (esperado: {expected_final_wins})")
        print(f"   Diamonds: {final_diamonds} (esperado: {expected_final_diamonds})")
        
        if final_wins == expected_final_wins and final_diamonds == expected_final_diamonds:
            print(f"\n✅ TEST PASADO: Todas las carreras se sincronizaron correctamente!")
        else:
            print(f"\n❌ TEST FALLIDO: Algunas carreras no se sincronizaron")
            print(f"   Diferencia Wins: {final_wins - expected_final_wins}")
            print(f"   Diferencia Diamonds: {final_diamonds - expected_final_diamonds}")
    
    # Limpiar datos de test
    print(f"\n🧹 Limpiando datos de test...")
    
    # Revertir cambios en country_stats
    client.table('global_country_stats').update({
        'total_wins': initial_wins,
        'total_diamonds': initial_diamonds
    }).eq('country', 'Argentina').execute()
    
    # Eliminar entradas de hall_of_fame
    for race in races:
        client.table('global_hall_of_fame').delete().eq('captain_name', race['captain']).execute()
    
    print(f"✅ Datos de test limpiados\n")

if __name__ == "__main__":
    asyncio.run(test_multiple_races())
