"""
Tests for CTGovAPIClient.

Uses the `responses` library to mock HTTP calls — no real network requests made.
"""

import json
import pytest
import responses as responses_lib

from ctgov_ingestion.api_client import CTGovAPIClient, CTGovAPIError
from tests.conftest import make_page, make_study


API_URL = "https://clinicaltrials.gov/api/v2/studies"


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def register_page(body: dict, status: int = 200):
    """Register a mocked GET response for the CT.gov studies endpoint."""
    responses_lib.add(
        responses_lib.GET,
        API_URL,
        json=body,
        status=status,
    )


# ------------------------------------------------------------------ #
# Pagination tests                                                     #
# ------------------------------------------------------------------ #

class TestPagination:

    @responses_lib.activate
    def test_single_page_yields_once(self, config):
        """When no nextPageToken, iter_pages should yield exactly once."""
        page = make_page(
            studies=[make_study("NCT00000001")],
            total_count=1,
        )
        register_page(page)

        client = CTGovAPIClient(config)
        results = list(client.iter_pages())

        assert len(results) == 1
        page_num, page_data = results[0]
        assert page_num == 1
        assert len(page_data["studies"]) == 1

    @responses_lib.activate
    def test_multi_page_follows_cursor(self, config, multi_page_responses):
        """Client should follow nextPageToken across all pages."""
        for page in multi_page_responses:
            register_page(page)

        client = CTGovAPIClient(config)
        results = list(client.iter_pages())

        assert len(results) == 2
        assert results[0][0] == 1   # page number
        assert results[1][0] == 2

    @responses_lib.activate
    def test_page_token_passed_on_subsequent_requests(self, config, multi_page_responses):
        """The nextPageToken from page N must appear as pageToken in request N+1."""
        for page in multi_page_responses:
            register_page(page)

        client = CTGovAPIClient(config)
        list(client.iter_pages())

        # Second request should contain the cursor from the first response
        second_request = responses_lib.calls[1].request
        assert "pageToken=cursor_abc123" in second_request.url

    @responses_lib.activate
    def test_total_studies_accumulated_correctly(self, config, multi_page_responses):
        """Studies from all pages should be accessible in the yielded data."""
        for page in multi_page_responses:
            register_page(page)

        client = CTGovAPIClient(config)
        total = sum(len(data["studies"]) for _, data in client.iter_pages())

        assert total == 5   # 3 on page 1 + 2 on page 2

    @responses_lib.activate
    def test_empty_studies_list_terminates_cleanly(self, config):
        """An empty studies array with no nextPageToken should yield once and stop."""
        register_page(make_page(studies=[]))

        client = CTGovAPIClient(config)
        results = list(client.iter_pages())

        assert len(results) == 1
        assert results[0][1]["studies"] == []


# ------------------------------------------------------------------ #
# Error handling tests                                                 #
# ------------------------------------------------------------------ #

class TestErrorHandling:

    @responses_lib.activate
    def test_raises_ctgov_api_error_on_404(self, config):
        responses_lib.add(responses_lib.GET, API_URL, status=404)

        client = CTGovAPIClient(config)
        with pytest.raises(CTGovAPIError, match="HTTP 404"):
            list(client.iter_pages())

    @responses_lib.activate
    def test_raises_ctgov_api_error_on_500(self, config):
        # With max_retries=1, one retry then raises
        responses_lib.add(responses_lib.GET, API_URL, status=500)
        responses_lib.add(responses_lib.GET, API_URL, status=500)

        client = CTGovAPIClient(config)
        with pytest.raises(CTGovAPIError):
            list(client.iter_pages())

    @responses_lib.activate
    def test_retries_on_429_then_succeeds(self, config):
        """Client should retry on 429 and succeed on the next attempt."""
        page = make_page(studies=[make_study("NCT00000001")])
        responses_lib.add(responses_lib.GET, API_URL, status=429)
        responses_lib.add(responses_lib.GET, API_URL, json=page, status=200)

        client = CTGovAPIClient(config)
        results = list(client.iter_pages())

        assert len(results) == 1

    @responses_lib.activate
    def test_raises_on_connection_error(self, config):
        responses_lib.add(
            responses_lib.GET,
            API_URL,
            body=ConnectionError("Network unreachable"),
        )

        client = CTGovAPIClient(config)
        with pytest.raises(CTGovAPIError, match="Request failed"):
            list(client.iter_pages())


# ------------------------------------------------------------------ #
# Request construction tests                                           #
# ------------------------------------------------------------------ #

class TestRequestConstruction:

    @responses_lib.activate
    def test_base_params_sent_on_first_request(self, config):
        register_page(make_page(studies=[]))

        client = CTGovAPIClient(config)
        list(client.iter_pages())

        first_request_url = responses_lib.calls[0].request.url
        assert "filter.studyType=INTERVENTIONAL" in first_request_url
        assert "PHASE2" in first_request_url
        assert "PHASE3" in first_request_url
        assert "2015-01-01" in first_request_url
        assert "pageSize=1000" in first_request_url

    @responses_lib.activate
    def test_user_agent_header_set(self, config):
        register_page(make_page(studies=[]))

        client = CTGovAPIClient(config)
        list(client.iter_pages())

        ua = responses_lib.calls[0].request.headers.get("User-Agent", "")
        assert "ctgov-pipeline" in ua

    @responses_lib.activate
    def test_get_total_count_returns_integer(self, config):
        register_page(make_page(studies=[], total_count=48302))

        client = CTGovAPIClient(config)
        count = client.get_total_count()

        assert count == 48302

    @responses_lib.activate
    def test_get_total_count_returns_none_on_api_error(self, config):
        responses_lib.add(responses_lib.GET, API_URL, status=500)
        responses_lib.add(responses_lib.GET, API_URL, status=500)

        client = CTGovAPIClient(config)
        count = client.get_total_count()

        assert count is None
