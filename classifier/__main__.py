"""CLI entry point for the location classifier: ``python -m classifier``.

Connects to the Mongo raw store, optionally stands up the local LLM fallback,
and classifies every unclassified incident. Runs as its own container in the
pipeline (see docker-compose.yml).
"""

from __future__ import annotations

import argparse
import logging

from dotenv import load_dotenv

import mongo_store
from classifier.llm import OllamaClassifier
from classifier.runner import run_classification


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Classify raw incidents into campus zones (hybrid lookup + local LLM)."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only classify the first N unclassified incidents (default: all).",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        help="Deterministic layer only; skip the Ollama fallback entirely.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args(argv)
    load_dotenv()

    llm: OllamaClassifier | None = None
    if not args.skip_llm:
        llm = OllamaClassifier()
        llm.ensure_available()

    client, collection = mongo_store.connect()
    try:
        run_classification(collection, llm=llm, limit=args.limit)
    finally:
        client.close()


if __name__ == "__main__":
    main()
