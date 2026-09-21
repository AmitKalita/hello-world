"""Small shared helpers used across the research agent."""

from datetime import datetime, timedelta, timezone


def cutoff_date(lookback_days: int) -> datetime:
    """Return the UTC datetime beyond which items are considered 'new'."""
    return datetime.now(timezone.utc) - timedelta(days=lookback_days)


def all_query_terms(topics: dict) -> list[str]:
    """Flatten the topics config into a single list of search terms."""
    terms = []
    for term_list in topics.values():
        terms.extend(term_list)
    return terms


def parse_date_loose(value: str) -> datetime | None:
    """Parse a handful of date formats seen across the different APIs."""
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None
