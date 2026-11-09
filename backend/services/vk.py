import requests

from django.conf import settings


def get_user(code, code_verifier, device_id, state):
    response = requests.post(
        'https://id.vk.ru/oauth2/auth',
        data={
            'grant_type': 'authorization_code',
            'code_verifier': code_verifier,
            'redirect_uri': settings.VK_REDIRECT_URI,
            'code': code,
            'client_id': settings.VK_CLIENT_ID,
            'device_id': device_id,
            'state': state,
            'scope': 'email',
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()['access_token']


def user_info(access_token):
    response = requests.post(
        'https://id.vk.ru/oauth2/user_info',
        data={
            'client_id': settings.VK_CLIENT_ID,
            'access_token': access_token,
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()['user']
