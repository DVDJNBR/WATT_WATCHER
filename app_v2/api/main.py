"""
WATT_WATCHER — dataviz API (FastAPI)

Public, read-only API serving the showroom dashboard from Supabase (Gold layer).
No auth — the Gold data is not sensitive and this is a portfolio demo.

Data is written by the separate Azure Functions pipeline (functions/), which
ingests RTE/Météo-France/ODRE on a schedule and loads it into the same Supabase DB.
"""

import logging
import os
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from api.capacity_service import query_capacity
from api.curtailment_service import query_curtailment_calendar, query_curtailment_risk
from api.db import get_db_connection
from api.error_handlers import bad_request, not_found, server_error
from api.export_service import export_to_csv
from api.maintenance_service import query_maintenance
from api.meteo_service import query_meteo
from api.models import parse_export_request, parse_production_request
from api.production_service import query_production

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="WATT_WATCHER API", version="1.0.0")

_allowed_origins = os.environ.get("CORS_ALLOW_ORIGINS", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if _allowed_origins == "*" else _allowed_origins.split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "healthy", "version": app.version}


@app.get("/v1/production/regional")
def production_regional(request: Request):
    request_id = str(uuid.uuid4())
    prod_req, validation_error = parse_production_request(dict(request.query_params))
    if validation_error:
        return JSONResponse(bad_request(validation_error, request_id), status_code=400)

    conn = None
    try:
        conn = get_db_connection()
        result = query_production(
            conn,
            region_code=prod_req.region_code,
            start_date=prod_req.start_date,
            end_date=prod_req.end_date,
            source_type=prod_req.source_type,
            limit=prod_req.limit,
            offset=prod_req.offset,
            request_id=request_id,
        )
        if not result["data"]:
            return JSONResponse(not_found(request_id=request_id), status_code=404)
        return JSONResponse(result, headers={"X-Request-Id": request_id})
    except Exception:
        logger.exception("production endpoint error [%s]", request_id)
        return JSONResponse(server_error(request_id=request_id), status_code=500)
    finally:
        if conn:
            conn.close()


@app.get("/v1/export/csv")
def export_csv(request: Request):
    request_id = str(uuid.uuid4())
    export_req = parse_export_request(dict(request.query_params))

    conn = None
    try:
        conn = get_db_connection()
        csv_bytes, filename, row_count = export_to_csv(
            conn,
            region_code=export_req.region_code,
            start_date=export_req.start_date,
            end_date=export_req.end_date,
            source_type=export_req.source_type,
            request_id=request_id,
        )
        if row_count == 0:
            return JSONResponse(not_found(request_id=request_id), status_code=404)
        return Response(
            csv_bytes,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Request-Id": request_id,
            },
        )
    except Exception:
        logger.exception("export endpoint error [%s]", request_id)
        return JSONResponse(server_error(request_id=request_id), status_code=500)
    finally:
        if conn:
            conn.close()


@app.get("/v1/meteo/regional")
def meteo_regional(request: Request):
    request_id = str(uuid.uuid4())
    params = request.query_params
    conn = None
    try:
        conn = get_db_connection()
        result = query_meteo(
            conn,
            region_code=params.get("region_code") or None,
            start_date=params.get("start_date") or None,
            end_date=params.get("end_date") or None,
            limit=min(int(params.get("limit", 500)), 5000),
            request_id=request_id,
        )
        return JSONResponse(result, headers={"X-Request-Id": request_id})
    except Exception:
        logger.exception("meteo endpoint error [%s]", request_id)
        return JSONResponse(server_error(request_id=request_id), status_code=500)
    finally:
        if conn:
            conn.close()


@app.get("/v1/capacity/regional")
def capacity_regional(request: Request):
    request_id = str(uuid.uuid4())
    params = request.query_params
    conn = None
    try:
        conn = get_db_connection()
        result = query_capacity(
            conn,
            region_code=params.get("region_code") or None,
            annee=params.get("annee") or None,
            request_id=request_id,
        )
        return JSONResponse(result, headers={"X-Request-Id": request_id})
    except Exception:
        logger.exception("capacity endpoint error [%s]", request_id)
        return JSONResponse(server_error(request_id=request_id), status_code=500)
    finally:
        if conn:
            conn.close()


@app.get("/v1/curtailment/regional")
def curtailment_regional(request: Request):
    request_id = str(uuid.uuid4())
    params = request.query_params
    conn = None
    try:
        conn = get_db_connection()
        result = query_curtailment_risk(
            conn,
            start_date=params.get("start_date") or None,
            end_date=params.get("end_date") or None,
            request_id=request_id,
        )
        return JSONResponse(result, headers={"X-Request-Id": request_id})
    except Exception:
        logger.exception("curtailment endpoint error [%s]", request_id)
        return JSONResponse(server_error(request_id=request_id), status_code=500)
    finally:
        if conn:
            conn.close()


@app.get("/v1/curtailment/calendar")
def curtailment_calendar(request: Request):
    request_id = str(uuid.uuid4())
    conn = None
    try:
        conn = get_db_connection()
        result = query_curtailment_calendar(conn, request_id=request_id)
        return JSONResponse(result, headers={"X-Request-Id": request_id})
    except Exception:
        logger.exception("curtailment calendar endpoint error [%s]", request_id)
        return JSONResponse(server_error(request_id=request_id), status_code=500)
    finally:
        if conn:
            conn.close()


@app.get("/v1/maintenance")
def maintenance(request: Request):
    request_id = str(uuid.uuid4())
    params = request.query_params
    conn = None
    try:
        conn = get_db_connection()
        result = query_maintenance(
            conn,
            region_code=params.get("region_code") or None,
            limit=min(int(params.get("limit", 100)), 500),
            request_id=request_id,
        )
        return JSONResponse(result, headers={"X-Request-Id": request_id})
    except Exception:
        logger.exception("maintenance endpoint error [%s]", request_id)
        return JSONResponse(server_error(request_id=request_id), status_code=500)
    finally:
        if conn:
            conn.close()
