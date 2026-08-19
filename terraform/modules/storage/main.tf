locals {
  # Storage account names must be 3-24 chars, lowercase alphanumeric only
  storage_account_name = replace(lower("${var.project}${var.environment}dlake"), "-", "")
}

resource "azurerm_storage_account" "datalake" {
  name                     = local.storage_account_name
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  is_hns_enabled           = true    # Required for ADLS Gen2

  blob_properties {
    versioning_enabled = true        # Protects against accidental deletion
  }

  tags = var.tags
}

# Container for raw JSON landing zone
resource "azurerm_storage_data_lake_gen2_filesystem" "raw" {
  name               = "raw"
  storage_account_id = azurerm_storage_account.datalake.id
}

# Dedicated container for Unity Catalog metastore
resource "azurerm_storage_data_lake_gen2_filesystem" "unity_catalog" {
  name               = "unity-catalog"
  storage_account_id = azurerm_storage_account.datalake.id
}
