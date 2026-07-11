"""Campus-safety pipeline DAG: scrape -> classify -> normalize -> dbt.

Rather than re-implement the pipeline inside Airflow, each task launches the same
container image used to run that stage by hand (DockerOperator against the host
Docker socket). The containers are attached to the compose network so they reach
mongodb, postgres, and ollama by service name, exactly as in a manual run. The
dependencies are strictly linear because each stage consumes the previous
stage's output.
"""

from __future__ import annotations

import os
from datetime import datetime

from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator

# The compose network the pipeline services live on; DockerOperator attaches each
# task's container to it so mongodb/postgres/ollama resolve by name.
PIPELINE_NETWORK = os.environ.get("PIPELINE_NETWORK", "campus-crime-data-pipeline_default")

MONGO_ENV = {
    "MONGODB_URI": "mongodb://mongodb:27017",
    "MONGO_DB_NAME": "byu_police_beat",
}
OLLAMA_ENV = {
    "OLLAMA_URL": "http://ollama:11434",
    "OLLAMA_MODEL": "llama3.2:3b",
}
POSTGRES_ENV = {
    "POSTGRES_HOST": "postgres",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "byu_police_beat",
    "POSTGRES_USER": "postgres",
    "POSTGRES_PASSWORD": "postgres",
}

# Shared DockerOperator settings. mount_tmp_dir is off because the host-mounted
# tmp dir is unnecessary here and awkward on Docker Desktop.
COMMON = {
    "docker_url": "unix://var/run/docker.sock",
    "network_mode": PIPELINE_NETWORK,
    "auto_remove": "success",
    "mount_tmp_dir": False,
}

with DAG(
    dag_id="campus_safety_pipeline",
    description="Scrape BYU Police Beat, classify locations, normalize, and build dbt marts.",
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["campus-safety"],
) as dag:
    scrape = DockerOperator(
        task_id="scrape",
        image="byu-police-scraper",
        command=["--max-pages", "5"],
        environment=MONGO_ENV,
        **COMMON,
    )

    classify = DockerOperator(
        task_id="classify",
        image="byu-police-classifier",
        environment={**MONGO_ENV, **OLLAMA_ENV},
        **COMMON,
    )

    normalize = DockerOperator(
        task_id="normalize",
        image="byu-police-normalizer",
        environment={**MONGO_ENV, **POSTGRES_ENV},
        **COMMON,
    )

    dbt_build = DockerOperator(
        task_id="dbt_build",
        image="byu-police-dbt",
        environment=POSTGRES_ENV,
        **COMMON,
    )

    scrape >> classify >> normalize >> dbt_build
