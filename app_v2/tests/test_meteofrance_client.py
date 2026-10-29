"""Tests for meteofrance_client.py — AROME GRIB2 decoding and run selection.

GRIB2 messages are built in-test (template 3.0 grid, 4.0 product, 5.42 CCSDS
data) so decoding is checked against known values without network access.
"""

import struct
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from imagecodecs import aec_encode

from functions.shared import meteofrance_client as mf
from functions.shared.open_meteo_client import REGION_CENTROIDS

AEC_FLAGS = 12  # AEC_DATA_PREPROCESS | AEC_DATA_MSB, as in Météo-France files

# Whole-domain grid at a coarse step: every region centroid and canvas-map
# point falls inside, and messages stay small.
GRID = dict(lat1=55.4, lon1=-12.0, dlat=0.1, dlon=0.1, ni=281, nj=180)


def _section(num: int, body: bytes) -> bytes:
    return struct.pack(">IB", 5 + len(body), num) + body


def _sign16(v: int) -> bytes:
    return struct.pack(">H", (abs(v) | 0x8000) if v < 0 else v)


def _grid_section(g: dict) -> bytes:
    lon1 = g["lon1"] + 360 if g["lon1"] < 0 else g["lon1"]
    body = (
        b"\x00" + struct.pack(">I", g["ni"] * g["nj"]) + b"\x00\x00" + struct.pack(">H", 0)
        + b"\x06" + b"\x00" * 15
        + struct.pack(">II", g["ni"], g["nj"]) + b"\x00" * 8
        + struct.pack(">ii", round(g["lat1"] * 1e6), round(lon1 * 1e6)) + b"\x30"
        + struct.pack(">ii", 0, 0)
        + struct.pack(">II", round(g["dlon"] * 1e6), round(g["dlat"] * 1e6)) + b"\x00"
    )
    return _section(3, body)


def _message(cat: int, num: int, step: int, values: np.ndarray, g: dict = GRID,
             bitmap: np.ndarray | None = None) -> bytes:
    """One GRIB2 message; `values` are physical values, D=1 decimal scaling."""
    present = values if bitmap is None else values[bitmap]
    packed_ints = np.round(present * 10).astype(np.int64)
    ref = int(packed_ints.min())
    nbits = max(int((packed_ints - ref).max()).bit_length(), 1)
    x = (packed_ints - ref).astype(">u1" if nbits <= 8 else ">u2")
    data = aec_encode(x.tobytes(), bitspersample=nbits, flags=AEC_FLAGS, blocksize=32, rsi=128)

    s4 = _section(4, struct.pack(">HH", 0, 0) + bytes([cat, num, 2, 0, 0]) + b"\x00\x00\x00\x01"
                  + struct.pack(">I", step) + b"\x67\x00" + b"\x00" * 10)
    s5 = _section(5, struct.pack(">IH", len(present), 42) + struct.pack(">f", ref)
                  + _sign16(0) + _sign16(1) + bytes([nbits, 0, AEC_FLAGS, 32]) + struct.pack(">H", 128))
    if bitmap is None:
        s6 = _section(6, b"\xff")
    else:
        s6 = _section(6, b"\x00" + np.packbits(bitmap.astype(np.uint8)).tobytes())
    s7 = _section(7, data)
    body = _section(1, b"\x00" * 16) + _grid_section(g) + s4 + s5 + s6 + s7 + b"7777"
    return b"GRIB\x00\x00\x00\x02" + struct.pack(">Q", 16 + len(body)) + body


