data "azurerm_client_config" "current" {}

# ---- Service Principal for Databricks jobs ----

resource "azuread_application" "databricks_sp" {
  display_name = "${var.project}-${var.environment}-databricks-sp"
}

resource "azuread_service_principal" "databricks_sp" {
  client_id = azuread_application.databricks_sp.client_id
}

resource "azuread_service_principal_password" "databricks_sp" {
  service_principal_id = azuread_service_principal.databricks_sp.id
  end_date_relative    = "8760h"   # 1 year; rotate via CI/CD
}

# Grant SP access to ADLS (Storage Blob Data Contributor)
resource "azurerm_role_assignment" "sp_storage" {
  scope                = var.storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azuread_service_principal.databricks_sp.object_id
}

# ---- Key Vault — stores all secrets ----

resource "azurerm_key_vault" "main" {
  name                = var.key_vault_name
  location            = var.location
  resource_group_name = var.resource_group_name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  # Allow Terraform deployer to manage secrets
  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id
    secret_permissions = ["Get", "List", "Set", "Delete", "Purge"]
  }

  tags = var.tags
}

# Store SP credentials in Key Vault
resource "azurerm_key_vault_secret" "sp_tenant_id" {
  name         = "sp-tenant-id"
  value        = data.azurerm_client_config.current.tenant_id
  key_vault_id = azurerm_key_vault.main.id
}

resource "azurerm_key_vault_secret" "sp_client_id" {
  name         = "sp-client-id"
  value        = azuread_application.databricks_sp.client_id
  key_vault_id = azurerm_key_vault.main.id
}

resource "azurerm_key_vault_secret" "sp_client_secret" {
  name         = "sp-client-secret"
  value        = azuread_service_principal_password.databricks_sp.value
  key_vault_id = azurerm_key_vault.main.id

  lifecycle {
    ignore_changes = [value]   # don't overwrite on re-apply after rotation
  }
}

# Placeholder for Databricks PAT (set manually after workspace creation)
resource "azurerm_key_vault_secret" "databricks_pat" {
  name         = "databricks-pat"
  value        = "REPLACE_WITH_REAL_PAT"
  key_vault_id = azurerm_key_vault.main.id

  lifecycle {
    ignore_changes = [value]   # managed outside Terraform after initial creation
  }
}
