# Terraform Commands

Plan, apply, inspect and repair the GCP resources in `infra/terraform/`. Commands are `bash` (Git Bash) from the project folder. Normal changes go through a pull request: CI plans, CD applies after the merge to `main`.

```bash
TF="terraform -chdir=infra/terraform"
export TF_STATE_BUCKET=dehehe-510014-tfstate
```

## 1. Accounts, state and variables

| Item | Value | Where |
|---|---|---|
| Version | Terraform 1.16.5, provider `hashicorp/google ~> 6.0` | `versions.tf`, `.terraform.lock.hcl` |
| State | `gs://dehehe-510014-tfstate`, prefix `stylehub` (versioned bucket) | `versions.tf`, `-backend-config` |
| Inputs | `project_id`, `bucket_name`, `state_bucket`, `github_repository`, `bucket_location = "ASIA"`, `source_location = "US"` | `terraform.tfvars` (git-ignored; template `terraform.tfvars.example`) |
| Who runs it by hand | Your Google account (project Owner) through `gcloud auth application-default login` | – |
| Who runs it in CI / CD | `sa-terraform-plan` (any branch, read only) / `sa-terraform-apply` (`main` only) | `wif.tf`, GitHub variables |
| Logs | `logs/infra/init_<stamp>.log`, `plan_<stamp>.log` | `infra/scripts/deploy.sh` |

Wrong locations in `terraform.tfvars` make the plan want to replace the bucket and the source dataset; `prevent_destroy` stops that plan.

### Service accounts

| Account | Used by | Rights |
|---|---|---|
| `sa-pipeline` | Airflow on a VM, dbt in CD | Job user; editor on Bronze, Staging, Silver, Gold, Ops; viewer on source; add and read Raw files |
| `sa-dashboard` | Streamlit | Job user; viewer on Bronze, Silver, Ops |
| `sa-github-cd` | CD image push | Artifact Registry writer |
| `sa-terraform-plan` | CI plan | Metadata and IAM-policy viewer roles only; state lock files |
| `sa-terraform-apply` | CD apply | Admin of storage, BigQuery, registry, accounts, WIF, project IAM, APIs |
| `end2endstylehub` | Local Airflow (key in `secrets/`) | Not managed by Terraform |

## 2. Operate

```bash
gcloud auth application-default login && unset GOOGLE_APPLICATION_CREDENTIALS   # use your account, not the key

infra/scripts/deploy.sh plan     # init + plan, saved to infra/terraform/tfplan and logs/infra/
$TF show -no-color tfplan | grep -E "^Plan:|must be replaced|will be destroyed"   # review: 0 destroy unless planned
$TF apply tfplan                 # apply exactly the reviewed plan
infra/scripts/deploy.sh apply    # or: plan again and ask yes/no
```

Never use `-auto-approve` by hand; only CD does that, after review in a pull request.

### Set the GitHub variables (after outputs change)

```bash
$TF output -json github_variables | uv run python -c "
import json, subprocess, sys
for k, v in json.load(sys.stdin).items(): subprocess.run(['gh', 'variable', 'set', k, '--body', v], check=True); print('set', k)"
gh variable set GCS_BUCKET_LOCATION --body ASIA
gh variable set BQ_SOURCE_LOCATION --body US
gh variable list
```

## 3. Check

| Check | Command | Healthy result |
|---|---|---|
| Format | `$TF fmt -check -recursive` | No output |
| Config is valid | `$TF validate` | `Success!` |
| Real cloud matches code | `infra/scripts/deploy.sh plan` | `No changes.` |
| Managed resources | `$TF state list \| wc -l` | 58 resources |
| One resource | `$TF state show 'google_storage_bucket.raw'` | Its attributes |
| Outputs | `$TF output` | Accounts, image repository, GitHub variables |
| Roles of an account | `gcloud projects get-iam-policy dehehe-510014 --flatten="bindings[].members" --filter="bindings.members:sa-terraform-plan@" --format="value(bindings.role)"` | The roles in the table above |
| Last CI plan | `gh run list --workflow CI --limit 1`, then `gh run view <id> --log \| grep -E "No changes\|Plan:"` | `No changes.` |

## 4. Debug and repair

| Problem | Command or fix |
|---|---|
| See what Terraform sends | `TF_LOG=DEBUG $TF plan 2> logs/infra/debug.log` |
| `Error acquiring the state lock` | Wait for the other run; only if it crashed: `$TF force-unlock <lock id>` |
| `Error 409: Already exists` | The resource exists outside state: add an `import` block or `$TF import <address> <id>`, plan, apply, then remove the block |
| Plan wants to replace bucket or dataset | Fix `bucket_location` / `source_location` in `terraform.tfvars` |
| Provider version error | `$TF init -upgrade -backend-config="bucket=$TF_STATE_BUCKET"`, commit `.terraform.lock.hcl` |
| Bad state after a mistake | The state bucket keeps old versions: `gcloud storage ls -a gs://$TF_STATE_BUCKET/stylehub/` |
| CI plan skipped | A GitHub variable is empty: `gh variable list` |
