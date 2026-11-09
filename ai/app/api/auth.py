import base64
import hashlib
import hmac
import json
import re
import secrets
import time

from fastapi import Depends, Header, Request
from fastapi.security import APIKeyHeader

from app.config import Settings
from app.domain import DomainError

service_header = APIKeyHeader(name="X-AI-Service-Key", auto_error=False)


def authenticate(settings: Settings, supplied: str | None, user_id: str | None):
    expected = settings.service_key.get_secret_value()
    if not expected:
        return "local"
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise DomainError("unauthorized", "Valid X-AI-Service-Key is required", 401)
    if not user_id or not re.fullmatch(r"[\w.@:-]{1,128}", user_id):
        raise DomainError("invalid_user_context", "Backend must supply a valid X-User-ID", 401)
    return user_id


async def owner(
    request: Request,
    key: str | None = Depends(service_header),
    user_id: str | None = Header(default=None, alias="X-User-ID"),
):
    return authenticate(request.app.state.settings, key, user_id)


class Tickets:
    def __init__(self, settings: Settings):
        configured = settings.service_key.get_secret_value()
        self.key = configured.encode() if configured else secrets.token_bytes(32)

    def issue(self, run_id: str, user_id: str, ttl=120):
        payload = {
            "run_id": run_id,
            "owner": user_id,
            "scope": "run.events",
            "exp": int(time.time()) + ttl,
        }
        body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(
            b"="
        )
        signature = hmac.new(self.key, body, hashlib.sha256).hexdigest()
        return body.decode() + "." + signature, payload["exp"]

    def verify(self, ticket: str, run_id: str):
        try:
            if len(ticket) > 2048:
                raise ValueError
            body, signature = ticket.split(".")
            expected = hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
            if (
                payload["run_id"] != run_id
                or payload["scope"] != "run.events"
                or payload["exp"] <= time.time()
            ):
                raise ValueError
            return payload["owner"]
        except (ValueError, KeyError, TypeError):
            raise DomainError(
                "invalid_ticket", "WebSocket ticket is invalid or expired", 401
            ) from None
