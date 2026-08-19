# CT.gov Data Pipeline

End-to-end data pipeline that ingests ClinicalTrials.gov Phase 2 & 3 interventional trials
into Azure Databricks and answers:

> **Which sponsor class has the highest proportion of trials that ended early,
> and how does this compare to industry-sponsored trials?**

## Stack

| Layer | Technology |
|---|---|
| Source | ClinicalTrials.gov v2 API |
| Raw landing | ADLS Gen2 |
| Warehouse | Azure Databricks (Unity Catalog + Delta Lake) |
| Transformation | dbt-databricks |
| Orchestration | Azure Logic Apps → Databricks Jobs API |
| IaC | Terraform (azurerm + databricks providers) |

## Project Structure

```
ctgov-pipeline/
  ingestion/          ← Python ingestion package (wheel)
  dbt/ctgov/          ← dbt project (staging + marts)
  terraform/          ← All infrastructure as code
  README.md
```

## Prerequisites

- Azure CLI authenticated (`az login`)
- Terraform >= 1.5.0
- Python >= 3.9
- `pip install build` (for building the wheel)
- Databricks CLI (for uploading wheel)

---

## Setup & Deployment

### Step 0 — Bootstrap Terraform state storage

Run once before anything else:

```bash
az group create -n ctgov-tfstate-rg -l uksouth
az storage account create -n ctgovtfstate -g ctgov-tfstate-rg --sku Standard_LRS
az storage container create -n tfstate --account-name ctgovtfstate
# Enable versioning to protect state file
az storage account blob-service-properties update \
  --account-name ctgovtfstate --enable-versioning true
```

### Step 1 — Stage-1 Terraform (Azure infrastructure)

```bash
cd terraform
terraform init
terraform apply \
  -target=module.resource_group \
  -target=module.storage \
  -target=module.iam \
  -target=module.databricks_workspace \
  -var-file=environments/dev/terraform.tfvars
```

Note the outputs — you'll need `databricks_workspace_url` and
`databricks_workspace_resource_id` for step 2.

### Step 2 — Set Databricks PAT in Key Vault

After the workspace is created, generate a Databricks Personal Access Token
(Workspace → Settings → Developer → Access Tokens) and store it:

```bash
az keyvault secret set \
  --vault-name ctgov-dev-kv \
  --name databricks-pat \
  --value "YOUR-PAT-HERE"
```

### Step 3 — Stage-2 Terraform (Databricks resources)

Update `environments/dev/terraform.tfvars` with the workspace URL from step 1, then:

```bash
terraform apply -var-file=environments/dev/terraform.tfvars
```

### Step 4 — Build and upload the Python wheel

```bash
cd ../ingestion
pip install build
python -m build --wheel

# Upload to Databricks workspace
databricks fs cp dist/ctgov_ingestion-1.0.0-py3-none-any.whl \
  dbfs:/FileStore/wheels/ctgov_ingestion-1.0.0-py3-none-any.whl
```

### Step 5 — Set up dbt profile

```bash
cd ../dbt/ctgov
cp profiles.yml.example ~/.dbt/profiles.yml
# Edit ~/.dbt/profiles.yml with your workspace URL and SQL Warehouse HTTP path
# (both available from terraform output)

# Install dbt packages
dbt deps

# Test connection
dbt debug
```

### Step 6 — Run the pipeline manually (first test)

Trigger the Databricks job directly:

```bash
# Get the job ID from Terraform output
JOB_ID=$(cd ../../terraform && terraform output -raw pipeline_job_id)

databricks jobs run-now --job-id $JOB_ID
```

Or run dbt locally against the warehouse:

```bash
cd dbt/ctgov
dbt run
dbt test
```

---

## Scheduling

The Logic App fires every Monday at 00:00, 02:00 ... 22:00 UTC.
A condition gate (`dayOfMonth <= 7`) ensures only the **first Monday of the month**
actually triggers the Databricks job. Subsequent Mondays exit silently.

To verify the Logic App is configured correctly:

```bash
az logic workflow show \
  --name ctgov-pipeline-scheduler \
  --resource-group ctgov-dev-rg \
  --query "definition.triggers"
```

---

## Data Models

```
ctgov.landing.raw_ctgov__studies       ← Raw JSON, one row per study per run
        ↓
ctgov.staging.stg_ctgov__studies       ← Flattened, deduplicated, classified
        ↓                    ↓
ctgov.marts.mart_sponsor_early_stop    ctgov.marts.mart_studies_classified
(aggregate answer)                     (study-level detail)
```

### Key columns in mart_sponsor_early_stop

| Column | Description |
|---|---|
| `sponsor_class` | INDUSTRY / NIH / OTHER_GOV / OTHER / INDIVIDUAL |
| `early_stop_rate` | Proportion of closed trials ending early (0–1) |
| `industry_early_stop_rate` | INDUSTRY benchmark (same value on all rows) |
| `vs_industry_delta` | Positive = worse than industry |
| `early_stop_rank` | 1 = highest early-stop proportion |

---

## Running Tests

```bash
cd dbt/ctgov
dbt test                    # all schema tests
dbt test --select staging   # staging only
dbt test --select marts     # marts only
```

Key tests:
- `nct_id` is unique and not null (staging + marts)
- `overall_status` and `sponsor_class` are within accepted value sets
- `early_stop_rate` is between 0 and 1 (via dbt_utils.accepted_range)

---

## Development Notes

- **Adding new API fields**: extract in `stg_ctgov__studies.sql` using the `:` operator.
  Raw JSON is always preserved in `raw_ctgov__studies` so no re-ingestion is needed.
- **Backfilling**: Auto Loader checkpoints are in ADLS. To reprocess all files,
  delete the checkpoint directory and re-run the ingestion job.
- **Schema drift**: Auto Loader is configured with `schemaEvolutionMode=addNewColumns`.
  New fields in the CT.gov API response are added to the raw table automatically.
