"""Fetch recent posts from X (Twitter) via the official v2 API.

Requires a paid API tier with access to the recent-search endpoint,
authenticated with a Bearer Token (X_BEARER_TOKEN). If no token is
configured, this source is skipped entirely rather than failing the
whole run — see agent/main.py.
"""

from datetime import timezone
import logging
import os

import requests

from agent.utils import cutoff_date

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
# X's recent-search query length limit is tier-dependent; splitting by
# topic keeps each query well under the limit instead of OR-ing every
# term from every topic into one long query.
MAX_TERMS_PER_QUERY = 6


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def fetch_posts(topics: dict, lookback_days: int, max_items: int) -> list[dict]:
    token = os.environ.get("X_BEARER_TOKEN")
    if not token:
        logger.info("X_BEARER_TOKEN not set; skipping X source.")
        return []

    headers = {"Authorization": f"Bearer {token}"}
    since = cutoff_date(min(lookback_days, 6))  # recent search only covers ~7 days
    start_time = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    all_terms = [term for term_list in topics.values() for term in term_list]
    posts, seen_ids = [], set()

    for chunk in _chunk(all_terms, MAX_TERMS_PER_QUERY):
        term_query = " OR ".join(f'"{term}"' for term in chunk)
        query = f"({term_query}) -is:retweet lang:en"
        params = {
            "query": query,
            "start_time": start_time,
            "max_results": min(max_items, 100),
            "tweet.fields": "created_at,author_id,public_metrics",
            "expansions": "author_id",
            "user.fields": "username",
        }
        try:
            resp = requests.get(SEARCH_URL, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("X API request failed for query %r: %s", query, exc)
            continue

        body = resp.json()
        users = {u["id"]: u.get("username", "") for u in body.get("includes", {}).get("users", [])}
        for tweet in body.get("data", []):
            if tweet["id"] in seen_ids:
                continue
            seen_ids.add(tweet["id"])
            username = users.get(tweet.get("author_id"), "")
            metrics = tweet.get("public_metrics", {})
            posts.append(
                {
                    "id": tweet["id"],
                    "author": f"@{username}" if username else tweet.get("author_id", ""),
                    "url": f"https://x.com/{username}/status/{tweet['id']}" if username else "",
                    "text": tweet.get("text", ""),
                    "date": tweet.get("created_at", ""),
                    "engagement": metrics.get("like_count", 0) + metrics.get("retweet_count", 0),
                }
            )
            if len(posts) >= max_items:
                return posts
    return posts
