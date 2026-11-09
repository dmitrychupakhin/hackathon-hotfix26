from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None or 'detail' not in response.data:
        return response

    detail = response.data['detail']
    if not isinstance(detail, list):
        response.data['detail'] = [detail]
    return response
