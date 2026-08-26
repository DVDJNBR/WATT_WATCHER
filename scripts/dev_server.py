#!/usr/bin/env python3
"""
WATT WATCHER — Local Dev Server

Wraps production_service.py / export_service.py directly (no Azure Functions runtime).
Auth is bypassed — set VITE_SKIP_AUTH=true in frontend/.env.local.

Usage:
    python scripts/dev_server.py

Endpoints:
    GET /api/health
    GET /api/v1/production/regional?region_code=&start_date=&end_date=&limit=&offset=
"""

import json
import logging
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# ─── Path setup ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

from functions.shared.api.production_service import query_production

GOLD_DB = ROOT / "gold.db"
PORT    = 8765


def _get_conn() -> sqlite3.Connection:
    if not GOLD_DB.exists():
        raise FileNotFoundError(
            f"Gold DB introuvable : {GOLD_DB}\n"
            "  → Lancez d'abord : python scripts/run_pipeline.py"
        )
    return sqlite3.connect(str(GOLD_DB))


class APIHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler — JSON API, CORS enabled."""

    def log_message(self, fmt: str, *args) -> None:  # type: ignore[override]
        logger.info(fmt, *args)

    def _send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # CORS preflight
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed  = urlparse(self.path)
        path    = parsed.path.rstrip("/")
        params  = parse_qs(parsed.query)

        def qp(key: str, default: str | None = None) -> str | None:
            vals = params.get(key, [])
            return vals[0] if vals else default

        # ── /api/health ───────────────────────────────────────────────────────
        if path in ("/api/health", "/api/health/"):
            self._send_json(200, {"status": "healthy", "mode": "local-dev", "db": str(GOLD_DB)})
            return

        # ── /api/v1/production/regional ───────────────────────────────────────
        if path == "/api/v1/production/regional":
            try:
                conn   = _get_conn()
                result = query_production(
                    conn,
                    region_code = qp("region_code") or None,
                    start_date  = qp("start_date"),
                    end_date    = qp("end_date"),
                    source_type = qp("source_type"),
                    limit       = int(qp("limit",  "100") or "100"),
                    offset      = int(qp("offset", "0")   or "0"),
                )
                conn.close()
                self._send_json(200, result)
            except FileNotFoundError as exc:
                self._send_json(503, {"message": str(exc)})
            except Exception as exc:
                logger.exception("Error in production endpoint")
                self._send_json(500, {"message": str(exc)})
            return

        self._send_json(404, {"message": f"Not found: {path}"})


def main() -> None:
    print(f"\n🚀 WATT WATCHER dev server → http://localhost:{PORT}/api")
    print(f"   Gold DB : {GOLD_DB}")

    if not GOLD_DB.exists():
        print("\n   ⚠️  Gold DB manquante — lancez d'abord :")
        print("      python scripts/run_pipeline.py\n")

    print("\n   Endpoints disponibles :")
    print(f"   GET http://localhost:{PORT}/api/health")
    print(f"   GET http://localhost:{PORT}/api/v1/production/regional")
    print("\n   Ctrl+C pour arrêter.\n")

    server = HTTPServer(("localhost", PORT), APIHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Serveur arrêté.")


if __name__ == "__main__":
    main()
