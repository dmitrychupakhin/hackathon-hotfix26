"""Source-preserving token-proxy chunks with overlap and deterministic offsets.

Luna's exact tokenizer is not available here. One proxy token is two Unicode
characters; callers must still budget JSON, instructions and model output.
"""

import math
import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    start: int
    end: int
    text: str
    estimated_tokens: int


def token_estimate(text: str) -> int:
    return math.ceil(len(text) / 2)


def _boundaries(text: str) -> list[int]:
    # Paragraphs, sentences and line endings preserve most prose and table rows.
    pattern = r"\n[ \t]*\n|[.!?…](?:[ \t]+|\n)(?=[A-ZА-ЯЁ0-9])|\n"
    return [0, *(m.end() for m in re.finditer(pattern, text)), len(text)]


def split_text(text: str, *, target_tokens=2000, overlap_tokens=200) -> list[TextChunk]:
    if type(target_tokens) is not int or type(overlap_tokens) is not int:
        raise ValueError("Token budgets must be integers")
    if target_tokens < 16 or not 0 <= overlap_tokens < target_tokens:
        raise ValueError("Require target_tokens >= 16 and 0 <= overlap < target")
    width, overlap = target_tokens * 2, overlap_tokens * 2
    boundaries = _boundaries(text)
    chunks = []
    start = 0
    while start < len(text):
        ceiling = min(start + width, len(text))
        if ceiling == len(text):
            end = ceiling
        else:
            lo = bisect_left(boundaries, start + width // 2)
            hi = bisect_right(boundaries, ceiling)
            end = boundaries[hi - 1] if hi > lo else ceiling
        left, right = start, end
        while left < right and text[left].isspace():
            left += 1
        while right > left and text[right - 1].isspace():
            right -= 1
        if left < right:
            chunks.append(
                TextChunk(left, right, text[left:right], token_estimate(text[left:right]))
            )
        if end == len(text):
            break
        if overlap:
            desired = end - overlap
            index = bisect_left(boundaries, max(start + 1, desired))
            candidate = boundaries[index] if index < len(boundaries) else end
            # A nearby source boundary gives <= requested overlap; a very long
            # sentence falls back to an exact character offset to ensure overlap.
            next_start = (
                candidate if candidate < end and candidate <= desired + overlap // 2 else desired
            )
            start = max(start + 1, next_start)
        else:
            start = end
    return chunks
