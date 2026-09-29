from __future__ import annotations

import re
from dataclasses import dataclass, field

from rag.metadata import MONTH_ABBR_TO_NUM, MONTH_NAME_TO_NUM, season_to_months


# Dataset `Branch` values
BRANCH_ALIASES: list[tuple[str, str]] = [
    ("disneyland hong kong", "Disneyland_HongKong"),
    ("hong kong disneyland", "Disneyland_HongKong"),
    ("hong kong", "Disneyland_HongKong"),
    (" hk ", "Disneyland_HongKong"),
    ("hongkong", "Disneyland_HongKong"),
    (" hkdl", "Disneyland_HongKong"),
    ("disneyland paris", "Disneyland_Paris"),
    ("paris disneyland", "Disneyland_Paris"),
    ("eurodisney", "Disneyland_Paris"),
    ("disneyland parc", "Disneyland_Paris"),
    ("paris", "Disneyland_Paris"),
    ("disneyland california", "Disneyland_California"),
    ("disneyland anaheim", "Disneyland_California"),
    ("anaheim", "Disneyland_California"),
    ("california adventure", "Disneyland_California"),
    ("disneyland resort california", "Disneyland_California"),
    ("california", "Disneyland_California"),
]

# Common `Reviewer_Location` strings (longest first for greedy match)
REVIEWER_LOCATIONS: tuple[str, ...] = (
    "United Arab Emirates",
    "United Kingdom",
    "United States",
    "South Africa",
    "New Zealand",
    "Saudi Arabia",
    "Philippines",
    "Netherlands",
    "Switzerland",
    "Australia",
    "Singapore",
    "Indonesia",
    "Malaysia",
    "Thailand",
    "Hong Kong",
    "Germany",
    "Belgium",
    "Portugal",
    "Romania",
    "Finland",
    "Denmark",
    "Sweden",
    "Norway",
    "Ireland",
    "France",
    "Canada",
    "Mexico",
    "Brazil",
    "Spain",
    "Italy",
    "India",
    "China",
    "Japan",
    "Israel",
    "Greece",
    "Turkey",
    "Egypt",
    "Qatar",
    "Malta",
    "Lebanon",
)


@dataclass
class QueryFilters:
    branch: str | None = None
    reviewer_location: str | None = None
    months: list[int] | None = None
    years: list[int] | None = None

    relaxations: list[str] = field(default_factory=list)


def _norm(q: str) -> str:
    return " " + re.sub(r"\s+", " ", q.lower()).strip() + " "


def _normalize_location_candidate(raw: str) -> str:
    s = re.sub(r"\s+", " ", raw).strip()
    if s.lower().startswith("the "):
        s = s[4:].strip()
    return s.title()


def infer_branch(q: str) -> str | None:
    # Fix 5a: word-boundary regex so "paris" doesn't fire inside
    # "comparison", "hk" doesn't fire inside "shaky", etc.
    # Longest aliases first so specific names beat generic ones.
    s = _norm(q)
    for alias, branch in sorted(BRANCH_ALIASES, key=lambda x: len(x[0]), reverse=True):
        pattern = r"\b" + re.escape(alias.strip()) + r"\b"
        if re.search(pattern, s):
            return branch
    return None


def infer_reviewer_location(q: str) -> str | None:
    s = _norm(q)
    m = re.search(r"\bfrom\s+([a-z][a-z\s]+?)(?:\s+say|\s+think|\s+about|\?|$)", q, re.I)
    if m:
        cand = _normalize_location_candidate(m.group(1).strip())
        for loc in REVIEWER_LOCATIONS:
            if loc.lower() == cand.lower():
                return loc
    m2 = re.search(r"visitors?\s+from\s+([a-z][a-z\s]+?)(?:\s+say|\s+about|\?|$)", q, re.I)
    if m2:
        cand = _normalize_location_candidate(m2.group(1).strip())
        for loc in REVIEWER_LOCATIONS:
            if loc.lower() == cand.lower():
                return loc
    for loc in sorted(REVIEWER_LOCATIONS, key=len, reverse=True):
        if loc.lower() in s:
            return loc
    return None


def infer_months(q: str, branch: str | None = None) -> list[int] | None:
    # Fix 1: word-boundary matching so "may" in "maybe" or "may be"
    # doesn't trigger May, "mar" in "smart" doesn't trigger March, etc.
    # Fix 4: season -> months is park-aware (HK summer includes Sep).
    months: set[int] = set()
    lowered = q.lower()
    for name, num in MONTH_NAME_TO_NUM.items():
        if name == "may":
            # "may" is also a modal verb: only accept capitalised "May"
            # or an explicit month context ("in may", "during may", ...).
            if re.search(r"\bMay\b", q):
                months.add(num)
            elif re.search(r"\b(in|for|during|visit(?:ed|ing)?|month of)\s+may\b", lowered):
                months.add(num)
            continue
        if re.search(r"\b" + re.escape(name) + r"\b", lowered):
            months.add(num)
    for abbr, num in MONTH_ABBR_TO_NUM.items():
        # Word boundaries already prevent inside-word hits ("mar" in
        # "smart" won't match). Abbreviations are matched
        # case-insensitively: "Jan", "jan", "Sept." all count.
        if re.search(r"\b" + re.escape(abbr) + r"\b\.?", lowered):
            months.add(num)
    for season, keys in (
        ("spring", ("spring",)),
        ("summer", ("summer",)),
        ("winter", ("winter",)),
        ("autumn", ("autumn", "fall")),
    ):
        if any(re.search(r"\b" + re.escape(k) + r"\b", lowered) for k in keys):
            months.update(season_to_months(season, branch))
    if months:
        return sorted(months)
    return None


def infer_years(q: str) -> list[int] | None:
    # Fix 5b: QueryFilters.years was never populated. Extract 4-digit
    # years in the dataset's plausible range (1990-2030). Catches single
    # years ("in 2015") and ranges ("2015-2017" -> [2015, 2017]).
    found: set[int] = set()
    for m in re.finditer(r"\b(19\d{2}|20\d{2})\b", q):
        y = int(m.group(1))
        if 1990 <= y <= 2030:
            found.add(y)
    if found:
        return sorted(found)
    return None


def interpret_query(question: str) -> QueryFilters:
    branch = infer_branch(question)
    reviewer_location = infer_reviewer_location(question)
    months = infer_months(question, branch=branch)
    years = infer_years(question)
    return QueryFilters(
        branch=branch,
        reviewer_location=reviewer_location,
        months=months,
        years=years,
    )


def build_chroma_where(f: QueryFilters) -> dict | None:
    clauses: list[dict] = []
    if f.branch:
        clauses.append({"branch": f.branch})
    if f.reviewer_location:
        clauses.append({"reviewer_location": f.reviewer_location})
    if f.months:
        clauses.append({"month": {"$in": f.months}})
    if f.years:
        clauses.append({"year": {"$in": f.years}})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}
