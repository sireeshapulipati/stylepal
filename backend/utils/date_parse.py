"""Parse and normalize date inputs for purchased_at. Always stores as first day of month (YYYY-MM-01)."""
from calendar import month_abbr, month_name
from datetime import date, datetime, timedelta
from typing import Optional


def parse_purchased_at(s: Optional[str]) -> Optional[date]:
    """Parse user input to date. Accepts: YYYY-MM, March 2024, last month, 3/2024, 2023, etc.
    Returns date(YYYY, MM, 1) or None. Always first of month."""
    if not s or not (s := str(s).strip().lower()):
        return None
    now = datetime.now().date()
    months_abbr_map = {m.lower(): i for i, m in enumerate(month_abbr) if m}
    months_full_map = {m.lower(): i for i, m in enumerate(month_name) if m}
    months = {**months_full_map, **months_abbr_map}

    # YYYY-MM or YYYY-M
    if len(s) >= 6 and s[4] in "-/":
        parts = s.replace("/", "-").split("-")[:2]
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            y, m = int(parts[0]), int(parts[1])
            if 1 <= m <= 12 and 2000 <= y <= 2100:
                return date(y, m, 1)
    # M/YYYY or MM/YYYY
    if "/" in s:
        parts = s.split("/")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            m, y = int(parts[0]), int(parts[1])
            if 1 <= m <= 12 and 2000 <= y <= 2100:
                return date(y, m, 1)
    # Month YYYY (e.g. "march 2024", "jan 2023")
    for name, num in months.items():
        if name in s:
            for part in s.replace(",", " ").split():
                if part.isdigit() and len(part) == 4 and 2000 <= int(part) <= 2100:
                    return date(int(part), num, 1)
            break
    # YYYY only
    for part in s.split():
        if part.isdigit() and len(part) == 4 and 2000 <= int(part) <= 2100:
            return date(int(part), 1, 1)
    # Relative: last month, last year
    if "last month" in s or "previous month" in s:
        first = date(now.year, now.month, 1)
        prev = first - timedelta(days=1)
        return date(prev.year, prev.month, 1)
    if "last year" in s or "previous year" in s:
        return date(now.year - 1, 1, 1)
    if "this month" in s:
        return date(now.year, now.month, 1)
    if "this year" in s:
        return date(now.year, 1, 1)
    # "2 years ago", "year ago"
    if "years ago" in s or "year ago" in s:
        n = 1
        for part in s.split():
            if part.isdigit():
                n = min(int(part), 10)
                break
        return date(now.year - n, 1, 1)
    # "2 months ago", "month ago"
    if "months ago" in s or "month ago" in s:
        n = 1
        for part in s.split():
            if part.isdigit():
                n = min(int(part), 24)
                break
        first = date(now.year, now.month, 1)
        for _ in range(n):
            first = (first.replace(day=28) - timedelta(days=28)).replace(day=1)
        return first
    return None


def normalize_purchased_at(value: Optional[date | str]) -> Optional[date]:
    """Ensure purchased_at is always first of month. Parses string or normalizes date."""
    if value is None:
        return None
    if isinstance(value, str):
        return parse_purchased_at(value)
    if isinstance(value, date):
        return date(value.year, value.month, 1)
    return None
