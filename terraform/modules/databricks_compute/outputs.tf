output "sql_warehouse_id"   { value = databricks_sql_endpoint.dbt.id }
output "sql_warehouse_http_path" {
  value = "/sql/1.0/warehouses/${databricks_sql_endpoint.dbt.id}"
}
