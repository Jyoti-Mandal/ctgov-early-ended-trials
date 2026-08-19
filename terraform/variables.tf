variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "uksouth"
}

variable "environment" {
  description = "Deployment environment (dev / prod)"
  type        = string
  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be 'dev' or 'prod'."
  }
}

variable "project" {
  description = "Project name prefix used in all resource names"
  type        = string
  default     = "ctgov"
}

variable "tags" {
  description = "Tags applied to all Azure resources"
  type        = map(string)
  default = {
    project     = "ctgov-pipeline"
    managed_by  = "terraform"
    team        = "data-engineering"
  }
}

# Populated after stage-1 apply — pass as -var on stage-2 apply
variable "databricks_workspace_url" {
  description = "Databricks workspace URL (e.g. adb-1234.5.azuredatabricks.net)"
  type        = string
  default     = ""
}

variable "databricks_workspace_resource_id" {
  description = "Azure resource ID of the Databricks workspace"
  type        = string
  default     = ""
}
