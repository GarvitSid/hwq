"""Text sanitization for untrusted hardware strings (SRS 4.6, FR-PARSE-6)."""

from __future__ import annotations

import re

# Match control characters except newline and tab
CONTROL_CHAR_REGEX = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def sanitize_text(text: str | None, max_len: int = 120) -> str | None:
    """Sanitize free-text strings from untrusted hardware and system sources.

    - Strips control characters (except standard whitespace).
    - Collapses consecutive whitespace.
    - Truncates to max_len (default 120).
    """
    if text is None:
        return None

    # Replace control characters with space
    cleaned = CONTROL_CHAR_REGEX.sub(" ", str(text))
    # Normalize and strip whitespace
    cleaned = " ".join(cleaned.split())

    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].strip()

    return cleaned if cleaned else None
