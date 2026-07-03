"""Batch job: classify unclassified incidents in the Mongo raw store.

Reads only documents whose ``location_zone`` is still null, so classification is
cached — re-running the job picks up newly scraped incidents and never re-does
work already stored (classifying via a local model isn't free). Each document is
updated in place with its zone, a confidence tier derived from which layer
decided, the deciding source, and a short reasoning string for auditability.
"""

from __future__ import annotations

import logging
from typing import Any

from pymongo.collection import Collection

from classifier.core import SupportsClassify, classify_incident

# The deterministic layers resolve from explicit landmarks/lots and are treated as
# high confidence; the model fallback is medium; abstentions carry none.
_CONFIDENCE_BY_SOURCE = {
    "landmark": "HIGH",
    "lot": "HIGH",
    "llm": "MEDIUM",
    "guardrail": "NONE",
    "none": "NONE",
}


def run_classification(
    collection: Collection,
    llm: SupportsClassify | None = None,
    limit: int | None = None,
) -> dict[str, int]:
    """Classify every not-yet-classified incident, updating each in place.

    Returns per-source counts (landmark, lot, llm, guardrail, none). ``limit``
    caps how many are processed in one run, useful for a quick smoke test.
    """
    query: dict[str, Any] = {"location_zone": None}
    cursor = collection.find(query, {"incident_text": 1})
    if limit is not None:
        cursor = cursor.limit(limit)

    source_counts: dict[str, int] = {}
    processed = 0

    for document in cursor:
        result = classify_incident(document.get("incident_text", ""), llm=llm)
        collection.update_one(
            {"_id": document["_id"]},
            {
                "$set": {
                    "location_zone": result.zone,
                    "location_confidence": _CONFIDENCE_BY_SOURCE.get(result.source, "NONE"),
                    "location_source": result.source,
                    "location_reasoning": result.reasoning,
                }
            },
        )
        source_counts[result.source] = source_counts.get(result.source, 0) + 1
        processed += 1

    logging.info("Classified %s incidents: %s", processed, source_counts)
    return source_counts
