"""
Météo-France AROME client — météo data for French regions and the canvas-map grid.

Replaces Open-Meteo for the live pipeline. Open-Meteo's free tier counts one
call per *location* (not per HTTP request): the 352-point grid plus 13 regions
every 15 min came to ~35k calls/day against a 10k/day cap, and Azure's shared
outbound IPs made the cutoff land at a different hour every day.

Source: AROME 0.025° open data, published by Météo-France on data.gouv.fr
("Paquets Arome - Résolution 0,025°"). Public bucket, no key, no quota.
https://www.data.gouv.fr/fr/datasets/paquets-arome-resolution-0-025deg/

  * A run starts every 3 h (00, 03, … 21 UTC) and lands ~2 h later.
  * Each run is split into hour-range files (00H06H, 07H12H, …); the SP1
    package (~55 MB per file) holds the surface fields we need: 2 m
    temperature, 10 m wind speed/direction, total cloud cover.
  * Format is GRIB2 with CCSDS compression (template 5.42), decoded here with
    imagecodecs' libaec binding + numpy — eccodes has no wheel for every dev
    machine, and only four fields of one fixed grid are needed.
"""

import logging
import struct
from datetime import datetime, timedelta, timezone

import numpy as np
import requests

from shared.open_meteo_client import REGION_CENTROIDS

logger = logging.getLogger(__name__)

BUCKET_URL = "https://meteofrance-pnt.s3.rbx.io.cloud.ovh.net/pnt"
PACKAGE = "SP1"

# (discipline 0) GRIB2 (category, number) → our field name
_FIELDS = {
    (0, 0): "temperature_k",   # temperature (2 m above ground)
    (2, 0): "wind_direction",  # wind direction (10 m), degrees
    (2, 1): "wind_speed_ms",   # wind speed (10 m), m/s
    (6, 1): "cloud_cover",     # total cloud cover, %
}

# Hour ranges of the files a run is split into: (first step, last step, label)
_STEP_FILES = [
    (0, 6, "00H06H"), (7, 12, "07H12H"), (13, 18, "13H18H"), (19, 24, "19H24H"),
    (25, 30, "25H30H"), (31, 36, "31H36H"), (37, 42, "37H42H"), (43, 48, "43H48H"),
    (49, 51, "49H51H"),
]

# How far back to look for a published run. Runs normally land ~2 h late, but
# Météo-France occasionally skips several in a row; a 51 h forecast horizon
# means an older run still covers the current hour.
MAX_RUN_AGE_HOURS = 24

# Canvas map grid constants (must match SourcesCanvasMap.jsx)
_G_LON0, _G_LAT0 = -5.0, 41.0
_DLON,   _DLAT   = 0.75, 0.75
_G_NCOL, _G_NROW = 22, 16


def _step_file(step: int) -> str:
    for first, last, label in _STEP_FILES:
        if first <= step <= last:
            return label
    raise ValueError(f"step {step} beyond AROME horizon")


def _file_url(run: datetime, label: str) -> str:
    ts = run.strftime("%Y-%m-%dT%H:00:00Z")
    return f"{BUCKET_URL}/{ts}/arome/0025/{PACKAGE}/arome__0025__{PACKAGE}__{label}__{ts}.grib2"


