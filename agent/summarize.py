"""Use Claude to filter raw search results down to what's actually
relevant, tag each item with a topic, and write a short summary.

This is what keeps the sheet readable: without it, a keyword search
across five sources would dump dozens of loosely-related items into
the sheet every day.
"""

import logging
import os

import anthropic

logger = logging.getLogger(__name__)

BATCH_SIZE = 8

TOOL_SCHEMA = {
    "name": "submit_classifications",
    "description": "Submit a relevance classification for each item in the batch.",
    "input_schema": {
        "type": "object",
        "properties": {
            "classifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "description": "0-based index of the item in this batch"},
                        "relevant": {"type": "boolean"},
                        "topic": {
                            "type": "string",
                            "enum": ["RNA Therapeutics", "LNP Engineering", "Oncology", "Cross-cutting", "Other"],
                        },
                        "score": {"type": "integer", "minimum": 1, "maximum": 5},
                        "summary": {"type": "string", "description": "1-2 sentence plain-English summary"},
                    },
                    "required": ["index", "relevant", "topic", "score", "summary"],
                },
            }
        },
        "required": ["classifications"],
    },
}

SYSTEM_PROMPT = """You are a research analyst screening items for a daily \
digest on RNA therapeutics, lipid nanoparticle (LNP) engineering, and \
oncology. For each item, decide if it represents a genuine advancement, \
finding, or notable development in one or more of those areas (not just \
a passing mention), assign the single best-fitting topic tag, score its \
relevance from 1 (barely related) to 5 (major, on-topic development), and \
write a 1-2 sentence plain-English summary of what it actually says."""


def _build_user_message(batch: list[dict], content_field: str) -> str:
    lines = []
    for i, item in enumerate(batch):
        title = item.get("title") or item.get("text", "")[:120]
        body = item.get(content_field, "") or "(no additional text available)"
        lines.append(f"[{i}] TITLE/TEXT: {title}\nDETAIL: {body}\n")
    return "Classify each of these items:\n\n" + "\n".join(lines)


def classify_items(items: list[dict], content_field: str, model: str) -> list[dict]:
    """Return items augmented with relevant/topic/score/summary fields.

    Items the API call fails to classify are dropped rather than
    silently included, since we'd rather under-report than spam the
    sheet with unfiltered results.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set; cannot classify items, dropping all.")
        return []
    if not items:
        return []

    client = anthropic.Anthropic(api_key=api_key)
    classified = []

    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start : start + BATCH_SIZE]
        try:
            response = client.messages.create(
                model=model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                tools=[TOOL_SCHEMA],
                tool_choice={"type": "tool", "name": "submit_classifications"},
                messages=[{"role": "user", "content": _build_user_message(batch, content_field)}],
            )
        except anthropic.APIError as exc:
            logger.error("Claude classification call failed: %s", exc)
            continue

        tool_use = next((b for b in response.content if b.type == "tool_use"), None)
        if not tool_use:
            logger.error("No tool_use block in Claude response; skipping batch.")
            continue

        for result in tool_use.input.get("classifications", []):
            idx = result.get("index")
            if idx is None or not (0 <= idx < len(batch)):
                continue
            item = dict(batch[idx])
            item["relevant"] = result.get("relevant", False)
            item["topic"] = result.get("topic", "Other")
            item["score"] = result.get("score", 1)
            item["summary"] = result.get("summary", "")
            classified.append(item)

    return classified
