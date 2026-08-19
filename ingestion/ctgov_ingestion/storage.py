"""
ADLS Gen2 storage writer for raw CT.gov JSON pages.

Writes one JSON file per API page to:
  abfss://raw@<account>.dfs.core.windows.net/ctgov/studies/
    run_date=YYYY-MM-DD/
      run_ts=YYYY-MM-DDTHH:MM:SSZ/
        page_0001.json
        page_0002.json
        ...

Authentication uses a service principal whose credentials are
retrieved from the Databricks secret scope at runtime.
"""

from __future__ import annotations

import json
import logging

from azure.identity import ClientSecretCredential
from azure.storage.filedatalake import DataLakeServiceClient

from .config import IngestionConfig

logger = logging.getLogger(__name__)


class ADLSWriter:
    """
    Writes raw API page responses as JSON files to ADLS Gen2.
    One file per API page, zero transformation applied.
    """

    def __init__(self, config: IngestionConfig) -> None:
        self.config = config
        self._client: DataLakeServiceClient | None = None

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    def write_page(self, page_num: int, page_data: dict) -> str:
        """
        Serialise page_data to JSON and upload to ADLS.

        Returns the full ADLS path of the written file.
        """
        file_name = f"page_{page_num:04d}.json"
        file_path = f"{self.config.adls_base_path}/run_date={self.config.run_date}/run_ts={self.config.run_ts}/{file_name}"

        content = json.dumps(page_data, ensure_ascii=False).encode("utf-8")

        file_client = (
            self._get_client()
            .get_file_system_client(self.config.storage_container_raw)
            .get_file_client(file_path)
        )

        # create_file + append + flush is the ADLS Gen2 pattern for atomic writes
        file_client.create_file()
        file_client.append_data(data=content, offset=0, length=len(content))
        file_client.flush_data(len(content))

        full_path = f"abfss://{self.config.storage_container_raw}@{self.config.storage_account_name}.dfs.core.windows.net/{file_path}"
        logger.info("Written page %04d → %s (%d bytes)", page_num, full_path, len(content))
        return full_path

    def write_run_manifest(self, total_pages: int, total_studies: int) -> None:
        """
        Write a small _manifest.json alongside the page files so the run
        is self-documenting and easy to audit.
        """
        manifest = {
            "run_ts": self.config.run_ts,
            "run_date": self.config.run_date,
            "total_pages": total_pages,
            "total_studies": total_studies,
            "api_params": self.config.api_params_base,
        }

        file_path = (
            f"{self.config.adls_base_path}"
            f"/run_date={self.config.run_date}"
            f"/run_ts={self.config.run_ts}"
            f"/_manifest.json"
        )

        content = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")

        file_client = (
            self._get_client()
            .get_file_system_client(self.config.storage_container_raw)
            .get_file_client(file_path)
        )
        file_client.create_file()
        file_client.append_data(data=content, offset=0, length=len(content))
        file_client.flush_data(len(content))
        logger.info("Manifest written for run_ts=%s", self.config.run_ts)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _get_client(self) -> DataLakeServiceClient:
        """Lazy-init the ADLS client using service principal credentials."""
        if self._client is None:
            tenant_id = self.config.get_secret("sp-tenant-id", "SP_TENANT_ID")
            client_id = self.config.get_secret("sp-client-id", "SP_CLIENT_ID")
            client_secret = self.config.get_secret("sp-client-secret", "SP_CLIENT_SECRET")

            credential = ClientSecretCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                client_secret=client_secret,
            )

            self._client = DataLakeServiceClient(
                account_url=f"https://{self.config.storage_account_name}.dfs.core.windows.net",
                credential=credential,
            )
            logger.info(
                "ADLS client initialised for account: %s",
                self.config.storage_account_name,
            )

        return self._client
