"""Entry point for the RNA therapeutics / LNP engineering / oncology
research agent. Run daily by the GitHub Actions workflow in
.github/workflows/daily-research.yml (or manually: python -m agent.main).

Pipeline: fetch raw items from each source -> drop anything already
in the sheet -> ask Claude to filter/tag/summarize what's left ->
append the ones that clear the relevance bar -> log the run.
"""

from datetime import datetime, timezone
import logging
import os

import yaml

from agent.sheets import (
    PAPERS_HEADERS, PAPERS_LINK_COL,
    POSTS_HEADERS, POSTS_LINK_COL,
    RUN_LOG_HEADERS,
    append_rows, build_service, ensure_tab, get_existing_keys,
)
from agent.sources import europepmc, semantic_scholar, twitter
from agent.summarize import classify_items
from agent.utils import all_query_terms

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def dedupe_by_key(items: list[dict], key_field: str, seen: set[str]) -> list[dict]:
    fresh = []
    for item in items:
        key = item.get(key_field, "")
        if key and key not in seen:
            seen.add(key)
            fresh.append(item)
    return fresh


def run() -> None:
    config = load_config()
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID is not set.")

    tabs = config["sheet_tabs"]
    errors: list[str] = []

    service = build_service()
    ensure_tab(service, sheet_id, tabs["papers"], PAPERS_HEADERS)
    ensure_tab(service, sheet_id, tabs["posts"], POSTS_HEADERS)
    ensure_tab(service, sheet_id, tabs["run_log"], RUN_LOG_HEADERS)

    terms = all_query_terms(config["topics"])
    lookback = config["lookback_days"]
    max_items = config["max_items_per_source"]
    threshold = config["relevance_threshold"]
    model = config["claude_model"]

    # --- Papers ---
    raw_papers = []
    for source in (europepmc, semantic_scholar):
        try:
            raw_papers.extend(source.fetch_papers(terms, lookback, max_items))
        except Exception as exc:  # noqa: BLE001 - one source failing shouldn't kill the run
            msg = f"{source.__name__} fetch failed: {exc}"
            logger.error(msg)
            errors.append(msg)

    existing_paper_links = get_existing_keys(service, sheet_id, tabs["papers"], PAPERS_LINK_COL)
    new_papers = dedupe_by_key(raw_papers, "url", set(existing_paper_links))

    classified_papers = []
    try:
        classified_papers = classify_items(new_papers, content_field="abstract", model=model)
    except Exception as exc:  # noqa: BLE001
        msg = f"Paper classification failed: {exc}"
        logger.error(msg)
        errors.append(msg)

    paper_rows = []
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    for p in classified_papers:
        if not p.get("relevant") or p.get("score", 0) < threshold:
            continue
        paper_rows.append([
            now_str, p.get("date", ""), p.get("title", ""), p.get("authors", ""),
            p.get("source", ""), p.get("url", ""), p.get("topic", ""),
            p.get("summary", ""), p.get("score", ""),
        ])
    append_rows(service, sheet_id, tabs["papers"], paper_rows)

    # --- X / Twitter posts ---
    raw_posts = []
    try:
        raw_posts = twitter.fetch_posts(config["topics"], lookback, max_items)
    except Exception as exc:  # noqa: BLE001
        msg = f"twitter fetch failed: {exc}"
        logger.error(msg)
        errors.append(msg)

    existing_post_links = get_existing_keys(service, sheet_id, tabs["posts"], POSTS_LINK_COL)
    new_posts = dedupe_by_key(raw_posts, "url", set(existing_post_links))

    classified_posts = []
    try:
        classified_posts = classify_items(new_posts, content_field="text", model=model)
    except Exception as exc:  # noqa: BLE001
        msg = f"Post classification failed: {exc}"
        logger.error(msg)
        errors.append(msg)

    post_rows = []
    for post in classified_posts:
        if not post.get("relevant") or post.get("score", 0) < threshold:
            continue
        post_rows.append([
            now_str, "X", post.get("author", ""), post.get("url", ""),
            post.get("text", "")[:280], post.get("summary", ""),
            post.get("topic", ""), post.get("engagement", 0),
        ])
    append_rows(service, sheet_id, tabs["posts"], post_rows)

    # --- Run log ---
    status = "OK" if not errors else "COMPLETED WITH ERRORS"
    append_rows(service, sheet_id, tabs["run_log"], [[
        now_str, status, len(paper_rows), len(post_rows), "; ".join(errors),
    ]])

    logger.info(
        "Run complete: %d new papers, %d new posts, %d errors.",
        len(paper_rows), len(post_rows), len(errors),
    )


if __name__ == "__main__":
    run()
