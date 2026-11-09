import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

import httpx

from app.config import Settings
from app.domain import DomainError

logger = logging.getLogger(__name__)


@dataclass
class Reply:
    message: dict[str, Any]
    finish_reason: str = "stop"
    model: str = ""
    usage: dict | None = None
    transport_attempts: int = 1


class ChatModel(Protocol):
    async def complete(
        self,
        *,
        model: str,
        messages: list[dict],
        max_tokens: int,
        tools: list[dict] | None = None,
        base_url: str | None = None,
    ) -> Reply: ...


class ApiMira:
    def __init__(self, settings: Settings, transport=None):
        self.settings = settings
        self.client = httpx.AsyncClient(
            base_url=settings.base_url.rstrip("/") + "/",
            timeout=httpx.Timeout(settings.llm_timeout, connect=15),
            transport=transport,
            follow_redirects=False,
        )

    async def close(self):
        await self.client.aclose()

    async def context_windows(self) -> dict[str, int]:
        key = self.settings.api_key.get_secret_value()
        if not key:
            return {}
        try:
            response = await self.client.get(
                "models", headers={"Authorization": f"Bearer {key}"}, timeout=10
            )
            if response.is_error or len(response.content) > 2 * 1024 * 1024:
                return {}
            rows = response.json()["data"]
            if not isinstance(rows, list):
                return {}
            result = {}
            for row in rows:
                if (
                    not isinstance(row, dict)
                    or not isinstance(row.get("id"), str)
                    or not 0 < len(row["id"]) <= 150
                ):
                    continue
                values = [row.get("context_window"), row.get("context_length")]
                valid = [v for v in values if type(v) is int and 1024 <= v <= 100_000_000]
                if valid:
                    result[row["id"]] = min(result.get(row["id"], min(valid)), min(valid))
            return result
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return {}

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict],
        max_tokens: int,
        tools=None,
        base_url=None,
        transport_attempt_limit: int | None = None,
    ):
        key = self.settings.api_key.get_secret_value()
        if not key:
            raise DomainError("provider_not_configured", "APIMIRA_API_KEY is not configured", 503)
        selected_base = base_url or self.settings.base_url
        if selected_base not in self.settings.base_urls:
            raise DomainError("provider_not_allowed", "Requested provider is not enabled", 422)
        body = {"model": model, "messages": messages, "temperature": 0, "max_tokens": max_tokens}
        if self.settings.enable_thinking is not None:
            body["enable_thinking"] = self.settings.enable_thinking
        if tools:
            body.update(tools=tools, tool_choice="auto")
        if len(json.dumps(body, ensure_ascii=False).encode()) > 2 * 1024 * 1024:
            raise DomainError(
                "request_too_large", "Provider request exceeds the 2 MB text-body limit", 413
            )
        attempts = 0
        allowed_attempts = min(1 + self.settings.rate_limit_retries, transport_attempt_limit or 6)
        try:
            for attempts in range(1, allowed_attempts + 1):
                response = await self.client.post(
                    selected_base.rstrip("/") + "/chat/completions",
                    json=body,
                    headers={"Authorization": f"Bearer {key}"},
                )
                if response.status_code != 429 or attempts == allowed_attempts:
                    break
                value = response.headers.get("Retry-After", "")
                try:
                    delay = float(value)
                except ValueError:
                    try:
                        delay = (
                            parsedate_to_datetime(value) - datetime.now(timezone.utc)
                        ).total_seconds()
                    except (ValueError, TypeError, OverflowError):
                        delay = 2 ** (attempts - 1)
                await asyncio.sleep(min(30, max(0, delay)))
        except asyncio.CancelledError as exc:
            exc.transport_attempts = attempts
            raise
        except httpx.TimeoutException:
            raise provider_error(
                "provider_timeout",
                "Provider timed out; automatic retry was not performed",
                504,
                attempts,
            ) from None
        except httpx.HTTPError as exc:
            logger.warning('LLM transport failure: %s', type(exc).__name__)
            raise provider_error(
                "provider_unreachable", "Provider connection failed", 502, attempts
            ) from None
        if response.status_code >= 400:
            code = "provider_error"
            try:
                candidate = response.json().get("error", {}).get("code", "")
                if (
                    isinstance(candidate, str)
                    and candidate.replace("_", "").isalnum()
                    and len(candidate) < 80
                ):
                    code = candidate
            except (ValueError, AttributeError):
                pass
            if response.status_code == 429:
                code = "rate_limited"
            try:
                message = str(response.json().get("error", {}).get("message", ""))[:4000].lower()
            except (ValueError, AttributeError):
                message = ""
            if code in {"maximum_context_length_exceeded", "context_window_exceeded"} or (
                response.status_code in {400, 413, 422}
                and (
                    "context" in message
                    and any(t in message for t in ["maximum", "exceed", "too long"])
                )
            ):
                code = "context_length_exceeded"
            raise provider_error(
                code,
                f"Provider returned HTTP {response.status_code}",
                429 if response.status_code == 429 else 502,
                attempts,
            )
        try:
            data = response.json()
            choice = data["choices"][0]
            message = choice["message"]
            if not isinstance(message, dict):
                raise ValueError
        except (ValueError, KeyError, IndexError, TypeError):
            raise provider_error(
                "provider_protocol", "Provider returned an invalid response", 502, attempts
            ) from None
        # Never forward hidden reasoning, credentials, request headers, or arbitrary metadata.
        safe = {"role": "assistant", "content": message.get("content")}
        if message.get("tool_calls"):
            safe["tool_calls"] = message["tool_calls"]
        return Reply(
            safe,
            choice.get("finish_reason", "unknown"),
            data.get("model", model),
            data.get("usage"),
            attempts,
        )


