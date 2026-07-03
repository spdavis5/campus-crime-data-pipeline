"""Location classification for BYU police-beat incidents.

A hybrid classifier that maps each incident's free-text narrative to a fixed
campus zone. A deterministic alias + parking-lot lookup runs first and resolves
the majority of incidents with high precision; a local LLM runs only on the
remainder, guardrailed to abstain (UNKNOWN) unless the text names an explicit
place. See ``classifier.core.classify_incident`` for the entry point.
"""

from __future__ import annotations

from classifier.core import ClassificationResult, classify_incident

__all__ = ["ClassificationResult", "classify_incident"]
