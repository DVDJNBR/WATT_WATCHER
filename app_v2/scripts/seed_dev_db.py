"""
seed_dev_db.py — copie les vraies tables Supabase dans un dev.sqlite local.

Usage:
    cd app_v2
    python scripts/seed_dev_db.py          # → crée dev.sqlite à la racine
    python scripts/seed_dev_db.py my.db    # → chemin personnalisé

Lancement ensuite :
    DB_TYPE=sqlite SQLITE_PATH=./dev.sqlite uvicorn api.main:app --port 8000 --reload
    # autre terminal :
    cd frontend && npm run dev
"""

import os
import sqlite3
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

DB_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "dev.sqlite"

# Tables à copier (ordre respecte les FK)
# Clé = nom Postgres (lowercase), valeur = nom SQLite (UPPERCASE, convention API)
TABLES = {
    "dim_region":           "DIM_REGION",
    "dim_source":           "DIM_SOURCE",
    "dim_time":             "DIM_TIME",
    "fact_capacity":        "FACT_CAPACITY",
    "fact_energy_flow":     "FACT_ENERGY_FLOW",
    "fact_meteo":           "FACT_METEO",
    "fact_market_price":    "FACT_MARKET_PRICE",
    "fact_maintenance":     "FACT_MAINTENANCE",
    "fact_national_mix":    "FACT_NATIONAL_MIX",
    "fact_cross_border_flow": "FACT_CROSS_BORDER_FLOW",
    "meteo_grid":           "METEO_GRID",
}

BATCH = 10_000


def load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


def pg_connect():
    import psycopg2
    db_url = os.environ.get("SUPABASE_CONNECTION_STRING")
    if not db_url:
        raise RuntimeError("SUPABASE_CONNECTION_STRING manquant dans .env")
    p = urlparse(db_url)
    return psycopg2.connect(
        host=p.hostname, port=p.port or 5432,
        dbname=(p.path or "/postgres").lstrip("/"),
        user=unquote(p.username or ""), password=unquote(p.password or ""),
        sslmode="require",
    )


def get_columns(pg_cur, table: str) -> list[str]:
    pg_cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
        (table,),
    )
    return [r[0] for r in pg_cur.fetchall()]


def pg_type_to_sqlite(pg_type: str) -> str:
    pg_type = pg_type.lower()
    if pg_type in ("integer", "bigint", "smallint", "serial", "bigserial"):
        return "INTEGER"
    if pg_type in ("real", "double precision", "numeric", "decimal", "float4", "float8"):
        return "REAL"
    return "TEXT"


def get_col_types(pg_cur, table: str) -> dict[str, str]:
    pg_cur.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
        (table,),
    )
    return {r[0]: pg_type_to_sqlite(r[1]) for r in pg_cur.fetchall()}


def copy_table(pg_conn, sqlite_conn: sqlite3.Connection, pg_table: str, sq_table: str) -> int:
    pg_cur = pg_conn.cursor()
    cols = get_columns(pg_cur, pg_table)
    col_types = get_col_types(pg_cur, pg_table)

    col_defs = ", ".join(f"{c} {col_types[c]}" for c in cols)
    sqlite_conn.execute(f"DROP TABLE IF EXISTS {sq_table}")
    sqlite_conn.execute(f"CREATE TABLE {sq_table} ({col_defs})")

    placeholders = ", ".join("?" * len(cols))
    insert_sql = f"INSERT INTO {sq_table} VALUES ({placeholders})"

    pg_cur.execute(f'SELECT COUNT(*) FROM "{pg_table}"')
    total = pg_cur.fetchone()[0]
    print(f"  {pg_table} → {sq_table} : {total} lignes", end="", flush=True)

    if total == 0:
        print()
        return 0

    pg_cur.execute(f'SELECT {", ".join(cols)} FROM "{pg_table}"')
    copied = 0
    while True:
        rows = pg_cur.fetchmany(BATCH)
        if not rows:
            break
        def coerce(v):
            from decimal import Decimal
            if isinstance(v, Decimal):
                return float(v)
            return v
        sqlite_conn.executemany(insert_sql, [tuple(coerce(v) for v in r) for r in rows])
        copied += len(rows)
        print(f"\r  {pg_table} → {sq_table} : {copied}/{total}", end="", flush=True)

    sqlite_conn.commit()
    print(f"\r  {pg_table} → {sq_table} : {total} lignes ✓")
    return total


def main():
    load_env()

    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Suppression ancienne DB : {DB_PATH}")

    print("Connexion à Supabase…")
    pg_conn = pg_connect()
    sqlite_conn = sqlite3.connect(DB_PATH)

    print(f"Copie vers {DB_PATH} :\n")
    total_rows = 0
    for pg_tbl, sq_tbl in TABLES.items():
        try:
            total_rows += copy_table(pg_conn, sqlite_conn, pg_tbl, sq_tbl)
        except Exception as e:
            print(f"\n  ⚠ {pg_tbl} ignoré : {e}")

    pg_conn.close()
    sqlite_conn.close()

    size_mb = DB_PATH.stat().st_size / 1_048_576
    print(f"\nDone. {total_rows:,} lignes → {DB_PATH} ({size_mb:.1f} MB)")
    print()
    print("Lancement :")
    print(f"  DB_TYPE=sqlite SQLITE_PATH={DB_PATH} uvicorn api.main:app --port 8000 --reload")
    print("  cd frontend && npm run dev")


if __name__ == "__main__":
    main()
