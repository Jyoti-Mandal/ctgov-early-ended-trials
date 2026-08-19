output "databricks_sp_object_id"     { value = azuread_service_principal.databricks_sp.object_id }
output "key_vault_id"                { value = azurerm_key_vault.main.id }
output "key_vault_uri"               { value = azurerm_key_vault.main.vault_uri }
output "databricks_pat_secret_uri"   {
  value = "${azurerm_key_vault.main.vault_uri}secrets/databricks-pat"
}
