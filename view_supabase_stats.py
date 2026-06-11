#!/usr/bin/env python3
"""
Quick viewer para ver el estado actual de las tablas de Supabase.
Útil para verificar que las carreras se están sincronizando.
"""

import os
from dotenv import load_dotenv
from supabase import create_client
from datetime import datetime

load_dotenv()

def view_stats(client):
    """Muestra un resumen visual del estado de Supabase."""
    
    print("\n" + "="*70)
    print("  📊 ESTADO ACTUAL DE SUPABASE")
    print("="*70 + "\n")
    
    # Country Stats
    print("🌍 COUNTRY STATS (Ordenado por victorias)")
    print("─"*70)
    
    response = client.table('global_country_stats').select('*').order('total_wins', desc=True).execute()
    
    if response.data:
        print(f"{'País':15} | {'Victorias':10} | {'Diamantes':12} | {'Última Act.'}")
        print("─"*70)
        
        for row in response.data:
            last_updated = row.get('last_updated', 'N/A')
            if last_updated != 'N/A':
                try:
                    dt = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                    last_updated = dt.strftime('%Y-%m-%d %H:%M')
                except:
                    pass
            
            print(f"{row['country']:15} | {row['total_wins']:10} | {row['total_diamonds']:12} | {last_updated}")
        
        total_wins = sum(r['total_wins'] for r in response.data)
        total_diamonds = sum(r['total_diamonds'] for r in response.data)
        
        print("─"*70)
        print(f"{'TOTAL':15} | {total_wins:10} | {total_diamonds:12} |")
    else:
        print("   (Sin datos)")
    
    # Hall of Fame
    print("\n\n🏆 HALL OF FAME (Top 15)")
    print("─"*70)
    
    response = client.table('global_hall_of_fame').select('*').order('total_diamonds', desc=True).limit(15).execute()
    
    if response.data:
        print(f"{'#':3} | {'Capitán':20} | {'Diamantes':10} | {'País':12} | {'Fecha'}")
        print("─"*70)
        
        for i, row in enumerate(response.data, 1):
            timestamp = row.get('race_timestamp', 'N/A')
            if timestamp != 'N/A':
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    timestamp = dt.strftime('%Y-%m-%d %H:%M')
                except:
                    pass
            
            print(f"{i:3} | {row['captain_name']:20} | {row['total_diamonds']:10} 💎 | {row['country']:12} | {timestamp}")
        
        print("─"*70)
        print(f"Total registros: {len(response.data)}")
        
        # Contar total de registros
        count_response = client.table('global_hall_of_fame').select('*', count='exact').execute()
        total_records = count_response.count if hasattr(count_response, 'count') else len(response.data)
        print(f"Total carreras en historial: {total_records}")
    else:
        print("   (Sin datos)")
    
    # Últimas 5 carreras
    print("\n\n🕐 ÚLTIMAS 5 CARRERAS")
    print("─"*70)
    
    response = client.table('global_hall_of_fame').select('*').order('race_timestamp', desc=True).limit(5).execute()
    
    if response.data:
        for i, row in enumerate(response.data, 1):
            timestamp = row.get('race_timestamp', 'N/A')
            if timestamp != 'N/A':
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
                except:
                    pass
            
            print(f"{i}. {timestamp} | {row['country']:12} | {row['captain_name']:20} | {row['total_diamonds']:5} 💎")
    else:
        print("   (Sin datos)")
    
    print("\n" + "="*70 + "\n")

