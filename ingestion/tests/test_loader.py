"""
Tests for DeltaLoader.

Uses a local PySpark session (no Databricks cluster required).
Delta Lake operations are tested via spark-local with the delta-spark package.

Run with:
    pip install pyspark delta-spark
    pytest tests/test_loader.py -v
"""

import json
import pytest

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StructField, StringType, ArrayType

from ctgov_ingestion.loader import DeltaLoader
from ctgov_ingestion.config import IngestionConfig
from tests.conftest import make_study, make_page


# ------------------------------------------------------------------ #
# Spark session fixture (session-scoped — one Spark per test run)     #
# ------------------------------------------------------------------ #

@pytest.fixture(scope="session")
def spark():
    """
    Local Spark session with Delta Lake support.
    Requires: pip install pyspark delta-spark
    """
    spark = (
        SparkSession.builder
        .master("local[2]")
        .appName("ctgov-ingestion-tests")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config(
            "spark.sql.catalog.spark_catalog",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        )
        .config("spark.sql.shuffle.partitions", "2")  # fast for small test data
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")
    yield spark
    spark.stop()


@pytest.fixture
def loader(spark, config):
    config.run_ts = "2026-08-05T00:00:00Z"
    return DeltaLoader(config, spark)


# ------------------------------------------------------------------ #
# Schema helpers                                                       #
# ------------------------------------------------------------------ #

def make_raw_page_df(spark, studies: list, next_token: str = None):
    """
    Build a DataFrame that mimics what Auto Loader produces when it reads
    a CT.gov page JSON file: one row, with a studies array column.
    """
    page = make_page(studies, next_token)
    # Auto Loader reads the top-level JSON and infers columns
    data = [{"studies": studies, "nextPageToken": next_token, "totalCount": len(studies)}]
    schema = StructType([
        StructField("studies", ArrayType(StringType()), True),
        StructField("nextPageToken", StringType(), True),
        StructField("totalCount", StringType(), True),
    ])
    # Represent each study as a JSON string (matches Auto Loader behaviour with inferColumnTypes=false)
    rows = [{"studies": [json.dumps(s) for s in studies],
             "nextPageToken": next_token,
             "totalCount": str(len(studies))}]
    return spark.createDataFrame(rows, schema=schema)


# ------------------------------------------------------------------ #
# _explode_studies transform                                           #
# ------------------------------------------------------------------ #

class TestExplodeStudies:

    def test_one_row_per_study(self, loader, spark):
        """Each study in the array must become its own row."""
        studies = [make_study(f"NCT0000000{i}") for i in range(1, 4)]
        input_df = make_raw_page_df(spark, studies)

        # Convert studies column to array of structs (simulating inferred schema)
        input_df = input_df.withColumn(
            "studies",
            F.from_json(
                F.col("studies").cast("string"),
                ArrayType(StringType()),
            )
        )

        result = DeltaLoader._explode_studies(input_df)
        assert result.count() == 3

    def test_studies_column_dropped_after_explode(self, loader, spark):
        """The studies array column must not appear in the output."""
        studies = [make_study("NCT00000001")]
        input_df = make_raw_page_df(spark, studies)

        result = DeltaLoader._explode_studies(input_df)
        assert "studies" not in result.columns

    def test_raw_json_column_present(self, loader, spark):
        """Each row must have a raw_json column containing the study JSON."""
        studies = [make_study("NCT00000001")]
        input_df = make_raw_page_df(spark, studies)

        result = DeltaLoader._explode_studies(input_df)
        assert "raw_json" in result.columns

    def test_nct_id_extracted_correctly(self, loader, spark):
        """nct_id must be extracted from protocolSection.identificationModule.nctId."""
        studies = [
            make_study("NCT00000001"),
            make_study("NCT00000002"),
        ]
        input_df = make_raw_page_df(spark, studies)

        result = DeltaLoader._explode_studies(input_df)
        nct_ids = {row.nct_id for row in result.collect()}

        assert "NCT00000001" in nct_ids
        assert "NCT00000002" in nct_ids

    def test_pagination_columns_dropped(self, loader, spark):
        """nextPageToken and totalCount from the page response must not appear in output."""
        studies = [make_study("NCT00000001")]
        input_df = make_raw_page_df(spark, studies, next_token="cursor_abc")

        result = DeltaLoader._explode_studies(input_df)
        assert "nextPageToken" not in result.columns
        assert "totalCount" not in result.columns

    def test_raw_json_is_parseable(self, loader, spark):
        """raw_json must be valid JSON containing the original study data."""
        studies = [make_study("NCT00000001", status="TERMINATED", sponsor_class="NIH")]
        input_df = make_raw_page_df(spark, studies)

        result = DeltaLoader._explode_studies(input_df)
        row = result.first()
        parsed = json.loads(row.raw_json)

        assert parsed["protocolSection"]["statusModule"]["overallStatus"] == "TERMINATED"
        assert parsed["protocolSection"]["sponsorCollaboratorsModule"]["leadSponsor"]["class"] == "NIH"


# ------------------------------------------------------------------ #
# _add_metadata transform                                              #
# ------------------------------------------------------------------ #

class TestAddMetadata:

    def test_run_ts_added(self, loader, spark):
        df = spark.createDataFrame([{"nct_id": "NCT00000001", "raw_json": "{}"}])
        result = loader._add_metadata(df)
        assert "run_ts" in result.columns
        assert result.first().run_ts == "2026-08-05T00:00:00Z"

    def test_run_date_added(self, loader, spark):
        df = spark.createDataFrame([{"nct_id": "NCT00000001", "raw_json": "{}"}])
        result = loader._add_metadata(df)
        assert "run_date" in result.columns
        assert result.first().run_date == "2026-08-05"

    def test_ingested_at_timestamp_added(self, loader, spark):
        df = spark.createDataFrame([{"nct_id": "NCT00000001", "raw_json": "{}"}])
        result = loader._add_metadata(df)
        assert "_ingested_at" in result.columns
        assert result.first()._ingested_at is not None

    def test_existing_columns_preserved(self, loader, spark):
        df = spark.createDataFrame([{"nct_id": "NCT00000001", "raw_json": '{"key": "val"}'}])
        result = loader._add_metadata(df)
        assert "nct_id" in result.columns
        assert "raw_json" in result.columns


# ------------------------------------------------------------------ #
# _ensure_table_exists                                                 #
# ------------------------------------------------------------------ #

class TestEnsureTableExists:

    def test_create_table_sql_uses_correct_table_name(self, loader, spark, config, mocker):
        """The CREATE TABLE statement must reference the fully qualified table name."""
        mock_sql = mocker.patch.object(spark, "sql", return_value=MagicMock())

        loader._ensure_table_exists()

        calls = [str(c) for c in mock_sql.call_args_list]
        create_call = next((c for c in calls if "CREATE TABLE" in c), None)
        assert create_call is not None
        assert config.raw_table_full in create_call

    def test_create_table_uses_if_not_exists(self, loader, spark, mocker):
        """Must use IF NOT EXISTS to be idempotent across pipeline runs."""
        mock_sql = mocker.patch.object(spark, "sql", return_value=MagicMock())

        loader._ensure_table_exists()

        calls = [str(c) for c in mock_sql.call_args_list]
        create_call = next((c for c in calls if "CREATE TABLE" in c), None)
        assert "IF NOT EXISTS" in create_call

    def test_raw_json_column_in_schema(self, loader, spark, mocker):
        """The landing table schema must include raw_json and nct_id."""
        mock_sql = mocker.patch.object(spark, "sql", return_value=MagicMock())

        loader._ensure_table_exists()

        calls = [str(c) for c in mock_sql.call_args_list]
        create_call = next((c for c in calls if "CREATE TABLE" in c), None)
        assert "raw_json" in create_call
        assert "nct_id" in create_call


# ------------------------------------------------------------------ #
# Missing value handling                                               #
# ------------------------------------------------------------------ #

class TestMissingValueHandling:

    def test_null_nct_id_when_field_missing(self, loader, spark):
        """Study with no nctId in identificationModule should produce NULL nct_id, not error."""
        study_no_nct = {
            "protocolSection": {
                "identificationModule": {},   # no nctId key
                "statusModule": {"overallStatus": "COMPLETED"},
            }
        }
        input_df = make_raw_page_df(spark, [study_no_nct])
        result = DeltaLoader._explode_studies(input_df)

        assert result.count() == 1
        assert result.first().nct_id is None

    def test_study_with_minimal_fields_does_not_error(self, loader, spark):
        """Loader must not crash on studies that are missing optional fields."""
        minimal_study = {"protocolSection": {}}
        input_df = make_raw_page_df(spark, [minimal_study])

        # Should not raise
        result = DeltaLoader._explode_studies(input_df)
        assert result.count() == 1
