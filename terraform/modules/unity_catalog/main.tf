# Unity Catalog metastore — created at the Databricks account level
resource "databricks_metastore" "main" {
  name          = "ctgov-metastore"
  storage_root  = var.metastore_storage_url
  region        = "uksouth"
  force_destroy = false
}

# Assign the metastore to the workspace
resource "databricks_metastore_assignment" "main" {
  metastore_id = databricks_metastore.main.id
  workspace_id = var.workspace_id
}

# Grant the ingestion service principal access to the metastore
resource "databricks_metastore_data_access" "sp_access" {
  metastore_id = databricks_metastore.main.id
  name         = "ctgov-sp-access"

  azure_service_principal {
    directory_id   = data.azurerm_client_config.current.tenant_id
    application_id = var.sp_object_id
    client_secret  = "{{secrets/ctgov-scope/sp-client-secret}}"  # Databricks secret reference
  }

  is_default = true
  depends_on = [databricks_metastore_assignment.main]
}

data "azurerm_client_config" "current" {}

# ---- Catalog ----

resource "databricks_catalog" "ctgov" {
  name         = "ctgov"
  metastore_id = databricks_metastore.main.id
  comment      = "ClinicalTrials.gov data pipeline — managed by Terraform"

  depends_on = [databricks_metastore_assignment.main]
}

# ---- Schemas (databases) ----

resource "databricks_schema" "landing" {
  catalog_name = databricks_catalog.ctgov.name
  name         = "landing"
  comment      = "Raw landing zone — populated by Python ingestion pipeline"
}

resource "databricks_schema" "staging" {
  catalog_name = databricks_catalog.ctgov.name
  name         = "staging"
  comment      = "Cleaned, flattened staging models — managed by dbt"
}

resource "databricks_schema" "marts" {
  catalog_name = databricks_catalog.ctgov.name
  name         = "marts"
  comment      = "Business-ready aggregated models — managed by dbt"
}

# ---- Secret scope (backed by Azure Key Vault) ----

resource "databricks_secret_scope" "ctgov" {
  name = "ctgov-scope"

  keyvault_metadata {
    resource_id = var.key_vault_id
    dns_name    = var.key_vault_uri
  }
}
