subscription_id = "YOUR-PROD-SUBSCRIPTION-ID"
environment     = "prod"
location        = "uksouth"
project         = "ctgov"

tags = {
  project     = "ctgov-pipeline"
  environment = "prod"
  managed_by  = "terraform"
  team        = "data-engineering"
}

databricks_workspace_url         = ""
databricks_workspace_resource_id = ""
