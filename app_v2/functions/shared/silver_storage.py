"""
ADLS Gen2 Silver Storage Module

Writes cleaned Parquet DataFrames to the Silver layer in ADLS Gen2,
Hive-partitioned when partition columns are provided, following the
convention: silver/<source>/<sub_path>/[part_col=value/...]/data.parquet

For local development, writes to a local `silver/` directory instead —
mirrors shared/bronze_storage.py's BronzeStorage local_mode/ADLS branching.
"""

import io
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class SilverStorage:
    """Write cleaned Parquet data to Silver layer (ADLS Gen2 or local filesystem)."""

    def __init__(
        self,
        storage_account_name: str | None = None,
        container_name: str = "silver",
        local_mode: bool = False,
        local_root: str | None = None,
    ):
        self.container_name = container_name
        self.local_mode = local_mode or storage_account_name is None

        if self.local_mode:
            self.local_root = Path(local_root or "silver")
            logger.info("SilverStorage in LOCAL mode: %s", self.local_root)
        else:
            from azure.identity import DefaultAzureCredential
            from azure.storage.filedatalake import DataLakeServiceClient

            credential = DefaultAzureCredential()
            account_url = f"https://{storage_account_name}.dfs.core.windows.net"
            self.service_client = DataLakeServiceClient(
                account_url=account_url, credential=credential
            )
            self.fs_client = self.service_client.get_file_system_client(container_name)
            logger.info("SilverStorage connected to ADLS: %s", account_url)

    def write_parquet(
        self,
        df: pd.DataFrame,
        source: str,
        sub_path: str = "",
        partition_cols: list[str] | None = None,
    ) -> int:
        """
        Write a cleaned DataFrame to Silver layer as Parquet.

        Args:
            df: Cleaned DataFrame. Must already contain any columns listed
                in `partition_cols` — this method does not derive them.
            source: Data source identifier (e.g. 'meteo', 'capacity').
            sub_path: Sub-directory under source (e.g. 'regional').
            partition_cols: Column names to Hive-partition by, in order
                (e.g. ["year", "month"]). Dropped from the written data.
                None or empty → a single data.parquet file.

        Returns:
            Number of Parquet files written.
        """
        if df.empty:
            logger.info("Silver write skipped: empty DataFrame (%s/%s)", source, sub_path)
            return 0

        prefix = f"{source}/{sub_path}" if sub_path else source

        if not partition_cols:
            self._write_partition(df, prefix)
            return 1

        files = 0
        for keys, group in df.groupby(partition_cols):
            keys = keys if isinstance(keys, tuple) else (keys,)
            part_prefix = prefix + "".join(
                f"/{col}={self._format_partition_value(col, val)}"
                for col, val in zip(partition_cols, keys)
            )
            self._write_partition(group.drop(columns=partition_cols), part_prefix)
            files += 1

        return files

    def upload_directory(self, local_dir: Path, prefix: str) -> int:
        """
        Upload an already Hive-partitioned local Parquet tree to ADLS, preserving
        its relative structure under `prefix`.

        For sources (like RTE) whose Silver transform writes real partitioned
        Parquet files to a local/temp directory first (see transform_rte_to_silver),
        this persists that same tree to the real ADLS Silver container instead of
        leaving it in an ephemeral tmp dir. No-op in local_mode (files already live
        in their final place on disk).

        Returns:
            Number of files uploaded (0 in local_mode).
        """
        if self.local_mode:
            return 0

        local_dir = Path(local_dir)
        files = sorted(local_dir.rglob("*.parquet"))
        for f in files:
            blob_path = f"{prefix}/{f.relative_to(local_dir)}"
            file_client = self.fs_client.get_file_client(blob_path)
            file_client.upload_data(f.read_bytes(), overwrite=True)
        logger.info("Uploaded %d Silver Parquet files to ADLS under %s/%s", len(files), self.container_name, prefix)
        return len(files)

    @staticmethod
    def _format_partition_value(col: str, val) -> str:
        if col in ("month", "day"):
            return f"{int(val):02d}"
        return str(val)

    def _write_partition(self, df: pd.DataFrame, prefix: str) -> None:
        full_path = f"{prefix}/data.parquet"
        if self.local_mode:
            out = self.local_root / full_path
            out.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(out, index=False)
            logger.info("Written (local): %s (%d rows)", out, len(df))
        else:
            buffer = io.BytesIO()
            df.to_parquet(buffer, index=False)
            file_client = self.fs_client.get_file_client(full_path)
            file_client.upload_data(buffer.getvalue(), overwrite=True)
            logger.info(
                "Written (ADLS): %s/%s (%d rows)", self.container_name, full_path, len(df)
            )
