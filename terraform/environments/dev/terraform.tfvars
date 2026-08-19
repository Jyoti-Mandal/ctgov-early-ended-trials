subscription_id = "YOUR-DEV-SUBSCRIPTION-ID"
environment     = "dev"
location        = "uksouth"
project         = "ctgov"

tags = {
  project     = "ctgov-pipeline"
  environment = "dev"
  managed_by  = "terraform"
  team        = "data-engineering"
}

# Populated after stage-1 apply — fill in before running stage-2
databricks_workspace_url         = ""
databricks_workspace_resource_id = ""
