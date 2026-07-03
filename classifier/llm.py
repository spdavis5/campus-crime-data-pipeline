"""Local LLM fallback for incidents the deterministic layer can't resolve.

Wraps a local Ollama model behind the ``SupportsClassify`` interface. The model
only ever sees incidents that have no known landmark or lot, and the prompt is
written to make abstention (UNKNOWN) the default: it must find an explicitly
named building to return a zone, and is told not to infer location from the
incident type, the activity, or stray keywords. The core guardrail is a second
line of defence on top of this prompt.

Connection details come from the OLLAMA_URL and OLLAMA_MODEL environment
variables. ``ensure_available`` fails loudly if the model isn't reachable, so a
misconfigured pipeline stops rather than silently labelling everything UNKNOWN.
"""

from __future__ import annotations

import json
import logging
import os

import requests

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2:3b"
REQUEST_TIMEOUT_SECONDS = 120

_PROMPT = """You extract the campus location zone from a BYU police incident report.

HARD RULES:
- Output a zone ONLY if the text names a SPECIFIC, PROPER-NAMED building, hall, or campus landmark.
- If no specific place is named, output UNKNOWN.
- These are NOT named landmarks and MUST be UNKNOWN: "an apartment", "an apartment complex", "a building", "the building", "a residence", "a field", "the area", a bare parking lot number, or any generic place.
- NEVER infer a location from the incident type, the activity, or a keyword in the story (an "engineering trip" or a "student" does NOT imply a building). If you are inferring rather than reading an explicit name, output UNKNOWN.

Valid zones and their explicit landmarks:
- ACADEMIC_CORE: JFSB, JSB, JKB, SWKT/Kimball Tower, HBLL/Harold B. Lee Library, Museum of Art, Bean Museum, BNSN, HFAC/Music Building, Maeser, Richards Building, Life Sciences Building, Heber J. Grant Building, Ellsworth, Talmage/TMCB, Taylor Building, Brimhall
- ENGINEERING_NORTH: Clyde, Eyring Science Center, Crabtree/CTB, Fletcher, MARB, Nicholes
- BUSINESS_SOUTH: Tanner Building/TNRB, Marriott School, Law Building/Law School/JRCB
- STUDENT_SERVICES: Wilkinson Student Center/WSC, Cougareat, Bookstore, Testing Center, Cougar Dash
- STADIUM_AREA: LaVell Edwards Stadium, Marriott Center, Smith Fieldhouse, Indoor Practice Facility, Cougar Field, Miller Field, RB Field
- DORMS_HELAMAN: Helaman Halls, Chipman/Merrill/Stover/Hinckley/Budge/Taylor Hall, Cannon Center
- DORMS_HERITAGE: Heritage Halls (also "HR #"), the Creamery / CONE
- WYVIEW_WYMOUNT: Wyview, Wymount
- MTC: the Missionary Training Center (MTC), MTC fields
- SERVICE_SUPPORT: Food-to-Go, Culinary Support Center, University Services Building, University Press Building, Brewster Building, West View Building
- OFF_CAMPUS: a street address, an off-campus apartment complex (e.g. Riviera), or a place clearly off campus

Respond with strict JSON only: {"location_zone": "<ONE_ZONE>"}

Incident report:
%s
"""


class OllamaClassifier:
    """Classify incident text into a zone via a local Ollama model."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int = REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = (base_url or os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL)).rstrip("/")
        self.model = model or os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)
        self.timeout = timeout

    def ensure_available(self) -> None:
        """Verify Ollama is reachable and the model is pulled, else fail loudly."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise SystemExit(
                f"Could not reach Ollama at {self.base_url}. Is the ollama container "
                f"running? Original error: {exc}"
            ) from exc

        available = {model.get("name") for model in response.json().get("models", [])}
        if self.model not in available:
            raise SystemExit(
                f"Model {self.model!r} is not available in Ollama at {self.base_url}. "
                f"Pull it with: ollama pull {self.model}"
            )
        logging.info("Ollama ready at %s with model %s", self.base_url, self.model)

    def classify(self, text: str) -> str:
        """Return a zone string for one incident, or UNKNOWN on any failure.

        A per-incident failure (timeout, malformed response) degrades to UNKNOWN
        rather than aborting the whole run, which is the safe direction given the
        precision bias — but it is logged so a failing model is visible.
        """
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": _PROMPT % text,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0},
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = json.loads(response.json()["response"])
            return str(payload.get("location_zone", "UNKNOWN")).strip().upper()
        except (requests.RequestException, KeyError, ValueError) as exc:
            logging.warning("Ollama classification failed, defaulting to UNKNOWN: %s", exc)
            return "UNKNOWN"
