# ============================================================
# Root module — CT.gov pipeline infrastructure
# ============================================================
# Apply in two stages:
#   Stage 1: resource_group, storage, iam, databricks_workspace
#   Stage 2: unity_catalog, databricks_compute, databricks_jobs, logic_apps
# ============================================================

# ---- Stage 1: Azure infrastructure --------------------------

module "resource_group" {
  source      = "./modules/resource_group"
  name        = "${var.project}-${var.environment}-rg"
  location    = var.location
  tags        = var.tags
}

module "storage" {
  source              = "./modules/storage"
  resource_group_name = module.resource_group.name
  location            = var.location
  project             = var.project
  environment         = var.environment
  tags                = var.tags
}

module "iam" {
  source              = "./modules/iam"
  resource_group_name = module.resource_group.name
  location            = var.location
  project             = var.project
  environment         = var.environment
  storage_account_id  = module.storage.storage_account_id
  key_vault_name      = "${var.project}-${var.environment}-kv"
  tags                = var.tags
}

module "databricks_workspace" {
  source                      = "./modules/databricks_workspace"
  resource_group_name         = module.resource_group.name
  location                    = var.location
  project                     = var.project
  environment                 = var.environment
  tags                        = var.tags
}

# ---- Stage 2: Databricks internals --------------------------
# These depend on the workspace URL being available.
# Run: terraform apply after setting databricks_workspace_url variable.

module "unity_catalog" {
  source                = "./modules/unity_catalog"
  metastore_storage_url = module.storage.unity_catalog_abfss_url
  workspace_id          = module.databricks_workspace.workspace_id
  storage_account_name  = module.storage.storage_account_name
  sp_object_id          = module.iam.databricks_sp_object_id

  depends_on = [module.databricks_workspace]
}

module "databricks_compute" {
  source = "./modules/databricks_compute"

  depends_on = [module.unity_catalog]
}

module "databricks_jobs" {
  source                = "./modules/databricks_jobs"
  sql_warehouse_id      = module.databricks_compute.sql_warehouse_id
  storage_account_name  = module.storage.storage_account_name
  uc_catalog            = "ctgov"
  secret_scope          = "ctgov-scope"
  key_vault_uri         = module.iam.key_vault_uri

  depends_on = [module.databricks_compute]
}

module "logic_apps" {
  source                  = "./modules/logic_apps"
  resource_group_name     = module.resource_group.name
  location                = var.location
  databricks_host         = module.databricks_workspace.workspace_url
  databricks_job_id       = module.databricks_jobs.pipeline_job_id
  keyvault_secret_uri     = module.iam.databricks_pat_secret_uri
  key_vault_id            = module.iam.key_vault_id
  tags                    = var.tags

  depends_on = [module.databricks_jobs]
}
