variable "sql_warehouse_id"      { type = string }
variable "storage_account_name"  { type = string }
variable "uc_catalog"            { type = string  default = "ctgov" }
variable "secret_scope"          { type = string  default = "ctgov-scope" }
variable "key_vault_uri"         { type = string  default = "" }
variable "ingestion_wheel_path"  { type = string  default = "" }
