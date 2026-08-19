# Key outputs needed for stage-2 apply and for CI/CD pipelines

output "resource_group_name" {
  description = "Name of the Azure resource group"
  value       = module.resource_group.name
}

output "storage_account_name" {
  description = "ADLS Gen2 storage account name"
  value       = module.storage.storage_account_name
}

output "databricks_workspace_url" {
  description = "Databricks workspace URL — use as var.databricks_workspace_url in stage-2 apply"
  value       = module.databricks_workspace.workspace_url
}

output "databricks_workspace_resource_id" {
  description = "Azure resource ID of the Databricks workspace"
  value       = module.databricks_workspace.workspace_resource_id
}

output "sql_warehouse_http_path" {
  description = "HTTP path for the dbt SQL Warehouse — add to profiles.yml"
  value       = module.databricks_compute.sql_warehouse_http_path
}

output "key_vault_uri" {
  description = "Azure Key Vault URI"
  value       = module.iam.key_vault_uri
}

output "pipeline_job_id" {
  description = "Databricks Job ID for the ctgov pipeline — used by Logic Apps"
  value       = module.databricks_jobs.pipeline_job_id
}

output "logic_app_name" {
  description = "Name of the Logic App scheduler"
  value       = module.logic_apps.logic_app_name
}
