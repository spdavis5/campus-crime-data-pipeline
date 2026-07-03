"""Unit tests for the hybrid location classifier's offline layers.

These cover the deterministic lookup and the guardrail — the parts that must be
correct regardless of the model. The LLM fallback is exercised with a fake so the
suite needs no running Ollama. Several cases pin down specific mistakes found
while building the classifier (Marriott Center vs Marriott School, "HR #" being
Heritage, non-breaking hyphens, "esc" not matching "rescue").
"""

from __future__ import annotations

import pytest

from classifier.core import (
    ClassificationResult,
    classify_incident,
    deterministic_lookup,
    names_explicit_place,
    normalize_text,
)


class FakeLLM:
    """Stand-in classifier that always returns a fixed zone (records its input)."""

    def __init__(self, zone: str) -> None:
        self.zone = zone
        self.seen: list[str] = []

    def classify(self, text: str) -> str:
        self.seen.append(text)
        return self.zone


# --- text normalization ------------------------------------------------------

def test_normalize_folds_non_breaking_hyphen():
    # The scraped source writes "Food-to-Go" with U+2011 non-breaking hyphens.
    assert normalize_text("Food‑to‑Go") == "Food-to-Go"


def test_normalize_collapses_whitespace():
    assert normalize_text("a   b\n c") == "a b c"


# --- deterministic landmark lookup -------------------------------------------

@pytest.mark.parametrize(
    "text, expected_zone",
    [
        ("officers responded to the HBLL for a fire alarm", "ACADEMIC_CORE"),
        ("a duress alarm at the Wilkinson Student Center", "STUDENT_SERVICES"),
        ("fire alarm at LaVell Edwards Stadium", "STADIUM_AREA"),
        ("responded to Wymount Terrace", "WYVIEW_WYMOUNT"),
        ("dispatched to the MTC fields", "MTC"),
        ("door alarm at the University Press Building", "SERVICE_SUPPORT"),
        ("called to the Riviera Apartments", "OFF_CAMPUS"),
    ],
)
def test_landmark_hits(text, expected_zone):
    result = deterministic_lookup(normalize_text(text))
    assert result is not None
    assert result.zone == expected_zone
    assert result.source == "landmark"


def test_marriott_center_is_stadium_not_business():
    # The arena, not the Marriott School of Business — a real early misclassification.
    result = deterministic_lookup(normalize_text("robbery alarm at the Marriott Center"))
    assert result is not None and result.zone == "STADIUM_AREA"


def test_hr_shorthand_is_heritage():
    result = deterministic_lookup(normalize_text("responded to HR #12 for a medical"))
    assert result is not None and result.zone == "DORMS_HERITAGE"


def test_chipman_hall_is_helaman_not_academic():
    result = deterministic_lookup(normalize_text("Officers responded to Chipman Hall"))
    assert result is not None and result.zone == "DORMS_HELAMAN"


def test_food_to_go_matches_after_hyphen_normalization():
    result = deterministic_lookup(normalize_text("alarm at the Food‑to‑Go Building"))
    assert result is not None and result.zone == "SERVICE_SUPPORT"


def test_short_code_does_not_match_inside_word():
    # "esc" (Eyring Science Center) must not fire on "rescue".
    assert deterministic_lookup(normalize_text("officers rescued the individual")) is None


# --- parking lot lookup ------------------------------------------------------

def test_lot_lookup_known():
    result = deterministic_lookup(normalize_text("scooter leaking fuel in Lot #41"))
    assert result is not None
    assert result.zone == "DORMS_HELAMAN"
    assert result.source == "lot"


def test_lot_lookup_unknown_number_is_miss():
    # A lot not in the table must not be guessed.
    assert deterministic_lookup(normalize_text("parked in Lot 999")) is None


# --- guardrail ---------------------------------------------------------------

def test_named_place_detection():
    assert names_explicit_place("responded to the Ellsworth Building")
    assert not names_explicit_place("found BYU employees working in the area")


def test_guardrail_overrides_fabricated_zone():
    # LLM proposes a zone, but the text names no explicit place -> forced UNKNOWN.
    llm = FakeLLM("ENGINEERING_NORTH")
    result = classify_incident("assisted with an out-of-state engineering trip", llm=llm)
    assert result.zone == "UNKNOWN"
    assert result.source == "guardrail"


def test_llm_zone_kept_when_place_is_named():
    llm = FakeLLM("ACADEMIC_CORE")
    result = classify_incident("responded to the Kimball Tower for a lockout", llm=llm)
    # Kimball Tower is in the alias table, so this resolves deterministically first.
    assert result.zone == "ACADEMIC_CORE"
    assert result.source == "landmark"


def test_llm_novel_building_passes_guardrail():
    # A real building not in the alias table: LLM answers, guardrail lets it through.
    llm = FakeLLM("ACADEMIC_CORE")
    result = classify_incident("responded to the Widtsoe Building for an alarm", llm=llm)
    assert result.zone == "ACADEMIC_CORE"
    assert result.source == "llm"


def test_invalid_llm_zone_becomes_unknown():
    llm = FakeLLM("NORTH_QUAD")  # not a real zone
    result = classify_incident("something at the Somewhere Building", llm=llm)
    assert result.zone == "UNKNOWN"


# --- orchestration without a model -------------------------------------------

def test_miss_without_llm_is_honest_unknown():
    result = classify_incident("no location mentioned here at all")
    assert result == ClassificationResult(
        zone="UNKNOWN", source="none", reasoning="no explicit location in text"
    )


def test_deterministic_hit_never_calls_llm():
    llm = FakeLLM("OFF_CAMPUS")
    result = classify_incident("fire alarm at the HBLL", llm=llm)
    assert result.zone == "ACADEMIC_CORE"
    assert llm.seen == []  # deterministic short-circuit, model untouched
