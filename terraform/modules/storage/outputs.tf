output "storage_account_id"   { value = azurerm_storage_account.datalake.id }
output "storage_account_name" { value = azurerm_storage_account.datalake.name }

output "unity_catalog_abfss_url" {
  value = "abfss://unity-catalog@${azurerm_storage_account.datalake.name}.dfs.core.windows.net/"
}
