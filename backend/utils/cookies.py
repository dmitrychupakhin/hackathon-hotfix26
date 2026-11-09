from django.conf import settings
from django.utils import timezone


def set_auth_cookies(response, access_token, refresh_token, remember_me=False):
    access_expires = timezone.now() + settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
    refresh_expires = timezone.now() + settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]

    response.set_cookie('access', access_token, httponly=True, secure=True, samesite='None', expires=access_expires)
    response.set_cookie('refresh', refresh_token, httponly=True, secure=True, samesite='None', expires=refresh_expires if remember_me else None)
    return response
