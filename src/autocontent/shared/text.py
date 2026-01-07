from __future__ import annotations

import hashlib
import re


def normalize_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    return normalized


_SUSPICIOUS_PATTERNS = [
    r"ignore\s+previous",
    r"system\s+prompt",
    r"developer\s+message",
    r"you\s+are\s+chatgpt",
    r"act\s+as",
    r"follow\s+these\s+instructions",
    r"do\s+not\s+follow",
]


def sanitize_raw_text(text: str, max_chars: int) -> str:
    cleaned = text or ""
    for pattern in _SUSPICIOUS_PATTERNS:
        cleaned = re.sub(
            rf"[^.?!]*{pattern}[^.?!]*[.?!]?",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = normalize_text(cleaned)
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars]
    return cleaned


def compute_content_hash(*parts: str) -> str:
    normalized_parts = [normalize_text(part) for part in parts]
    payload = "|".join(normalized_parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def compute_draft_hash(
    project_id: int, source_item_id: int, template_id: str | None, raw_text: str
) -> str:
    return compute_content_hash(str(project_id), str(source_item_id), template_id or "", raw_text)
