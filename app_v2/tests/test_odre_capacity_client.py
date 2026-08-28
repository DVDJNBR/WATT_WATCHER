"""Tests for odre_capacity_client.py — FT/MEDALLION (fetch/parse split for Bronze archival)."""

from unittest.mock import MagicMock, patch

from functions.shared.odre_capacity_client import (
    fetch_raw_csv,
    parse_capacity_csv,
    fetch_capacity,
)

RAW_CSV = (
    "coderegion;region;filiere;puismaxinstallee\n"
    "11;Ile-de-France;eolien terrestre;100000\n"
    "11;Ile-de-France;eolien terrestre;50000\n"
    "76;Occitanie;solaire;200000\n"
    "0;Inconnu;gaz;9999\n"
)


class TestFetchRawCsv:
    def test_returns_raw_text_unparsed(self):
        mock_resp = MagicMock(status_code=200)
        mock_resp.content = RAW_CSV.encode("utf-8")
        mock_resp.raise_for_status = MagicMock()

        with patch("functions.shared.odre_capacity_client.requests.get", return_value=mock_resp):
            raw = fetch_raw_csv()

        assert raw == RAW_CSV


class TestParseCapacityCsv:
    def test_aggregates_by_region_and_source(self):
        records = parse_capacity_csv(RAW_CSV)
        idf_eolien = next(r for r in records if r["region_code"] == "11" and r["source_name"] == "eolien")
        # 100000 kW + 50000 kW = 150 MW
        assert idf_eolien["puissance_installee_mw"] == 150.0

    def test_drops_region_code_zero(self):
        records = parse_capacity_csv(RAW_CSV)
        assert all(r["region_code"] != "0" for r in records)

    def test_unknown_filiere_dropped(self):
        csv_text = "coderegion;region;filiere;puismaxinstallee\n11;IDF;filiere_inconnue;1000\n"
        records = parse_capacity_csv(csv_text)
        assert records == []

    def test_record_shape(self):
        records = parse_capacity_csv(RAW_CSV)
        r = records[0]
        assert set(r.keys()) == {"region_code", "region_name", "source_name", "puissance_installee_mw", "annee"}


class TestFetchCapacity:
    def test_composes_fetch_and_parse(self):
        mock_resp = MagicMock(status_code=200)
        mock_resp.content = RAW_CSV.encode("utf-8")
        mock_resp.raise_for_status = MagicMock()

        with patch("functions.shared.odre_capacity_client.requests.get", return_value=mock_resp):
            records = fetch_capacity()

        assert len(records) > 0
        assert any(r["region_code"] == "11" for r in records)