def view_fulbito_stats(client):
    """Muestra estadísticas de la variante Fulbito — Mundial 2026."""
    print("\n" + "="*70)
    print("  ⚽ FULBITO — MUNDIAL 2026")
    print("="*70 + "\n")

    # ── Tabla de posiciones acumulativa ──────────────────────────────────
    print("🏆 TABLA DE POSICIONES (por victorias)")
    print("─"*70)

    response = client.table('match_results') \
        .select('winner') \
        .eq('variant', 'fulbito') \
        .execute()

    if response.data:
        from collections import Counter
        wins = Counter(r['winner'] for r in response.data if r['winner'])
        print(f"{'#':3} | {'País':15} | {'Victorias':10}")
        print("─"*70)
        for i, (country, count) in enumerate(wins.most_common(), 1):
            print(f"{i:3} | {country:15} | {count:10}")
        print("─"*70)
        print(f"Total partidos: {len(response.data)}")
    else:
        print("   (Sin datos)")

    # ── Últimos 10 partidos ───────────────────────────────────────────────
    print("\n\n🕐 ÚLTIMOS 10 PARTIDOS")
    print("─"*70)

    response = client.table('match_results') \
        .select('*') \
        .eq('variant', 'fulbito') \
        .order('date', desc=True) \
        .limit(10) \
        .execute()

    if response.data:
        print(f"{'Fecha':18} | {'Equipos':35} | {'Ganador':10} | {'Duración'}")
        print("─"*70)
        for row in response.data:
            date = row.get('date', 'N/A')
            try:
                dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
                date = dt.strftime('%Y-%m-%d %H:%M')
            except Exception:
                pass
            teams = ' vs '.join(filter(None, [
                row.get('team_a'), row.get('team_b'),
                row.get('team_c'), row.get('team_d'),
            ]))
            winner = row.get('winner', 'N/A')
            dur = row.get('duration_secs', '?')
            print(f"{date:18} | {teams:35} | {winner:10} | {dur}s")
    else:
        print("   (Sin datos)")

    # ── Top donadores ─────────────────────────────────────────────────────
    print("\n\n💎 TOP DONADORES")
    print("─"*70)

    response = client.table('live_gift_events') \
        .select('username, diamond_count, gift_count') \
        .eq('variant', 'fulbito') \
        .execute()

    if response.data:
        from collections import defaultdict
        totals = defaultdict(int)
        for r in response.data:
            totals[r['username']] += r['diamond_count'] * r['gift_count']
        sorted_donors = sorted(totals.items(), key=lambda x: x[1], reverse=True)
        print(f"{'#':3} | {'Viewer':25} | {'Diamantes':10}")
        print("─"*70)
        for i, (username, diamonds) in enumerate(sorted_donors[:10], 1):
            print(f"{i:3} | {username:25} | {diamonds:10} 💎")
    else:
        print("   (Sin datos)")

    # ── Sesiones ──────────────────────────────────────────────────────────
    print("\n\n📋 SESIONES")
    print("─"*70)

    response = client.table('session_summary') \
        .select('*') \
        .eq('variant', 'fulbito') \
        .order('date', desc=True) \
        .limit(10) \
        .execute()

    if response.data:
        print(f"{'Fecha':18} | {'Partidos':9} | {'Diamonds':9} | {'Viewers':8} | {'Top País'}")
        print("─"*70)
        for row in response.data:
            date = row.get('date', 'N/A')
            try:
                dt = datetime.fromisoformat(date.replace('Z', '+00:00'))
                date = dt.strftime('%Y-%m-%d %H:%M')
            except Exception:
                pass
            print(f"{date:18} | {row.get('total_races', 0):9} | "
                  f"{row.get('total_diamonds', 0):9} | "
                  f"{row.get('unique_viewers', 0):8} | "
                  f"{row.get('top_country', '?')}")
    else:
        print("   (Sin datos)")

    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    try:
        client = create_client(
            os.getenv('SUPABASE_URL'),
            os.getenv('SUPABASE_KEY'),
        )
        view_stats(client)
        view_fulbito_stats(client)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nVerifica que:")
        print("  - El archivo .env existe y tiene SUPABASE_URL y SUPABASE_KEY")
        print("  - Tienes conexión a internet")
        print("  - Las credenciales de Supabase son válidas\n")
