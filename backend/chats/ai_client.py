import requests
from django.conf import settings


def ai_request(method, path, *, user_id='catalog', payload=None, timeout=20, idempotency_key=None):
    if not settings.AI_SERVICE_KEY:
        raise RuntimeError('AI_SERVICE_KEY не настроен.')
    headers = {
        'X-AI-Service-Key': settings.AI_SERVICE_KEY,
        'X-User-ID': str(user_id),
    }
    if idempotency_key:
        headers['Idempotency-Key'] = str(idempotency_key)
    response = requests.request(
        method,
        f"{settings.AI_BASE_URL.rstrip('/')}/api/v1{path}",
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()
