"""CLI entry point for the normalizer: ``python -m normalizer``.

Connects to the Mongo raw store and the PostgreSQL clean store and mirrors every
classified-but-not-normalized incident into Postgres. Runs as its own container
in the pipeline (see docker-compose.yml).
"""

from __future__ import annotations

import argparse
import logging

from dotenv import load_dotenv

import mongo_store
import postgres_store
from normalizer.runner import run_normalization


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize classified incidents from Mongo into PostgreSQL."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only normalize the first N pending incidents (default: all).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)
    load_dotenv()

    mongo_client, collection = mongo_store.connect()
    conn = postgres_store.connect()
    try:
        run_normalization(collection, conn, limit=args.limit)
    finally:
        conn.close()
        mongo_client.close()


if __name__ == "__main__":
    main()
