#!/usr/bin/env python3
"""
Verifica el estado de las políticas de RLS en Supabase.
"""

import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

def check_rls_status():
    """Verifica el estado de RLS en las tablas."""
    client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
    
    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║         VERIFICACIÓN DE POLÍTICAS DE SUPABASE               ║")
    print("╚══════════════════════════════════════════════════════════════╝\n")
    
    # Test 1: Intentar SELECT
    print("1️⃣ Test SELECT:")
    try:
        response = client.table('global_country_stats').select('*').limit(1).execute()
        print(f"   ✅ SELECT funciona (encontrados: {len(response.data)} registros)")
    except Exception as e:
        print(f"   ❌ SELECT falló: {e}")
    
    # Test 2: Intentar INSERT (en hall_of_fame para no afectar stats)
    print("\n2️⃣ Test INSERT:")
    try:
        test_data = {
            "country": "Argentina",
            "captain_name": "policy_test_temp",
            "total_diamonds": 1,
            "streamer_name": "test"
        }
        response = client.table('global_hall_of_fame').insert(test_data).execute()
        if response.data:
            print(f"   ✅ INSERT funciona")
            # Limpiar el test
            client.table('global_hall_of_fame').delete().eq('captain_name', 'policy_test_temp').execute()
        else:
            print(f"   ❌ INSERT no retornó datos")
    except Exception as e:
        print(f"   ❌ INSERT falló: {e}")
    
    # Test 3: Intentar UPDATE (el problemático)
    print("\n3️⃣ Test UPDATE:")
    try:
        # Primero obtener el valor actual
        response = client.table('global_country_stats').select('*').eq('country', 'Chile').execute()
        if response.data:
            current_wins = response.data[0]['total_wins']
            current_diamonds = response.data[0]['total_diamonds']
            
            print(f"   Valores actuales Chile: wins={current_wins}, diamonds={current_diamonds}")
            
            # Intentar actualizar (sin cambiar realmente los valores, solo last_updated)
            from datetime import datetime
            update_response = client.table('global_country_stats').update({
                'last_updated': datetime.now().isoformat()
            }).eq('country', 'Chile').execute()
            
            if update_response.data and len(update_response.data) > 0:
                print(f"   ✅ UPDATE funciona (response tiene datos)")
            elif not update_response.data or len(update_response.data) == 0:
                print(f"   ❌ UPDATE bloqueado por RLS (response vacío)")
                print(f"   👉 NECESITAS EJECUTAR fix_supabase_policies.sql")
            
            # Verificar si realmente se actualizó
            verify = client.table('global_country_stats').select('*').eq('country', 'Chile').execute()
            if verify.data:
                new_updated = verify.data[0].get('last_updated', '')
                if new_updated != response.data[0].get('last_updated', ''):
                    print(f"   ✅ UPDATE verificado (last_updated cambió)")
                else:
                    print(f"   ⚠️  UPDATE no cambió datos")
        else:
            print(f"   ❌ No se encontró el país Chile")
    except Exception as e:
        print(f"   ❌ UPDATE falló: {e}")
    
    # Test 4: Test completo de incremento
    print("\n4️⃣ Test INCREMENTO COMPLETO:")
    try:
        test_country = "Venezuela"
        
        # Obtener valores actuales
        response = client.table('global_country_stats').select('*').eq('country', test_country).execute()
        if response.data:
            current_wins = response.data[0]['total_wins']
            current_diamonds = response.data[0]['total_diamonds']
            
            print(f"   Antes: wins={current_wins}, diamonds={current_diamonds}")
            
            # Intentar incrementar
            new_wins = current_wins + 1
            new_diamonds = current_diamonds + 100
            
            update_response = client.table('global_country_stats').update({
                'total_wins': new_wins,
                'total_diamonds': new_diamonds,
                'last_updated': datetime.now().isoformat()
            }).eq('country', test_country).execute()
            
            # Verificar
            verify = client.table('global_country_stats').select('*').eq('country', test_country).execute()
            if verify.data:
                final_wins = verify.data[0]['total_wins']
                final_diamonds = verify.data[0]['total_diamonds']
                
                print(f"   Después: wins={final_wins}, diamonds={final_diamonds}")
                
                if final_wins == new_wins and final_diamonds == new_diamonds:
                    print(f"   ✅ INCREMENTO FUNCIONA PERFECTAMENTE!")
                    
                    # Revertir el cambio de test
                    client.table('global_country_stats').update({
                        'total_wins': current_wins,
                        'total_diamonds': current_diamonds
                    }).eq('country', test_country).execute()
                    print(f"   ℹ️  Test revertido (valores restaurados)")
                else:
                    print(f"   ❌ INCREMENTO NO FUNCIONÓ")
                    print(f"   👉 URGENTE: Ejecuta fix_supabase_policies.sql")
    except Exception as e:
        print(f"   ❌ Test de incremento falló: {e}")
    
    print("\n" + "="*64)
    print("\n💡 CONCLUSIÓN:")
    print("   Si ves '❌ UPDATE bloqueado por RLS' o '❌ INCREMENTO NO FUNCIONÓ':")
    print("   → Ejecuta fix_supabase_policies.sql en Supabase SQL Editor")
    print("   → Ver FIX_INSTRUCTIONS.md para pasos detallados\n")

if __name__ == "__main__":
    check_rls_status()
