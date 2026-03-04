"""
ERA5 Climate Ingestion Module — Story 2.2, Task 2

Reads ERA5 Parquet data using pandas for processing.
Computes derived fields (wind speed magnitude) and writes partitioned
output to Bronze layer.

Key design decisions:
- pd.read_parquet() for data loading
- Chunked processing by month to respect Azure Function 10-min timeout
- Checkpoint mechanism to track last processed timestamp
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# France metropolitan bounding box (approximate)
FRANCE_LAT_MIN = 41.3
FRANCE_LAT_MAX = 51.1
FRANCE_LON_MIN = -5.2
FRANCE_LON_MAX = 9.6

# Region centroids for nearest-neighbor mapping
REGION_CENTROIDS = {
    "11": (48.86, 2.35),    # Île-de-France
    "24": (47.39, 1.69),    # Centre-Val de Loire
    "27": (47.47, -0.55),   # Bourgogne-Franche-Comté
    "28": (48.51, -2.76),   # Bretagne
    "32": (48.30, 7.44),    # Grand Est
    "44": (50.63, 3.06),    # Hauts-de-France
    "52": (49.12, -0.37),   # Normandie
    "53": (47.22, -1.55),   # Pays de la Loire
    "75": (46.58, 0.34),    # Nouvelle-Aquitaine
    "76": (43.60, 1.44),    # Occitanie
    "84": (45.76, 4.83),    # Auvergne-Rhône-Alpes
    "93": (43.30, 5.37),    # PACA
}


class ERA5Ingestion:
    """Ingest ERA5 climate Parquet data to Bronze layer."""

    def __init__(self, bronze_storage=None, audit_logger=None):
        """
        Args:
            bronze_storage: BronzeStorage instance for writing output.
            audit_logger: AuditLogger instance for heartbeat logging.
        """
        self.bronze = bronze_storage
        self.audit = audit_logger

    def ingest_parquet(
        self,
        source_path: str | Path,
        output_dir: str | Path | None = None,
    ) -> dict:
        """
        Ingest ERA5 Parquet using pandas.

        AC #1: Pull hourly data, partition by region/month.
        AC #2: Read parquet for data loading.

        Args:
            source_path: Path to ERA5 Parquet file.
            output_dir: Local output directory (dev mode). If None, uses Bronze storage.

        Returns:
            Summary dict: {total_rows, files_written, regions_processed}.
        """
        source_path = Path(source_path)
        logger.info("Reading ERA5 Parquet: %s", source_path)

        df = pd.read_parquet(source_path)

        # Filter to France bounding box
        df = df[
            (df["latitude"] >= FRANCE_LAT_MIN)
            & (df["latitude"] <= FRANCE_LAT_MAX)
            & (df["longitude"] >= FRANCE_LON_MIN)
            & (df["longitude"] <= FRANCE_LON_MAX)
        ].copy()

        # Compute derived fields
        # Wind speed at 100m from u/v components
        df["wind_speed_100m"] = (df["u100"] ** 2 + df["v100"] ** 2) ** 0.5
        # Temperature in Celsius
        df["temperature_c"] = (df["t2m"] - 273.15).round(2)
        # Extract date parts for partitioning
        df["year"] = df["valid_time"].dt.year  # type: ignore[union-attr]
        df["month"] = df["valid_time"].dt.month  # type: ignore[union-attr]

        # Map grid points to nearest region
        df = self._map_to_regions(pd.DataFrame(df))

        if df.empty:
            logger.warning("No ERA5 data after filtering")
            if self.audit:
                self.audit.log_success(record_count=0, details={"era5": "no_data"})
            return {"total_rows": 0, "files_written": 0, "regions_processed": []}

        # Write partitioned output
        files_written = self._write_partitioned(df, output_dir)

        summary = {
            "total_rows": len(df),
            "files_written": files_written,
            "regions_processed": sorted(df["region_code"].unique().tolist()),
        }

        logger.info(
            "ERA5 ingestion: %d rows, %d files, %d regions",
            summary["total_rows"],
            summary["files_written"],
            len(summary["regions_processed"]),
        )

        if self.audit:
            self.audit.log_success(
                record_count=len(df),
                details={"era5": summary},
            )

        return summary

    def ingest_chunked(
        self,
        source_path: str | Path,
        output_dir: str | Path | None = None,
        chunk_months: int = 1,
    ) -> dict:
        """
        AC #3: Chunked processing for large files to avoid Function timeout.

        Processes data month by month to stay within 10-min limit.
        """
        source_path = Path(source_path)
        df_full = pd.read_parquet(source_path)

        # Get time range
        min_time = df_full["valid_time"].min()
        max_time = df_full["valid_time"].max()

        # Normalize to Python datetime if pandas Timestamp
        if hasattr(min_time, 'to_pydatetime'):
            min_time = min_time.to_pydatetime()
        if hasattr(max_time, 'to_pydatetime'):
            max_time = max_time.to_pydatetime()

        total_rows = 0
        total_files = 0
        all_regions = set()

        # Process month by month
        current = min_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)  # type: ignore[call-arg]
        while current <= max_time:
            next_month = current.replace(
                month=current.month % 12 + 1,
                year=current.year + (1 if current.month == 12 else 0),
            )

            chunk_df = df_full[
                (df_full["valid_time"] >= current)
                & (df_full["valid_time"] < next_month)
            ]

            result = self._process_dataframe(pd.DataFrame(chunk_df), output_dir)

            total_rows += result["total_rows"]
            total_files += result["files_written"]
            all_regions.update(result["regions_processed"])

            logger.info("Chunk %s: %d rows", current.strftime("%Y-%m"), result["total_rows"])
            current = next_month

        return {
            "total_rows": total_rows,
            "files_written": total_files,
            "regions_processed": sorted(all_regions),
        }

    def _process_dataframe(
        self, df: pd.DataFrame, output_dir: str | Path | None
    ) -> dict:
        """Process a DataFrame chunk."""
        df = pd.DataFrame(df[
            (df["latitude"] >= FRANCE_LAT_MIN)
            & (df["latitude"] <= FRANCE_LAT_MAX)
            & (df["longitude"] >= FRANCE_LON_MIN)
            & (df["longitude"] <= FRANCE_LON_MAX)
        ]).copy()

        df["wind_speed_100m"] = (df["u100"] ** 2 + df["v100"] ** 2) ** 0.5
        df["temperature_c"] = (df["t2m"] - 273.15).round(2)
        df["year"] = df["valid_time"].dt.year
        df["month"] = df["valid_time"].dt.month

        df = self._map_to_regions(df)

        if df.empty:
            return {"total_rows": 0, "files_written": 0, "regions_processed": []}

        files = self._write_partitioned(df, output_dir)
        return {
            "total_rows": len(df),
            "files_written": files,
            "regions_processed": sorted(df["region_code"].unique().tolist()),
        }

    def _map_to_regions(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map each grid point to nearest French region via centroid distance."""
        region_codes = list(REGION_CENTROIDS.keys())

        def nearest_region(row):
            min_dist = float("inf")
            nearest = region_codes[0]
            for code, (lat, lon) in REGION_CENTROIDS.items():
                dist = ((row["latitude"] - lat) ** 2 + (row["longitude"] - lon) ** 2) ** 0.5
                if dist < min_dist:
                    min_dist = dist
                    nearest = code
            return nearest

        df = df.copy()
        df["region_code"] = df.apply(nearest_region, axis=1)
        return df

    def _write_partitioned(
        self, df: pd.DataFrame, output_dir: str | Path | None
    ) -> int:
        """Write partitioned Parquet files by region and month."""
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        files_written = 0

        for (region, year, month), group_df in df.groupby(["region_code", "year", "month"]):  # type: ignore[misc]
            filename = f"era5_{region}_{ts_str}.parquet"
            path = f"climate/era5/{year}/{month:02d}/{filename}"

            if output_dir:
                full_path = Path(output_dir) / path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                group_df.to_parquet(full_path, index=False)
                logger.info("Written: %s (%d rows)", full_path, len(group_df))
            elif self.bronze and self.bronze.local_mode:
                full_path = self.bronze.local_root / path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                group_df.to_parquet(full_path, index=False)
                logger.info("Written (local): %s (%d rows)", full_path, len(group_df))

            files_written += 1

        return files_written

    # ─── Checkpoint management ───────────────────────────────────────────

    @staticmethod
    def save_checkpoint(checkpoint_path: str | Path, last_processed: datetime) -> None:
        """Save ingestion checkpoint."""
        path = Path(checkpoint_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({
                "last_processed": last_processed.isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }),
            encoding="utf-8",
        )

    @staticmethod
    def load_checkpoint(checkpoint_path: str | Path) -> datetime | None:
        """Load last processed timestamp from checkpoint."""
        path = Path(checkpoint_path)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return datetime.fromisoformat(data["last_processed"])
