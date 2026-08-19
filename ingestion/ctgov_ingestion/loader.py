"""
Auto Loader: ADLS Gen2 → Delta table (raw_ctgov__studies).

Uses Databricks Auto Loader (cloudFiles) in trigger-once mode to:
1. Read all new JSON page files written in the current and prior runs
2. Explode the studies[] array — one Delta row per study
3. Extract nct_id as the row key
4. Append to the Unity Catalog raw Delta table with run metadata

Idempotency: Auto Loader checkpoints ensure files are never reprocessed.
Deduplication: handled downstream in the dbt staging model via ROW_NUMBER().
"""

from __future__ import annotations

import logging

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StringType

from .config import IngestionConfig

logger = logging.getLogger(__name__)


class DeltaLoader:
    """
    Loads raw CT.gov JSON files from ADLS into a Delta landing table
    using Databricks Auto Loader.
    """

    def __init__(self, config: IngestionConfig, spark: SparkSession) -> None:
        self.config = config
        self.spark = spark

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    def load(self) -> int:
        """
        Run Auto Loader in trigger-once mode.
        Returns the number of rows appended in this run.
        """
        logger.info(
            "Starting Auto Loader: %s → %s",
            self.config.adls_watch_path,
            self.config.raw_table_full,
        )

        self._ensure_table_exists()

        # Count rows before load for delta calculation
        rows_before = self._row_count()

        (
            self.spark.readStream
            .format("cloudFiles")
            .option("cloudFiles.format", "json")
            .option("cloudFiles.schemaLocation", self.config.checkpoint_path + "/schema")
            .option("cloudFiles.inferColumnTypes", "false")   # keep everything as string
            .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
            .option("multiLine", "true")                      # each file is one JSON object
            .load(self.config.adls_watch_path)
            .transform(self._explode_studies)
            .transform(self._add_metadata)
            .writeStream
            .format("delta")
            .outputMode("append")
            .option("checkpointLocation", self.config.checkpoint_path + "/data")
            .option("mergeSchema", "true")
            .trigger(once=True)                               # batch mode, not continuous
            .toTable(self.config.raw_table_full)
            .awaitTermination()
        )

        rows_after = self._row_count()
        rows_added = rows_after - rows_before

        logger.info(
            "Auto Loader complete. Rows added: %d (total in table: %d)",
            rows_added,
            rows_after,
        )
        return rows_added

    # ------------------------------------------------------------------ #
    # Private transforms                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _explode_studies(df):
        """
        Each JSON file contains {"studies": [...], "nextPageToken": ..., "totalCount": ...}.
        Explode the studies array so we get one row per study.
        """
        return (
            df
            # studies column is an array after Auto Loader reads the JSON
            .withColumn("study", F.explode(F.col("studies")))
            .drop("studies", "nextPageToken", "totalCount")
            # Serialise the study struct back to a JSON string for schema-agnostic storage
            .withColumn("raw_json", F.to_json(F.col("study")))
            # Extract nct_id for use as the row key — avoids full JSON parse in downstream SQL
            .withColumn(
                "nct_id",
                F.get_json_object(F.col("raw_json"), "$.protocolSection.identificationModule.nctId")
                .cast(StringType()),
            )
            .drop("study")
        )

    def _add_metadata(self, df):
        """Add pipeline metadata columns to every row."""
        return (
            df
            .withColumn("run_ts", F.lit(self.config.run_ts))
            .withColumn("run_date", F.lit(self.config.run_date))
            .withColumn(
                "_ingested_at",
                F.current_timestamp(),
            )
        )

    # ------------------------------------------------------------------ #
    # Table management                                                     #
    # ------------------------------------------------------------------ #

    def _ensure_table_exists(self) -> None:
        """
        Create the raw Delta table if it doesn't already exist.
        Schema is intentionally minimal — raw_json is the source of truth.
        """
        self.spark.sql(f"USE CATALOG {self.config.uc_catalog}")
        self.spark.sql(f"USE SCHEMA {self.config.uc_schema_landing}")

        self.spark.sql(f"""
            CREATE TABLE IF NOT EXISTS {self.config.raw_table_full} (
                nct_id      STRING  COMMENT 'NCT identifier extracted from raw JSON for indexing',
                raw_json    STRING  COMMENT 'Full study JSON as returned by CT.gov v2 API',
                run_ts      STRING  COMMENT 'Pipeline run timestamp (UTC ISO-8601)',
                run_date    STRING  COMMENT 'Pipeline run date (YYYY-MM-DD)',
                _ingested_at TIMESTAMP COMMENT 'Timestamp row was written to Delta'
            )
            USING DELTA
            COMMENT 'Raw landing table for ClinicalTrials.gov study data. One row per study per pipeline run.'
            TBLPROPERTIES (
                'delta.autoOptimize.optimizeWrite' = 'true',
                'delta.autoOptimize.autoCompact'   = 'true'
            )
        """)
        logger.info("Table %s ready", self.config.raw_table_full)

    def _row_count(self) -> int:
        try:
            return self.spark.table(self.config.raw_table_full).count()
        except Exception:
            return 0
