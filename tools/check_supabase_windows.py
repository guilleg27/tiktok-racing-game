#!/usr/bin/env python3
"""
Diagnostico de conexion Supabase para Windows.
Correr en el mismo entorno que el juego:
  python tools/check_supabase_windows.py
"""
import sys
import os

print(f"Python: {sys.version}")
print(f"CWD: {os.getcwd()}")
print()

# 1. Check dotenv
try:
    from dotenv import load_dotenv
    print("[OK] python-dotenv instalado")
except ImportError:
    print("[ERROR] python-dotenv NO instalado  ->  pip install python-dotenv")
    sys.exit(1)

# 2. Load .env
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
loaded = load_dotenv(env_path)
print(f"[{'OK' if loaded else 'WARN'}] .env cargado desde: {env_path}")

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
print(f"  SUPABASE_URL: {'SET (' + url[:30] + '...)' if url else 'NO ENCONTRADA'}")
print(f"  SUPABASE_KEY: {'SET (' + key[:10] + '...)' if key else 'NO ENCONTRADA'}")
print()

if not url or not key:
    print("[ERROR] Faltan credenciales en .env")
    sys.exit(1)

# 3. Check supabase library
try:
    from supabase import create_client
    print("[OK] supabase instalado")
except ImportError:
    print("[ERROR] supabase NO instalado  ->  pip install supabase")
    sys.exit(1)

# 4. Test HTTP connectivity (before creating client)
print("\nProbando conectividad HTTP...")
try:
    import urllib.request
    import ssl
    ctx = ssl.create_default_context()
    host = url.replace("https://", "").split("/")[0]
    req = urllib.request.urlopen(f"https://{host}", context=ctx, timeout=8)
    print(f"[OK] Conexion HTTPS a {host} exitosa (status {req.status})")
except Exception as e:
    print(f"[ERROR] No se puede conectar a Supabase: {e}")
    print("  Posibles causas:")
    print("  - Firewall / antivirus bloqueando HTTPS saliente")
    print("  - Certificado SSL no verificable (try: pip install certifi)")
    print("  - Sin acceso a internet")
    sys.exit(1)

# 5. Test Supabase client query
print("\nProbando query a Supabase...")
try:
    client = create_client(url, key)
    resp = client.table("global_country_stats") \
        .select("country, total_wins") \
        .order("total_wins", desc=True) \
        .limit(3) \
        .execute()
    if resp.data:
        print(f"[OK] Query exitosa. Top paises:")
        for row in resp.data:
            print(f"     {row['country']:15s} {row['total_wins']} wins")
    else:
        print("[WARN] Query exitosa pero tabla vacia (sin datos de carreras)")
except Exception as e:
    print(f"[ERROR] Query fallo: {e}")
    sys.exit(1)

print("\n[LISTO] Supabase funciona correctamente en este entorno.")
