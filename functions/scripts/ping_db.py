#!/usr/bin/env python3
"""
Ping Supabase — vérifie la connexion et les tables existantes.

Usage:
    SUPABASE_CONNECTION_STRING="postgresql://..." python functions/scripts/ping_db.py
"""
import os
import sys

url = os.environ.get("SUPABASE_CONNECTION_STRING", "")
if not url:
    print("❌  SUPABASE_CONNECTION_STRING non défini")
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    print("❌  psycopg2 non installé — pip install psycopg2-binary")
    sys.exit(1)

try:
    conn = psycopg2.connect(url, connect_timeout=10)
    cur = conn.cursor()

    res = cur.fetchone()
    version = res[0] if res else "Inconnue"
    print(f"✅  Connecté — {version[:50]}")

    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    tables = [r[0] for r in cur.fetchall()]
    if tables:
        print(f"📋  Tables existantes : {', '.join(tables)}")
    else:
        print("📋  Aucune table — schéma vierge, prêt pour la migration")

    conn.close()
    sys.exit(0)

except Exception as e:
    print(f"❌  Connexion échouée : {e}")
    sys.exit(1)
