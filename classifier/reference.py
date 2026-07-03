"""Reference data for location classification: campus zones and their landmarks.

This module is deliberately data-only. Keeping the zone list, the landmark alias
table, and the parking-lot map here (rather than inline in the matching logic)
makes them easy to audit and extend as new buildings appear in the data — the
alias table was in fact grown by running the LLM over real incidents and
promoting every genuine building it surfaced into a deterministic rule.

Zone assignments were verified against real police-beat text and confirmed with
local knowledge of BYU campus. A few resolve common surprises: the Marriott
*Center* is the arena (STADIUM_AREA), not the Marriott *School* (BUSINESS_SOUTH);
"HR #12" is Heritage Halls; the Creamery on Ninth ("CONE") is by the Heritage
dorms; Cannon Center and Chipman Hall are Helaman, not Heritage.
"""

from __future__ import annotations

# The fixed set of zones a valid classification can produce. UNKNOWN is a
# first-class outcome: roughly a third of incidents never state where they
# happened, and labelling those honestly matters more than guessing.
ZONES: tuple[str, ...] = (
    "ACADEMIC_CORE",
    "ENGINEERING_NORTH",
    "BUSINESS_SOUTH",
    "STUDENT_SERVICES",
    "STADIUM_AREA",
    "DORMS_HELAMAN",
    "DORMS_HERITAGE",
    "WYVIEW_WYMOUNT",
    "MTC",
    "SERVICE_SUPPORT",
    "OFF_CAMPUS",
    "UNKNOWN",
)