def provider_error(code, message, status, attempts):
    error = DomainError(code, message, status)
    error.transport_attempts = attempts
    return error


def estimate_tokens(messages: list[dict]) -> int:
    """Conservative heuristic for Russian text, not the provider's exact tokenizer."""
    return (len(json.dumps(messages, ensure_ascii=False)) + 1) // 2 + 256


@dataclass
class Usage:
    calls: int = 0
    transport_attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    missing_usage_calls: int = 0
    returned_models: set[str] = field(default_factory=set)

    def add(self, reply: Reply):
        self.transport_attempts += reply.transport_attempts
        self.returned_models.add(reply.model)
        usage = reply.usage or {}
        if not isinstance(usage, dict) or not isinstance(
            usage.get("prompt_tokens_details") or {}, dict
        ):
            self.missing_usage_calls += 1
            return
        input_tokens, output_tokens = usage.get("prompt_tokens"), usage.get("completion_tokens")
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        if (
            any(type(v) is not int or v < 0 for v in (input_tokens, output_tokens, cached))
            or cached > input_tokens
        ):
            self.missing_usage_calls += 1
            return
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cached_tokens += cached

    def snapshot(self, settings: Settings):
        cost = None
        if (
            not self.missing_usage_calls
            and settings.input_price is not None
            and settings.output_price is not None
        ):
            cached_price = (
                settings.cached_price if settings.cached_price is not None else settings.input_price
            )
            cost = (
                (self.input_tokens - self.cached_tokens) * settings.input_price
                + self.cached_tokens * cached_price
                + self.output_tokens * settings.output_price
            ) / 1_000_000
        return {
            "model_calls": self.calls,
            "transport_attempts": self.transport_attempts,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "known_total_tokens": self.input_tokens + self.output_tokens,
            "missing_usage_calls": self.missing_usage_calls,
            "returned_models": sorted(self.returned_models),
            "cost": cost,
            "currency": settings.price_currency if cost is not None else None,
            "price_snapshot": {
                "input": settings.input_price,
                "output": settings.output_price,
                "cached": settings.cached_price,
            },
        }
