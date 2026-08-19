# Serverless SQL Warehouse — used by dbt to run transformations
resource "databricks_sql_endpoint" "dbt" {
  name             = "ctgov-dbt-warehouse"
  cluster_size     = "Small"
  auto_stop_mins   = 10          # Stop after 10 min idle — controls cost
  serverless       = true
  warehouse_type   = "PRO"       # Required for serverless

  tags {
    custom_tags {
      key   = "project"
      value = "ctgov-pipeline"
    }
    custom_tags {
      key   = "managed_by"
      value = "terraform"
    }
  }
}
