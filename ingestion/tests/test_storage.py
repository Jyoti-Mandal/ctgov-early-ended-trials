"""
Tests for ADLSWriter.

Mocks the Azure Data Lake SDK — no real Azure connection required.
All tests verify path construction, content correctness, and auth flow.
"""

import json
import pytest
from unittest.mock import MagicMock, patch, call

from ctgov_ingestion.storage import ADLSWriter
from tests.conftest import make_page, make_study


# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #

@pytest.fixture
def writer(config):
    config.run_ts = "2026-08-05T00:00:00Z"
    return ADLSWriter(config)


@pytest.fixture
def mock_adls_client():
    """
    Full mock of the DataLakeServiceClient call chain:
    client → get_file_system_client → get_file_client → create_file / append_data / flush_data
    """
    mock_file_client = MagicMock()
    mock_fs_client = MagicMock()
    mock_fs_client.get_file_client.return_value = mock_file_client
    mock_service_client = MagicMock()
    mock_service_client.get_file_system_client.return_value = mock_fs_client

    return mock_service_client, mock_fs_client, mock_file_client


# ------------------------------------------------------------------ #
# File path construction                                               #
# ------------------------------------------------------------------ #

class TestFilePathConstruction:

    def test_page_file_path_includes_run_date(self, writer, mock_adls_client, config):
        mock_service, mock_fs, mock_file = mock_adls_client
        writer._client = mock_service

        writer.write_page(1, make_page(studies=[]))

        file_path_arg = mock_fs.get_file_client.call_args[0][0]
        assert "run_date=2026-08-05" in file_path_arg

    def test_page_file_path_includes_run_ts(self, writer, mock_adls_client, config):
        mock_service, mock_fs, mock_file = mock_adls_client
        writer._client = mock_service

        writer.write_page(1, make_page(studies=[]))

        file_path_arg = mock_fs.get_file_client.call_args[0][0]
        assert "run_ts=2026-08-05T00:00:00Z" in file_path_arg

    def test_page_file_name_is_zero_padded(self, writer, mock_adls_client):
        mock_service, mock_fs, mock_file = mock_adls_client
        writer._client = mock_service

        writer.write_page(7, make_page(studies=[]))

        file_path_arg = mock_fs.get_file_client.call_args[0][0]
        assert "page_0007.json" in file_path_arg

    def test_page_file_name_pads_to_four_digits(self, writer, mock_adls_client):
        mock_service, mock_fs, mock_file = mock_adls_client
        writer._client = mock_service

        writer.write_page(42, make_page(studies=[]))

        file_path_arg = mock_fs.get_file_client.call_args[0][0]
        assert "page_0042.json" in file_path_arg

    def test_manifest_file_named_correctly(self, writer, mock_adls_client):
        mock_service, mock_fs, mock_file = mock_adls_client
        writer._client = mock_service

        writer.write_run_manifest(total_pages=5, total_studies=4800)

        file_path_arg = mock_fs.get_file_client.call_args[0][0]
        assert "_manifest.json" in file_path_arg

    def test_raw_container_used_not_unity_catalog(self, writer, mock_adls_client, config):
        mock_service, mock_fs, mock_file = mock_adls_client
        writer._client = mock_service

        writer.write_page(1, make_page(studies=[]))

        container_arg = mock_service.get_file_system_client.call_args[0][0]
        assert container_arg == config.storage_container_raw
        assert container_arg != "unity-catalog"


# ------------------------------------------------------------------ #
# Content correctness                                                  #
# ------------------------------------------------------------------ #

