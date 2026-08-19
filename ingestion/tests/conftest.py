"""
Shared pytest fixtures for the ctgov_ingestion test suite.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from ctgov_ingestion.config import IngestionConfig


# ------------------------------------------------------------------ #
# Config fixtures                                                      #
# ------------------------------------------------------------------ #

@pytest.fixture
def config():
    """
    Minimal IngestionConfig for testing.
    Secret resolution is patched out — no Databricks/Azure required.
    """
    cfg = IngestionConfig()
    cfg.storage_account_name = "testaccount"
    cfg.api_rate_limit_sleep = 0   # no sleep during tests
    cfg.api_max_retries = 1
    return cfg


# ------------------------------------------------------------------ #
# Sample API response helpers                                          #
# ------------------------------------------------------------------ #

def make_study(nct_id: str, status: str = "COMPLETED", sponsor_class: str = "INDUSTRY") -> dict:
    """Build a minimal CT.gov v2 study object."""
    return {
        "protocolSection": {
            "identificationModule": {
                "nctId": nct_id,
                "briefTitle": f"Test study {nct_id}",
            },
            "statusModule": {
                "overallStatus": status,
                "whyStopped": "Budget constraints" if status == "TERMINATED" else None,
                "startDateStruct": {"date": "2020-01-15"},
                "completionDateStruct": {"date": "2023-06-01"},
                "studyFirstSubmitDate": "2019-12-01",
            },
            "sponsorCollaboratorsModule": {
                "leadSponsor": {
                    "name": f"Sponsor of {nct_id}",
                    "class": sponsor_class,
                }
            },
            "designModule": {
                "studyType": "INTERVENTIONAL",
                "phases": ["PHASE2"],
            },
        }
    }


def make_page(studies: list, next_token: str = None, total_count: int = None) -> dict:
    """Build a CT.gov v2 API page response."""
    response = {"studies": studies}
    if next_token:
        response["nextPageToken"] = next_token
    if total_count is not None:
        response["totalCount"] = total_count
    return response


@pytest.fixture
def single_page_response():
    """One page, three studies, no nextPageToken — pagination ends here."""
    return make_page(
        studies=[
            make_study("NCT00000001", status="COMPLETED", sponsor_class="INDUSTRY"),
            make_study("NCT00000002", status="TERMINATED", sponsor_class="NIH"),
            make_study("NCT00000003", status="WITHDRAWN", sponsor_class="INDUSTRY"),
        ],
        total_count=3,
    )


@pytest.fixture
def multi_page_responses():
    """Two pages of results."""
    page1 = make_page(
        studies=[make_study(f"NCT0000000{i}") for i in range(1, 4)],
        next_token="cursor_abc123",
        total_count=5,
    )
    page2 = make_page(
        studies=[make_study(f"NCT0000000{i}") for i in range(4, 6)],
        # no nextPageToken — last page
    )
    return [page1, page2]
