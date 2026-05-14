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


def month_to_season(month: int) -> str:
    """Meteorological seasons, Northern Hemisphere (used consistently for all branches)."""
    if month == 0:
        return "unknown"
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
