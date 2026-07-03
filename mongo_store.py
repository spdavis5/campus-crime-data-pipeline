"""MongoDB raw landing zone for scraped police-beat incidents.

This module owns all interaction with the raw store. The scraper produces incident
documents; this module persists them idempotently. Incremental loading is enforced
two ways: a unique index on ``raw_text_hash`` at the database level, and a
``DuplicateKeyError`` catch at the application level. Re-running the scraper is
therefore always safe and never creates duplicate rows.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterable

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError

DEFAULT_MONGODB_URI = "mongodb://localhost:27017"
DEFAULT_DB_NAME = "byu_police_beat"
COLLECTION_NAME = "raw_incidents"

# Fail fast with a clear message instead of hanging when MongoDB is unreachable.
SERVER_SELECTION_TIMEOUT_MS = 5000

HASH_INDEX_NAME = "uq_raw_text_hash"
BEAT_URL_INDEX_NAME = "ix_beat_url"


def connect() -> tuple[MongoClient, Collection]:
    """Open a connection to the raw_incidents collection, verifying it is reachable.

    Connection details come from the MONGODB_URI and MONGO_DB_NAME environment
    variables (see .env.example). Raises SystemExit with a clear message if MongoDB
    cannot be reached, so the pipeline fails loudly rather than silently.
    """
    uri = os.environ.get("MONGODB_URI", DEFAULT_MONGODB_URI)
    db_name = os.environ.get("MONGO_DB_NAME", DEFAULT_DB_NAME)

    client: MongoClient = MongoClient(uri, serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS)
    try:
        client.admin.command("ping")
    except ServerSelectionTimeoutError as exc:
        raise SystemExit(
            f"Could not connect to MongoDB at {uri}. Is the mongodb container running? "
            f"Original error: {exc}"
        ) from exc

    collection = client[db_name][COLLECTION_NAME]
    ensure_indexes(collection)
    logging.info("Connected to MongoDB %s/%s", db_name, COLLECTION_NAME)
    return client, collection


def ensure_indexes(collection: Collection) -> None:
    """Create the dedup and lookup indexes if they do not already exist.

    The unique index on raw_text_hash is the database-level guarantee that
    duplicate incidents cannot be inserted even if the application check is bypassed.
    """
    collection.create_index("raw_text_hash", unique=True, name=HASH_INDEX_NAME)
    collection.create_index("beat_url", name=BEAT_URL_INDEX_NAME)


def insert_new_incidents(
    collection: Collection, documents: Iterable[dict[str, Any]]
) -> tuple[int, int]:
    """Insert only incidents not already stored, returning (inserted, skipped).

    Relies on the unique raw_text_hash index: an attempt to insert a duplicate
    raises DuplicateKeyError, which we count as a skip. This keeps the load
    idempotent without a separate read-before-write round trip per document.
    """
    inserted = 0
    skipped = 0

    for document in documents:
        try:
            collection.insert_one(document)
            inserted += 1
        except DuplicateKeyError:
            skipped += 1

    return inserted, skipped
