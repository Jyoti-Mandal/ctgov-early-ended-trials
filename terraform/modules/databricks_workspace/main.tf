resource "azurerm_databricks_workspace" "main" {
  name                        = "${var.project}-${var.environment}-dbx"
  resource_group_name         = var.resource_group_name
  location                    = var.location
  sku                         = "premium"   # Required for Unity Catalog

  # Databricks creates a managed resource group for cluster VMs etc.
  managed_resource_group_name = "${var.project}-${var.environment}-dbx-managed-rg"

  tags = var.tags
}
