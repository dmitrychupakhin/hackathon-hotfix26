"""Provider URL normalization and a small documentation-only model shortlist."""

from urllib.parse import urlsplit

MODEL_EXAMPLES = [
    "openai/gpt-6-luna",
    "openai/gpt-6-astra",
    "openai/gpt-5.4-mini",
    "anthropic/claude-sonnet-4.6",
    "google/gemini-3-flash-preview",
    "deepseek/deepseek-v4-flash",
]


def normalize_base_url(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 2000
        or any(ord(c) < 33 for c in value)
    ):
        raise ValueError("Provider base URL must be a nonempty URL without whitespace")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        raise ValueError("Invalid provider base URL") from None
    if (
        not hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.scheme not in {"https", "http"}
        or (parsed.scheme == "http" and hostname not in {"localhost", "127.0.0.1", "::1"})
    ):
        raise ValueError(
            "Provider URL must use HTTPS (or local HTTP) without credentials, query or fragment"
        )
    return value.rstrip("/")