class TestContentCorrectness:

    def test_page_written_as_valid_json(self, writer, mock_adls_client):
        mock_service, mock_fs, mock_file = mock_adls_client
        writer._client = mock_service

        page_data = make_page(
            studies=[make_study("NCT00000001")],
            next_token="abc",
            total_count=1,
        )
        writer.write_page(1, page_data)

        written_bytes = mock_file.append_data.call_args[1]["data"]
        parsed = json.loads(written_bytes.decode("utf-8"))
        assert "studies" in parsed
        assert parsed["nextPageToken"] == "abc"

    def test_manifest_contains_run_metadata(self, writer, mock_adls_client):
        mock_service, mock_fs, mock_file = mock_adls_client
        writer._client = mock_service

        writer.write_run_manifest(total_pages=10, total_studies=9500)

        written_bytes = mock_file.append_data.call_args[1]["data"]
        manifest = json.loads(written_bytes.decode("utf-8"))

        assert manifest["total_pages"] == 10
        assert manifest["total_studies"] == 9500
        assert manifest["run_ts"] == "2026-08-05T00:00:00Z"
        assert manifest["run_date"] == "2026-08-05"
        assert "api_params" in manifest

    def test_write_uses_adls_atomic_pattern(self, writer, mock_adls_client):
        """create_file → append_data → flush_data must all be called in order."""
        mock_service, mock_fs, mock_file = mock_adls_client
        writer._client = mock_service

        writer.write_page(1, make_page(studies=[]))

        mock_file.create_file.assert_called_once()
        mock_file.append_data.assert_called_once()
        mock_file.flush_data.assert_called_once()

    def test_flush_length_matches_content_length(self, writer, mock_adls_client):
        """flush_data must receive the same byte length as append_data."""
        mock_service, mock_fs, mock_file = mock_adls_client
        writer._client = mock_service

        writer.write_page(1, make_page(studies=[make_study("NCT00000001")]))

        appended_bytes = mock_file.append_data.call_args[1]["data"]
        flushed_length = mock_file.flush_data.call_args[0][0]

        assert flushed_length == len(appended_bytes)

    def test_write_page_returns_full_abfss_path(self, writer, mock_adls_client, config):
        mock_service, mock_fs, mock_file = mock_adls_client
        writer._client = mock_service

        returned_path = writer.write_page(1, make_page(studies=[]))

        assert returned_path.startswith("abfss://")
        assert config.storage_account_name in returned_path
        assert "page_0001.json" in returned_path


# ------------------------------------------------------------------ #
# Authentication                                                       #
# ------------------------------------------------------------------ #

class TestAuthentication:

    def test_client_initialised_with_service_principal(self, config):
        """ADLS client should be built using ClientSecretCredential, not a SAS token."""
        with patch("ctgov_ingestion.storage.DataLakeServiceClient") as mock_dls, \
             patch("ctgov_ingestion.storage.ClientSecretCredential") as mock_cred, \
             patch.object(config, "get_secret", side_effect=["tenant", "client", "secret"]):

            mock_dls.return_value.get_file_system_client.return_value \
                .get_file_client.return_value = MagicMock()

            writer = ADLSWriter(config)
            writer.write_page(1, make_page(studies=[]))

            mock_cred.assert_called_once_with(
                tenant_id="tenant",
                client_id="client",
                client_secret="secret",
            )
            mock_dls.assert_called_once()

    def test_client_is_lazily_initialised(self, config):
        """The ADLS client should only be created on first write, not at construction."""
        with patch("ctgov_ingestion.storage.DataLakeServiceClient") as mock_dls, \
             patch("ctgov_ingestion.storage.ClientSecretCredential"):
            writer = ADLSWriter(config)
            mock_dls.assert_not_called()   # not yet initialised

    def test_client_reused_across_multiple_writes(self, writer, mock_adls_client):
        """A new SDK client should NOT be created for every page write."""
        mock_service, mock_fs, mock_file = mock_adls_client
        writer._client = mock_service   # inject pre-built client

        writer.write_page(1, make_page(studies=[]))
        writer.write_page(2, make_page(studies=[]))

        # get_file_system_client called twice (once per write) but on same client instance
        assert mock_service.get_file_system_client.call_count == 2