class TestDecode:
    def test_ccsds_values_round_trip(self):
        g = dict(lat1=50.0, lon1=0.0, dlat=1.0, dlon=1.0, ni=4, nj=3)
        values = np.arange(12, dtype=float) * 1.5 + 270.0
        s = mf._sections(_message(0, 0, 1, values, g))
        np.testing.assert_allclose(mf._decode_values(s), values, atol=0.05)

    def test_bitmap_masks_points_as_nan(self):
        g = dict(lat1=50.0, lon1=0.0, dlat=1.0, dlon=1.0, ni=4, nj=3)
        values = np.arange(12, dtype=float)
        bitmap = np.array([True, False] * 6)
        decoded = mf._decode_values(mf._sections(_message(6, 1, 1, values, g, bitmap)))
        assert np.isnan(decoded[~bitmap]).all()
        np.testing.assert_allclose(decoded[bitmap], values[bitmap], atol=0.05)

    def test_grid_negative_longitude_and_nearest_index(self):
        grid = mf._Grid(_grid_section(GRID))
        assert grid.lon1 == pytest.approx(-12.0)
        assert grid.index(55.4, -12.0) == (0, 0)
        assert grid.index(48.83, 2.35) == (66, 144)


def _arome_file(steps: list[int]) -> bytes:
    n = GRID["ni"] * GRID["nj"]
    out = b""
    for step in steps:
        out += _message(0, 0, step, np.full(n, 283.0))   # 9.85 °C
        out += _message(2, 0, step, np.full(n, 90.0))
        out += _message(2, 1, step, np.full(n, 5.0))      # 18 km/h
        out += _message(6, 1, step, np.full(n, 40.0))
        out += _message(2, 2, step, np.full(n, 1.0))      # u-wind: ignored
    return out


def _resp(status=200, content=b""):
    r = MagicMock(status_code=status, content=content)
    r.raise_for_status = MagicMock()
    return r


class TestFetchArome:
    NOW = datetime(2026, 10, 29, 16, 20, tzinfo=timezone.utc)
    RUN = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)

    def _fetch(self, content: bytes):
        run_url = mf._file_url(self.RUN, "00H06H")
        with patch.object(mf.requests, "head",
                          side_effect=lambda url, **_: _resp(200 if url == run_url else 404)), \
             patch.object(mf.requests, "get", return_value=_resp(content=content)) as get:
            regional, grid = mf.fetch_arome(past_hours=6, now=self.NOW)
        return regional, grid, get

    def test_regional_records_cover_run_start_to_now(self):
        regional, _, get = self._fetch(_arome_file(list(range(0, 5))))
        hours = sorted({r["timestamp"] for r in regional})
        # Hours before the 12Z run aren't in it; nothing past the current hour.
        assert hours == [f"2026-10-29T{h}:00" for h in range(12, 17)]
        assert len(regional) == 5 * len(REGION_CENTROIDS)
        assert "00H06H" in get.call_args.args[0]

    def test_units_match_stored_open_meteo_data(self):
        regional, grid, _ = self._fetch(_arome_file([4]))
        r = regional[0]
        assert r["temperature_c"] == pytest.approx(9.85, abs=0.01)
        assert r["wind_speed_10m"] == pytest.approx(18.0, abs=0.05)
        assert r["cloudcover_pct"] == pytest.approx(40.0, abs=0.05)
        assert len(grid) == 352
        assert grid[0] == {"lat": 41.0, "lon": -5.0, "cloud_cover": 40,
                           "wind_speed": pytest.approx(18.0, abs=0.05), "wind_direction": 90}

    def test_no_run_published_returns_empty(self):
        with patch.object(mf.requests, "head", return_value=_resp(status=404)), \
             patch.object(mf.requests, "get") as get:
            assert mf.fetch_arome(now=self.NOW) == ([], [])
        get.assert_not_called()


class TestFindLatestRun:
    def test_walks_back_past_unpublished_runs(self):
        now = datetime(2026, 10, 29, 16, 0, tzinfo=timezone.utc)
        published = mf._file_url(datetime(2026, 10, 29, 3, tzinfo=timezone.utc), "13H18H")
        with patch.object(mf.requests, "head",
                          side_effect=lambda url, **_: _resp(200 if url == published else 404)):
            assert mf.find_latest_run(now) == datetime(2026, 10, 29, 3, tzinfo=timezone.utc)

    def test_step_file_boundaries(self):
        assert mf._step_file(0) == "00H06H"
        assert mf._step_file(6) == "00H06H"
        assert mf._step_file(7) == "07H12H"
        assert mf._step_file(51) == "49H51H"
        with pytest.raises(ValueError):
            mf._step_file(52)
