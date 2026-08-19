# Remote state in Azure Blob Storage.
# IMPORTANT: This storage account must be created manually (bootstrap) before
# running `terraform init`. It cannot manage its own backend.
#
# Bootstrap script (run once):
#   az group create -n ctgov-tfstate-rg -l uksouth
#   az storage account create -n ctgovtfstate -g ctgov-tfstate-rg --sku Standard_LRS
#   az storage container create -n tfstate --account-name ctgovtfstate
#   az storage account blob-service-properties update \
#     --account-name ctgovtfstate --enable-versioning true

terraform {
  backend "azurerm" {
    resource_group_name  = "ctgov-tfstate-rg"
    storage_account_name = "ctgovtfstate"
    container_name       = "tfstate"
    key                  = "ctgov.tfstate"
  }
}
