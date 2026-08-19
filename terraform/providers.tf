terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.90"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 2.47"
    }
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.36"
    }
  }
}

# Stage 1 provider — Azure resources
provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
  subscription_id = var.subscription_id
}

provider "azuread" {}

# Stage 2 provider — Databricks workspace resources
# host is set after the workspace is provisioned (output from databricks_workspace module)
provider "databricks" {
  host = var.databricks_workspace_url  # populated after stage-1 apply
  # Uses Azure CLI / service principal auth automatically when running in CI
  azure_workspace_resource_id = var.databricks_workspace_resource_id
}
