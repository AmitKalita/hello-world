"""Thin wrapper around the Google Sheets API: creates tabs/headers if
missing, reads existing rows for deduplication, and appends new ones.

Auth: a Google Cloud service account. Its full JSON key is expected
in the GOOGLE_SERVICE_ACCOUNT_JSON env var (see README for setup),
and the target spreadsheet must be shared with that service
account's email address with Editor access.
"""

import json
import logging
import os

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

PAPERS_HEADERS = [
    "Date Added", "Pub Date", "Title", "Authors", "Source",
    "Link", "Topic", "Summary", "Relevance Score",
]
PAPERS_LINK_COL = "F"

POSTS_HEADERS = [
    "Date Added", "Platform", "Author", "Link", "Snippet",
    "Summary", "Topic", "Engagement",
]
POSTS_LINK_COL = "D"

RUN_LOG_HEADERS = ["Timestamp", "Status", "New Papers", "New Posts", "Errors"]


def build_service():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError(
            "GOOGLE_SERVICE_ACCOUNT_JSON is not set. See README for how to "
            "create a Google Cloud service account and add it as a secret."
        )
    info = json.loads(raw)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def _existing_tab_titles(service, sheet_id: str) -> set[str]:
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    return {s["properties"]["title"] for s in meta.get("sheets", [])}


def ensure_tab(service, sheet_id: str, tab: str, headers: list[str]) -> None:
    """Create the tab if missing, and write headers if the tab is empty."""
    if tab not in _existing_tab_titles(service, sheet_id):
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": tab}}}]},
        ).execute()
        logger.info("Created missing sheet tab: %s", tab)

    existing = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=f"'{tab}'!A1:Z1")
        .execute()
        .get("values", [])
    )
    if not existing:
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"'{tab}'!A1",
            valueInputOption="RAW",
            body={"values": [headers]},
        ).execute()


def get_existing_keys(service, sheet_id: str, tab: str, column_letter: str) -> set[str]:
    values = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=sheet_id, range=f"'{tab}'!{column_letter}2:{column_letter}")
        .execute()
        .get("values", [])
    )
    return {row[0] for row in values if row}


def append_rows(service, sheet_id: str, tab: str, rows: list[list]) -> None:
    if not rows:
        return
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"'{tab}'!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()
