#!/usr/bin/env python3
"""
Test para simular múltiples carreras en el juego y verificar sincronización.
Simula el flujo real del game_engine.
"""

import asyncio
import logging
from src.cloud_manager import CloudManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class GameEngineSimulator:
    """Simula el comportamiento del game_engine para testing."""
    
    def __init__(self):
        self.cloud_manager = CloudManager()
        self.race_synced = False
        self.winner_animation_time = 0.0
        self.race_finished = False
        self.winner = None
        self.streamer_name = "test_streamer"
        
    async def simulate_race_win(self, country: str, captain: str, diamonds: int):
        """Simula una victoria en la carrera."""
        logger.info(f"\n{'='*70}")
        logger.info(f"🏁 NUEVA CARRERA: {country} - {captain}")
        logger.info(f"{'='*70}")
        
        # Simular estado pre-victoria
        self.race_finished = False
        self.winner = None
        self.race_synced = False
        self.winner_animation_time = 0.0
        
        logger.info(f"Estado inicial: race_synced={self.race_synced}, winner_animation_time={self.winner_animation_time:.4f}")
        
        # Simular victoria (se detecta el ganador)
        self.race_finished = True
        self.winner = country
        
        logger.info(f"🎯 Victoria detectada: {country}")
        
        # Simular varios frames de la animación (como en update())
        dt = 1/60  # 60 FPS
        
        for frame in range(10):  # Simular 10 frames
            if self.race_finished and self.winner:
                # Esta es la lógica EXACTA del game_engine.py líneas 1008-1023
                if not self.race_synced and self.winner_animation_time < dt * 2:
                    self.race_synced = True
                    
                    # Async sync to cloud
                    asyncio.create_task(
                        self.cloud_manager.sync_race_result(
                            country=country,
                            winner_name=captain,
                            total_diamonds=diamonds,
                            streamer_name=self.streamer_name
                        )
                    )
                    logger.info(f"☁️ Frame {frame}: Queued cloud sync (time={self.winner_animation_time:.4f}, threshold={dt*2:.4f})")
                elif frame == 0:
                    logger.warning(f"⚠️ Frame {frame}: NO sync (race_synced={self.race_synced}, time={self.winner_animation_time:.4f} >= {dt*2:.4f})")
                
                # Incrementar animation time (como en línea 1025)
                self.winner_animation_time += dt
        
        # Esperar a que termine la sincronización
        await asyncio.sleep(1)
        
        # Simular vuelta a IDLE (llamar a _return_to_idle)
        logger.info(f"🔄 Volviendo a IDLE...")
        self._return_to_idle()
        logger.info(f"Estado después de IDLE: race_synced={self.race_synced}, winner_animation_time={self.winner_animation_time:.4f}")
    
    def _return_to_idle(self):
        """Simula _return_to_idle() del game_engine."""
        self.race_synced = False
        self.winner_animation_time = 0.0
        self.race_finished = False
        self.winner = None

async def main():
    """Test principal."""
    print("\n" + "="*70)
    print("  🧪 TEST DE SINCRONIZACIÓN MÚLTIPLES CARRERAS")
    print("="*70 + "\n")
    
    sim = GameEngineSimulator()
    
    races = [
        ("Argentina", "captain_1", 1000),
        ("Brasil", "captain_2", 1500),
        ("Mexico", "captain_3", 2000),
    ]
    
    for i, (country, captain, diamonds) in enumerate(races, 1):
        print(f"\n{'#'*70}")
        print(f"# CARRERA {i}/3")
        print(f"{'#'*70}\n")
        
        await sim.simulate_race_win(country, captain, diamonds)
        
        # Pausa entre carreras
        await asyncio.sleep(0.5)
    
    print("\n" + "="*70)
    print("  ✅ TEST COMPLETADO")
    print("="*70 + "\n")
    
    # Verificar en Supabase
    print("Verificando en Supabase...")
    from dotenv import load_dotenv
    import os
    from supabase import create_client
    
    load_dotenv()
    client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
    
    # Ver últimas 5 carreras
    response = client.table('global_hall_of_fame').select('*').order('race_timestamp', desc=True).limit(5).execute()
    
    print("\n📊 Últimas carreras en Supabase:")
    for row in response.data[:5]:
        print(f"  - {row['captain_name']:15} | {row['country']:12} | {row['total_diamonds']:5}💎")
    
    # Limpiar datos de test
    print("\n🧹 Limpiando datos de test...")
    for country, captain, _ in races:
        client.table('global_hall_of_fame').delete().eq('captain_name', captain).execute()
    print("✅ Limpieza completada")

if __name__ == "__main__":
    asyncio.run(main())
