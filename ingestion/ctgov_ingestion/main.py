"""
Entry point for the CT.gov ingestion Databricks Job.

Orchestrates:
1. Fetch all pages from CT.gov v2 API
2. Write each page as JSON to ADLS Gen2
3. Run Auto Loader to land studies into Delta (raw_ctgov__studies)

Designed to run as a Python wheel task on Databricks serverless compute.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

from pyspark.sql import SparkSession

from .api_client import CTGovAPIClient, CTGovAPIError
from .config import IngestionConfig
from .loader import DeltaLoader
from .storage import ADLSWriter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def run(config: IngestionConfig | None = None) -> None:
    """
    Main pipeline function.

    Args:
        config: Optional pre-built config (useful for testing).
                If None, a default IngestionConfig is constructed.
    """
    start = datetime.now(timezone.utc)
    logger.info("=== CT.gov ingestion pipeline starting: run_ts=%s ===", start.isoformat())

    if config is None:
        config = IngestionConfig()

    logger.info(
        "Config: account=%s, table=%s, phases=%s, study_type=%s",
        config.storage_account_name,
        config.raw_table_full,
        config.phases,
        config.study_type,
    )

    # Get or create Spark session (already running on Databricks)
    spark = SparkSession.getActiveSession() or SparkSession.builder.getOrCreate()

    # ------------------------------------------------------------------ #
    # Step 1: Fetch from API and write to ADLS                            #
    # ------------------------------------------------------------------ #
    api_client = CTGovAPIClient(config)
    adls_writer = ADLSWriter(config)

    approximate_total = api_client.get_total_count()
    if approximate_total:
        logger.info("Approximate total studies to fetch: %d", approximate_total)

    total_pages = 0
    total_studies = 0

    try:
        for page_num, page_data in api_client.iter_pages():
            studies_in_page = len(page_data.get("studies", []))
            adls_writer.write_page(page_num, page_data)
            total_pages += 1
            total_studies += studies_in_page

    except CTGovAPIError as exc:
        logger.error("API error after %d pages: %s", total_pages, exc)
        raise

    adls_writer.write_run_manifest(
        total_pages=total_pages,
        total_studies=total_studies,
    )

    logger.info(
        "API fetch complete. Pages: %d, Studies: %d, ADLS path: %s",
        total_pages,
        total_studies,
        config.adls_run_path,
    )

    # ------------------------------------------------------------------ #
    # Step 2: Auto Loader → Delta                                         #
    # ------------------------------------------------------------------ #
    loader = DeltaLoader(config, spark)
    rows_added = loader.load()

    # ------------------------------------------------------------------ #
    # Summary                                                             #
    # ------------------------------------------------------------------ #
    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info(
        "=== Pipeline complete. Pages=%d, Studies fetched=%d, "
        "Delta rows added=%d, Elapsed=%.1fs ===",
        total_pages,
        total_studies,
        rows_added,
        elapsed,
    )


def main() -> None:
    """Wheel entry point (referenced in setup.py console_scripts)."""
    run()


if __name__ == "__main__":
    main()
