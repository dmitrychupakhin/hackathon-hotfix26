from django.conf import settings
from django.core.mail import send_mail


def send_email(recipient_email, data):
    sender_email =  f"Betelgeuse <{settings.EMAIL_HOST_USER}>"
    subject = "Подтверждение"
    message = f"{data}"

    try:
        send_mail(subject, message, sender_email, [recipient_email])
        return True
    except Exception as err:
        return False
