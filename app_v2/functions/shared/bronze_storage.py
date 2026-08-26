"""
ADLS Gen2 Bronze Storage Module — Story 1.1, Task 4

Writes raw JSON payloads to the Bronze layer in ADLS Gen2
following the convention: bronze/rte/production/YYYY/MM/DD/eco2mix_regional_{timestamp}.json

For local development, writes to a local `bronze/` directory instead.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class BronzeStorage:
    """Write raw API data to Bronze layer (ADLS Gen2 or local filesystem)."""

    def __init__(
        self,
        storage_account_name: str | None = None,
        container_name: str = "bronze",
        local_mode: bool = False,
        local_root: str | None = None,
    ):
        self.container_name = container_name
        self.local_mode = local_mode or storage_account_name is None

        if self.local_mode:
            self.local_root = Path(local_root or "bronze")
            logger.info("BronzeStorage in LOCAL mode: %s", self.local_root)
        else:
            from azure.identity import DefaultAzureCredential
            from azure.storage.filedatalake import DataLakeServiceClient

            credential = DefaultAzureCredential()
            account_url = f"https://{storage_account_name}.dfs.core.windows.net"
            self.service_client = DataLakeServiceClient(
                account_url=account_url, credential=credential
            )
            self.fs_client = self.service_client.get_file_system_client(container_name)
            logger.info("BronzeStorage connected to ADLS: %s", account_url)

    def write_json(
        self,
        data: list[dict] | dict,
        source: str = "rte",
        sub_path: str = "production",
        timestamp: datetime | None = None,
    ) -> str:
        """
        Write raw JSON data to Bronze layer.

        Args:
            data: Raw API response data (list of records or full response).
            source: Data source identifier (e.g. 'rte', 'maintenance').
            sub_path: Sub-directory under source (e.g. 'production').
            timestamp: Timestamp for the file name. Defaults to now.

        Returns:
            Full path of the written file.
        """
        ts = timestamp or datetime.now(timezone.utc)
        ts_str = ts.strftime("%Y%m%dT%H%M%SZ")
        date_path = ts.strftime("%Y/%m/%d")

        filename = f"eco2mix_regional_{ts_str}.json"
        full_path = f"{source}/{sub_path}/{date_path}/{filename}"

        content = json.dumps(data, ensure_ascii=False, indent=2)

        if self.local_mode:
            return self._write_local(full_path, content)
        else:
            return self._write_adls(full_path, content)

    def write_audit(
        self,
        audit_entry: dict,
        timestamp: datetime | None = None,
    ) -> str:
        """Write an audit log entry to Bronze audit layer."""
        ts = timestamp or datetime.now(timezone.utc)
        ts_str = ts.strftime("%Y%m%dT%H%M%SZ")
        date_path = ts.strftime("%Y/%m/%d")

        filename = f"heartbeat_{ts_str}.json"
        full_path = f"audit/ingestion/{date_path}/{filename}"

        content = json.dumps(audit_entry, ensure_ascii=False, indent=2)

        if self.local_mode:
            return self._write_local(full_path, content)
        else:
            return self._write_adls(full_path, content)

    def _write_local(self, path: str, content: str) -> str:
        """Write to local filesystem (dev mode)."""
        full_path = self.local_root / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        logger.info("Written (local): %s (%d bytes)", full_path, len(content))
        return str(full_path)

    def _write_adls(self, path: str, content: str) -> str:
        """Write to ADLS Gen2 (production mode)."""
        file_client = self.fs_client.get_file_client(path)
        data = content.encode("utf-8")
        file_client.upload_data(data, overwrite=True)
        logger.info("Written (ADLS): %s/%s (%d bytes)", self.container_name, path, len(data))
        return f"{self.container_name}/{path}"
