# Docs: where to start

Not sure which page to open? Find your goal in the first table.

## Pick by goal

| I want to... | Open |
|---|---|
| Run the whole pipeline for the first time | [RUN_END_TO_END.md](RUN_END_TO_END.md) |
| Understand how the layers fit together | [ARCHITECTURE.md](ARCHITECTURE.md) |
| See the data flow as a picture | [html/architecture.html](html/architecture.html) (open in a browser) |
| Read the main code line by line | [html/code-walkthrough.html](html/code-walkthrough.html) (open in a browser) |
| Know why we choose ELT and where rules live | [ETL_VS_ELT.md](ETL_VS_ELT.md) |
| Know why a design choice was made | [DECISIONS.md](DECISIONS.md) |
| Change a business rule or add a table | [EXTENDING.md](EXTENDING.md) |
| Understand CI, Docker and pre-commit | [DEVOPS.md](DEVOPS.md) |
| Publish the Docker image | [CD.md](CD.md) |
| Run the pipeline on a GCP VM | [DEPLOY_VM.md](DEPLOY_VM.md) |
| See what is done and what comes next | [ROADMAP.md](ROADMAP.md) |

## Suggested reading order

| Step | Page | Why |
|---|---|---|
| 1 | [../README.md](../README.md) | What the project does and how to start |
| 2 | [ARCHITECTURE.md](ARCHITECTURE.md) | The layers: Raw, Bronze, Silver, Gold |
| 3 | [RUN_END_TO_END.md](RUN_END_TO_END.md) | Run it yourself and check each step |
| 4 | [DECISIONS.md](DECISIONS.md) | The reasons behind the design |
| 5 | The rest | Open them when you need them |

## Other READMEs in the repo

| Folder | What it explains |
|---|---|
| [../dbt/README.md](../dbt/README.md) | The dbt models, folders and tests |
| [../deploy/airflow/README.md](../deploy/airflow/README.md) | How to run Airflow and the daily DAG |
| [../CLAUDE.md](../CLAUDE.md) | Rules for anyone who changes the code |

> [!NOTE]
> Some pages describe the VM path (`DEPLOY_VM.md`, `CD.md`). The systemd timers were removed. Airflow now schedules the pipeline.
