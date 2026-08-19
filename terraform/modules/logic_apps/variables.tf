variable "resource_group_name"  { type = string }
variable "location"             { type = string }
variable "databricks_host"      { type = string }
variable "databricks_job_id"    { type = number }
variable "keyvault_secret_uri"  { type = string  sensitive = true }
variable "key_vault_id"         { type = string }
variable "tags"                 { type = map(string) }