# Ordered (pattern, zone) rules. Order matters only where one landmark's text is
# a substring of another's; more specific rules are listed first. Short building
# codes use \b boundaries so they don't match inside unrelated words (e.g. "esc"
# must not fire on "rescue"). Patterns are matched case-insensitively against
# hyphen-normalized text (see core.normalize_text).
LANDMARK_ALIASES: tuple[tuple[str, str], ...] = (
    # --- DORMS_HERITAGE (Heritage Halls + the Creamery on Ninth East / CONE) ---
    (r"heritage", "DORMS_HERITAGE"),
    (r"\bhr\s*#", "DORMS_HERITAGE"),
    (r"creamery", "DORMS_HERITAGE"),
    (r"\bcone\b", "DORMS_HERITAGE"),
    # --- DORMS_HELAMAN (Helaman Halls, its named buildings, Cannon dining) ---
    (r"helaman", "DORMS_HELAMAN"),
    (r"cannon center", "DORMS_HELAMAN"),
    (r"chipman hall", "DORMS_HELAMAN"),
    (r"\bchipman\b", "DORMS_HELAMAN"),
    (r"merrill hall", "DORMS_HELAMAN"),
    (r"stover hall", "DORMS_HELAMAN"),
    (r"hinckley hall", "DORMS_HELAMAN"),
    (r"budge hall", "DORMS_HELAMAN"),
    (r"taylor hall", "DORMS_HELAMAN"),
    (r"deseret towers", "DORMS_HELAMAN"),
    # --- WYVIEW_WYMOUNT ---
    (r"wyview", "WYVIEW_WYMOUNT"),
    (r"wymount", "WYVIEW_WYMOUNT"),
    # --- STADIUM_AREA (athletics cluster) ---
    (r"lavell edwards", "STADIUM_AREA"),
    (r"\bstadium\b", "STADIUM_AREA"),
    (r"marriott center", "STADIUM_AREA"),
    (r"indoor practice", "STADIUM_AREA"),
    (r"cougar field", "STADIUM_AREA"),
    (r"miller (field|park)", "STADIUM_AREA"),
    (r"smith\s+field\s*house", "STADIUM_AREA"),
    (r"\brb field\b", "STADIUM_AREA"),
    (r"student athlete", "STADIUM_AREA"),
    # --- MTC (its own zone) ---
    (r"\bmtc\b", "MTC"),
    (r"missionary training", "MTC"),
    # --- BUSINESS_SOUTH ---
    (r"tanner building", "BUSINESS_SOUTH"),
    (r"\btnrb\b", "BUSINESS_SOUTH"),
    (r"marriott school", "BUSINESS_SOUTH"),
    (r"\bscob\b", "BUSINESS_SOUTH"),
    (r"law school", "BUSINESS_SOUTH"),
    (r"law building", "BUSINESS_SOUTH"),
    (r"\bjrcb\b", "BUSINESS_SOUTH"),
    # --- ENGINEERING_NORTH ---
    (r"clyde", "ENGINEERING_NORTH"),
    (r"eyring", "ENGINEERING_NORTH"),
    (r"\besc\b", "ENGINEERING_NORTH"),
    (r"crabtree", "ENGINEERING_NORTH"),
    (r"\bctb\b", "ENGINEERING_NORTH"),
    (r"fletcher", "ENGINEERING_NORTH"),
    (r"\bmarb\b", "ENGINEERING_NORTH"),
    (r"nicholes", "ENGINEERING_NORTH"),
    # --- STUDENT_SERVICES ---
    (r"wilkinson", "STUDENT_SERVICES"),
    (r"\bwsc\b", "STUDENT_SERVICES"),
    (r"cougar\s?eat", "STUDENT_SERVICES"),
    (r"cougar dash", "STUDENT_SERVICES"),
    (r"bookstore", "STUDENT_SERVICES"),
    (r"testing center", "STUDENT_SERVICES"),
    # --- ACADEMIC_CORE (central academic buildings) ---
    (r"\bjfsb\b", "ACADEMIC_CORE"),
    (r"joseph (fielding )?smith building", "ACADEMIC_CORE"),
    (r"\bjsb\b", "ACADEMIC_CORE"),
    (r"\bjkb\b", "ACADEMIC_CORE"),
    (r"jesse knight", "ACADEMIC_CORE"),
    (r"\bswkt\b", "ACADEMIC_CORE"),
    (r"kimball tower", "ACADEMIC_CORE"),
    (r"\bhbll\b", "ACADEMIC_CORE"),
    (r"harold b\.? lee", "ACADEMIC_CORE"),
    (r"museum of art", "ACADEMIC_CORE"),
    (r"bean (life science )?museum", "ACADEMIC_CORE"),
    (r"\bbnsn\b", "ACADEMIC_CORE"),
    (r"benson building", "ACADEMIC_CORE"),
    (r"\bhfac\b", "ACADEMIC_CORE"),
    (r"music building", "ACADEMIC_CORE"),
    (r"arts building", "ACADEMIC_CORE"),
    (r"maeser", "ACADEMIC_CORE"),
    (r"richards building", "ACADEMIC_CORE"),
    (r"life scien", "ACADEMIC_CORE"),
    (r"heber j\.? grant", "ACADEMIC_CORE"),
    (r"grant building", "ACADEMIC_CORE"),
    (r"ellsworth", "ACADEMIC_CORE"),
    (r"talmage", "ACADEMIC_CORE"),
    (r"\btlmb\b", "ACADEMIC_CORE"),
    (r"\btmcb\b", "ACADEMIC_CORE"),
    (r"taylor building", "ACADEMIC_CORE"),
    (r"clark building", "ACADEMIC_CORE"),
    (r"brimhall", "ACADEMIC_CORE"),
    (r"\bmckb\b", "ACADEMIC_CORE"),
    (r"mckay building", "ACADEMIC_CORE"),
    # --- SERVICE_SUPPORT (facilities / auxiliary buildings, mostly peripheral) ---
    (r"food[ -]?to[ -]?go", "SERVICE_SUPPORT"),
    (r"culinary support", "SERVICE_SUPPORT"),
    (r"university services", "SERVICE_SUPPORT"),
    (r"university press", "SERVICE_SUPPORT"),
    (r"brewster", "SERVICE_SUPPORT"),
    (r"west\s?view building", "SERVICE_SUPPORT"),
    # --- OFF_CAMPUS ---
    (r"riviera", "OFF_CAMPUS"),
    (r"university avenue", "OFF_CAMPUS"),
    (r"freedom boulevard", "OFF_CAMPUS"),
    (r"center street", "OFF_CAMPUS"),
    (r"provo city", "OFF_CAMPUS"),
    (r"off[- ]campus", "OFF_CAMPUS"),
)

# Numbered parking lots mapped to their zone. Lots carry no meaning to a language
# model (a bare "Lot 41" is unguessable), so they are resolved deterministically
# from this table, provided from the campus parking map. Only lots that actually
# appear in the data are listed; extend as new ones show up.
LOT_ZONES: dict[int, str] = {
    2: "STUDENT_SERVICES",
    4: "ENGINEERING_NORTH",
    20: "STADIUM_AREA",
    23: "STADIUM_AREA",
    25: "DORMS_HELAMAN",
    37: "STADIUM_AREA",
    38: "STADIUM_AREA",
    41: "DORMS_HELAMAN",
    45: "STADIUM_AREA",
    46: "OFF_CAMPUS",
    47: "STADIUM_AREA",
    50: "ACADEMIC_CORE",
    52: "WYVIEW_WYMOUNT",
}
