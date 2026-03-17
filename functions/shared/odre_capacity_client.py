"""
ODRE Capacity Client — installed generation capacity from ODRE open data.

Dataset: registre-national-installation-production-stockage-electricite-agrege-region
Source:  https://odre.opendatasoft.com/
No authentication required.
"""

import io
import logging

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# CSV export without use_labels to get machine-readable column names
ODRE_URL = (
    "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    "registre-national-installation-production-stockage-electricite-agrege-region"
    "/exports/csv?lang=fr&timezone=Europe%2FParis&delimiter=%3B"
)

# Map ODRE filière values → our dim_source source_name
FILIERE_MAP = {
    "hydraulique": "hydraulique",
    "hydraulique - fil de l'eau et éclusée": "hydraulique",
    "hydraulique - lacs": "hydraulique",
    "hydraulique - step turbinage": "hydraulique",
    "éolien terrestre": "eolien",
    "eolien terrestre": "eolien",
    "éolien en mer": "eolien",
    "eolien en mer": "eolien",
    "éolien": "eolien",
    "eolien": "eolien",
    "photovoltaïque": "solaire",
    "solaire": "solaire",
    "nucléaire": "nucleaire",
    "nucleaire": "nucleaire",
    "thermique gaz": "gaz",
    "gaz": "gaz",
    "thermique charbon": "charbon",
    "charbon": "charbon",
    "thermique fioul": "fioul",
    "fioul": "fioul",
    "bioénergies": "bioenergies",
    "bioenergies": "bioenergies",
    "bioénergie": "bioenergies",
}

# Known column name variants in the ODRE dataset
_REGION_CODE_CANDIDATES = ["code_insee_region", "code_region", "code_insee", "codeinsee"]
_REGION_NAME_CANDIDATES = ["nom_region", "region", "libelle_region", "nomreg"]
_FILIERE_CANDIDATES = ["filiere", "filière", "source_energie"]
_PUISSANCE_CANDIDATES = [
    "puissance_installee", "puiss_installee", "puissance_installee_mw",
    "puiss_mw", "puissance_mw", "puissance",
]
_ANNEE_CANDIDATES = ["annee", "année", "year", "an"]


def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def fetch_capacity() -> list[dict]:
    """
    Download and parse installed capacity from ODRE.

    Returns:
        List of dicts with keys:
            region_code, region_name, source_name, puissance_installee_mw, annee
    """
    resp = requests.get(ODRE_URL, timeout=60)
    resp.raise_for_status()

    df = pd.read_csv(io.BytesIO(resp.content), sep=";", low_memory=False, encoding="utf-8")

    # Normalize column names: lowercase, spaces→_, special chars stripped
    df.columns = [
        c.lower().strip()
         .replace(" ", "_")
         .replace("-", "_")
         .replace("é", "e").replace("è", "e").replace("ê", "e")
         .replace("â", "a").replace("î", "i")
         .replace("(", "").replace(")", "")
         .replace("mw", "mw")
        for c in df.columns
    ]

    col_code   = _find_col(df, _REGION_CODE_CANDIDATES)
    col_name   = _find_col(df, _REGION_NAME_CANDIDATES)
    col_fil    = _find_col(df, _FILIERE_CANDIDATES)
    col_puiss  = _find_col(df, _PUISSANCE_CANDIDATES)
    col_annee  = _find_col(df, _ANNEE_CANDIDATES)

    logger.info(
        "ODRE columns mapped: code=%s name=%s filiere=%s puissance=%s annee=%s",
        col_code, col_name, col_fil, col_puiss, col_annee,
    )

    records = []
    for _, row in df.iterrows():
        filiere_raw = str(row.get(col_fil, "") or "").strip().lower() if col_fil else ""
        source_name = FILIERE_MAP.get(filiere_raw)
        if not source_name:
            continue  # skip unknown sources

        region_code = str(row.get(col_code, "") or "").strip() if col_code else None
        region_name = str(row.get(col_name, "") or "").strip() if col_name else None

        try:
            puissance = float(str(row.get(col_puiss, "") or "").replace(",", "."))
        except (ValueError, TypeError):
            puissance = None

        try:
            annee = int(float(str(row.get(col_annee, "") or "").replace(",", ".")))
        except (ValueError, TypeError):
            annee = None

        records.append({
            "region_code": region_code,
            "region_name": region_name,
            "source_name": source_name,
            "puissance_installee_mw": puissance,
            "annee": annee,
        })

    logger.info("Parsed %d capacity records from ODRE (%d total rows)", len(records), len(df))
    return records