def find_latest_run(now: datetime) -> datetime | None:
    """Newest run whose file covering `now` is published."""
    run = now.replace(minute=0, second=0, microsecond=0)
    run -= timedelta(hours=run.hour % 3)
    oldest = now - timedelta(hours=MAX_RUN_AGE_HOURS)
    while run >= oldest:
        step = int((now - run).total_seconds() // 3600)
        try:
            resp = requests.head(_file_url(run, _step_file(step)), timeout=10)
            if resp.status_code == 200:
                return run
        except requests.RequestException as exc:
            logger.warning("AROME run %s probe failed: %s", run.isoformat(), exc)
        run -= timedelta(hours=3)
    return None


# ── GRIB2 decoding ────────────────────────────────────────────────────────────

def _sections(msg: bytes) -> dict[int, bytes]:
    """Split one GRIB2 message into its numbered sections (last occurrence wins)."""
    out, p = {}, 16
    while p < len(msg) - 4:
        length = struct.unpack(">I", msg[p:p + 4])[0]
        out[msg[p + 4]] = msg[p:p + length]
        p += length
    return out


def _iter_messages(data: bytes):
    pos = 0
    while pos < len(data):
        if data[pos:pos + 4] != b"GRIB":
            raise ValueError(f"not a GRIB message at byte {pos}")
        total = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
        yield data[pos:pos + total]
        pos += total


def _signed16(raw: bytes) -> int:
    """GRIB2 sign-and-magnitude 16-bit integer."""
    v = struct.unpack(">H", raw)[0]
    return -(v & 0x7FFF) if v & 0x8000 else v


def _signed32(raw: bytes) -> int:
    v = struct.unpack(">I", raw)[0]
    return -(v & 0x7FFFFFFF) if v & 0x80000000 else v


def _decode_values(s: dict[int, bytes]) -> np.ndarray:
    """Data values of one message (template 5.42, CCSDS), NaN where bitmapped out."""
    from imagecodecs import aec_decode

    s5 = s[5]
    n_packed = struct.unpack(">I", s5[5:9])[0]
    template = struct.unpack(">H", s5[9:11])[0]
    if template != 42:
        raise ValueError(f"unsupported GRIB2 data template 5.{template}")
    ref = struct.unpack(">f", s5[11:15])[0]
    bin_scale = _signed16(s5[15:17])
    dec_scale = _signed16(s5[17:19])
    nbits, flags, block, rsi = s5[19], s5[21], s5[22], struct.unpack(">H", s5[23:25])[0]

    if nbits == 0:
        values = np.full(n_packed, ref / 10.0 ** dec_scale)
    else:
        three_byte = 16 < nbits <= 24 and flags & 2  # AEC_DATA_3BYTE
        width = 1 if nbits <= 8 else 2 if nbits <= 16 else 3 if three_byte else 4
        # Explicit output size: libaec's own guess from the compressed length
        # falls short on near-constant fields, which compress extremely well.
        # It writes whole blocks, so round up; the padding is sliced off below.
        n_blocks = -(-n_packed // block)
        raw = aec_decode(s[7][5:], bitspersample=nbits, flags=flags, blocksize=block, rsi=rsi,
                         out=n_blocks * block * width)
        if width == 3:
            b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.uint32)
            packed = (b[:, 0] << 16) | (b[:, 1] << 8) | b[:, 2]
        else:
            packed = np.frombuffer(raw, {1: ">u1", 2: ">u2", 4: ">u4"}[width])
        values = (ref + packed[:n_packed].astype(np.float64) * 2.0 ** bin_scale) / 10.0 ** dec_scale

    bitmap_flag = s[6][5]
    if bitmap_flag == 255:
        return values
    if bitmap_flag != 0:
        raise ValueError(f"unsupported GRIB2 bitmap indicator {bitmap_flag}")
    n_points = struct.unpack(">I", s[3][6:10])[0]
    mask = np.unpackbits(np.frombuffer(s[6][6:], np.uint8))[:n_points].astype(bool)
    full = np.full(n_points, np.nan)
    full[mask] = values
    return full


class _Grid:
    """Regular lat/lon grid (template 3.0), scanned north→south, west→east."""

    def __init__(self, s3: bytes):
        self.ni = struct.unpack(">I", s3[30:34])[0]
        self.nj = struct.unpack(">I", s3[34:38])[0]
        self.lat1 = _signed32(s3[46:50]) / 1e6
        lon1 = _signed32(s3[50:54]) / 1e6
        self.lon1 = lon1 - 360 if lon1 > 180 else lon1
        self.dlon = struct.unpack(">I", s3[63:67])[0] / 1e6
        self.dlat = struct.unpack(">I", s3[67:71])[0] / 1e6

    def index(self, lat: float, lon: float) -> tuple[int, int]:
        j = round((self.lat1 - lat) / self.dlat)
        i = round((lon - self.lon1) / self.dlon)
        if not (0 <= j < self.nj and 0 <= i < self.ni):
            raise ValueError(f"({lat}, {lon}) outside AROME grid")
        return j, i


def _sample(data: bytes, steps: set[int], points: list[tuple[float, float]]) -> dict[int, dict[str, np.ndarray]]:
    """
    Values of every _FIELDS field at `points` (nearest grid node), for each
    forecast step in `steps`: {step: {field: array aligned with points}}.
    """
    out: dict[int, dict[str, np.ndarray]] = {}
    idx = None
    for msg in _iter_messages(data):
        s = _sections(msg)
        if msg[6] != 0:  # discipline: meteorological products only
            continue
        s4 = s[4]
        field = _FIELDS.get((s4[9], s4[10]))
        step = struct.unpack(">I", s4[18:22])[0]
        if field is None or step not in steps:
            continue
        if idx is None:
            grid = _Grid(s[3])
            ij = [grid.index(lat, lon) for lat, lon in points]
            idx = (np.array([j for j, _ in ij]), np.array([i for _, i in ij]), grid)
        rows, cols, grid = idx
        values = _decode_values(s).reshape(grid.nj, grid.ni)
        out.setdefault(step, {})[field] = values[rows, cols]
    return out


# ── Public API ────────────────────────────────────────────────────────────────

def _grid_points() -> list[tuple[float, float]]:
    return [
        (round(_G_LAT0 + row * _DLAT, 4), round(_G_LON0 + col * _DLON, 4))
        for row in range(_G_NROW)
        for col in range(_G_NCOL)
    ]


def _finite(v) -> float | None:
    return None if v is None or np.isnan(v) else float(v)


def fetch_arome(past_hours: int = 6, now: datetime | None = None) -> tuple[list[dict], list[dict]]:
    """
    Regional hourly records and the current canvas-map grid, from the newest
    published AROME run.

    Args:
        past_hours: Hours before the current one to (re)write, so a missed
            pipeline slot heals on the next run. Hours before the run's own
            start aren't in it and are skipped.
        now: Override of the current time (tests).

    Returns:
        (regional, grid)
        regional: [{region_code, region_name, timestamp, temperature_c,
                    wind_speed_10m, cloudcover_pct}] — timestamps UTC
                    "YYYY-MM-DDTHH:MM", never past the current hour.
        grid:     [{lat, lon, cloud_cover, wind_speed, wind_direction}] at the
                  current hour.
        Wind speeds are km/h, matching the Open-Meteo data already stored.
        Both lists are empty if no run could be fetched.
    """
    now = (now or datetime.now(timezone.utc)).replace(minute=0, second=0, microsecond=0)
    run = find_latest_run(now)
    if run is None:
        logger.warning("No AROME run published in the last %d h", MAX_RUN_AGE_HOURS)
        return [], []

    hours = [now - timedelta(hours=k) for k in range(past_hours, -1, -1)]
    hours = [h for h in hours if h >= run]
    steps = {int((h - run).total_seconds() // 3600): h for h in hours}

    regions = list(REGION_CENTROIDS.items())
    grid_pts = _grid_points()
    points = [(info["lat"], info["lon"]) for _, info in regions] + grid_pts
    n_reg = len(regions)

    sampled: dict[int, dict[str, np.ndarray]] = {}
    for label in sorted({_step_file(st) for st in steps}):
        url = _file_url(run, label)
        try:
            resp = requests.get(url, timeout=120)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("AROME download failed (%s): %s", url, exc)
            continue
        sampled.update(_sample(resp.content, set(steps), points))
    logger.info("AROME run %s: steps %s decoded", run.isoformat(), sorted(sampled))

    regional = []
    for step, fields in sorted(sampled.items()):
        if len(fields) < len(_FIELDS):
            continue
        ts = steps[step].strftime("%Y-%m-%dT%H:%M")
        for k, (code, info) in enumerate(regions):
            temp = _finite(fields["temperature_k"][k])
            if temp is None:
                continue
            wind = _finite(fields["wind_speed_ms"][k])
            cloud = _finite(fields["cloud_cover"][k])
            regional.append({
                "region_code": code,
                "region_name": info["name"],
                "timestamp": ts,
                "temperature_c": round(temp - 273.15, 2),
                "wind_speed_10m": round(wind * 3.6, 2) if wind is not None else None,
                "cloudcover_pct": round(cloud, 1) if cloud is not None else None,
            })

    grid = []
    current = sampled.get(int((now - run).total_seconds() // 3600))
    if current and len(current) == len(_FIELDS):
        for k, (lat, lon) in enumerate(grid_pts, start=n_reg):
            grid.append({
                "lat": lat,
                "lon": lon,
                "cloud_cover": int(round(_finite(current["cloud_cover"][k]) or 0)),
                "wind_speed": round((_finite(current["wind_speed_ms"][k]) or 0.0) * 3.6, 2),
                "wind_direction": int(round(_finite(current["wind_direction"][k]) or 0)) % 360,
            })

    logger.info("AROME: %d regional records, %d grid points", len(regional), len(grid))
    return regional, grid
