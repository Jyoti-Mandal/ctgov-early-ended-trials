# Single Databricks Job with two dependent tasks:
#   Task 1 — ingest: Python wheel calling CT.gov API → ADLS → Delta
#   Task 2 — dbt_run: dbt build (depends on ingest completing)
#
# No schedule defined here — Logic Apps triggers via /api/2.1/jobs/run-now

resource "databricks_job" "ctgov_pipeline" {
  name = "ctgov-pipeline"

  # ---- Task 1: Python ingestion --------------------------------
  task {
    task_key        = "ingest"
    description     = "Fetch CT.gov v2 API, write raw JSON to ADLS, load into Delta"

    python_wheel_task {
      package_name = "ctgov_ingestion"
      entry_point  = "main"       # maps to console_scripts entry in setup.py
    }

    # Serverless compute — no cluster block needed
    environment_key = "default"

    # PyPI libraries installed at runtime on serverless
    library {
      pypi {
        package = "requests>=2.31.0"
      }
    }
    library {
      pypi {
        package = "azure-storage-file-datalake>=12.14.0"
      }
    }
    library {
      pypi {
        package = "azure-identity>=1.15.0"
      }
    }

    # Pass config as environment variables; secrets resolved from Databricks scope
    environment {
      environment_key = "default"
      spec {
        type = "SERVERLESS"
        environment_variables = {
          STORAGE_ACCOUNT_NAME = var.storage_account_name
          SECRET_SCOPE         = var.secret_scope
          CHECKPOINT_BASE      = "abfss://raw@${var.storage_account_name}.dfs.core.windows.net/_checkpoints/ctgov"
        }
      }
    }
  }

  # ---- Task 2: dbt run -----------------------------------------
  task {
    task_key    = "dbt_run"
    description = "Run dbt build: staging + marts models"

    depends_on {
      task_key = "ingest"
    }

    python_wheel_task {
      package_name = "ctgov_dbt_runner"
      entry_point  = "main"
    }

    environment_key = "default"

    library {
      pypi {
        package = "dbt-databricks>=1.7.0"
      }
    }

    environment {
      environment_key = "default"
      spec {
        type = "SERVERLESS"
        environment_variables = {
          DBT_DATABRICKS_HTTP_PATH = "/sql/1.0/warehouses/${var.sql_warehouse_id}"
          DBT_DATABRICKS_TOKEN     = "{{secrets/${var.secret_scope}/databricks-pat}}"
        }
      }
    }
  }

  # Retry the whole job once on failure before alerting
  max_concurrent_runs = 1

  tags = {
    project    = "ctgov-pipeline"
    managed_by = "terraform"
  }
}

# Upload the Python wheel to Databricks workspace
# In practice, this is done via CI/CD (Azure DevOps pipeline)
# The wheel path below assumes it's been uploaded to DBFS or a volume
resource "databricks_dbfs_file" "ingestion_wheel" {
  source = var.ingestion_wheel_path
  path   = "/FileStore/wheels/ctgov_ingestion-1.0.0-py3-none-any.whl"

  # Only upload if the wheel path is provided (not empty)
  count  = var.ingestion_wheel_path != "" ? 1 : 0
}
