"""Hybrid classification logic: deterministic lookup, guardrail, orchestration.

The public entry point is ``classify_incident``. It applies three layers in order:

1. Deterministic lookup — explicit landmark aliases and the parking-lot table.
   High precision; resolves most incidents that state a location.
2. LLM fallback — only runs on layer-1 misses, and only if a classifier is
   supplied. Kept as an injected dependency so this module is fully unit-testable
   without a running model.
3. Guardrail — if the LLM proposes a zone but the text names no explicit place,
   the answer is overridden to UNKNOWN. This is what stops the model fabricating
   a location from context (the incident type, an activity, a stray keyword).

The design bias is precision over coverage: a wrong zone is worse than an honest
UNKNOWN, because downstream analysis treats a zone as ground truth.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from classifier.reference import LANDMARK_ALIASES, LOT_ZONES, ZONES

# Unicode dash/hyphen variants that appear in the scraped text (the source uses a
# non-breaking hyphen, U+2011, inside names like "Food‑to‑Go"). Normalizing them
# to a plain hyphen lets the alias patterns match without needing to enumerate
# every dash codepoint.
_DASH_CHARS = "‐‑‒–—―−"
_DASH_TABLE = {ord(ch): "-" for ch in _DASH_CHARS}
_WHITESPACE_RE = re.compile(r"\s+")

_COMPILED_ALIASES: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), zone) for pattern, zone in LANDMARK_ALIASES
)
_LOT_RE = re.compile(r"\blot\s*#?\s*(\d+)", re.IGNORECASE)

# A proper-named place: one or more capitalized tokens followed by a place noun.
# Used only by the guardrail — if the LLM returns a zone, the text must contain
# at least one phrase like this, otherwise the model is inferring rather than
# reading an explicit location and we abstain.
_NAMED_PLACE_RE = re.compile(
    r"\b(?:[A-Z][\w.'-]+\s+){0,4}"
    r"(?:Building|Hall|Halls|Center|Centre|Stadium|Library|Museum|Tower|"
    r"Fieldhouse|Field\s?House|Complex|Terrace|Pavilion|Field|Annex|Court|"
    r"Apartments|Park|Commons|Dorm)\b"
)


class SupportsClassify(Protocol):
    """Anything that turns incident text into a zone string (the LLM fallback)."""

    def classify(self, text: str) -> str: ...


@dataclass(frozen=True)
class ClassificationResult:
    """Outcome of classifying one incident.

    ``source`` records which layer decided: "landmark" or "lot" (deterministic),
    "llm" (model fallback), "guardrail" (model overridden to UNKNOWN), or "none"
    (no location and no model available). ``reasoning`` is a short human-readable
    explanation stored alongside the zone for auditability.
    """

    zone: str
    source: str
    reasoning: str


def normalize_text(text: str) -> str:
    """Fold unicode dashes to ASCII and collapse whitespace before matching."""
    return _WHITESPACE_RE.sub(" ", text.translate(_DASH_TABLE)).strip()


def deterministic_lookup(text: str) -> ClassificationResult | None:
    """Resolve a zone from an explicit landmark or parking lot, else None.

    ``text`` is expected to be normalized already. Returns None (not UNKNOWN) on a
    miss so the caller can decide whether to fall through to the LLM.
    """
    for pattern, zone in _COMPILED_ALIASES:
        match = pattern.search(text)
        if match:
            return ClassificationResult(
                zone=zone, source="landmark", reasoning=f"matched '{match.group(0)}'"
            )

    lot_match = _LOT_RE.search(text)
    if lot_match:
        lot_number = int(lot_match.group(1))
        zone = LOT_ZONES.get(lot_number)
        if zone:
            return ClassificationResult(
                zone=zone, source="lot", reasoning=f"parking Lot {lot_number}"
            )

    return None


def names_explicit_place(text: str) -> bool:
    """True if the text contains a proper-named place phrase (guardrail check)."""
    return _NAMED_PLACE_RE.search(text) is not None


def classify_incident(
    text: str, llm: SupportsClassify | None = None
) -> ClassificationResult:
    """Classify one incident's text into a campus zone.

    With no ``llm`` supplied, only the deterministic layer runs and misses become
    UNKNOWN — this is the fast, offline path used by tests. With an ``llm``, misses
    fall through to the model, whose non-UNKNOWN answers are guardrailed against
    fabrication.
    """
    normalized = normalize_text(text)

    deterministic = deterministic_lookup(normalized)
    if deterministic is not None:
        return deterministic

    if llm is None:
        return ClassificationResult(
            zone="UNKNOWN", source="none", reasoning="no explicit location in text"
        )

    proposed = llm.classify(normalized).strip().upper()
    if proposed not in ZONES:
        proposed = "UNKNOWN"

    if proposed == "UNKNOWN":
        return ClassificationResult(
            zone="UNKNOWN", source="llm", reasoning="model found no explicit location"
        )

    if not names_explicit_place(normalized):
        return ClassificationResult(
            zone="UNKNOWN",
            source="guardrail",
            reasoning=f"model proposed {proposed} but text names no explicit place",
        )

    return ClassificationResult(
        zone=proposed, source="llm", reasoning="model matched an explicit place"
    )
