"""
Configuration for the CT.gov ingestion pipeline.

All secrets are expected to be in Databricks secret scope (backed by Azure Key Vault).
Non-sensitive config can be overridden via environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _get_secret(scope: str, key: str, fallback_env: str = "") -> str:
    """
    Retrieve a secret from Databricks secret scope.
    Falls back to environment variable for local dev.
    """
    try:
        from pyspark.dbutils import DBUtils  # type: ignore
        from pyspark.sql import SparkSession  # type: ignore

        spark = SparkSession.getActiveSession()
        dbutils = DBUtils(spark)
        return dbutils.secrets.get(scope=scope, key=key)
    except Exception:
        return os.environ.get(fallback_env, "")


@dataclass
class IngestionConfig:
    # ------------------------------------------------------------------ #
    # CT.gov API                                                           #
    # ------------------------------------------------------------------ #
    api_base_url: str = "https://clinicaltrials.gov/api/v2/studies"
    api_page_size: int = 1000          # max allowed by the API
    api_rate_limit_sleep: float = 0.5  # seconds between page requests
    api_timeout: int = 30              # request timeout in seconds
    api_max_retries: int = 3

    # Scope filters (per problem statement)
    study_type: str = "INTERVENTIONAL"
    phases: str = "PHASE2,PHASE3"
    first_submitted_date_from: str = "2015-01-01"

    # ------------------------------------------------------------------ #
    # ADLS Gen2                                                            #
    # ------------------------------------------------------------------ #
    storage_account_name: str = field(
        default_factory=lambda: os.environ.get("STORAGE_ACCOUNT_NAME", "")
    )
    storage_container_raw: str = "raw"
    adls_base_path: str = "ctgov/studies"

    # ------------------------------------------------------------------ #
    # Unity Catalog / Delta                                                #
    # ------------------------------------------------------------------ #
    uc_catalog: str = "ctgov"
    uc_schema_landing: str = "landing"
    raw_table_name: str = "raw_ctgov__studies"

    # Auto Loader checkpoint location (ADLS path)
    checkpoint_base: str = field(
        default_factory=lambda: os.environ.get(
            "CHECKPOINT_BASE",
            "abfss://raw@{account}.dfs.core.windows.net/_checkpoints/ctgov",
        )
    )

    # ------------------------------------------------------------------ #
    # Auth (resolved from Databricks secret scope at runtime)             #
    # ------------------------------------------------------------------ #
    secret_scope: str = "ctgov-scope"

    # ------------------------------------------------------------------ #
    # Runtime (set at instantiation time)                                  #
    # ------------------------------------------------------------------ #
    run_ts: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    )

    # ------------------------------------------------------------------ #
    # Derived properties                                                   #
    # ------------------------------------------------------------------ #

    @property
    def raw_table_full(self) -> str:
        return f"{self.uc_catalog}.{self.uc_schema_landing}.{self.raw_table_name}"

    @property
    def run_date(self) -> str:
        return self.run_ts[:10]

    @property
    def adls_run_path(self) -> str:
        """ABFS path for this pipeline run's raw files."""
        return (
            f"abfss://{self.storage_container_raw}"
            f"@{self.storage_account_name}.dfs.core.windows.net"
            f"/{self.adls_base_path}"
            f"/run_date={self.run_date}"
            f"/run_ts={self.run_ts}"
        )

    @property
    def adls_watch_path(self) -> str:
        """ABFS path Auto Loader watches (all runs)."""
        return (
            f"abfss://{self.storage_container_raw}"
            f"@{self.storage_account_name}.dfs.core.windows.net"
            f"/{self.adls_base_path}"
        )

    @property
    def checkpoint_path(self) -> str:
        return self.checkpoint_base.format(account=self.storage_account_name)

    def get_secret(self, key: str, fallback_env: str = "") -> str:
        return _get_secret(self.secret_scope, key, fallback_env)

    @property
    def api_params_base(self) -> dict:
        """Base query parameters for every CT.gov API request."""
        return {
            "filter.studyType": self.study_type,
            "filter.phase": self.phases,
            "filter.firstSubmittedDate": f"{self.first_submitted_date_from},",
            "pageSize": self.api_page_size,
            "format": "json",
        }
