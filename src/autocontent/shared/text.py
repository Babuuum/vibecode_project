from __future__ import annotations

import hashlib
import re


def normalize_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    return normalized


def compute_content_hash(*parts: str) -> str:
    normalized_parts = [normalize_text(part) for part in parts]
    payload = "|".join(normalized_parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
