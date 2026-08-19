"""
ClinicalTrials.gov v2 API client.

Handles pagination (cursor-based via nextPageToken), retries,
rate limiting, and yields one page of studies at a time.
"""

from __future__ import annotations

import logging
import time
from typing import Generator, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import IngestionConfig

logger = logging.getLogger(__name__)


class CTGovAPIError(Exception):
    """Raised when the CT.gov API returns an unrecoverable error."""


class CTGovAPIClient:
    """
    Paginated client for the ClinicalTrials.gov v2 /studies endpoint.

    Usage:
        client = CTGovAPIClient(config)
        for page_num, page_data in client.iter_pages():
            # page_data is the full parsed JSON response for that page
            process(page_data)
    """

    def __init__(self, config: IngestionConfig) -> None:
        self.config = config
        self.session = self._build_session()

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    def iter_pages(self) -> Generator[tuple[int, dict], None, None]:
        """
        Yield (page_number, page_response_dict) for every page of results.

        Handles:
        - Cursor-based pagination via nextPageToken
        - Per-page retries with exponential backoff (via requests HTTPAdapter)
        - Rate limiting sleep between successful page fetches
        - Logging of progress
        """
        params = dict(self.config.api_params_base)
        page_num = 0
        total_studies = 0

        while True:
            page_num += 1
            logger.info("Fetching page %d (params: %s)", page_num, params)

            response_data = self._fetch_page(params)
            studies = response_data.get("studies", [])
            total_studies += len(studies)

            logger.info(
                "Page %d: received %d studies (total so far: %d)",
                page_num,
                len(studies),
                total_studies,
            )

            yield page_num, response_data

            next_token = response_data.get("nextPageToken")
            if not next_token:
                logger.info(
                    "Pagination complete. Total pages: %d, total studies: %d",
                    page_num,
                    total_studies,
                )
                break

            # Advance cursor
            params["pageToken"] = next_token

            # Respect rate limit
            time.sleep(self.config.api_rate_limit_sleep)

    def get_total_count(self) -> Optional[int]:
        """
        Fetch approximate total count without retrieving all pages.
        Useful for progress estimation.
        Note: CT.gov totalCount is approximate; do not use as exact truth.
        """
        params = {**self.config.api_params_base, "pageSize": 1}
        try:
            data = self._fetch_page(params)
            return data.get("totalCount")
        except CTGovAPIError:
            return None

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _fetch_page(self, params: dict) -> dict:
        """
        Fetch a single page from the API with retry logic.
        Raises CTGovAPIError on non-retryable failures.
        """
        try:
            response = self.session.get(
                self.config.api_base_url,
                params=params,
                timeout=self.config.api_timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response else "unknown"
            raise CTGovAPIError(
                f"HTTP {status} from CT.gov API: {exc}"
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise CTGovAPIError(f"Request failed: {exc}") from exc

    def _build_session(self) -> requests.Session:
        """
        Build a requests Session with automatic retry on transient errors.

        Retries on:
        - 429 Too Many Requests
        - 500, 502, 503, 504 server errors
        """
        session = requests.Session()

        retry_strategy = Retry(
            total=self.config.api_max_retries,
            backoff_factor=1.0,          # 1s, 2s, 4s between retries
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,       # we handle status ourselves
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        session.headers.update(
            {
                "User-Agent": "ctgov-pipeline/1.0 (personal data engineering project)",
                "Accept": "application/json",
            }
        )

        return session
