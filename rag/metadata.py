from __future__ import annotations

def parse_year_month(value: str) -> tuple[int, int]:
    s = str(value).strip()
    if not s or s.lower() == "missing":
        return 0, 0
    parts = s.split("-", 1)
    if len(parts) != 2:
        raise ValueError(f"Bad Year_Month: {value!r}")
    year = int(parts[0])
    month = int(parts[1])
    if not 1 <= month <= 12:
        raise ValueError(f"Bad month in Year_Month: {value!r}")
    return year, month


def month_to_season(month: int, branch: str | None = None) -> str:
    """Park-local season label.

    California/Paris use meteorological NH seasons (DJF/MAM/JJA/SON).
    Hong Kong is subtropical (HKO climatology): summer is long (Jun-Sep),
    autumn is short (Oct-Nov), winter Dec-Feb, spring Mar-May.
    """
    if month == 0:
        return "unknown"
    if branch == "Disneyland_HongKong":
        if month in (12, 1, 2):
            return "winter"
        if month in (3, 4, 5):
            return "spring"
        if month in (6, 7, 8, 9):
            return "summer"
        return "autumn"
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "autumn"


SEASON_TO_MONTHS = {
    "winter": [12, 1, 2],
    "spring": [3, 4, 5],
    "summer": [6, 7, 8],
    "autumn": [9, 10, 11],
    "fall": [9, 10, 11],
}

# Park-local season -> months. Hong Kong summer extends through September
# (HKO: hot/humid May-Sep), autumn is Oct-Nov only.
BRANCH_SEASON_TO_MONTHS: dict[str, dict[str, list[int]]] = {
    "Disneyland_California": dict(SEASON_TO_MONTHS),
    "Disneyland_Paris": dict(SEASON_TO_MONTHS),
    "Disneyland_HongKong": {
        "winter": [12, 1, 2],
        "spring": [3, 4, 5],
        "summer": [6, 7, 8, 9],
        "autumn": [10, 11],
        "fall": [10, 11],
    },
}


def season_to_months(season: str, branch: str | None = None) -> list[int]:
    """Months for a season name, optionally park-aware."""
    s = season.lower()
    if branch and branch in BRANCH_SEASON_TO_MONTHS:
        return list(BRANCH_SEASON_TO_MONTHS[branch].get(s, []))
    return list(SEASON_TO_MONTHS.get(s, []))

MONTH_NAME_TO_NUM = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

# Common abbreviations (matched with word boundaries in filters.py).
MONTH_ABBR_TO_NUM = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
