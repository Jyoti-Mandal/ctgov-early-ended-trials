"""
Tests for IngestionConfig.

Validates derived properties, defaults, and secret resolution fallback.
"""

import pytest
from ctgov_ingestion.config import IngestionConfig


class TestIngestionConfigDefaults:

    def test_api_base_url(self):
        cfg = IngestionConfig()
        assert cfg.api_base_url == "https://clinicaltrials.gov/api/v2/studies"

    def test_phases_filter(self):
        cfg = IngestionConfig()
        assert "PHASE2" in cfg.phases
        assert "PHASE3" in cfg.phases

    def test_study_type_filter(self):
        cfg = IngestionConfig()
        assert cfg.study_type == "INTERVENTIONAL"

    def test_first_submitted_date_from(self):
        cfg = IngestionConfig()
        assert cfg.first_submitted_date_from == "2015-01-01"

    def test_page_size_at_maximum(self):
        # CT.gov v2 allows max 1000 — we should use it for efficiency
        cfg = IngestionConfig()
        assert cfg.api_page_size == 1000


class TestIngestionConfigDerivedProperties:

    def test_raw_table_full(self):
        cfg = IngestionConfig()
        cfg.uc_catalog = "ctgov"
        cfg.uc_schema_landing = "landing"
        cfg.raw_table_name = "raw_ctgov__studies"
        assert cfg.raw_table_full == "ctgov.landing.raw_ctgov__studies"

    def test_run_date_derived_from_run_ts(self):
        cfg = IngestionConfig()
        cfg.run_ts = "2026-08-05T00:00:00Z"
        assert cfg.run_date == "2026-08-05"

    def test_adls_run_path_contains_run_date_and_ts(self):
        cfg = IngestionConfig()
        cfg.storage_account_name = "testaccount"
        cfg.run_ts = "2026-08-05T00:00:00Z"

        path = cfg.adls_run_path
        assert "run_date=2026-08-05" in path
        assert "run_ts=2026-08-05T00:00:00Z" in path
        assert "testaccount" in path

    def test_adls_watch_path_does_not_include_run_partition(self):
        """Watch path is the parent — Auto Loader monitors all runs, not just current."""
        cfg = IngestionConfig()
        cfg.storage_account_name = "testaccount"
        cfg.run_ts = "2026-08-05T00:00:00Z"

        assert "run_date" not in cfg.adls_watch_path
        assert "run_ts" not in cfg.adls_watch_path

    def test_api_params_base_contains_required_filters(self):
        cfg = IngestionConfig()
        params = cfg.api_params_base

        assert params["filter.studyType"] == "INTERVENTIONAL"
        assert "PHASE2" in params["filter.phase"]
        assert "PHASE3" in params["filter.phase"]
        assert params["filter.firstSubmittedDate"].startswith("2015-01-01")
        assert params["pageSize"] == 1000
        assert params["format"] == "json"

    def test_first_submitted_date_open_ended(self):
        """The date filter must be open-ended (trailing comma) to fetch all studies since 2015."""
        cfg = IngestionConfig()
        assert cfg.api_params_base["filter.firstSubmittedDate"].endswith(",")


class TestIngestionConfigSecretFallback:

    def test_get_secret_falls_back_to_env_var(self, monkeypatch):
        """When not running on Databricks, secrets should fall back to env vars."""
        monkeypatch.setenv("SP_TENANT_ID", "test-tenant-123")
        cfg = IngestionConfig()
        # pyspark import will fail outside Databricks → falls back to env var
        result = cfg.get_secret("sp-tenant-id", "SP_TENANT_ID")
        assert result == "test-tenant-123"

    def test_get_secret_returns_empty_string_if_not_set(self):
        cfg = IngestionConfig()
        result = cfg.get_secret("nonexistent-key", "NONEXISTENT_ENV_VAR")
        assert result == ""
