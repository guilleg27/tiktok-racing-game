#!/usr/bin/env python3
"""
Backfill Supabase con carreras del log que fallaron por falta de conexion.

Uso:
  python tools/backfill_supabase.py /ruta/al/tiktok_live_bot.log
  python tools/backfill_supabase.py /ruta/al/tiktok_live_bot.log --execute
"""
import re
import sys
import os
from datetime import datetime
from collections import defaultdict

# Load .env from project root
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_env_path = os.path.join(_project_root, ".env")

try:
    from dotenv import load_dotenv
    load_dotenv(_env_path)
except ImportError:
    print("ERROR: python-dotenv not installed. Run: pip install python-dotenv")
    sys.exit(1)

try:
    from supabase import create_client
except ImportError:
    print("ERROR: supabase not installed. Run: pip install supabase")
    sys.exit(1)


LOG_PATTERN = re.compile(
    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ .*'
    r'\u2601\ufe0f Queued cloud sync: ([^-]+?) - (.+?) \((\d+)\U0001f48e\)$'
)

BATCH_SIZE = 50


def parse_log(path: str) -> list[dict]:
    races = []
    skipped_stress = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = LOG_PATTERN.match(line.strip())
            if m:
                ts, country, captain, diamonds = m.groups()
                captain = captain.strip()
                if captain.startswith("stress_"):
                    skipped_stress += 1
                    continue
                races.append({
                    "race_timestamp": datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").isoformat(),
                    "country": country.strip(),
                    "captain_name": captain,
                    "total_diamonds": int(diamonds),
                    "streamer_name": "",
                })
    if skipped_stress:
        print(f"[Filtro] Se ignoraron {skipped_stress} carreras de stress-test (captain 'stress_*')")
    return races


def get_existing_keys(client) -> set[tuple]:
    resp = client.table("global_hall_of_fame") \
        .select("race_timestamp, country, captain_name").execute()
    return {
        (r["race_timestamp"], r["country"], r["captain_name"])
        for r in (resp.data or [])
    }


def backfill(races: list[dict], client, dry_run: bool = True) -> None:
    print("Consultando registros existentes en Supabase...")
    existing = get_existing_keys(client)

    new_races = [
        r for r in races
        if (r["race_timestamp"], r["country"], r["captain_name"]) not in existing
    ]

    print(f"\nTotal en log:   {len(races)}")
    print(f"Ya en Supabase: {len(races) - len(new_races)}")
    print(f"A insertar:     {len(new_races)}")

    agg = defaultdict(lambda: {"wins": 0, "diamonds": 0})
    for r in new_races:
        agg[r["country"]]["wins"] += 1
        agg[r["country"]]["diamonds"] += r["total_diamonds"]

    print("\nResumen por pais (nuevas entradas):")
    for country, data in sorted(agg.items(), key=lambda x: -x[1]["wins"]):
        print(f"  {country:15s}  +{data['wins']} wins  +{data['diamonds']} diamonds")

    if dry_run:
        print("\n[DRY RUN] Nada fue modificado. Usar --execute para insertar.")
        return

    if not new_races:
        print("\nNo hay nada nuevo que insertar.")
        return

    # Upsert country stats FIRST (FK constraint requires countries to exist)
    print("\nActualizando global_country_stats...")
    for country, data in agg.items():
        resp = client.table("global_country_stats") \
            .select("*").eq("country", country).execute()
        if resp.data:
            existing_row = resp.data[0]
            client.table("global_country_stats").update({
                "total_wins": existing_row.get("total_wins", 0) + data["wins"],
                "total_diamonds": existing_row.get("total_diamonds", 0) + data["diamonds"],
                "last_updated": datetime.now().isoformat(),
            }).eq("country", country).execute()
            print(f"  {country}: updated")
        else:
            client.table("global_country_stats").insert({
                "country": country,
                "total_wins": data["wins"],
                "total_diamonds": data["diamonds"],
                "last_updated": datetime.now().isoformat(),
            }).execute()
            print(f"  {country}: inserted")

    # Insert hall_of_fame in batches (after FK refs exist)
    print(f"\nInsertando {len(new_races)} filas en global_hall_of_fame...")
    for i in range(0, len(new_races), BATCH_SIZE):
        batch = new_races[i : i + BATCH_SIZE]
        client.table("global_hall_of_fame").insert(batch).execute()
        print(f"  {min(i + BATCH_SIZE, len(new_races))}/{len(new_races)} insertadas")

    print("\nBackfill completado.")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    log_path = args[0]
    execute = "--execute" in args

    if not os.path.isfile(log_path):
        print(f"ERROR: No se encontro el archivo: {log_path}")
        sys.exit(1)

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        print(f"ERROR: Faltan SUPABASE_URL o SUPABASE_KEY en {_env_path}")
        sys.exit(1)

    print(f"Parseando log: {log_path}")
    races = parse_log(log_path)

    if not races:
        print("No se encontraron entradas de cloud sync en el log.")
        sys.exit(0)

    client = create_client(url, key)
    backfill(races, client, dry_run=not execute)


if __name__ == "__main__":
    main()
