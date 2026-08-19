# Logic App: fires every Monday at every even UTC hour,
# checks if it's the first Monday of the month, then triggers the Databricks job.

resource "azurerm_logic_app_workflow" "ctgov_scheduler" {
  name                = "ctgov-pipeline-scheduler"
  location            = var.location
  resource_group_name = var.resource_group_name
  tags                = var.tags

  # System-assigned managed identity — used to read Databricks PAT from Key Vault
  identity {
    type = "SystemAssigned"
  }

  workflow_definition = jsonencode({
    "$schema"      = "https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#"
    contentVersion = "1.0.0.0"

    parameters = {
      databricks_host = {
        type         = "String"
        defaultValue = var.databricks_host
      }
      databricks_job_id = {
        type         = "Int"
        defaultValue = var.databricks_job_id
      }
      keyvault_secret_uri = {
        type         = "String"
        defaultValue = var.keyvault_secret_uri
      }
    }

    triggers = {
      every_monday_bihourly = {
        type = "Recurrence"
        recurrence = {
          frequency = "Week"
          interval  = 1
          schedule = {
            weekDays = ["Monday"]
            hours    = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22]
            minutes  = [0]
          }
          timeZone  = "UTC"
          # startTime must fall on a Monday — first Monday of intended launch month
          startTime = "2026-09-07T00:00:00Z"
        }
      }
    }

    actions = {

      # Gate: only proceed if today is the first Monday of the month (day 1–7)
      check_first_monday = {
        type = "If"
        runAfter = {}
        expression = {
          and = [{
            lessOrEquals = [
              "@dayOfMonth(utcNow())",
              7
            ]
          }]
        }

        # TRUE branch: fetch token then trigger job
        actions = {

          get_databricks_pat = {
            type = "Http"
            runAfter = {}
            inputs = {
              method = "GET"
              uri    = "@parameters('keyvault_secret_uri')?api-version=7.0"
              authentication = {
                type     = "ManagedServiceIdentity"
                audience = "https://vault.azure.net"
              }
            }
          }

          trigger_databricks_job = {
            type     = "Http"
            runAfter = { get_databricks_pat = ["Succeeded"] }
            inputs = {
              method = "POST"
              uri    = "@concat('https://', parameters('databricks_host'), '/api/2.1/jobs/run-now')"
              headers = {
                Authorization = "@concat('Bearer ', body('get_databricks_pat')?['value'])"
                Content-Type  = "application/json"
              }
              body = {
                job_id = "@parameters('databricks_job_id')"
              }
            }
          }
        }

        # FALSE branch: not first Monday — terminate silently
        else = {
          actions = {}
        }
      }
    }
  })
}

# Allow the Logic App's managed identity to read secrets from Key Vault
resource "azurerm_role_assignment" "logic_app_kv_reader" {
  scope                = var.key_vault_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_logic_app_workflow.ctgov_scheduler.identity[0].principal_id
}
