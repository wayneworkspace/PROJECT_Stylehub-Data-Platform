// Jenkins pipeline with the same checks as .github/workflows/ci_test.yml (test job).
// Runs on the local Jenkins of docker-compose.yaml (profile jenkins): Poll SCM,
// because a laptop cannot receive GitHub webhooks. It checks only; deploys
// stay in GitHub Actions, so Jenkins never holds cloud credentials.
pipeline {
    agent any

    options {
        buildDiscarder(logRotator(numToKeepStr: '10'))  // keep the disk small
        disableConcurrentBuilds()
        timeout(time: 30, unit: 'MINUTES')
        timestamps()
    }

    triggers {
        pollSCM('H/15 * * * *')  // look for new commits every 15 minutes
    }

    environment {
        UV_VERSION = '0.12.13'
        PATH = "${env.HOME}/.local/bin:${env.PATH}"
        GCP_PROJECT_ID = 'ci-dummy-project'  // dbt parse needs no warehouse
        GCS_BUCKET = 'ci-dummy-bucket'
    }

    stages {
        stage('Install uv and dependencies') {
            steps {
                sh 'command -v uv || curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh'
                sh 'uv sync --frozen --extra dev --extra dbt --extra serving'
            }
        }
        stage('Lint') {
            steps {
                sh 'uv run ruff check .'
                sh 'uv run ruff format --check .'
            }
        }
        stage('Unit tests') {
            steps {
                sh 'uv run pytest -q'
            }
        }
        stage('dbt parse') {
            steps {
                sh 'uv run dbt deps --project-dir dbt_project --profiles-dir dbt_project --log-path logs/dbt'
                sh 'uv run dbt parse --project-dir dbt_project --profiles-dir dbt_project --log-path logs/dbt'
            }
        }
        stage('SQL lint') {
            steps {
                sh 'uv run sqlfluff lint dbt_project/models dbt_project/macros dbt_project/tests include/sql'
            }
        }
    }

    post {
        failure {
            echo 'Checks failed: open the stage log above for the first error.'
        }
    }
}
