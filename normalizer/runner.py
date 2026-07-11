"""Batch job: normalize classified incidents from Mongo into PostgreSQL.

Processes only documents that are classified but not yet normalized
(``location_zone`` set, ``normalized`` false), so the job is cached and
idempotent: re-running picks up newly classified incidents and skips work already
mirrored into Postgres. Each document is upserted into the clean store and then
flagged ``normalized`` in Mongo. If the process dies between those two steps the
Postgres upsert is simply repeated on the next run, never duplicated.
"""

from __future__ import annotations

import logging

from psycopg2.extensions import connection as Connection
from pymongo.collection import Collection

import postgres_store
from normalizer.core import transform


def run_normalization(
    collection: Collection, conn: Connection, limit: int | None = None
) -> int:
    """Normalize every classified-but-not-normalized incident; return the count."""
    query = {"normalized": False, "location_zone": {"$ne": None}}
    cursor = collection.find(query)
    if limit is not None:
        cursor = cursor.limit(limit)

    # Materialize before mutating: the loop flips ``normalized``, which is part of
    # the query filter, so iterating a live cursor could behave unpredictably.
    documents = list(cursor)

    count = 0
    for document in documents:
        postgres_store.write_incident(conn, transform(document))
        collection.update_one({"_id": document["_id"]}, {"$set": {"normalized": True}})
        count += 1

    logging.info("Normalized %s incidents into PostgreSQL", count)
    return count
